#!/usr/bin/env python3
"""
Werkzeug für den Entwickler zum Verwalten von Lizenzschlüsseln.

Nicht für Kunden — nur für interne Verwaltung von Schlüsselpaaren
und Kundenlizenzen.
"""

import argparse
import base64
import json
import secrets
import sys
from datetime import date
from pathlib import Path

from spotify_playlist_generator.licensing import parse_key


def cmd_keygen(args):
    """
    Erzeugt ein Ed25519-Schlüsselpaar.

    Privaten Schlüssel als PEM in PFAD schreiben (Datei auf 0600 setzen).
    Öffentlichen Schlüssel als Hex auf die Konsole ausgeben.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    out_path = Path(args.out)

    # Nicht überschreiben
    if out_path.exists():
        print(f"Fehler: {out_path} existiert bereits. Nicht überschreiben.", file=sys.stderr)
        sys.exit(1)

    # Schlüsselpaar erzeugen
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Privaten Schlüssel als PEM schreiben
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(pem)

    # Dateirechte setzen
    out_path.chmod(0o600)

    # Öffentlichen Schlüssel als Hex ausgeben
    public_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_key_hex = public_key_bytes.hex()

    print(f"Privater Schlüssel in {out_path} gespeichert.")
    print(f"\nÖffentlicher Schlüssel (hex):")
    print(public_key_hex)
    print(f"\nDiesen Wert in licensing.py als PUBLIC_KEY_HEX eintragen.")


def cmd_issue(args):
    """
    Stellt einen Lizenzschlüssel aus.

    Format: KDS1.<payload>.<signature>
    payload: base64url über JSON {n, id, i, e}
    signature: Ed25519 über payload-Bytes
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    # Privaten Schlüssel laden
    key_path = Path(args.key)
    try:
        with open(key_path, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except Exception as e:
        print(f"Fehler beim Laden des Schlüssels: {e}", file=sys.stderr)
        sys.exit(1)

    # Kennung: zufällig oder vorgegeben
    key_id = args.id or secrets.token_hex(4)

    # Payload zusammenstellen
    payload_dict = {
        "n": args.name,
        "id": key_id,
        "i": date.today().isoformat(),
    }

    # Ablaufdatum (optional)
    if args.until:
        payload_dict["e"] = args.until
    else:
        payload_dict["e"] = None

    # JSON ohne Whitespace
    payload_json = json.dumps(payload_dict, separators=(",", ":"), ensure_ascii=False)
    payload_bytes = payload_json.encode("utf-8")

    # Signatur berechnen
    signature_bytes = private_key.sign(payload_bytes)

    # base64url ohne Polsterung
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    signature_b64 = base64.urlsafe_b64encode(signature_bytes).decode("ascii").rstrip("=")

    # Schlüssel zusammensetzen
    key = f"KDS1.{payload_b64}.{signature_b64}"

    # Auf 64-Zeichen-Zeilen umbrechen
    wrapped = "\n".join(key[i : i + 64] for i in range(0, len(key), 64))

    print(wrapped)


def cmd_verify(args):
    """
    Prüft einen Lizenzschlüssel.

    Gibt Name, Kennung, Ausstellungs- und Ablaufdatum sowie Restlaufzeit aus.
    """
    key = args.key

    try:
        license = parse_key(key)
    except Exception as e:
        print(f"Fehler: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Name:                 {license.name}")
    print(f"Kennung:              {license.key_id}")
    print(f"Ausgestellt:          {license.issued}")

    if license.expires:
        days_left = (license.expires - date.today()).days
        print(f"Gültig bis:           {license.expires}")
        if days_left > 0:
            print(f"Restlaufzeit:         {days_left} Tag{'e' if days_left != 1 else ''}")
        elif days_left == 0:
            print(f"Restlaufzeit:         heute ablaufen")
        else:
            print(f"Restlaufzeit:         abgelaufen ({abs(days_left)} Tage ago)")
    else:
        print(f"Gültig bis:           unbefristet")


def main():
    """Hauptprogramm: argparse-Befehlszeile."""
    parser = argparse.ArgumentParser(
        description="Werkzeug zum Verwalten von Lizenzschlüsseln."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Befehl: keygen
    keygen_parser = subparsers.add_parser("keygen", help="Erzeugt ein Ed25519-Schlüsselpaar")
    keygen_parser.add_argument("--out", required=True, help="Datei für privaten Schlüssel")
    keygen_parser.set_defaults(func=cmd_keygen)

    # Befehl: issue
    issue_parser = subparsers.add_parser("issue", help="Stellt einen Lizenzschlüssel aus")
    issue_parser.add_argument("--name", required=True, help="Kundenname")
    issue_parser.add_argument("--until", help="Ablaufdatum (YYYY-MM-DD)")
    issue_parser.add_argument("--key", required=True, help="Pfad zum privaten Schlüssel")
    issue_parser.add_argument("--id", help="Schlüsselkennung (zufällig wenn nicht vorgegeben)")
    issue_parser.set_defaults(func=cmd_issue)

    # Befehl: verify
    verify_parser = subparsers.add_parser("verify", help="Prüft einen Lizenzschlüssel")
    verify_parser.add_argument("key", help="Lizenzschlüssel")
    verify_parser.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
