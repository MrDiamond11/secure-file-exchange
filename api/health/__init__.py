"""GET /api/health: diagnóstico TEMPORAL. Se borra cuando la API funcione.

Informa de si las dependencias se importan, si el módulo de la API carga y qué
variables de entorno existen (solo si están definidas, nunca su valor).
"""
import importlib
import json
import os
import sys

import azure.functions as func

IMPORTS = ["pgpy", "cryptography", "azure.identity", "azure.keyvault.secrets", "azure.cosmos"]
ENV = [
    "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET",
    "KEYVAULT_URL", "COSMOS_ENDPOINT", "COSMOS_CONNECTION_STRING",
]


def main(req: func.HttpRequest) -> func.HttpResponse:
    report = {"python": sys.version.split()[0], "imports": {}, "env_vars_present": {}}

    for name in IMPORTS:
        try:
            module = importlib.import_module(name)
            report["imports"][name] = getattr(module, "__version__", "ok")
        except Exception as e:
            report["imports"][name] = f"{type(e).__name__}: {e}"

    try:
        from ..shared_code import pgp_server  # noqa: F401
        report["imports"]["shared_code.pgp_server"] = "ok"
    except Exception as e:
        report["imports"]["shared_code.pgp_server"] = f"{type(e).__name__}: {e}"

    try:
        from .. import upload  # noqa: F401
        report["imports"]["modulo upload"] = "ok"
    except Exception as e:
        report["imports"]["modulo upload"] = f"{type(e).__name__}: {e}"

    for name in ENV:
        report["env_vars_present"][name] = bool(os.environ.get(name))

    return func.HttpResponse(json.dumps(report, indent=2), mimetype="application/json")
