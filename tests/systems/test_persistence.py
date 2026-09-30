from app.backtesting.market_data import Timeframe
from app.database.connection import Database
from app.database.schema import CURRENT_SCHEMA_VERSION
from app.systems import persistence
from app.systems.campaign import CampaignStatus, new_campaign_id
from app.systems.experiment import ExperimentStatus, new_experiment_id


def test_migration_3_creates_research_tables(database: Database) -> None:
    assert CURRENT_SCHEMA_VERSION >= 3
    versions = {row["version"] for row in database.query_all("SELECT version FROM schema_migrations")}
    assert 3 in versions

    tables = {row["name"] for row in database.query_all("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"research_campaigns", "research_experiments"}.issubset(tables)


def test_create_and_load_campaign(database: Database) -> None:
    campaign_id = new_campaign_id()
    persistence.create_campaign(
        database,
        campaign_id=campaign_id,
        strategy_name="fixed_trade",
        research_system="parameter_explorer",
        purpose="sweep qty",
        configuration={"space": {"qty": [1, 2]}},
    )
    record = persistence.load_campaign(database, campaign_id)
    assert record is not None
    assert record.status is CampaignStatus.CREATED
    assert record.research_system == "parameter_explorer"
    assert record.configuration == {"space": {"qty": [1, 2]}}
    assert record.experiment_count == 0


def test_set_campaign_status_records_timestamps(database: Database) -> None:
    campaign_id = new_campaign_id()
    persistence.create_campaign(
        database, campaign_id=campaign_id, strategy_name=None, research_system="adversarial", purpose="p", configuration={}
    )
    persistence.set_campaign_status(database, campaign_id, CampaignStatus.RUNNING, started=True)
    record = persistence.load_campaign(database, campaign_id)
    assert record.status is CampaignStatus.RUNNING
    assert record.started_at is not None
    assert record.completed_at is None

    persistence.set_campaign_status(database, campaign_id, CampaignStatus.COMPLETED, completed=True)
    record = persistence.load_campaign(database, campaign_id)
    assert record.status is CampaignStatus.COMPLETED
    assert record.completed_at is not None


def test_refresh_campaign_counts_reflects_experiment_statuses(database: Database) -> None:
    campaign_id = new_campaign_id()
    persistence.create_campaign(
        database, campaign_id=campaign_id, strategy_name=None, research_system="x", purpose="p", configuration={}
    )
    for status in (ExperimentStatus.COMPLETED, ExperimentStatus.COMPLETED, ExperimentStatus.FAILED):
        exp_id = new_experiment_id()
        persistence.create_experiment(
            database,
            experiment_id=exp_id,
            campaign_id=campaign_id,
            research_system="x",
            strategy_name="s",
            strategy_version="1",
            parameters={},
            rule_configuration={},
            execution_configuration={},
            data_identity="d",
            timeframe=Timeframe.M1,
            data_start=None,
            data_end=None,
            parent_experiment_id=None,
            fingerprint=f"fp-{exp_id}",
        )
        persistence.set_experiment_status(database, exp_id, status, completed=True)

    persistence.refresh_campaign_counts(database, campaign_id)
    record = persistence.load_campaign(database, campaign_id)
    assert record.experiment_count == 3
    assert record.completed_count == 2
    assert record.failed_count == 1


def test_create_and_load_experiment_round_trip(database: Database) -> None:
    exp_id = new_experiment_id()
    persistence.create_experiment(
        database,
        experiment_id=exp_id,
        campaign_id=None,
        research_system="parameter_explorer",
        strategy_name="fixed_trade",
        strategy_version="2",
        parameters={"qty": 1.5},
        rule_configuration={"variant_name": "a"},
        execution_configuration={"fee_model": {"type": "ZeroFeeModel"}},
        data_identity="abc123",
        timeframe=Timeframe.M5,
        data_start=None,
        data_end=None,
        parent_experiment_id=None,
        fingerprint="fp-1",
    )
    record = persistence.load_experiment(database, exp_id)
    assert record.status is ExperimentStatus.CREATED
    assert record.parameters == {"qty": 1.5}
    assert record.rule_configuration == {"variant_name": "a"}
    assert record.timeframe == "5m"
    assert record.fingerprint == "fp-1"


def _insert_dummy_backtest_run(database: Database, run_id: str) -> None:
    # research_experiments.backtest_run_id is a real FK into experiments(id)
    # (Phase 2's table), so tests that set it must satisfy the constraint.
    database.execute(
        "INSERT INTO experiments (id, system_name, status) VALUES (?, 'test', 'completed')", (run_id,)
    )


def test_find_completed_by_fingerprint_ignores_non_completed(database: Database) -> None:
    _insert_dummy_backtest_run(database, "run-1")
    exp_id = new_experiment_id()
    persistence.create_experiment(
        database,
        experiment_id=exp_id,
        campaign_id=None,
        research_system="x",
        strategy_name="s",
        strategy_version="1",
        parameters={},
        rule_configuration={},
        execution_configuration={},
        data_identity="d",
        timeframe=Timeframe.M1,
        data_start=None,
        data_end=None,
        parent_experiment_id=None,
        fingerprint="shared-fp",
    )
    assert persistence.find_completed_by_fingerprint(database, "shared-fp") is None  # still CREATED

    persistence.set_experiment_status(database, exp_id, ExperimentStatus.COMPLETED, completed=True, backtest_run_id="run-1")
    found = persistence.find_completed_by_fingerprint(database, "shared-fp")
    assert found is not None
    assert found.id == exp_id
    assert found.backtest_run_id == "run-1"


def test_find_completed_by_fingerprint_excludes_duplicates_themselves(database: Database) -> None:
    _insert_dummy_backtest_run(database, "run-1")
    original_id = new_experiment_id()
    persistence.create_experiment(
        database, experiment_id=original_id, campaign_id=None, research_system="x", strategy_name="s",
        strategy_version="1", parameters={}, rule_configuration={}, execution_configuration={},
        data_identity="d", timeframe=Timeframe.M1, data_start=None, data_end=None,
        parent_experiment_id=None, fingerprint="shared-fp",
    )
    persistence.set_experiment_status(database, original_id, ExperimentStatus.COMPLETED, completed=True, backtest_run_id="run-1")

    duplicate_id = new_experiment_id()
    persistence.create_experiment(
        database, experiment_id=duplicate_id, campaign_id=None, research_system="x", strategy_name="s",
        strategy_version="1", parameters={}, rule_configuration={}, execution_configuration={},
        data_identity="d", timeframe=Timeframe.M1, data_start=None, data_end=None,
        parent_experiment_id=None, fingerprint="shared-fp",
    )
    persistence.set_experiment_status(
        database, duplicate_id, ExperimentStatus.COMPLETED, completed=True,
        backtest_run_id="run-1", duplicate_of_experiment_id=original_id,
    )

    # A third experiment with the same fingerprint must still resolve to
    # the ORIGINAL, not to the duplicate (no duplicate-of-duplicate chains).
    found = persistence.find_completed_by_fingerprint(database, "shared-fp")
    assert found.id == original_id
