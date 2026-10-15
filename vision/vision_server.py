"""Proceso de visión: lee peticiones JSON (una por línea) en stdin y responde una línea JSON en stdout.

No controla el navegador ni decide el resultado del test: solo describe lo que ve en una captura.
Un valor ilegible se devuelve como null con un error, nunca como cero.

Órdenes:
  {"cmd": "ping"}
  {"cmd": "read", "image": ruta, "regions": {nombre: [x, y, ancho, alto]}, "text_hsv": [[h,s,v],[h,s,v]] (opcional)}
      (regiones en fracciones 0-1; con text_hsv solo se lee el texto de ese color y se exige unanimidad)
  {"cmd": "motion", "image_a": ruta, "image_b": ruta, "region": [x, y, ancho, alto], "mode": "pixel" | "cells", "grid": [columnas, filas] (modo cells)}
  {"cmd": "find_text", "image": ruta, "patterns": [regex, ...], "region": [x, y, ancho, alto] (opcional)}
  {"cmd": "locate", "image": ruta, "template": ruta, "reference_width": px, "threshold": 0-1}
"""

import json
import re
import sys
import unicodedata
from decimal import Decimal, InvalidOperation

import cv2
import numpy
import pytesseract

OCR_LANG = "spa+eng"
MIN_WORD_CONFIDENCE = 60
OCR_TARGET_HEIGHT = 60
MOTION_PIXEL_DELTA = 12
# Importe con formato español: 1.234,56 (también 0,20 o 12)
AMOUNT_PATTERN = re.compile(r"(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{2}))?")


def load_image(path):
    image = cv2.imread(path)
    if image is None:
        raise ValueError(f"no se pudo abrir la imagen {path}")
    return image


def crop(image, region):
    height, width = image.shape[:2]
    x, y, w, h = region
    left, top = int(x * width), int(y * height)
    return image[top:top + int(h * height), left:left + int(w * width)]


def ocr(image, single_line):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Tesseract lee mejor líneas de unos 40-60 px: ampliar solo las regiones pequeñas.
    scale = max(1.0, OCR_TARGET_HEIGHT / gray.shape[0]) if single_line else 2.0
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    # Texto claro sobre fondo oscuro es lo habitual en las tragaperras: invertir si hace falta.
    if numpy.mean(gray) < 128:
        gray = 255 - gray
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # En importes solo se admiten dígitos, separadores y el símbolo de moneda.
    config = "--psm 7 -c tessedit_char_whitelist=0123456789.,€" if single_line else "--psm 11"
    data = pytesseract.image_to_data(binary, lang=OCR_LANG, config=config, output_type=pytesseract.Output.DICT)
    words, confidences = [], []
    for word, confidence in zip(data["text"], data["conf"]):
        if word.strip():
            words.append(word.strip())
            confidences.append(float(confidence))
    min_confidence = min(confidences) if confidences else 0.0
    return " ".join(words), min_confidence


def parse_amount(text):
    """Devuelve (céntimos, error). Exige exactamente un importe legible en el texto."""
    cleaned = text.replace(" ", "")
    matches = [m for m in AMOUNT_PATTERN.finditer(cleaned) if m.group(0)]
    if len(matches) != 1:
        return None, f"se esperaba un importe y se encontraron {len(matches)} en {text!r}"
    integer_part, decimal_part = matches[0].group(1), matches[0].group(2) or "00"
    try:
        amount = Decimal(integer_part.replace(".", "") + "." + decimal_part)
    except InvalidOperation:
        return None, f"importe no válido en {text!r}"
    return int(amount * 100), None


# Escalas para leer importes de un color conocido: solo se acepta el importe si todas coinciden.
CONSENSUS_SCALES = [2, 3, 4, 5]


def ocr_colored_amount(image, hsv_range):
    """Aísla el texto del color indicado y lo lee a varias escalas. Devuelve (texto, error)."""
    lower, upper = hsv_range
    mask = cv2.inRange(cv2.cvtColor(image, cv2.COLOR_BGR2HSV), tuple(lower), tuple(upper))
    if cv2.countNonZero(mask) == 0:
        return "", "no hay texto del color esperado en la región"
    texts = []
    for scale in CONSENSUS_SCALES:
        resized = cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        _, binary = cv2.threshold(resized, 127, 255, cv2.THRESH_BINARY)
        binary = cv2.copyMakeBorder(255 - binary, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
        texts.append(pytesseract.image_to_string(
            binary, lang="eng", config="--psm 7 -c tessedit_char_whitelist=0123456789,€").strip())
    if len(set(texts)) != 1:
        return texts[0], f"lecturas OCR discrepantes: {texts}"
    return texts[0], None


def read_regions(request):
    image = load_image(request["image"])
    hsv_range = request.get("text_hsv")
    readings = {}
    for name, region in request["regions"].items():
        region_image = crop(image, region)
        if hsv_range:
            text, error = ocr_colored_amount(region_image, hsv_range)
            confidence = 100.0 if error is None else 0.0
        else:
            text, confidence = ocr(region_image, single_line=True)
            error = None
        cents = None
        if error is None:
            cents, error = parse_amount(text)
        if cents is not None and confidence < MIN_WORD_CONFIDENCE:
            cents, error = None, f"confianza OCR baja ({confidence:.0f})"
        readings[name] = {
            "text": text,
            "cents": cents,
            "has_euro": "€" in text or "EUR" in text.upper(),
            "confidence": confidence,
            "error": error,
        }
    return {"readings": readings}


# Modo "cells": la región se divide en la cuadrícula de rodillos y se compara el histograma de color de cada
# celda. Ignora animaciones en reposo (símbolos que se mecen unos píxeles) y detecta cambios de símbolo.
# Devuelve la fracción de celdas cuyo histograma dejó de parecerse.
CELL_MIN_CORRELATION = 0.8


def cell_histogram(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [18, 8], [0, 180, 0, 256])
    cv2.normalize(histogram, histogram)
    return histogram


def cells_changed(image_a, image_b, grid):
    columns, rows = grid
    height, width = image_a.shape[:2]
    changed = 0
    for column in range(columns):
        for row in range(rows):
            x0, x1 = column * width // columns, (column + 1) * width // columns
            y0, y1 = row * height // rows, (row + 1) * height // rows
            correlation = cv2.compareHist(cell_histogram(image_a[y0:y1, x0:x1]),
                                          cell_histogram(image_b[y0:y1, x0:x1]), cv2.HISTCMP_CORREL)
            changed += correlation < CELL_MIN_CORRELATION
    return changed / (columns * rows)


def motion(request):
    region = request["region"]
    image_a = crop(load_image(request["image_a"]), region)
    image_b = crop(load_image(request["image_b"]), region)
    if image_a.shape != image_b.shape:
        raise ValueError("las capturas tienen tamaños distintos")
    if request.get("mode") == "cells":
        changed = cells_changed(image_a, image_b, request["grid"])
    else:
        gray_a = cv2.cvtColor(image_a, cv2.COLOR_BGR2GRAY)
        gray_b = cv2.cvtColor(image_b, cv2.COLOR_BGR2GRAY)
        changed = numpy.mean(cv2.absdiff(gray_a, gray_b) > MOTION_PIXEL_DELTA)
    return {"changed_fraction": float(changed)}


def normalize(text):
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def find_text(request):
    image = load_image(request["image"])
    if request.get("region"):
        image = crop(image, request["region"])
    text, _ = ocr(image, single_line=False)
    normalized = normalize(text)
    for pattern in request["patterns"]:
        match = re.search(pattern, normalized)
        if match:
            return {"found": True, "match": match.group(0), "text": text}
    return {"found": False, "match": None, "text": text}


# La plantilla se recortó de un juego de `reference_width` px de ancho; se prueba a varias escalas alrededor.
LOCATE_SCALES = [0.85, 1.0, 1.15, 1.3, 1.45]


def locate(request):
    """Busca un control por plantilla. Devuelve su centro en fracciones (0-1) de la imagen y la puntuación."""
    image = cv2.cvtColor(load_image(request["image"]), cv2.COLOR_BGR2GRAY)
    template = cv2.cvtColor(load_image(request["template"]), cv2.COLOR_BGR2GRAY)
    base = image.shape[1] / request["reference_width"]
    best = (0.0, None, None)
    for factor in LOCATE_SCALES:
        scale = base * factor
        resized = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if resized.shape[0] > image.shape[0] or resized.shape[1] > image.shape[1]:
            continue
        result = cv2.matchTemplate(image, resized, cv2.TM_CCOEFF_NORMED)
        _, score, _, top_left = cv2.minMaxLoc(result)
        if score > best[0]:
            best = (float(score), top_left, resized.shape)
    score, top_left, shape = best
    if top_left is None or score < request["threshold"]:
        return {"found": False, "score": score, "x": None, "y": None}
    center_x = (top_left[0] + shape[1] / 2) / image.shape[1]
    center_y = (top_left[1] + shape[0] / 2) / image.shape[0]
    return {"found": True, "score": score, "x": center_x, "y": center_y}


COMMANDS = {
    "locate": locate,
    "ping": lambda request: {"pong": True},
    "read": read_regions,
    "motion": motion,
    "find_text": find_text,
}


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = {"ok": True, **COMMANDS[request["cmd"]](request)}
        except Exception as error:  # cualquier fallo se devuelve como error, nunca como lectura
            response = {"ok": False, "error": f"{type(error).__name__}: {error}"}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
