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
from .evaluation import BetssonBalance, evaluate_insufficient, evaluate_spin
from .evidence import EvidenceStore
from .geometry import ROI, page_point
from .language import detect_language
from .imaging import decode_png, load_image
from .matching import TemplateMatch, load_template
from .money import parse_money, reconcile
from .motion import MotionObservation, MotionState, MotionSummary, MotionTracker
from .ocr import OcrReading
from .profile import GameProfile, Market, load_markets
from .ready import ReadyDetector, ReadyObservation
from .report import TestResult, render_matrix, render_test
from .scenario import FrameRecord, ScenarioRecord, SpinAttemptRecorder
from .verdict import AssertionResult, ScenarioReport, Verdict

__all__ = [
    'AssertionResult', 'CalibrationError', 'ConsensusResult', 'ConsensusStatus', 'EvidenceStore',
    'BetssonBalance', 'FrameRecord', 'GameProfile', 'ImageError', 'MotionObservation', 'MotionState',
    'MotionSummary', 'MotionTracker', 'OcrReading', 'OcrUnavailableError', 'ProfileError', 'ROI',
    'ReadyDetector', 'ReadyObservation', 'ScenarioRecord', 'ScenarioReport', 'SequenceError',
    'SpinAttemptRecorder', 'SpinNotFoundError', 'TemplateMatch', 'Verdict', 'VisionEngine',
    'VisionError', 'consensus', 'decode_png', 'detect_currency', 'evaluate_insufficient',
    'evaluate_spin', 'load_image', 'load_template', 'page_point', 'parse_money', 'reconcile',
    'detect_language', 'Market', 'load_markets', 'TestResult', 'render_matrix', 'render_test',
]
