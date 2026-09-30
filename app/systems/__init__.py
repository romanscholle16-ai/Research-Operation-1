"""Five independent research systems, sharing common experiment/campaign
infrastructure. None of them calculate financial performance - they
build `ExperimentDefinition`s that `ExperimentRunner`/`CampaignRunner`
send through `app.backtesting.run_backtest()`, the sole source of truth
for P&L, fees, slippage, drawdown, expectancy, and profit factor.
"""

from app.systems.base import ResearchRequest, ResearchSystem
from app.systems.campaign import CampaignRecord, CampaignStatus, new_campaign_id
from app.systems.experiment import ExperimentDefinition, ExperimentRecord, ExperimentStatus, new_experiment_id
from app.systems.fingerprint import compute_experiment_fingerprint
from app.systems.parameter_space import Categorical, Fixed, ParameterSpace, ValueList, ValueRange
from app.systems.runner import CampaignRunner, ExperimentRunner

__all__ = [
    "CampaignRecord",
    "CampaignRunner",
    "CampaignStatus",
    "Categorical",
    "ExperimentDefinition",
    "ExperimentRecord",
    "ExperimentRunner",
    "ExperimentStatus",
    "Fixed",
    "ParameterSpace",
    "ResearchRequest",
    "ResearchSystem",
    "ValueList",
    "ValueRange",
    "compute_experiment_fingerprint",
    "new_campaign_id",
    "new_experiment_id",
]
