import logging
import random
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class GeminiHTTPError(RuntimeError):
    pass


RETRIABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
RETRY_SAFETY_BUFFER_SECONDS = 1.0


def post_json_with_retries(
    *,
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    json_body: dict[str, Any],
    operation: str,
    max_retries: int,
    max_retry_delay_seconds: float,
) -> httpx.Response:
    """POST JSON to Gemini and honor provider-requested retry delays.

    Retries transient network failures and HTTP 408/429/5xx responses.
    For quota errors, prefers Gemini's Retry-After / RetryInfo / "retry in Xs"
    delay instead of retrying too early.
    """
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = client.post(
                url,
                headers=headers,
                json=json_body,
            )
            last_error = None
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            last_error = exc
            if attempt >= max_retries:
                raise GeminiHTTPError(
                    f"{operation} network request failed after "
                    f"{attempt + 1} attempt(s): {type(exc).__name__}"
                ) from exc

            delay = _fallback_delay(attempt)
            _sleep(delay, operation, type(exc).__name__, attempt, max_retries)
            continue

        if response.status_code in RETRIABLE_STATUS_CODES:
            if attempt >= max_retries:
                raise GeminiHTTPError(
                    _http_error_message(response, operation, attempt + 1)
                )

            delay = _retry_delay_from_response(
                response,
                attempt,
                max_retry_delay_seconds,
            )
            _sleep(
                delay,
                operation,
                f"HTTP {response.status_code}",
                attempt,
                max_retries,
            )
            continue

        if not response.is_success:
            raise GeminiHTTPError(
                _http_error_message(response, operation, attempt + 1)
            )

        return response

    if last_error is not None:
        raise GeminiHTTPError(
            f"{operation} failed before receiving a response"
        ) from last_error

    raise GeminiHTTPError(f"{operation} failed before receiving a response")


def _retry_delay_from_response(
    response: httpx.Response,
    attempt: int,
    max_retry_delay_seconds: float,
) -> float:
    retry_after = _parse_retry_after(response.headers.get("retry-after"))
    if retry_after is not None:
        return _bounded_delay(retry_after, max_retry_delay_seconds)

    try:
        payload = response.json()
    except (ValueError, TypeError):
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")

        if isinstance(error, dict):
            details = error.get("details")

            if isinstance(details, list):
                for detail in details:
                    if not isinstance(detail, dict):
                        continue

                    retry_delay = detail.get("retryDelay")
                    parsed = _parse_duration_seconds(retry_delay)

                    if parsed is not None:
                        return _bounded_delay(
                            parsed,
                            max_retry_delay_seconds,
                        )

            message = error.get("message")

            if isinstance(message, str):
                parsed = _parse_retry_delay_from_text(message)
                if parsed is not None:
                    return _bounded_delay(
                        parsed,
                        max_retry_delay_seconds,
                    )

    parsed = _parse_retry_delay_from_text(response.text)
    if parsed is not None:
        return _bounded_delay(parsed, max_retry_delay_seconds)

    if response.status_code == 429:
        return min(
            60.0 + random.uniform(0.5, 1.5),
            max_retry_delay_seconds,
        )

    return _fallback_delay(attempt)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None

    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None

    return seconds if seconds >= 0 else None


def _parse_duration_seconds(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        seconds = float(value)
        return seconds if seconds >= 0 else None

    if not isinstance(value, str):
        return None

    match = re.fullmatch(
        r"([0-9]+(?:\.[0-9]+)?)s",
        value.strip(),
    )

    if not match:
        return None

    try:
        seconds = float(match.group(1))
    except ValueError:
        return None

    return seconds if seconds >= 0 else None


def _parse_retry_delay_from_text(text: str | None) -> float | None:
    if not text:
        return None

    match = re.search(
        r"retry\s+in\s+([0-9]+(?:\.[0-9]+)?)s",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    try:
        seconds = float(match.group(1))
    except ValueError:
        return None

    return seconds if seconds >= 0 else None


def _bounded_delay(
    seconds: float,
    max_retry_delay_seconds: float,
) -> float:
    return max(
        0.5,
        min(
            seconds + RETRY_SAFETY_BUFFER_SECONDS,
            max_retry_delay_seconds,
        ),
    )


def _fallback_delay(attempt: int) -> float:
    return min(
        (2**attempt) + random.uniform(0.0, 0.5),
        8.0,
    )


def _sleep(
    delay: float,
    operation: str,
    reason: str,
    attempt: int,
    max_retries: int,
) -> None:
    logger.warning(
        "%s: retrying in %.2fs after %s (attempt %s/%s)",
        operation,
        delay,
        reason,
        attempt + 1,
        max_retries + 1,
    )
    time.sleep(delay)


def _http_error_message(
    response: httpx.Response,
    operation: str,
    attempts: int,
) -> str:
    try:
        body = response.text.strip()
    except Exception:
        body = "<unreadable response body>"

    if not body:
        body = "<empty response body>"
    elif len(body) > 1200:
        body = body[:1200] + "..."

    return (
        f"{operation} failed with HTTP {response.status_code} "
        f"after {attempts} attempt(s): {body}"
    )
