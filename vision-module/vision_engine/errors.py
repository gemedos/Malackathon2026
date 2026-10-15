"""Errores explícitos del módulo.

Los errores de datos heredan de ValueError para que el equipo integrador pueda
capturarlos de forma genérica. Un error NUNCA se convierte en un valor por
defecto (por ejemplo, un OCR fallido jamás pasa a ser cero).
"""


class VisionError(ValueError):
    """Base de todos los errores de datos del motor de visión."""


class ProfileError(VisionError):
    """Perfil de juego inválido, incompleto o peligrosamente genérico."""


class CalibrationError(VisionError):
    """La imagen no coincide con la calibración (resolución, ROI o caja CSS)."""


class ImageError(VisionError):
    """Imagen o plantilla ilegible o inutilizable."""


class SequenceError(VisionError):
    """Orden temporal o de acciones inválido (timestamps, segundo clic...)."""


class SpinNotFoundError(VisionError):
    """No hay evidencia suficiente del botón Spin: no se debe hacer clic."""


class OcrUnavailableError(RuntimeError):
    """Tesseract o el idioma configurado no están instalados (problema de entorno)."""
