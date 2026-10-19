"""POST /api/upload: recibe un fichero cifrado y firmado con PGP.

Descifra con la clave privada del servidor (Key Vault), verifica la firma del
cliente, guarda en Cosmos DB el mensaje tal como llegó (sigue cifrado) y devuelve
una confirmación cifrada para el cliente y firmada por el servidor.
"""
import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import azure.functions as func
from azure.cosmos import CosmosClient
from azure.identity import ClientSecretCredential
from azure.keyvault.secrets import SecretClient

from ..shared_code import pgp_server, rules

# Un documento de Cosmos DB admite 2 MB como máximo, y el mensaje PGP en ASCII
# ocupa más que el fichero original.
MAX_BODY_BYTES = 1_000_000

_secret_client = None
_secret_cache = {}
_container = None


def _secret(name):
    """Lee un secreto de Key Vault y lo recuerda mientras la instancia siga viva."""
    global _secret_client
    if name not in _secret_cache:
        if _secret_client is None:
            credential = ClientSecretCredential(
                tenant_id=os.environ["AZURE_TENANT_ID"],
                client_id=os.environ["AZURE_CLIENT_ID"],
                client_secret=os.environ["AZURE_CLIENT_SECRET"],
            )
            _secret_client = SecretClient(
                vault_url=os.environ["KEYVAULT_URL"], credential=credential
            )
        _secret_cache[name] = _secret_client.get_secret(name).value
    return _secret_cache[name]


def _files_container():
    global _container
    if _container is None:
        client = CosmosClient.from_connection_string(os.environ["COSMOS_CONNECTION_STRING"])
        _container = client.get_database_client("files").get_container_client("encrypted-files")
    return _container


def _json(status, payload):
    return func.HttpResponse(
        json.dumps(payload), status_code=status, mimetype="application/json"
    )


def main(req: func.HttpRequest) -> func.HttpResponse:
    body = req.get_body()
    if not body:
        return _json(400, {"error": "Cuerpo vacío"})
    if len(body) > MAX_BODY_BYTES:
        return _json(413, {"error": f"Demasiado grande (máximo {MAX_BODY_BYTES} bytes cifrados)"})
    try:
        armored = body.decode("ascii")
    except UnicodeDecodeError:
        return _json(400, {"error": "El cuerpo debe ser un mensaje PGP en ASCII (armor)"})

    # El nombre es solo un dato informativo: se limpia y se acota.
    filename = re.sub(r"[^\w.\- ]", "_", req.headers.get("X-Filename", ""))[:200]
    receipt_id = str(uuid.uuid4())

    try:
        server_priv = _secret("pgp-server-private-key")
        passphrase = _secret("pgp-server-passphrase")
        client_pub = _secret("pgp-client-public-key")

        # Si esto falla, el remitente no está autenticado: error 400 sin firma del servidor.
        content = pgp_server.open_upload(armored, server_priv, passphrase, client_pub)

        info = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
            "received_at": datetime.now(timezone.utc).isoformat(),
            "receipt_id": receipt_id,
        }

        # Fichero auténtico pero que el servidor no acepta: rechazo firmado y cifrado.
        rejection = rules.check_upload(content, filename)
        if rejection:
            code, message = rejection
            logging.warning("Fichero rechazado por las reglas: %s", code)
            confirmation = pgp_server.build_confirmation(
                {"status": "REJECTED", "reason": code, "message": message, **info},
                server_priv, passphrase, client_pub,
            )
            return func.HttpResponse(confirmation, status_code=422, mimetype="text/plain")

        confirmation = pgp_server.build_confirmation(
            {"status": "RECEIVED", **info}, server_priv, passphrase, client_pub
        )
        _files_container().create_item({
            "id": receipt_id,
            "filename": filename,
            **info,
            "ciphertext": armored,  # cifrado: solo la clave del servidor lo abre
        })
    except pgp_server.InvalidUpload as e:
        logging.warning("Subida rechazada: %s", e)
        return _json(400, {"error": str(e)})
    except Exception as e:
        # Solo para esta demo: devolvemos el tipo de error para poder depurar
        # sin acceso a los logs. En producción no se expondría.
        logging.exception("Error interno")
        return _json(500, {"error": type(e).__name__, "detail": str(e)})

    return func.HttpResponse(confirmation, status_code=200, mimetype="text/plain")
