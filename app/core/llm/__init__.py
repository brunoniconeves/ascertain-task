"""LLM integration layer.

This package is intentionally small and conservative:
- No prompt/output logging (may contain PHI).
- Configurable via environment variables.
- Treated as a pure/stateless function by callers.
"""


