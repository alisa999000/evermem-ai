"""evermem: local-first eternal memory engine for any LLM.

Conflict-aware claims with temporal validity, trust scoring and retrieval
plasticity. Zero dependencies; SQLite under the hood; optional LLM extraction
via Ollama or any OpenAI-compatible endpoint.
"""

from .embed_backends import OllamaEmbedder
from .extractor import EXTRACTION_SYSTEM_PROMPT, ExtractionResult, LLMExtractor, RuleExtractor
from .events import MemoryEvent, build_temporal_gaps, extract_assistant_claims, extract_memory_events
from .ingest import IngestError, IngestReport, extract_text, split_blocks
from .llm import LLMUnavailable, OllamaLLM, OpenAICompatLLM
from .memory import EverMem
from .plasticity import PathPlasticity
from .store import ClaimStore
from .types import (
    AggregateResult,
    Claim,
    ClaimDraft,
    ConflictHint,
    Episode,
    MemoryPack,
    ObserveReport,
    ScoredClaim,
    SessionPrimer,
    EntityCountSummary,
    MemoryEventSummary,
    TemporalGapSummary,
    Turn,
)

__version__ = "0.4.1"

__all__ = [
    "EverMem",
    "ClaimStore",
    "PathPlasticity",
    "LLMExtractor",
    "RuleExtractor",
    "ExtractionResult",
    "EXTRACTION_SYSTEM_PROMPT",
    "OllamaLLM",
    "OllamaEmbedder",
    "OpenAICompatLLM",
    "LLMUnavailable",
    "IngestError",
    "IngestReport",
    "extract_text",
    "split_blocks",
    "extract_countable_claims",
    "summarize_entity_counts",
    "extract_memory_events",
    "extract_assistant_claims",
    "build_temporal_gaps",
    "MemoryEvent",
    "Claim",
    "ClaimDraft",
    "ConflictHint",
    "Episode",
    "MemoryPack",
    "ObserveReport",
    "ScoredClaim",
    "SessionPrimer",
    "AggregateResult",
    "EntityCountSummary",
    "MemoryEventSummary",
    "TemporalGapSummary",
    "Turn",
    "__version__",
]
