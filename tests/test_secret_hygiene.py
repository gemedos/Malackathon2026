"""Higiene de secretos: ningún valor de BETSSON_* puede aparecer en artifacts/.

Se ejecuta SIEMPRE (también en CI con `if: always()`). No se puede desactivar ni debilitar.
Recorre todos los archivos, incluido el contenido descomprimido de los .zip (traza de Playwright).
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Iterator
from urllib.parse import quote, quote_plus

import pytest

from validator.evidence import ARTIFACTS_DIR
from validator.secrets import secret_values


def _variants(value: str) -> set[bytes]:
    """Formas en que un valor puede quedar escrito (texto, URL, JSON, UTF-16)."""
    fully_encoded = "".join(f"%{b:02X}" for b in value.encode("utf-8"))
    forms = {value, quote(value, safe=""), quote_plus(value), fully_encoded, json.dumps(value)[1:-1]}
    out = {f.encode("utf-8") for f in forms if f}
    out.add(value.encode("utf-16-le"))
    return out


def _blobs(root: Path) -> Iterator[tuple[str, bytes]]:
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        data = path.read_bytes()
        rel = path.relative_to(root).as_posix()
        yield rel, data
        if zipfile.is_zipfile(io.BytesIO(data)):
            yield from _zip_blobs(rel, data)


def _zip_blobs(prefix: str, data: bytes) -> Iterator[tuple[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            member = zf.read(name)
            yield f"{prefix}!{name}", member
            if zipfile.is_zipfile(io.BytesIO(member)):
                yield from _zip_blobs(f"{prefix}!{name}", member)


def test_no_secrets_in_artifacts() -> None:
    values = secret_values()
    if not values:
        pytest.skip("No hay variables BETSSON_* definidas: no hay valores que buscar")
    if not ARTIFACTS_DIR.exists():
        return
    patterns = [(i, form) for i, value in enumerate(values) for form in _variants(value)]
    leaks: list[str] = []
    for name, blob in _blobs(ARTIFACTS_DIR):
        lowered = blob.lower()
        for index, form in patterns:
            if form in blob or form.lower() in lowered:
                # Solo se informa del archivo y del índice de la variable, nunca del valor.
                leaks.append(f"{name} (secreto #{index})")
                break
    assert not leaks, "Se encontraron secretos en artifacts/: " + ", ".join(leaks)


def test_no_auth_state_in_artifacts() -> None:
    if not ARTIFACTS_DIR.exists():
        return
    offenders = [p.as_posix() for p in ARTIFACTS_DIR.rglob("*") if ".auth" in p.parts]
    assert not offenders, f"storage_state dentro de artifacts/: {offenders}"
