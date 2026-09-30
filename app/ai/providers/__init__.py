"""AI provider implementations. `mock.py`'s `MockAIProvider` is the only
one this phase ships - see app/ai/provider.py's module docstring."""

from app.ai.providers.mock import MockAIProvider

__all__ = ["MockAIProvider"]
