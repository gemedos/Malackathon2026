"""Motor de visión independiente de navegador para slots (OpenCV + Tesseract).

Recibe frames BGR del rectángulo visible del juego y devuelve coordenadas
locales, confianzas, lecturas OCR por campo, estados visuales, errores
explícitos y veredictos PASS/FAIL/INCONCLUSIVE por aserción.
"""
from .consensus import ConsensusResult, ConsensusStatus, consensus
from .currency import detect_currency
from .engine import VisionEngine
from .errors import (CalibrationError, ImageError, OcrUnavailableError, ProfileError,
                     SequenceError, SpinNotFoundError, VisionError)
from .evaluation import ExternalBalance, evaluate_insufficient, evaluate_spin
from .evidence import EvidenceStore
from .geometry import ROI, page_point
from .imaging import decode_png, load_image
from .matching import TemplateMatch, load_template
from .money import parse_money, reconcile
from .motion import MotionObservation, MotionState, MotionSummary, MotionTracker
from .ocr import OcrReading
from .profile import GameProfile
from .ready import ReadyDetector, ReadyObservation
from .scenario import FrameRecord, ScenarioRecord, SpinAttemptRecorder
from .verdict import AssertionResult, ScenarioReport, Verdict

__all__ = [
    'AssertionResult', 'CalibrationError', 'ConsensusResult', 'ConsensusStatus', 'EvidenceStore',
    'ExternalBalance', 'FrameRecord', 'GameProfile', 'ImageError', 'MotionObservation', 'MotionState',
    'MotionSummary', 'MotionTracker', 'OcrReading', 'OcrUnavailableError', 'ProfileError', 'ROI',
    'ReadyDetector', 'ReadyObservation', 'ScenarioRecord', 'ScenarioReport', 'SequenceError',
    'SpinAttemptRecorder', 'SpinNotFoundError', 'TemplateMatch', 'Verdict', 'VisionEngine',
    'VisionError', 'consensus', 'decode_png', 'detect_currency', 'evaluate_insufficient',
    'evaluate_spin', 'load_image', 'load_template', 'page_point', 'parse_money', 'reconcile',
]
