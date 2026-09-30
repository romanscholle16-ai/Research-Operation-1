"""Parameter Explorer: tests different values of configurable strategy
parameters (indicator periods, thresholds, stop/target distances, ...).
Generic - never hardcodes a particular strategy."""

from app.systems.parameter_explorer.explorer import ParameterExplorer, ParameterExplorerRequest

__all__ = ["ParameterExplorer", "ParameterExplorerRequest"]
