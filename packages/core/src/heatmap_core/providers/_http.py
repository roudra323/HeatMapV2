"""HTTP helpers that translate transport failures into provider errors."""

from __future__ import annotations

from typing import Any

import httpx

from heatmap_core.providers.errors import AuthError, RateLimitedError, TransientProviderError


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def send_json(client: httpx.Client, method: str, url: str, **kwargs: Any) -> Any:
    try:
        response = client.request(method, url, **kwargs)
    except httpx.TimeoutException as exc:
        raise TransientProviderError(f"timeout: {exc}") from exc
    except httpx.TransportError as exc:
        raise TransientProviderError(f"transport error: {exc}") from exc

    if response.status_code == 429:
        raise RateLimitedError("HTTP 429", retry_after=_retry_after(response))
    if response.status_code in (401, 403):
        raise AuthError(f"HTTP {response.status_code}: {response.text[:200]}")
    if response.status_code >= 500:
        raise TransientProviderError(f"HTTP {response.status_code}")
    if response.status_code >= 400:
        raise TransientProviderError(f"HTTP {response.status_code}: {response.text[:200]}")
    try:
        return response.json()
    except ValueError as exc:
        raise TransientProviderError("response is not JSON") from exc


def redact(url: str, secret: str) -> str:
    return url.replace(secret, "***") if secret else url
