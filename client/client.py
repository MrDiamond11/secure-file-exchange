"""Cliente: cifra y firma un fichero, lo sube por HTTPS y verifica la confirmación.

Uso:
    python client/client.py fichero.txt --url https://<tu-app>.azurestaticapps.net
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import requests

import client_gpg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fichero")
    parser.add_argument("--url", required=True, help="URL base de la Static Web App")
    args = parser.parse_args()

    path = Path(args.fichero)
    data = path.read_bytes()

    print(f"Cifrando y firmando {path.name} ({len(data)} bytes)...")
    armored = client_gpg.encrypt_and_sign(data)

    print("Subiendo...")
    response = requests.post(
        args.url.rstrip("/") + "/api/upload",
        data=armored.encode("ascii"),
        headers={"Content-Type": "text/plain", "X-Filename": path.name},
        timeout=60,
    )
    if response.status_code not in (200, 422):
        sys.exit(f"El servidor respondió {response.status_code}: {response.text}")

    # La confirmación llega cifrada para nosotros y firmada por el servidor.
    confirmation_file = path.with_name(path.name + ".confirmacion.asc")
    confirmation_file.write_text(response.text, encoding="ascii")
    info = json.loads(client_gpg.decrypt_and_verify(response.text))

    if info.get("sha256") != hashlib.sha256(data).hexdigest():
        sys.exit("La confirmación no corresponde al fichero enviado (hash distinto)")

    recibido = info.get("status") == "RECEIVED"
    print("Confirmación válida, firmada por el servidor:" if recibido
          else "FICHERO RECHAZADO. Confirmación válida, firmada por el servidor:")
    print(json.dumps(info, indent=2, ensure_ascii=False))
    print(f"Guardada tal como llegó (cifrada) en {confirmation_file}")
    if not recibido:
        sys.exit(2)


if __name__ == "__main__":
    main()
