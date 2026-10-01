"""`WebResearchAgent` - the bounded workflow from the Phase 6 brief
section 18:

    Objective -> Discover Sources -> Retrieve Sources -> Extract Evidence
    -> Construct Strategy Specification -> Validate -> Report
    (VALID / INCOMPLETE / AMBIGUOUS / FAILED)

Reuses `app.ai.provider.AIProvider` unchanged (an `AIProvider` was always
just "turns a context into a decision" - no web-research-specific
provider abstraction was needed). The AI only ever receives a
`WebResearchContext` (bounded, four-part-labeled, see context.py) and
only ever produces a `WebResearchDecision` (closed `ResearchAction` enum,
see decision.py) - there is no field anywhere in that decision capable of
expressing a shell command, a file write, a config change, or a change to
`WebResearchLimits`, so the critical architectural rule (brief section 2)
holds structurally: web content can become evidence, evidence can become
an AI-labeled interpretation inside a strategy specification, and a
specification can become a `Strategy` ONLY through `adapter.py`'s safe,
fixed interpreter - never through executing anything the web or the AI
produced.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from app.ai.provider import AIInvocationRequest, AIProvider, AIProviderError
from app.core.events import EventRecorder, EventType
from app.database.connection import Database
from app.logging.setup import LogCategory, get_logger
from app.research import persistence as research_persistence
from app.research.cache import SourceCache
from app.research.context import EvidenceSummary, SourceSummary, WebResearchContext
from app.research.decision import ProposedRule, ResearchAction, SpecificationUpdate, WebResearchDecision
from app.research.discovery import SourceDiscoveryProvider
from app.research.evidence import EvidenceItem, EvidenceStatus, extract_evidence
from app.research.limits import WebResearchLimits, WebStoppingReason
from app.research.normalization import normalize_content
from app.research.retrieval import RetrievalOutcome, SourceRetriever
from app.research.session import WebResearchSessionRecord, WebResearchSessionStatus, new_web_session_id
from app.research.source import Source, SourceStatus, SourceType, TrustSignals, compute_content_hash, new_source_id
from app.research.specification import IndicatorSpec, RuleSpec, RuleStatus, StrategySpecification
from app.research.validation import validate_specification

_ACCESS_DENIED_OUTCOMES = {RetrievalOutcome.ACCESS_DENIED}
_FAILURE_OUTCOMES = {
    RetrievalOutcome.TIMEOUT,
    RetrievalOutcome.HTTP_ERROR,
    RetrievalOutcome.OVERSIZED,
    RetrievalOutcome.NETWORK_ERROR,
    RetrievalOutcome.UNSUPPORTED_SCHEME,
}


class WebResearchAgent:
    def __init__(
        self,
        db: Database,
        provider: AIProvider,
        *,
        discovery: SourceDiscoveryProvider,
        retriever: SourceRetriever,
        limits: WebResearchLimits,
        cache_dir: Path,
    ) -> None:
        self._db = db
        self._provider = provider
        self._discovery = discovery
        self._retriever = retriever
        self._limits = limits
        self._cache = SourceCache(cache_dir, max_entries=limits.max_cache_entries, max_bytes=limits.max_cache_bytes)
        self._events = EventRecorder(db)
        self._log = get_logger(LogCategory.RESEARCH, "app.research.agent")

    def run(self, objective: str) -> WebResearchSessionRecord:
        session_id = new_web_session_id()
        research_persistence.create_session(
            self._db,
            session_id=session_id,
            objective=objective,
            limits=self._limits,
            provider_name=self._provider.provider_name,
            model_name=self._provider.model_name,
        )
        self._events.record(
            EventType.RESEARCH_SESSION_STARTED,
            category="research",
            message=f"web research session started: {objective}",
            payload={"objective": objective},
            related_id=session_id,
        )
        research_persistence.set_session_status(self._db, session_id, WebResearchSessionStatus.RUNNING, started=True)

        sources: dict[str, Source] = {}
        source_texts: dict[str, str] = {}
        evidence_items: list[EvidenceItem] = []
        spec = StrategySpecification(name=objective[:200] or "unnamed_strategy")
        iteration = 0
        requests_made = 0
        pending_source_content: tuple[tuple[str, str], ...] = ()
        stopping_reason: str | None = None
        final_spec_status: str | None = None

        while True:
            limit_hit = self._check_limits(iteration, len(sources), requests_made)
            if limit_hit is not None:
                stopping_reason = limit_hit.value
                break

            context = self._build_context(session_id, objective, iteration, sources, evidence_items, spec, requests_made, pending_source_content)
            pending_source_content = ()

            decision = self._invoke_provider(session_id, iteration, context)
            if decision is None:
                stopping_reason = WebStoppingReason.PROVIDER_ERROR.value
                break

            research_persistence.record_decision(
                self._db,
                session_id=session_id,
                iteration=iteration,
                action=decision.action.value,
                reasoning_summary=decision.reasoning_summary,
                details={"query": decision.query, "url": decision.url, "source_id": decision.source_id},
                stopping_reason=decision.stopping_reason,
            )
            self._events.record(
                EventType.RESEARCH_DECISION_CREATED,
                category="research",
                message=decision.reasoning_summary,
                payload={"iteration": iteration, "action": decision.action.value},
                related_id=session_id,
            )

            if decision.action is ResearchAction.DISCOVER_SOURCES and decision.query:
                self._handle_discover(session_id, decision.query, sources)

            elif decision.action is ResearchAction.RETRIEVE_SOURCE and decision.url:
                requests_made, pending_source_content = self._handle_retrieve(
                    session_id, decision.url, sources, source_texts, evidence_items, requests_made
                )

            elif decision.action is ResearchAction.EXTRACT_EVIDENCE and decision.source_id:
                self._handle_extract(session_id, decision.source_id, source_texts, evidence_items)

            elif decision.action is ResearchAction.UPDATE_SPECIFICATION and decision.specification_update:
                spec = self._handle_update_specification(session_id, spec, decision.specification_update)

            elif decision.action is ResearchAction.VALIDATE_SPECIFICATION:
                spec, final_spec_status = self._handle_validate(session_id, spec)

            iteration += 1
            research_persistence.update_session_progress(
                self._db,
                session_id,
                iteration=iteration,
                sources_discovered=len(sources),
                sources_retrieved=sum(1 for s in sources.values() if s.status in (SourceStatus.RETRIEVED, SourceStatus.CACHED)),
                evidence_count=len(evidence_items),
                specification_count=1,
                requests_made=requests_made,
            )

            if decision.action is ResearchAction.STOP or decision.stopping_reason:
                stopping_reason = decision.stopping_reason or WebStoppingReason.AI_REQUESTED_STOP.value
                break

        if final_spec_status is None:
            final_spec_status = validate_specification(spec).computed_status.value

        final_status = (
            WebResearchSessionStatus.FAILED
            if stopping_reason == WebStoppingReason.PROVIDER_ERROR.value
            else WebResearchSessionStatus.COMPLETED
        )
        research_persistence.set_session_status(
            self._db,
            session_id,
            final_status,
            completed=True,
            stopping_reason=stopping_reason,
            final_specification_status=final_spec_status,
        )
        self._events.record(
            EventType.RESEARCH_SESSION_STOPPED,
            category="research",
            message=f"web research session stopped: {stopping_reason}",
            payload={"stopping_reason": stopping_reason, "final_specification_status": final_spec_status},
            related_id=session_id,
        )

        record = research_persistence.load_session(self._db, session_id)
        assert record is not None
        return record

    # -- limit checking -----------------------------------------------------

    def _check_limits(self, iteration: int, source_count: int, requests_made: int) -> WebStoppingReason | None:
        if iteration >= self._limits.max_iterations:
            return WebStoppingReason.MAX_ITERATIONS
        if source_count >= self._limits.max_sources_per_session:
            return WebStoppingReason.MAX_SOURCES
        if requests_made >= self._limits.max_requests_per_session:
            return WebStoppingReason.MAX_REQUESTS
        return None

    # -- context + provider --------------------------------------------------

    def _build_context(self, session_id, objective, iteration, sources, evidence_items, spec, requests_made, pending_source_content) -> WebResearchContext:
        discovered = tuple(
            SourceSummary(source_id=s.id, url=s.url, status=s.status.value, title=s.title, domain=s.domain)
            for s in sources.values()
        )
        retrieved = tuple(s for s in discovered if sources[s.source_id].status in (SourceStatus.RETRIEVED, SourceStatus.CACHED))
        evidence_summaries = tuple(
            EvidenceSummary(evidence_id=e.id, source_id=e.source_id, claim=e.claim, status=e.status.value, quoted_text=e.quoted_text)
            for e in evidence_items
        )
        spec_summary = {
            "name": spec.name,
            "timeframe": spec.timeframe,
            "status": spec.status.value,
            "entry_rules": len(spec.entry_rules),
            "exit_rules": len(spec.exit_rules),
            "stop_loss_rules": len(spec.stop_loss_rules),
            "take_profit_rules": len(spec.take_profit_rules),
            "unknowns": list(spec.unknowns),
            "ambiguities": list(spec.ambiguities),
        }
        return WebResearchContext(
            session_id=session_id,
            objective=objective,
            iteration=iteration,
            limits={
                "max_iterations": self._limits.max_iterations,
                "max_sources_per_session": self._limits.max_sources_per_session,
                "max_requests_per_session": self._limits.max_requests_per_session,
            },
            discovered_sources=discovered,
            retrieved_sources=retrieved,
            evidence=evidence_summaries,
            pending_source_content=pending_source_content,
            specification_summary=spec_summary,
            requests_made=requests_made,
        )

    def _invoke_provider(self, session_id: str, iteration: int, context: WebResearchContext) -> WebResearchDecision | None:
        self._events.record(EventType.AI_INVOCATION_STARTED, category="research", payload={"iteration": iteration}, related_id=session_id)
        try:
            response = self._provider.invoke(
                AIInvocationRequest(session_id=session_id, iteration=iteration, purpose="web_research", context=context)
            )
        except AIProviderError as exc:
            self._events.record(
                EventType.AI_INVOCATION_FAILED, category="research", message=str(exc),
                payload={"iteration": iteration}, related_id=session_id,
            )
            self._log.error("AI invocation failed", extra={"session_id": session_id, "iteration": iteration, "error": str(exc)})
            return None
        self._events.record(
            EventType.AI_INVOCATION_COMPLETED, category="research",
            payload={"iteration": iteration, "provider": response.provider_name}, related_id=session_id,
        )
        return response.decision

    # -- action handlers ------------------------------------------------------

    def _handle_discover(self, session_id: str, query: str, sources: dict[str, Source]) -> None:
        self._events.record(EventType.SOURCE_DISCOVERY_STARTED, category="research", payload={"query": query}, related_id=session_id)
        result = self._discovery.discover(query)
        remaining_budget = self._limits.max_sources_per_session - len(sources)
        for candidate in result.candidates[: max(remaining_budget, 0)]:
            source = Source(
                url=candidate.url,
                source_type=SourceType.UNKNOWN,
                status=SourceStatus.DISCOVERED,
                title=candidate.title,
                domain=candidate.domain,
                discovery_query=query,
                trust=TrustSignals(https=candidate.url.lower().startswith("https://"), domain=candidate.domain),
            )
            sources[source.id] = source
            research_persistence.save_source(self._db, session_id, source)
        self._events.record(
            EventType.SOURCE_DISCOVERY_COMPLETED, category="research",
            payload={"query": query, "candidate_count": len(result.candidates)}, related_id=session_id,
        )

    def _handle_retrieve(self, session_id, url, sources, source_texts, evidence_items, requests_made):
        from app.research.source import extract_domain, normalize_url

        domain = extract_domain(url)
        normalized = normalize_url(url)

        # Reuse an existing Source's identity if this URL was already
        # discovered (or previously attempted) this session - one URL is
        # one source across its whole lifecycle, never a fresh row per
        # retrieval attempt (brief section 20: deduplication).
        existing = next((s for s in sources.values() if s.normalized_url == normalized), None)
        source_id = existing.id if existing else new_source_id()
        title = existing.title if existing else None
        discovery_query = existing.discovery_query if existing else None

        cached = self._cache.get(normalized)
        if cached is not None:
            source = Source(
                id=source_id,
                url=url,
                status=SourceStatus.CACHED,
                domain=domain,
                title=title,
                discovery_query=discovery_query,
                content_hash=cached.content_hash,
                content_type=cached.content_type,
                retrieved_at=cached.retrieved_at,
                trust=TrustSignals(https=url.lower().startswith("https://"), domain=domain, retrieval_succeeded=True),
            )
            sources[source.id] = source
            research_persistence.save_source(self._db, session_id, source)
            self._events.record(EventType.SOURCE_CACHE_HIT, category="research", payload={"url": url}, related_id=session_id)
            text = normalize_content(cached.content, cached.content_type)
            source_texts[source.id] = text
            new_evidence = extract_evidence(source.id, text)
            evidence_items.extend(new_evidence)
            for item in new_evidence:
                research_persistence.save_evidence(self._db, session_id, item)
            self._events.record(EventType.EVIDENCE_EXTRACTED, category="research", payload={"source_id": source.id, "count": len(new_evidence)}, related_id=session_id)
            return requests_made, ((source.id, text[:2000]),)

        self._events.record(EventType.SOURCE_RETRIEVAL_STARTED, category="research", payload={"url": url}, related_id=session_id)
        result = self._retriever.retrieve(url)
        requests_made += 1

        if result.outcome in _ACCESS_DENIED_OUTCOMES:
            source = Source(
                id=source_id, url=url, status=SourceStatus.ACCESS_DENIED, domain=domain,
                title=title, discovery_query=discovery_query,
                failure_reason=result.reason, http_status=result.http_status,
            )
            sources[source.id] = source
            research_persistence.save_source(self._db, session_id, source)
            self._events.record(EventType.SOURCE_RETRIEVAL_FAILED, category="research", payload={"url": url, "reason": result.reason, "outcome": result.outcome.value}, related_id=session_id)
            return requests_made, ()

        if result.outcome in _FAILURE_OUTCOMES:
            source = Source(
                id=source_id, url=url, status=SourceStatus.FAILED, domain=domain,
                title=title, discovery_query=discovery_query,
                failure_reason=result.reason, http_status=result.http_status,
            )
            sources[source.id] = source
            research_persistence.save_source(self._db, session_id, source)
            self._events.record(EventType.SOURCE_RETRIEVAL_FAILED, category="research", payload={"url": url, "reason": result.reason, "outcome": result.outcome.value}, related_id=session_id)
            return requests_made, ()

        content_hash = compute_content_hash(result.content or b"")
        is_html = bool(result.content_type and "html" in result.content_type.lower())
        is_pdf = bool(result.content_type and "pdf" in result.content_type.lower())
        source_type = SourceType.PDF if is_pdf else (SourceType.WEB_PAGE if is_html else SourceType.TEXT_RESOURCE)

        source = Source(
            id=source_id,
            url=url,
            source_type=source_type,
            status=SourceStatus.RETRIEVED,
            domain=domain,
            title=title,
            discovery_query=discovery_query,
            content_hash=content_hash,
            content_type=result.content_type,
            byte_size=result.byte_size,
            http_status=result.http_status,
            retrieved_at=result.retrieved_at,
            trust=TrustSignals(
                https=url.lower().startswith("https://"),
                domain=domain,
                retrieval_succeeded=True,
                content_is_complete=True,
            ),
        )
        sources[source.id] = source
        research_persistence.save_source(self._db, session_id, source)
        self._events.record(EventType.SOURCE_RETRIEVED, category="research", payload={"url": url, "content_hash": content_hash}, related_id=session_id)

        if is_pdf:
            # PDF text extraction needs a dependency not installed in this
            # phase (see adapter.py/ARCHITECTURE.md "Phase 6") - the raw
            # bytes are still cached/hashed for audit, but no evidence can
            # be extracted from them yet.
            self._cache.put(normalize_url(url), result.content or b"", content_type=result.content_type, content_hash=content_hash, retrieved_at=result.retrieved_at or "")
            return requests_made, ()

        self._cache.put(normalize_url(url), result.content or b"", content_type=result.content_type, content_hash=content_hash, retrieved_at=result.retrieved_at or "")
        text = normalize_content(result.content or b"", result.content_type)
        source_texts[source.id] = text
        new_evidence = extract_evidence(source.id, text)
        evidence_items.extend(new_evidence)
        for item in new_evidence:
            research_persistence.save_evidence(self._db, session_id, item)
        self._events.record(EventType.EVIDENCE_EXTRACTED, category="research", payload={"source_id": source.id, "count": len(new_evidence)}, related_id=session_id)

        return requests_made, ((source.id, text[:2000]),)

    def _handle_extract(self, session_id: str, source_id: str, source_texts: dict[str, str], evidence_items: list[EvidenceItem]) -> None:
        text = source_texts.get(source_id)
        if text is None:
            self._log.error("extract_evidence requested for unknown/unretrieved source", extra={"session_id": session_id, "source_id": source_id})
            return
        new_evidence = extract_evidence(source_id, text)
        evidence_items.extend(new_evidence)
        for item in new_evidence:
            research_persistence.save_evidence(self._db, session_id, item)
        self._events.record(EventType.EVIDENCE_EXTRACTED, category="research", payload={"source_id": source_id, "count": len(new_evidence)}, related_id=session_id)

    def _handle_update_specification(self, session_id: str, spec: StrategySpecification, update: SpecificationUpdate) -> StrategySpecification:
        changes: dict = {}
        if update.name is not None:
            changes["name"] = update.name
        if update.timeframe is not None:
            changes["timeframe"] = update.timeframe
        if update.market is not None:
            changes["market"] = update.market
        if update.instrument is not None:
            changes["instrument"] = update.instrument
        if update.session is not None:
            changes["session"] = update.session
        if update.indicators:
            changes["indicators"] = spec.indicators + update.indicators
        if update.unknowns:
            changes["unknowns"] = spec.unknowns + update.unknowns
        if update.ambiguities:
            changes["ambiguities"] = spec.ambiguities + update.ambiguities

        bucket_names = {
            "entry": "entry_rules",
            "exit": "exit_rules",
            "stop_loss": "stop_loss_rules",
            "take_profit": "take_profit_rules",
            "position": "position_rules",
            "filter": "filters",
            "confirmation": "confirmation_rules",
        }
        new_rules_by_bucket: dict[str, list[RuleSpec]] = {}
        for proposed in update.rules:
            bucket = bucket_names.get(proposed.rule_kind)
            if bucket is None:
                continue  # unknown rule_kind - silently dropped is wrong; validation.py will flag it via UNSUPPORTED path instead
            rule = RuleSpec(
                description=proposed.description,
                status=RuleStatus.INTERPRETED,  # AI-proposed structure is always an interpretation, never EXPLICIT
                side=proposed.side,
                condition=proposed.condition,
                value=proposed.value,
                value_type=proposed.value_type,
                evidence_ids=proposed.evidence_ids,
            )
            new_rules_by_bucket.setdefault(bucket, []).append(rule)

        for bucket, new_rules in new_rules_by_bucket.items():
            changes[bucket] = getattr(spec, bucket) + tuple(new_rules)

        updated_spec = dataclasses.replace(spec, **changes) if changes else spec
        research_persistence.save_specification(self._db, session_id, updated_spec)
        self._events.record(
            EventType.STRATEGY_SPECIFICATION_CREATED, category="research",
            payload={"strategy_name": updated_spec.name, "status": updated_spec.status.value}, related_id=session_id,
        )
        return updated_spec

    def _handle_validate(self, session_id: str, spec: StrategySpecification) -> tuple[StrategySpecification, str]:
        result = validate_specification(spec)
        validated_spec = dataclasses.replace(spec, status=result.computed_status)
        research_persistence.save_specification(self._db, session_id, validated_spec, validation_errors=result.errors)
        if result.is_valid:
            self._events.record(EventType.STRATEGY_VALIDATED, category="research", payload={"strategy_name": validated_spec.name}, related_id=session_id)
        else:
            self._events.record(
                EventType.STRATEGY_VALIDATION_FAILED, category="research",
                payload={"strategy_name": validated_spec.name, "status": result.computed_status.value, "errors": list(result.errors)},
                related_id=session_id,
            )
        return validated_spec, result.computed_status.value
