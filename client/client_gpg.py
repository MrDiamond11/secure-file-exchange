"""Lado cliente: usa el binario gpg instalado en tu equipo.

La clave privada del cliente nunca sale del llavero de gpg. Cuando haga
falta, gpg abrirá una ventana (pinentry) pidiendo su passphrase.

Nota de compatibilidad: gpg 2.5 cifra con AEAD (OCB) si la clave del destinatario
lo anuncia, y PGPy no lo soporta. Por eso la clave del servidor se ajustó con
`gpg --edit-key ... setpref` para no anunciar AEAD.
"""
import subprocess

CLIENT_ID = "cliente-demo@proyecto.local"
SERVER_ID = "servidor-demo@proyecto.local"
# Fingerprint de la clave del servidor: solo aceptamos confirmaciones firmadas por ella.
SERVER_FPR = "FE59E82CAE1CBC8EF814673C82FC05DCD0DB127E"


class GpgError(Exception):
    pass


def _gpg(args, data):
    result = subprocess.run(
        ["gpg", "--batch", "--yes", "--status-fd", "2", *args],
        input=data,
        capture_output=True,
    )
    if result.returncode != 0:
        raise GpgError(result.stderr.decode(errors="replace"))
    return result


def encrypt_and_sign(data: bytes) -> str:
    """Cifra con la pública del servidor y firma con la privada del cliente."""
    r = _gpg(
        ["--armor", "--encrypt", "--sign",
         "--local-user", CLIENT_ID, "--recipient", SERVER_ID,
         "--trust-model", "always"],
        data,
    )
    return r.stdout.decode()


def encrypt_only(data: bytes) -> str:
    """Cifra SIN firmar. Solo lo usa el selftest para comprobar que el servidor lo rechaza."""
    r = _gpg(
        ["--armor", "--encrypt", "--recipient", SERVER_ID, "--trust-model", "always"],
        data,
    )
    return r.stdout.decode()


def decrypt_and_verify(armored: str) -> bytes:
    """Descifra con la privada del cliente y exige firma válida del servidor."""
    r = _gpg(["--decrypt"], armored.encode())
    status = r.stderr.decode(errors="replace")
    valid = [l for l in status.splitlines() if l.startswith("[GNUPG:] VALIDSIG")]
    if not any(SERVER_FPR in l for l in valid):
        raise GpgError("La confirmación no está firmada por el servidor esperado")
    return r.stdout
