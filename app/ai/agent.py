"""`ResearchAgent` - the iterative loop from the Phase 4 brief section 7:

    Objective -> Hypothesis -> Experiment -> Backtest -> Result -> Analysis
    -> New Hypothesis -> Next Experiment (bounded by ResearchLimits)

The agent NEVER calls `app.backtesting.engine.run_backtest()` directly -
every experiment goes `ExperimentProposal` (from the AI) -> `validate_
proposal()` -> `proposal_to_experiment_definitions()` (Phase 3 systems,
unchanged) -> `CampaignRunner.run()` -> `ExperimentRunner.execute()` ->
`run_backtest()`. The AI only ever sees `ResearchContext` (bounded,
metrics-only) and only ever produces a `ResearchDecision` (typed,
validated); it never sees or writes raw trades, and it never touches
`ResearchLimits` (see limits.py's module docstring for why that alone is
what makes "the AI cannot expand its own research budget" true).
"""

from __future__ import annotations

from app.ai import persistence as ai_persistence
from app.ai.catalog import ResearchCatalog
from app.ai.context import build_research_context
from app.ai.limits import ResearchLimits, StoppingReason
from app.ai.provider import AIInvocationRequest, AIProvider, AIProviderError
from app.ai.session import ResearchSessionRecord, SessionStatus, new_session_id
from app.ai.translation import proposal_to_experiment_definitions
from app.ai.validation import validate_proposal
from app.core.events import EventRecorder, EventType
from app.database.connection import Database
from app.logging.setup import LogCategory, get_logger
from app.systems import persistence as systems_persistence
from app.systems.runner import CampaignRunner


class ResearchAgent:
    def __init__(self, db: Database, provider: AIProvider, catalog: ResearchCatalog, limits: ResearchLimits) -> None:
        self._db = db
        self._provider = provider
        self._catalog = catalog
        self._limits = limits
        self._events = EventRecorder(db)
        self._campaign_runner = CampaignRunner(db)
        self._log = get_logger(LogCategory.RESEARCH, "app.ai.agent")

    def run(self, objective: str) -> ResearchSessionRecord:
        session_id = new_session_id()
        ai_persistence.create_session(
            self._db,
            session_id=session_id,
            objective=objective,
            limits=self._limits,
            provider_name=self._provider.provider_name,
            model_name=self._provider.model_name,
        )
        self._events.record(
            EventType.AI_RESEARCH_STARTED,
            category="ai",
            message=f"research session started: {objective}",
            payload={"objective": objective},
            related_id=session_id,
        )
        ai_persistence.set_session_status(self._db, session_id, SessionStatus.RUNNING, started=True)
        self._log.info("research session started", extra={"session_id": session_id, "objective": objective})

        iteration = 0
        experiments_run = 0
        experiments_failed = 0
        consecutive_no_progress = 0
        previous_hypotheses: list[str] = []
        stopping_reason: str | None = None

        while True:
            limit_hit = self._check_limits(iteration, experiments_run, experiments_failed, consecutive_no_progress)
            if limit_hit is not None:
                stopping_reason = limit_hit.value
                break

            context = build_research_context(
                self._db,
                session_id=session_id,
                objective=objective,
                iteration=iteration,
                catalog=self._catalog,
                limits=self._limits,
                previous_hypotheses=previous_hypotheses,
                experiments_run=experiments_run,
                experiments_failed=experiments_failed,
                consecutive_no_progress=consecutive_no_progress,
            )

            decision = self._invoke_provider(session_id, iteration, context)
            if decision is None:
                stopping_reason = StoppingReason.PROVIDER_ERROR.value
                break

            ai_persistence.record_decision(self._db, session_id=session_id, iteration=iteration, decision=decision)
            self._events.record(
                EventType.RESEARCH_DECISION_CREATED,
                category="ai",
                message=decision.hypothesis,
                payload={"iteration": iteration, "requested_count": len(decision.requested_experiments)},
                related_id=session_id,
            )
            previous_hypotheses.append(decision.hypothesis)

            definitions, invalid_count = self._resolve_proposals(session_id, iteration, decision.requested_experiments)
            experiments_failed += invalid_count

            progressed = False
            if definitions:
                remaining_budget = self._limits.max_experiments - experiments_run
                if remaining_budget <= 0:
                    stopping_reason = StoppingReason.MAX_EXPERIMENTS.value
                    break
                definitions = definitions[:remaining_budget]

                systems_used = {p.research_system for p in decision.requested_experiments}
                research_system_label = systems_used.pop() if len(systems_used) == 1 else "ai_research_mixed"

                campaign = self._campaign_runner.run(
                    definitions,
                    research_system=research_system_label,
                    strategy_name=self._catalog.strategy_name,
                    purpose=f"AI research iteration {iteration}: {decision.hypothesis}"[:200],
                    configuration={"session_id": session_id, "iteration": iteration},
                )
                ai_persistence.link_campaign_to_session(
                    self._db, session_id=session_id, campaign_id=campaign.id, iteration=iteration
                )

                experiments_run += campaign.experiment_count
                experiments_failed += campaign.failed_count

                campaign_experiments = systems_persistence.list_experiments_for_campaign(self._db, campaign.id)
                progressed = any(
                    e.status.value == "completed" and e.duplicate_of_experiment_id is None
                    for e in campaign_experiments
                )

            consecutive_no_progress = 0 if progressed else consecutive_no_progress + 1

            self._events.record(
                EventType.RESEARCH_ANALYSIS_COMPLETED,
                category="ai",
                payload={"iteration": iteration, "progressed": progressed, "experiments_run": experiments_run},
                related_id=session_id,
            )

            iteration += 1
            ai_persistence.update_session_progress(
                self._db,
                session_id,
                iteration=iteration,
                experiments_run=experiments_run,
                experiments_failed=experiments_failed,
                consecutive_no_progress=consecutive_no_progress,
            )

            if decision.stopping_reason:
                stopping_reason = decision.stopping_reason
                break

        final_status = SessionStatus.FAILED if stopping_reason == StoppingReason.PROVIDER_ERROR.value else SessionStatus.COMPLETED
        ai_persistence.set_session_status(
            self._db, session_id, final_status, completed=True, stopping_reason=stopping_reason
        )
        self._events.record(
            EventType.AI_RESEARCH_STOPPED,
            category="ai",
            message=f"research session stopped: {stopping_reason}",
            payload={
                "stopping_reason": stopping_reason,
                "iterations": iteration,
                "experiments_run": experiments_run,
                "experiments_failed": experiments_failed,
            },
            related_id=session_id,
        )
        self._log.info(
            "research session stopped",
            extra={"session_id": session_id, "stopping_reason": stopping_reason, "iterations": iteration},
        )

        record = ai_persistence.load_session(self._db, session_id)
        assert record is not None
        return record

    def _check_limits(
        self, iteration: int, experiments_run: int, experiments_failed: int, consecutive_no_progress: int
    ) -> StoppingReason | None:
        if iteration >= self._limits.max_iterations:
            return StoppingReason.MAX_ITERATIONS
        if experiments_run >= self._limits.max_experiments:
            return StoppingReason.MAX_EXPERIMENTS
        if experiments_failed >= self._limits.max_failed_experiments:
            return StoppingReason.MAX_FAILED_EXPERIMENTS
        if consecutive_no_progress >= self._limits.max_consecutive_no_progress:
            return StoppingReason.MAX_CONSECUTIVE_NO_PROGRESS
        return None

    def _invoke_provider(self, session_id: str, iteration: int, context):
        self._events.record(
            EventType.AI_INVOCATION_STARTED, category="ai", payload={"iteration": iteration}, related_id=session_id
        )
        try:
            response = self._provider.invoke(
                AIInvocationRequest(session_id=session_id, iteration=iteration, purpose="propose_experiments", context=context)
            )
        except AIProviderError as exc:
            self._events.record(
                EventType.AI_INVOCATION_FAILED,
                category="ai",
                message=str(exc),
                payload={"iteration": iteration},
                related_id=session_id,
            )
            ai_persistence.record_ai_action(
                self._db,
                provider=self._provider.provider_name,
                action_type="propose_experiments",
                related_id=session_id,
                prompt_summary=context.summary(),
                result_summary=f"ERROR: {exc}",
            )
            self._log.error("AI invocation failed", extra={"session_id": session_id, "iteration": iteration, "error": str(exc)})
            return None

        self._events.record(
            EventType.AI_INVOCATION_COMPLETED,
            category="ai",
            payload={"iteration": iteration, "provider": response.provider_name},
            related_id=session_id,
        )
        ai_persistence.record_ai_action(
            self._db,
            provider=response.provider_name,
            action_type="propose_experiments",
            related_id=session_id,
            prompt_summary=context.summary(),
            result_summary=response.raw_summary[:2000],
            metadata={"model": response.model_name},
        )
        return response.decision

    def _resolve_proposals(self, session_id: str, iteration: int, proposals):
        definitions = []
        invalid_count = 0
        for proposal in proposals:
            errors = validate_proposal(proposal, self._catalog)
            if errors:
                invalid_count += 1
                self._log.error(
                    "AI experiment proposal rejected",
                    extra={"session_id": session_id, "iteration": iteration, "errors": errors},
                )
                continue
            try:
                new_definitions = proposal_to_experiment_definitions(proposal, self._catalog)
            except (KeyError, ValueError) as exc:
                invalid_count += 1
                self._log.error(
                    "AI experiment proposal failed translation",
                    extra={"session_id": session_id, "iteration": iteration, "error": str(exc)},
                )
                continue
            definitions.extend(new_definitions)
            self._events.record(
                EventType.RESEARCH_EXPERIMENT_REQUESTED,
                category="ai",
                payload={"research_system": proposal.research_system, "count": len(new_definitions)},
                related_id=session_id,
            )
        return definitions, invalid_count
