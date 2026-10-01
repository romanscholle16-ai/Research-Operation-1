"""AI provider implementations.

- `mock.py` - `MockAIProvider`/`AlwaysFailingAIProvider`: deterministic,
  no network, the only providers Phase 4's tests needed.
- `claude.py` - `ClaudeAIProvider`: real Anthropic Messages API adapter
  (stdlib HTTP, forced tool-use for structured output). Untested against
  the live API in this environment - no API key was available.
- `ollama.py` - `OllamaAIProvider`: real local-model adapter. Untested
  against a live server - Ollama is not installed by this project.
- `freebuff.py` - `FreebuffAIProvider`: structural placeholder only. See
  its module docstring - no verified API contract was available to
  implement against.

See app/ai/router.py for how a provider is selected by configuration.
"""

from app.ai.providers.claude import ClaudeAIProvider
from app.ai.providers.freebuff import FreebuffAIProvider
from app.ai.providers.mock import AlwaysFailingAIProvider, MockAIProvider
from app.ai.providers.ollama import OllamaAIProvider

__all__ = [
    "AlwaysFailingAIProvider",
    "ClaudeAIProvider",
    "FreebuffAIProvider",
    "MockAIProvider",
    "OllamaAIProvider",
]
