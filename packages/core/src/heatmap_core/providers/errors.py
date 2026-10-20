"""Provider error taxonomy. The router decides what to do based on the type."""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for provider failures."""


class RateLimitedError(ProviderError):
    """Short-term rate limit hit; the key is benched for ``retry_after`` or its cooldown."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class QuotaExceededError(ProviderError):
    """Daily/monthly allowance used up; the key is benched until the next UTC day."""


class AuthError(ProviderError):
    """Key is invalid or revoked; the key is disabled for the rest of the process."""


class TransientProviderError(ProviderError):
    """Timeouts, 5xx and malformed responses; retried with backoff."""


class UnsupportedError(ProviderError):
    """The provider cannot serve this chain or request; try another provider."""


class AllProvidersExhaustedError(ProviderError):
    """No configured key on any provider can serve the request right now."""
