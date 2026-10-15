"""Errores que llevan adjunta la ruta de su evidencia (para el campo `evidence` de los resultados)."""

from __future__ import annotations


class EvidenceError(RuntimeError):
    def __init__(self, message: str, evidence: str | None = None) -> None:
        super().__init__(message if evidence is None else f"{message} (evidencia: {evidence})")
        self.evidence = evidence


class SiteBlockedError(EvidenceError):
    """La web no está disponible desde la ubicación (IP) del navegador: bloqueo geográfico."""
