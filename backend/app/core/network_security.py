"""Network security utilities for outbound HTTP requests and SSRF prevention.

Defends against Server-Side Request Forgery (SSRF, CWE-918 / OWASP API7)
by verifying that destination hosts resolve exclusively to routable, public IP
addresses and explicitly rejecting loopback, RFC 1918 private, link-local,
multicast, reserved, and cloud-provider metadata endpoints (169.254.169.254, etc.).
"""
import ipaddress
import socket
from typing import Optional
from urllib.parse import urlsplit

from backend.app.core.exceptions import ValidationAppError

BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
    "169.254.169.123",
    "fd00:ec2::254",
})


def is_ip_address(host: str) -> bool:
    """Returns True if host is an IPv4 or IPv6 address literal."""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def is_safe_ip(ip_str: str) -> bool:
    """Returns True if the given IP address is public and safe to contact."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False

    # Block 169.254.0.0/16 IPv4 link-local (cloud metadata) explicitly even if IPv4-mapped
    if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("169.254.0.0/16"):
        return False

    return True


def is_safe_url(url: Optional[str]) -> bool:
    """Validates that a URL is well-formed, uses http/https, and does not target
    localhost, internal private networks, or cloud metadata endpoints.
    """
    if not url or not isinstance(url, str):
        return False

    cleaned = url.strip()
    if cleaned.startswith(("//", "/\\")):
        return False

    try:
        parts = urlsplit(cleaned)
    except Exception:
        return False

    if parts.scheme.lower() not in ("http", "https"):
        return False

    hostname = (parts.hostname or "").strip().lower()
    if not hostname:
        return False

    if hostname in BLOCKED_HOSTNAMES:
        return False

    for blocked in (".localhost", ".local", ".internal", ".test", ".example", ".invalid"):
        if hostname.endswith(blocked):
            return False

    # If hostname is a literal IP, check directly
    if is_ip_address(hostname):
        return is_safe_ip(hostname)

    # Resolve hostname via DNS to prevent DNS rebinding or internal domain resolution
    try:
        addr_info = socket.getaddrinfo(hostname, parts.port or (443 if parts.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
        if not addr_info:
            return False
        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            if not is_safe_ip(ip_str):
                return False
    except Exception:
        # DNS resolution failure or network error -> treat as unsafe
        return False

    return True


def assert_safe_url(url: Optional[str], field_name: str = "url") -> str:
    """Raises ValidationAppError if the URL is not safe for outbound connection."""
    if not url:
        raise ValidationAppError(f"{field_name} is required.", {"fields": {field_name: "required"}})
    if not is_safe_url(url):
        raise ValidationAppError(
            f"The provided {field_name} is not permitted because it targets a private, loopback, or prohibited network address.",
            {"fields": {field_name: "prohibited_address"}},
        )
    return url.strip()
