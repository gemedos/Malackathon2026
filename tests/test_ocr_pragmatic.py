"""OCR del HUD de Pragmatic Play sobre recortes REALES de Sweet Bonanza (betsson.es, 2026-10-15).

El nombre de cada archivo de tests/fixtures/ocr/pragmatic-play/ es `<campo>_<valor esperado>[-nota].png`. Estos
recortes fallaban antes de `light_text`: «48,14 €» se leía 4.14 y los premios «GANANCIA x,xx €» eran ilegibles.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from validator.config import load_market
from validator.game.calibration import build_profile, load_calibration
from vision_engine.errors import OcrUnavailableError
from vision_engine.evidence import EvidenceStore
from vision_engine.geometry import ROI
from vision_engine.imaging import load_image
from vision_engine.ocr import FieldReader, tesseract_backend

FIXTURES = Path(__file__).parent / "fixtures" / "ocr" / "pragmatic-play"
CROPS = sorted(FIXTURES.glob("*.png"))


def _reader(backend=tesseract_backend) -> FieldReader:
    calibration = load_calibration("Pragmatic Play", "Sweet Bonanza").calibration
    profile = build_profile(calibration, load_market("es"), (770, 433))
    return FieldReader(profile, EvidenceStore(tempfile.mkdtemp()), backend)


def _tesseract_available() -> bool:
    try:
        tesseract_backend(np.full((10, 10), 255, np.uint8), "eng", "--psm 7")
        return True
    except OcrUnavailableError:
        return False


@pytest.mark.skipif(not _tesseract_available(), reason="Tesseract no instalado")
@pytest.mark.parametrize("path", CROPS, ids=[p.stem for p in CROPS])
def test_recorte_real_se_lee_exacto(path: Path) -> None:
    field, label = path.stem.split("_", 1)
    expected = label.split("-", 1)[0]
    image = load_image(path)
    reading = _reader().read(image, field, "fixture", 0.0, ROI(0, 0, image.shape[1], image.shape[0]))
    assert reading.value == expected, f"{path.name}: leído {reading.value!r} (raw {reading.raw_text!r})"


def test_hay_recortes_de_cada_campo() -> None:
    assert {p.stem.split("_", 1)[0] for p in CROPS} == {"balance", "wager", "payout"}


def test_lectura_alternativa_que_pierde_cifras_no_se_acepta() -> None:
    """psm 7 lee «4814» (sin coma) y psm 8 «4,14»: perder una cifra daría un saldo erróneo => ilegible."""
    answers = {"--psm 7": "4814", "--psm 8": "4,14", "--psm 13": "4,14"}

    def backend(image, language, config):
        return next(v for k, v in answers.items() if config.startswith(k))

    image = load_image(FIXTURES / "balance_48.14.png")
    reading = _reader(backend).read(image, "balance", "guard", 0.0, ROI(0, 0, image.shape[1], image.shape[0]))
    assert reading.value is None and "cifras distintas" in (reading.error or "")


def test_lectura_alternativa_con_las_mismas_cifras_si_se_acepta() -> None:
    answers = {"--psm 7": "4814", "--psm 8": "48,14", "--psm 13": "48,14"}

    def backend(image, language, config):
        return next(v for k, v in answers.items() if config.startswith(k))

    image = load_image(FIXTURES / "balance_48.14.png")
    reading = _reader(backend).read(image, "balance", "guard", 0.0, ROI(0, 0, image.shape[1], image.shape[0]))
    assert reading.value == "48.14"
