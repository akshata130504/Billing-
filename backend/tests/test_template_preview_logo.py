"""Document template preview: logo URL handling and previewing unsaved editor values.

The preview must show https:// logos, same-origin relative paths (/logos/..., /uploads/...)
and inlined uploaded files, while refusing dangerous schemes. The server never fetches a
remote URL (no SSRF): it only hands the URL to the viewer's browser.
"""
import os

import pytest

from backend.app.services import customization_service
from backend.app.services.customization_service import resolve_preview_logo_src

_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\x9f\x81\x01\x01\x00\x18\xfe\x02\xfeC\xa5P\x96\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.example.com/logo.png",
        "https://cdn.example.com/brand/logo.webp?v=2",
        "/logos/acme.png",
        "/uploads/logos/does-not-exist-on-disk.png",
        "data:image/png;base64,iVBORw0KGgo=",
    ],
)
def test_accepted_logo_urls_are_rendered_as_is(url):
    assert resolve_preview_logo_src(url) == url


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "   ",
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "file:///etc/passwd",
        "data:text/html;base64,PHNjcmlwdD4=",
        "data:image/svg+xml;base64,PHN2Zz4=",
        "http://cdn.example.com/logo.png",  # blocked by CSP img-src (https: only)
        "//evil.example.com/logo.png",  # protocol-relative = remote over any scheme
        "/uploads/../secret.png",
        "/logos/../../etc/passwd",
        '/logos/a.png" onerror="alert(1)',
        "https://cdn.example.com/a.png\" onerror=\"x",
        "logos/relative-without-slash.png",
        "ftp://example.com/logo.png",
    ],
)
def test_dangerous_or_unsupported_logo_urls_are_rejected(url):
    assert resolve_preview_logo_src(url) is None


def test_resolver_never_fetches_remote_urls(monkeypatch):
    """SSRF guard: resolving an https logo must not open any network connection."""
    import socket
    import urllib.request

    def _boom(*_a, **_kw):
        raise AssertionError("preview must not fetch remote logos server-side")

    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    assert resolve_preview_logo_src("https://169.254.169.254/latest/meta-data") == "https://169.254.169.254/latest/meta-data"


def _create_template(client, auth_headers, **extra):
    res = client.post(
        "/api/v1/templates",
        headers=auth_headers,
        json={"document_type": "invoice", "name": "Logo Tmpl", "layout_type": "standard", **extra},
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_preview_shows_saved_relative_logo_path(client, tenant, auth_headers):
    tmpl = _create_template(client, auth_headers, logo_url="/logos/acme.png")
    preview = client.post(f"/api/v1/templates/{tmpl['id']}/preview", headers=auth_headers).json()
    assert '<img src="/logos/acme.png"' in preview["rendered_html"]


def test_preview_does_not_render_javascript_logo(client, tenant, auth_headers):
    tmpl = _create_template(client, auth_headers, logo_url="javascript:alert(1)")
    preview = client.post(f"/api/v1/templates/{tmpl['id']}/preview", headers=auth_headers).json()
    assert "<img" not in preview["rendered_html"]
    assert "javascript:" not in preview["rendered_html"]


def test_preview_renders_unsaved_logo_override_without_persisting(client, tenant, auth_headers, db):
    tmpl = _create_template(client, auth_headers, logo_url="https://cdn.example.com/old.png", footer_text="Saved footer")

    res = client.post(
        f"/api/v1/templates/{tmpl['id']}/preview",
        headers=auth_headers,
        json={"logo_url": "https://cdn.example.com/new.png", "footer_text": "Draft footer"},
    )
    assert res.status_code == 200, res.text
    html_out = res.json()["rendered_html"]
    assert "https://cdn.example.com/new.png" in html_out
    assert "old.png" not in html_out
    assert "Draft footer" in html_out

    # Nothing persisted.
    stored = client.get(f"/api/v1/templates/{tmpl['id']}", headers=auth_headers).json()
    assert stored["logo_url"] == "https://cdn.example.com/old.png"
    assert stored["footer_text"] == "Saved footer"

    # No body keeps the saved behaviour.
    saved_preview = client.post(f"/api/v1/templates/{tmpl['id']}/preview", headers=auth_headers).json()
    assert "https://cdn.example.com/old.png" in saved_preview["rendered_html"]


def test_preview_override_inlines_uploaded_logo(client, tenant, auth_headers):
    from backend.app.core.config import settings

    logo_dir = os.path.join(settings.UPLOAD_DIR, "logos")
    os.makedirs(logo_dir, exist_ok=True)
    logo_path = os.path.join(logo_dir, "preview_override_logo.png")
    with open(logo_path, "wb") as f:
        f.write(_PNG_1X1)
    try:
        tmpl = _create_template(client, auth_headers)
        res = client.post(
            f"/api/v1/templates/{tmpl['id']}/preview",
            headers=auth_headers,
            json={"logo_url": "/uploads/logos/preview_override_logo.png"},
        )
        assert res.status_code == 200, res.text
        assert "data:image/png;base64," in res.json()["rendered_html"]
    finally:
        os.remove(logo_path)


def test_render_template_preview_override_service_level(db, tenant, client, auth_headers):
    tmpl = _create_template(client, auth_headers)
    out = customization_service.render_template_preview(
        db, tmpl["id"], tenant.organization.id, overrides={"logo_url": "/logos/x.png", "layout_type": "modern"}
    )
    assert '<img src="/logos/x.png"' in out["rendered_html"]
    assert out["layout_type"] == "modern"
