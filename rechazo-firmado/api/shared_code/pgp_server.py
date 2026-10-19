"""Lado servidor: lógica PGP con PGPy (Python puro, sin binario gpg).

Las claves llegan como parámetros (en Azure vienen de Key Vault), así que
aquí no se lee nada de disco.
"""
import hashlib
import json
from datetime import datetime, timezone

import pgpy
from pgpy.constants import SymmetricKeyAlgorithm


class InvalidUpload(Exception):
    """El fichero recibido no se puede descifrar o no tiene una firma válida."""


def _load_key(armored: str):
    key, _ = pgpy.PGPKey.from_blob(armored)
    return key


def _to_bytes(content) -> bytes:
    return content.encode("utf-8") if isinstance(content, str) else bytes(content)


def _sign_and_encrypt(info: dict, server_priv, passphrase: str, client_pub) -> str:
    """Firma con la privada del servidor y cifra con la pública del cliente."""
    msg = pgpy.PGPMessage.new(json.dumps(info))
    with server_priv.unlock(passphrase):
        msg |= server_priv.sign(msg)
    cipher = SymmetricKeyAlgorithm.AES256
    sessionkey = cipher.gen_key()
    encrypted = client_pub.encrypt(msg, cipher=cipher, sessionkey=sessionkey)
    del sessionkey
    return str(encrypted)


def open_upload(armored_upload, server_priv_armored, server_passphrase, client_pub_armored) -> bytes:
    """Descifra y verifica la firma del cliente. Devuelve el contenido en claro.

    Lanza InvalidUpload si no descifra o si la firma falta o no es válida.
    """
    server_priv = _load_key(server_priv_armored)
    client_pub = _load_key(client_pub_armored)

    try:
        message = pgpy.PGPMessage.from_blob(armored_upload)
        with server_priv.unlock(server_passphrase):
            decrypted = server_priv.decrypt(message)
    except Exception as e:
        raise InvalidUpload(f"No se pudo descifrar: {e}")

    if not decrypted.signatures:
        raise InvalidUpload("El fichero no está firmado")

    try:
        verification = client_pub.verify(decrypted)
    except Exception as e:
        raise InvalidUpload(f"Firma no verificable con la clave del cliente: {e}")

    # Exigimos al menos una firma buena y que ninguna sea mala.
    if not bool(verification) or not any(True for _ in verification.good_signatures):
        raise InvalidUpload("Firma inválida")

    return _to_bytes(decrypted.message)


def build_confirmation(info: dict, server_priv_armored, server_passphrase, client_pub_armored) -> str:
    """Confirmación (recibido o rechazado): firmada por el servidor y cifrada para el cliente."""
    return _sign_and_encrypt(
        info, _load_key(server_priv_armored), server_passphrase, _load_key(client_pub_armored)
    )


def process_upload(armored_upload, server_priv_armored, server_passphrase,
                   client_pub_armored, receipt_id=None):
    """Flujo completo de aceptación: devuelve (contenido, confirmación RECEIVED)."""
    content = open_upload(armored_upload, server_priv_armored, server_passphrase, client_pub_armored)
    info = {
        "status": "RECEIVED",
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    if receipt_id:
        info["receipt_id"] = receipt_id
    confirmation = build_confirmation(info, server_priv_armored, server_passphrase, client_pub_armored)
    return content, confirmation
