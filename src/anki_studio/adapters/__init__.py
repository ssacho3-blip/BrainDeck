"""Adapters layer for Anki Studio (SQLite WAL Store, .apkg Codec, AI Synthesizer, and Document Ingestor)."""

from .ai_engine import AICardSynthesizer
from .document_ingestor import (
    MAX_DOCUMENT_BYTES,
    AppleVisionOcrAdapter,
    DocumentIngestor,
    ExtractionResult,
    LlmVisionAdapter,
    StdlibPdfTextAdapter,
)
from .sqlite_store import AnkiStudioStore

__all__ = [
    "MAX_DOCUMENT_BYTES",
    "AICardSynthesizer",
    "AnkiStudioStore",
    "AppleVisionOcrAdapter",
    "DocumentIngestor",
    "ExtractionResult",
    "LlmVisionAdapter",
    "StdlibPdfTextAdapter",
]

