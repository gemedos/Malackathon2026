"""Lectura segura de credenciales desde variables de entorno.

Reglas (CLAUDE.md §3): los valores nunca se imprimen, loguean ni aparecen en errores.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field

from validator import PROJECT_ROOT

log = logging.getLogger(__name__)

ACCOUNTS = ("FUNDED", "EMPTY")
SECRET_ENV_PREFIX = "BETSSON_"


class MissingCredentialError(RuntimeError):
    """Falta una variable de entorno de credenciales (el mensaje solo nombra la variable)."""


@dataclass(frozen=True)
class Credentials:
    """Usuario y contraseña. Nunca se representan en texto."""

    username: str = field(repr=False)
    password: str = field(repr=False)

    def __repr__(self) -> str:
        return "Credentials(***)"

    def __str__(self) -> str:
        return "***"


def load_env_file() -> None:
    """Carga `.env` solo si existe (en CI las variables vienen de GitHub Secrets)."""
    env_file = PROJECT_ROOT / ".env"
    if env_file.is_file():
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
        log.info("Variables cargadas desde .env")


def env_var_names(market: str, account: str) -> tuple[str, str]:
    prefix = f"{SECRET_ENV_PREFIX}{market.upper()}_{account.upper()}"
    return f"{prefix}_USER", f"{prefix}_PASS"


def _mask_in_ci(value: str) -> None:
    """Pide a GitHub Actions que enmascare el valor en los logs.

    Se escribe en el stdout real del proceso (pytest captura sys.stdout).
    """
    if os.environ.get("GITHUB_ACTIONS") == "true":
        stream = sys.__stdout__
        if stream is not None:
            stream.write(f"::add-mask::{value}\n")
            stream.flush()


def get_credentials(account: str, market: str = "es") -> Credentials:
    """Devuelve las credenciales de la cuenta (FUNDED o EMPTY) del mercado."""
    account = account.upper()
    if account not in ACCOUNTS:
        raise ValueError(f"Cuenta desconocida: {account!r}. Usa una de {ACCOUNTS}")
    load_env_file()
    user_var, pass_var = env_var_names(market, account)
    missing = [name for name in (user_var, pass_var) if not os.environ.get(name)]
    if missing:
        raise MissingCredentialError(
            ("Falta la variable de entorno " if len(missing) == 1 else "Faltan las variables de entorno ")
            + ", ".join(missing)
            + (". Defínela" if len(missing) == 1 else ". Defínelas") + " en .env (local) o en GitHub Secrets (CI)."
        )
    username = os.environ[user_var]
    password = os.environ[pass_var]
    _mask_in_ci(username)
    _mask_in_ci(password)
    log.info("Credenciales de la cuenta %s cargadas desde %s / %s", account, user_var, pass_var)
    return Credentials(username=username, password=password)


def secret_values() -> list[str]:
    """Valores de todas las variables BETSSON_* (para el test de higiene; nunca se muestran)."""
    load_env_file()
    return [v for k, v in os.environ.items() if k.startswith(SECRET_ENV_PREFIX) and v]
