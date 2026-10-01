"""Internet & strategy research layer (Phase 6).

Pipeline: Source Discovery -> Source Retrieval -> Evidence Extraction ->
Strategy Specification -> Deterministic Validation -> (optionally)
`adapter.py` -> a Phase 2 `Strategy` Phase 3 can experiment with.

Web content is untrusted input end to end. It can become `EvidenceItem`
quotes and, through an AI's explicitly-labeled interpretation, parts of a
`StrategySpecification` - never executable code, never a shell command,
never a trade. See ARCHITECTURE.md "Phase 6 - Internet & Strategy
Research Layer" for the full design and its safety boundaries.
"""

from app.research.adapter import AdapterResult, SpecDrivenStrategy, adapt_specification
from app.research.decision import ProposedRule, ResearchAction, SpecificationUpdate, WebResearchDecision
from app.research.discovery import (
    DiscoveryCandidate,
    DiscoveryResult,
    ManualSourceDiscoveryProvider,
    MockSourceDiscoveryProvider,
    SourceDiscoveryProvider,
)
from app.research.evidence import EvidenceItem, EvidenceStatus, extract_evidence
from app.research.limits import RetrievalLimits, WebResearchLimits, WebStoppingReason
from app.research.retrieval import HttpSourceRetriever, RetrievalOutcome, RetrievalResult, SourceRetriever
from app.research.session import WebResearchSessionRecord, WebResearchSessionStatus
from app.research.source import Source, SourceStatus, SourceType, TrustSignals, normalize_url
from app.research.specification import (
    Condition,
    FieldRef,
    IndicatorSpec,
    RuleSpec,
    RuleStatus,
    SpecStatus,
    StrategySpecification,
)
from app.research.validation import ValidationResult, validate_specification

__all__ = [
    "AdapterResult",
    "Condition",
    "DiscoveryCandidate",
    "DiscoveryResult",
    "EvidenceItem",
    "EvidenceStatus",
    "FieldRef",
    "HttpSourceRetriever",
    "IndicatorSpec",
    "ManualSourceDiscoveryProvider",
    "MockSourceDiscoveryProvider",
    "ProposedRule",
    "ResearchAction",
    "RetrievalLimits",
    "RetrievalOutcome",
    "RetrievalResult",
    "RuleSpec",
    "RuleStatus",
    "SourceDiscoveryProvider",
    "SourceRetriever",
    "SourceStatus",
    "SourceType",
    "Source",
    "SpecDrivenStrategy",
    "SpecStatus",
    "SpecificationUpdate",
    "StrategySpecification",
    "TrustSignals",
    "ValidationResult",
    "WebResearchDecision",
    "WebResearchLimits",
    "WebResearchSessionRecord",
    "WebResearchSessionStatus",
    "WebStoppingReason",
    "adapt_specification",
    "extract_evidence",
    "normalize_url",
    "validate_specification",
]
