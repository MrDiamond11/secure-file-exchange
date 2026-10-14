"""Prueba local del ciclo completo, sin Azure.

Necesita cliente-publica.asc y servidor-privada.asc en la carpeta indicada:
    python client/selftest.py --keys-dir "C:\\ruta\\a\\las\\claves"
"""
import argparse
import getpass
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

import client_gpg
from shared_code import pgp_server

parser = argparse.ArgumentParser()
parser.add_argument("--keys-dir", default=".")
keys_dir = Path(parser.parse_args().keys_dir)

server_priv = (keys_dir / "servidor-privada.asc").read_text()
client_pub = (keys_dir / "cliente-publica.asc").read_text()
server_pass = getpass.getpass("Passphrase del servidor: ")

# Incluye bytes binarios para comprobar que no se corrompe nada.
original = b"Fichero de prueba\n" + bytes(range(256))

print("1) El cliente cifra y firma con gpg...")
upload = client_gpg.encrypt_and_sign(original)

print("2) El servidor (PGPy) descifra y verifica la firma...")
content, confirmation = pgp_server.process_upload(
    upload, server_priv, server_pass, client_pub, receipt_id="recibo-de-prueba"
)
assert content == original, "El contenido descifrado no coincide con el original"
print("   contenido idéntico al original")

print("3) El cliente descifra la confirmación y verifica la firma del servidor...")
info = json.loads(client_gpg.decrypt_and_verify(confirmation))
assert info["sha256"] == hashlib.sha256(original).hexdigest(), "El hash no coincide"
assert info["receipt_id"] == "recibo-de-prueba", "Falta el identificador de recibo"
print("   confirmación válida:", info)

print("4) Un fichero SIN firma debe ser rechazado...")
try:
    pgp_server.process_upload(
        client_gpg.encrypt_only(original), server_priv, server_pass, client_pub
    )
except pgp_server.InvalidUpload as e:
    print("   rechazado correctamente:", e)
else:
    raise SystemExit("   ERROR: el servidor aceptó un fichero sin firma")

print("\nTODO OK")
