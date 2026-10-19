"""Reglas de negocio que el servidor aplica a un fichero ya autenticado."""
import os

ALLOWED_EXTENSIONS = {".txt", ".csv", ".xml", ".json", ".pdf"}


def check_upload(content: bytes, filename: str):
    """Devuelve (código, mensaje) si hay que rechazar el fichero, o None si es válido."""
    if len(content) == 0:
        return "EMPTY_FILE", "El fichero está vacío"
    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        permitidas = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return "EXTENSION_NOT_ALLOWED", f"Extensión no permitida (permitidas: {permitidas})"
    return None
