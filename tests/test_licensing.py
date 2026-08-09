"""Tests for licensing module."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

import spotify_playlist_generator.licensing as licensing_module
from spotify_playlist_generator.licensing import (
    STATE_CLOCK,
    STATE_EXPIRED,
    STATE_INVALID,
    STATE_MISSING,
    STATE_UNCHECKED,
    STATE_VALID,
    check,
    load_state,
    parse_key,
    save_state,
)

# Die Signaturtests brauchen cryptography. Der Import steht in einem try, weil das
# Paket in manchen Umgebungen zwar installiert, aber nicht ladbar ist. Nur ein echter
# Ladeversuch verrät das – eine feste Zuweisung würde die Tests still abschalten und
# damit genau die Prüfung verstecken, auf der das Lizenzsystem beruht.
# BaseException, weil ein gegen unpassende Systembibliotheken gebautes cryptography
# mit einer PanicException aus der Rust-Anbindung abbricht statt mit ImportError.
try:  # pragma: no cover - hängt von der Umgebung ab
    from cryptography.hazmat.primitives.asymmetric import ed25519 as _ed25519_probe

    HAS_CRYPTO = _ed25519_probe is not None
except (KeyboardInterrupt, SystemExit):
    raise
except BaseException:
    HAS_CRYPTO = False


def _make_keypair():
    """Generate Ed25519 keypair for testing."""
    if not HAS_CRYPTO:
        pytest.skip("cryptography not available")

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_key_hex = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    return private_key, public_key_hex


# Unterscheidet "nicht angegeben" von "ausdrücklich unbefristet". Ohne dieses
# Merkmal ließe sich ein unbefristeter Schlüssel im Test gar nicht bauen, weil
# None bereits für die Vorgabe von einem Jahr steht.
_UNSET = object()


def _make_license_key(private_key, name="Test Customer", key_id="test1",
                      issued=None, expires=_UNSET):
    """Create a valid signed license key."""
    import base64

    if issued is None:
        issued = date.today()
    if expires is _UNSET:
        expires = date.today() + timedelta(days=365)

    payload_dict = {
        "n": name,
        "id": key_id,
        "i": issued.isoformat(),
        "e": expires.isoformat() if expires is not None else None,
    }

    payload_json = json.dumps(payload_dict, separators=(",", ":"), ensure_ascii=False)
    payload_bytes = payload_json.encode("utf-8")
    signature_bytes = private_key.sign(payload_bytes)

    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    signature_b64 = base64.urlsafe_b64encode(signature_bytes).decode("ascii").rstrip("=")

    return f"KDS1.{payload_b64}.{signature_b64}"


# Tests that don't require cryptography


def test_load_state_missing_file_returns_empty(tmp_path):
    """load_state returns empty dict when file doesn't exist."""
    path = tmp_path / "license.json"

    result = load_state(path)

    assert result == {}


def test_load_state_broken_json_returns_empty(tmp_path):
    """load_state returns empty dict on broken JSON."""
    path = tmp_path / "license.json"
    path.write_text("not valid json {")

    result = load_state(path)

    assert result == {}


def test_load_state_reads_valid_json(tmp_path):
    """load_state reads and returns valid JSON."""
    path = tmp_path / "license.json"
    data = {"key": "KDS1.xxx.yyy", "last_seen": "2024-06-15"}
    path.write_text(json.dumps(data))

    result = load_state(path)

    assert result == data


def test_save_state_creates_parent_directory(tmp_path):
    """save_state creates missing parent directories."""
    path = tmp_path / "a" / "b" / "license.json"
    key = "KDS1.test.key"
    last_seen = date.today()

    save_state(key, last_seen, path)

    assert path.exists()
    assert path.parent.exists()


def test_check_missing_key_returns_state_missing():
    """check returns STATE_MISSING when no key is provided."""
    status = check(None, date.today())

    assert status.state == STATE_MISSING
    assert status.license is None


def test_check_empty_key_returns_state_missing():
    """check returns STATE_MISSING when key is empty string."""
    status = check("", date.today())

    assert status.state == STATE_MISSING


def test_check_invalid_key_returns_state_invalid(monkeypatch):
    """check returns STATE_INVALID when parse_key raises."""
    monkeypatch.setattr(licensing_module, "PUBLIC_KEY_HEX", "")

    status = check("definitely not a license key", date.today())

    assert status.state == STATE_INVALID
    assert status.detail  # Should have error text


# Tests that require cryptography


@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not available")
def test_parse_key_valid_key_is_read(monkeypatch):
    """parse_key successfully reads a valid signed key."""
    private_key, public_key_hex = _make_keypair()
    monkeypatch.setattr(licensing_module, "PUBLIC_KEY_HEX", public_key_hex)

    issued = date(2024, 1, 1)
    expires = date(2025, 1, 1)
    key = _make_license_key(private_key, "Test Co", "id123", issued, expires)

    license_obj = parse_key(key)

    assert license_obj.name == "Test Co"
    assert license_obj.key_id == "id123"
    assert license_obj.issued == issued
    assert license_obj.expires == expires


@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not available")
def test_parse_key_wrong_prefix_raises(monkeypatch):
    """parse_key raises LicenseError if prefix is wrong."""
    private_key, public_key_hex = _make_keypair()
    monkeypatch.setattr(licensing_module, "PUBLIC_KEY_HEX", public_key_hex)

    key = _make_license_key(private_key)
    wrong_key = key.replace("KDS1", "INVALID")

    with pytest.raises(licensing_module.LicenseError):
        parse_key(wrong_key)


@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not available")
def test_parse_key_broken_base64_raises(monkeypatch):
    """parse_key raises LicenseError on broken base64."""
    monkeypatch.setattr(licensing_module, "PUBLIC_KEY_HEX", "")
    key = "KDS1.!!!invalid!!!.signature"

    with pytest.raises(licensing_module.LicenseError):
        parse_key(key)


@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not available")
def test_check_expired_key_returns_state_expired(monkeypatch):
    """check returns STATE_EXPIRED when now > expires."""
    private_key, public_key_hex = _make_keypair()
    monkeypatch.setattr(licensing_module, "PUBLIC_KEY_HEX", public_key_hex)

    issued = date(2024, 1, 1)
    expires = date(2024, 6, 1)
    key = _make_license_key(private_key, issued=issued, expires=expires)
    now = date(2024, 7, 1)

    status = check(key, now)

    assert status.state == STATE_EXPIRED
    assert status.days_left == (expires - now).days


@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not available")
def test_check_valid_key_returns_state_valid(monkeypatch):
    """check returns STATE_VALID for a valid, non-expired key."""
    private_key, public_key_hex = _make_keypair()
    monkeypatch.setattr(licensing_module, "PUBLIC_KEY_HEX", public_key_hex)

    now = date.today()
    expires = now + timedelta(days=30)
    key = _make_license_key(private_key, expires=expires)

    status = check(key, now)

    assert status.state == STATE_VALID
    assert status.license is not None
    assert status.days_left == 30


@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not available")
def test_check_unlimited_key_has_no_days_left(monkeypatch):
    """check returns None for days_left when license has no expiry."""
    private_key, public_key_hex = _make_keypair()
    monkeypatch.setattr(licensing_module, "PUBLIC_KEY_HEX", public_key_hex)

    key = _make_license_key(private_key, expires=None)

    status = check(key, date.today())

    assert status.state == STATE_VALID
    assert status.days_left is None
    assert status.license.expires is None


def test_tooling_error_is_unchecked_not_invalid(monkeypatch):
    """
    Eine unbrauchbare Krypto-Bibliothek führt zu STATE_UNCHECKED.

    Der Schlüssel des Kunden ist in diesem Fall womöglich tadellos – nur die
    Prüfung lässt sich auf seinem Rechner nicht durchführen. Ihn als ungültig
    zu melden wäre eine falsche Anschuldigung.
    """
    monkeypatch.setattr(licensing_module, "PUBLIC_KEY_HEX", "aa" * 32)

    def kaputt(*args, **kwargs):
        raise licensing_module.ToolingError("cryptography nicht verwendbar")

    monkeypatch.setattr(licensing_module, "_verify_signature", kaputt)

    # Eine syntaktisch einwandfreie Nutzlast, damit wirklich die Signaturprüfung greift
    payload = json.dumps(
        {"n": "Kunde", "id": "a1", "i": "2026-01-01", "e": "2027-01-01"},
        separators=(",", ":"),
    ).encode()
    import base64
    key = "KDS1.{}.{}".format(
        base64.urlsafe_b64encode(payload).decode().rstrip("="),
        base64.urlsafe_b64encode(b"x" * 64).decode().rstrip("="),
    )

    status = check(key, date(2026, 6, 1))

    assert status.state == STATE_UNCHECKED
    assert "cryptography" in status.detail


def test_tampered_key_stays_invalid(monkeypatch):
    """Ein echter Signaturfehler bleibt STATE_INVALID – die Trennung muss halten."""
    monkeypatch.setattr(licensing_module, "PUBLIC_KEY_HEX", "aa" * 32)

    def falsch(*args, **kwargs):
        raise licensing_module.LicenseError("Signatur ungültig")

    monkeypatch.setattr(licensing_module, "_verify_signature", falsch)

    payload = json.dumps(
        {"n": "Kunde", "id": "a1", "i": "2026-01-01", "e": "2027-01-01"},
        separators=(",", ":"),
    ).encode()
    import base64
    key = "KDS1.{}.{}".format(
        base64.urlsafe_b64encode(payload).decode().rstrip("="),
        base64.urlsafe_b64encode(b"x" * 64).decode().rstrip("="),
    )

    assert check(key, date(2026, 6, 1)).state == STATE_INVALID
