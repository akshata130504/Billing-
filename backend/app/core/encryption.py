"""Encryption of small secrets at rest (integration credentials, TOTP seeds).

Provider abstraction
--------------------
``get_encryption_provider()`` returns the active ``EncryptionProvider``. The only built-in
implementation is ``KeyringProvider``: a Fernet (AES-128-CBC + HMAC-SHA256) keyring built on
``cryptography.fernet.MultiFernet``:

* ``ENCRYPTION_KEYS`` = ``"<key_id>:<fernet key>,<key_id>:<fernet key>,..."``. The FIRST key
  encrypts; every key decrypts.
* The legacy key (SHA-256 of ``SECRET_KEY``, what every build before the keyring used) is
  appended as a decrypt-only key while ``ENCRYPTION_LEGACY_SECRET_KEY_FALLBACK=true``, so
  existing ciphertext keeps working. With ``ENCRYPTION_KEYS`` empty the legacy key is also
  the encryption key (behaviour identical to earlier builds).
* Ciphertext is a plain Fernet token (no key-id prefix), so old and new rows look the same
  and the database schema is unchanged. Key ids exist for operators and rotation reports.

Rotation: add a new key at the FRONT of ``ENCRYPTION_KEYS``, deploy, then run
``python -m backend.app.core.encryption rotate`` (``--dry-run`` first) to re-encrypt every
stored secret with the new primary key. Old keys can be removed once the report shows no
row still needs them. See docs/database-security.md.

A cloud KMS provider (envelope encryption with AWS KMS / GCP KMS / Vault Transit) can be
plugged in by implementing ``EncryptionProvider``; production KMS provider integration
requires infrastructure configuration and is NOT implemented here.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from backend.app.core.config import settings


class DecryptionError(Exception):
    """Ciphertext could not be decrypted with any configured key (never carries plaintext)."""


class EncryptionProvider(Protocol):
    primary_key_id: str

    def encrypt(self, plaintext: bytes) -> str: ...

    def decrypt(self, token: str) -> bytes: ...

    def key_id_for(self, token: str) -> Optional[str]: ...

    def needs_rotation(self, token: str) -> bool: ...

    def rotate(self, token: str) -> str: ...


LEGACY_KEY_ID = "legacy-secret-key"


def legacy_fernet_key(secret_key: str) -> bytes:
    """Key derivation used before the keyring existed: urlsafe_b64(SHA-256(SECRET_KEY))."""
    return base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode("utf-8")).digest())


def parse_keyring(entries: Sequence[str]) -> List[Tuple[str, bytes]]:
    """``["k2:<key>", "k1:<key>"]`` -> ``[("k2", b"<key>"), ...]``. Raises ValueError (without
    echoing key material) on duplicates or malformed keys. Entries without an id get ``k<n>``."""
    keys: List[Tuple[str, bytes]] = []
    seen = set()
    for index, raw in enumerate(entries):
        entry = (raw or "").strip()
        if not entry:
            continue
        if ":" in entry:
            key_id, key = entry.split(":", 1)
            key_id, key = key_id.strip(), key.strip()
        else:
            key_id, key = f"k{index + 1}", entry
        if not key_id or key_id in seen:
            raise ValueError(f"ENCRYPTION_KEYS: missing or duplicate key id at position {index + 1}")
        try:
            Fernet(key.encode("utf-8"))
        except Exception:
            raise ValueError(
                f"ENCRYPTION_KEYS: key {key_id!r} is not a valid Fernet key (32 url-safe base64-encoded bytes)"
            ) from None
        seen.add(key_id)
        keys.append((key_id, key.encode("utf-8")))
    return keys


@dataclass
class KeyringProvider:
    """Fernet keyring: encrypt with the primary key, decrypt with any key."""

    keys: List[Tuple[str, Fernet]]

    def __post_init__(self) -> None:
        if not self.keys:
            raise ValueError("KeyringProvider needs at least one key")
        self._multi = MultiFernet([f for _, f in self.keys])

    @classmethod
    def from_settings(
        cls,
        encryption_keys: Sequence[str],
        secret_key: str,
        legacy_fallback: bool = True,
    ) -> "KeyringProvider":
        keys: List[Tuple[str, Fernet]] = [(kid, Fernet(k)) for kid, k in parse_keyring(encryption_keys)]
        if not keys or legacy_fallback:
            keys.append((LEGACY_KEY_ID, Fernet(legacy_fernet_key(secret_key))))
        return cls(keys)

    @property
    def primary_key_id(self) -> str:
        return self.keys[0][0]

    @property
    def key_ids(self) -> List[str]:
        return [kid for kid, _ in self.keys]

    def encrypt(self, plaintext: bytes) -> str:
        return self._multi.encrypt(plaintext).decode("utf-8")

    def decrypt(self, token: str) -> bytes:
        try:
            return self._multi.decrypt(token.encode("utf-8"))
        except (InvalidToken, ValueError, TypeError, AttributeError):
            raise DecryptionError("ciphertext could not be decrypted with any configured key") from None

    def key_id_for(self, token: str) -> Optional[str]:
        data = token.encode("utf-8")
        for kid, fernet in self.keys:
            try:
                fernet.decrypt(data)
                return kid
            except (InvalidToken, ValueError, TypeError):
                continue
        return None

    def needs_rotation(self, token: str) -> bool:
        return self.key_id_for(token) != self.primary_key_id

    def rotate(self, token: str) -> str:
        """Re-encrypt under the primary key (raises DecryptionError if no key fits)."""
        try:
            return self._multi.rotate(token.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError, AttributeError):
            raise DecryptionError("ciphertext could not be decrypted with any configured key") from None


_cache: Dict[Tuple[Any, ...], KeyringProvider] = {}


def get_encryption_provider() -> KeyringProvider:
    """Provider for the current settings (cached per configuration, so tests can patch settings)."""
    cache_key = (
        tuple(settings.ENCRYPTION_KEYS),
        settings.SECRET_KEY,
        bool(settings.ENCRYPTION_LEGACY_SECRET_KEY_FALLBACK),
    )
    provider = _cache.get(cache_key)
    if provider is None:
        provider = KeyringProvider.from_settings(*cache_key)
        _cache.clear()
        _cache[cache_key] = provider
    return provider


def encrypt_str(value: str) -> str:
    return get_encryption_provider().encrypt(value.encode("utf-8"))


def decrypt_str(token: str) -> str:
    """Raises DecryptionError when no configured key can decrypt ``token``."""
    return get_encryption_provider().decrypt(token).decode("utf-8")


# --- Re-encryption / rotation -----------------------------------------------------------


def rotate_token(token: Optional[str]) -> Optional[str]:
    """Return ``token`` re-encrypted with the primary key, or None if it already is (or is empty).

    Raises DecryptionError when no key can decrypt it (e.g. a key was removed too early).
    """
    if not token:
        return None
    provider = get_encryption_provider()
    if not provider.needs_rotation(token):
        return None
    return provider.rotate(token)


def reencrypt_all(db: Any, dry_run: bool = False, batch_size: int = 500) -> Dict[str, Any]:
    """Re-encrypt every stored secret (TOTP seeds, integration configs) with the primary key.

    Returns counts only (never plaintext or ciphertext). Commits per batch unless dry_run.
    """
    from sqlalchemy import select

    from backend.app.models.identity import User
    from backend.app.models.integrations import OrganizationIntegration

    report: Dict[str, Any] = {"primary_key_id": get_encryption_provider().primary_key_id, "dry_run": dry_run}
    targets = ((User, "totp_secret", "users.totp_secret"), (OrganizationIntegration, "encrypted_config", "organization_integrations.encrypted_config"))
    for model, attr, label in targets:
        column = getattr(model, attr)
        stats = {"scanned": 0, "rotated": 0, "already_primary": 0, "undecryptable": 0}
        last_id = None
        while True:
            stmt = select(model).where(column.isnot(None)).order_by(model.id).limit(batch_size)
            if last_id is not None:
                stmt = stmt.where(model.id > last_id)
            rows = list(db.scalars(stmt))
            if not rows:
                break
            for row in rows:
                stats["scanned"] += 1
                try:
                    new_token = rotate_token(getattr(row, attr))
                except DecryptionError:
                    stats["undecryptable"] += 1
                    continue
                if new_token is None:
                    stats["already_primary"] += 1
                    continue
                stats["rotated"] += 1
                if not dry_run:
                    setattr(row, attr, new_token)
            last_id = rows[-1].id
            if dry_run:
                db.rollback()
            else:
                db.commit()
        report[label] = stats
    return report


def _main(argv: Sequence[str]) -> int:
    if not argv or argv[0] not in {"rotate", "status"}:
        print("usage: python -m backend.app.core.encryption rotate [--dry-run] | status", file=sys.stderr)
        return 2
    provider = get_encryption_provider()
    if argv[0] == "status":
        print(json.dumps({"primary_key_id": provider.primary_key_id, "key_ids": provider.key_ids}))
        return 0
    from backend.app.core.database import SessionLocal

    db = SessionLocal()
    try:
        report = reencrypt_all(db, dry_run="--dry-run" in argv)
    finally:
        db.close()
    print(json.dumps(report, indent=2))
    undecryptable = sum(v.get("undecryptable", 0) for v in report.values() if isinstance(v, dict))
    return 1 if undecryptable else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main(sys.argv[1:]))


__all__ = [
    "DecryptionError",
    "EncryptionProvider",
    "KeyringProvider",
    "LEGACY_KEY_ID",
    "decrypt_str",
    "encrypt_str",
    "get_encryption_provider",
    "legacy_fernet_key",
    "parse_keyring",
    "reencrypt_all",
    "rotate_token",
]
