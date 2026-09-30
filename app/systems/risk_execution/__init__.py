"""Risk/Execution Optimizer: tests execution and risk assumptions (stop
models, sizing, fee/slippage assumptions, execution policy) rather than
strategy logic or parameters. Leverage/margin is out of scope - Phase 2
does not model it, and this phase does not extend Phase 2 to add it."""

from app.systems.risk_execution.optimizer import ExecutionVariant, RiskExecutionOptimizer, RiskExecutionRequest

__all__ = ["ExecutionVariant", "RiskExecutionOptimizer", "RiskExecutionRequest"]
