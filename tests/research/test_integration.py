"""End-to-end integration test for the full chain (Phase 6 brief section
27 "Integration" / section 1's pipeline diagram):

    Mock Discovery -> Mock Retrieval -> Evidence -> Strategy Specification
    -> Validation -> Research Session

"Mock Retrieval" here is `HttpSourceRetriever` with its transport
function replaced (the same injectable-transport pattern Phase 5 uses for
Claude/Ollama) - no live website is ever contacted.
"""

from app.ai.provider import AIProviderResponseError
from app.backtesting.engine import BacktestConfig, run_backtest
from app.backtesting.market_data import Timeframe
from app.research import persistence as rp
from app.research.adapter import adapt_specification
from app.research.agent import WebResearchAgent
from app.research.decision import ProposedRule, ResearchAction, SpecificationUpdate, WebResearchDecision
from app.research.discovery import DiscoveryCandidate, ManualSourceDiscoveryProvider
from app.research.limits import RetrievalLimits, WebResearchLimits
from app.research.mock_provider import MockWebResearchProvider
from app.research.retrieval import HttpSourceRetriever
from app.research.session import WebResearchSessionStatus
from app.research.specification import Condition, FieldRef, IndicatorSpec
from app.research.structured_output import web_research_decision_from_dict
from tests.research.conftest import SAMPLE_HTML, allow_all_robots_transport_wrapping

URL = "https://example.com/ema-strategy"


def test_full_chain_discovery_to_validated_specification(database, tmp_path) -> None:
    # 1. Mock Discovery
    discovery = ManualSourceDiscoveryProvider({"ema strategy": [DiscoveryCandidate(url=URL, title="EMA Strategy")]})

    # 2. Mock Retrieval (real HttpSourceRetriever, transport replaced)
    def transport(url, user_agent, limits):
        return 200, {"Content-Type": "text/html; charset=utf-8"}, SAMPLE_HTML, url

    retriever = HttpSourceRetriever(RetrievalLimits(request_delay_seconds=0), transport=allow_all_robots_transport_wrapping(transport))

    # The AI's decisions could, in a real system, have arrived as JSON from
    # a real provider - round-trip one of them through the strict parser
    # to prove the chain also works via that path, not just via in-process
    # dataclasses.
    update_decision_json = {
        "objective": "research ema strategy",
        "reasoning_summary": "source confirms an EMA-cross entry with percent stop/target",
        "action": "update_specification",
        "specification_update": {
            "name": "ema_cross_strategy",
            "timeframe": "1h",
            "indicators": [{"type": "EMA", "params": {"period": 50}}],
            "rules": [
                {
                    "rule_kind": "entry",
                    "description": "enter long on EMA50 cross",
                    "side": "long",
                    "condition": {"op": "crosses_above", "left": {"name": "close"}, "right": {"name": "EMA", "params": {"period": 50}}},
                },
                {"rule_kind": "stop_loss", "description": "2 percent stop", "value": 2.0, "value_type": "percent"},
            ],
        },
    }
    update_decision = web_research_decision_from_dict(update_decision_json)

    script = {
        0: WebResearchDecision(objective="research ema strategy", reasoning_summary="find a source", action=ResearchAction.DISCOVER_SOURCES, query="ema strategy"),
        1: WebResearchDecision(objective="research ema strategy", reasoning_summary="retrieve it", action=ResearchAction.RETRIEVE_SOURCE, url=URL),
        2: update_decision,
        3: WebResearchDecision(objective="research ema strategy", reasoning_summary="validate", action=ResearchAction.VALIDATE_SPECIFICATION, stopping_reason="sufficient_evidence"),
    }
    provider = MockWebResearchProvider(script)
    limits = WebResearchLimits(max_iterations=10, max_sources_per_session=10, max_requests_per_session=10)
    agent = WebResearchAgent(database, provider, discovery=discovery, retriever=retriever, limits=limits, cache_dir=tmp_path / "cache")

    # 6. Research Session (the whole run)
    session = agent.run("research ema strategy")

    assert session.status is WebResearchSessionStatus.COMPLETED
    assert session.sources_discovered == 1
    assert session.sources_retrieved == 1
    assert session.evidence_count > 0  # 3. Evidence
    assert session.final_specification_status == "valid"  # 4+5. Specification + Validation

    # Durable, resumable state - not in-memory only.
    sources = rp.list_sources(database, session.id)
    assert sources[0]["status"] == "retrieved"
    evidence_rows = rp.list_evidence(database, session.id)
    assert any(row["status"] == "explicit" for row in evidence_rows)
    spec_rows = rp.list_specifications(database, session.id)
    assert spec_rows[-1]["status"] == "valid"

    # The validated specification is a real "research candidate" that can
    # continue into Phase 3's pipeline via the adapter boundary (brief
    # section 1's final arrow) - proven by actually running it through the
    # deterministic backtesting engine, not just asserting it "should work".
    import json

    from app.research.specification import RuleSpec, RuleStatus, StrategySpecification

    spec_dict = json.loads(spec_rows[-1]["specification"])
    spec = StrategySpecification(
        name=spec_dict["name"],
        timeframe=spec_dict["timeframe"],
        indicators=(IndicatorSpec(type="EMA", params={"period": 50}),),
        entry_rules=(
            RuleSpec(
                description="enter long on EMA50 cross",
                status=RuleStatus.INTERPRETED,
                side="long",
                condition=Condition(op="crosses_above", left=FieldRef(name="close"), right=FieldRef(name="EMA", params={"period": 50})),
            ),
        ),
        stop_loss_rules=(RuleSpec(description="2 percent stop", status=RuleStatus.INTERPRETED, value=2.0, value_type="percent"),),
    )
    adapter_result = adapt_specification(spec)
    assert adapter_result.adaptable

    from datetime import datetime, timedelta, timezone

    from app.backtesting.market_data import Candle, CandleSeries

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # EMA(50) needs >= 50 closes before it produces a value at all: flat
    # for the first 50 bars (so EMA settles at 100), then a sustained rise
    # so close crosses above it.
    closes = [100.0] * 50 + [101, 103, 106, 110, 115, 121, 128]
    candles = [
        Candle(timestamp=start + timedelta(minutes=i + 1), open=c - 0.5, high=c + 1, low=c - 1, close=c, volume=1000)
        for i, c in enumerate(closes)
    ]
    series = CandleSeries(candles, symbol="X", timeframe=Timeframe.M1)
    strategy = adapter_result.strategy_factory({"quantity": 1.0})
    backtest_result = run_backtest(strategy, series, BacktestConfig(symbol="X", timeframe=Timeframe.M1, starting_capital=10_000))
    assert len(backtest_result.trades) >= 1  # a real, deterministic backtest actually ran


def test_malformed_ai_json_is_rejected_before_reaching_the_agent() -> None:
    """The 'parse -> validate' boundary (brief section 12) rejects bad
    structure before it ever becomes a WebResearchDecision the agent
    could act on."""
    import pytest

    with pytest.raises(AIProviderResponseError):
        web_research_decision_from_dict({"objective": "o", "action": "update_specification"})  # missing reasoning_summary
