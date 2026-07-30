"""Optional OpenTelemetry tracing support with a no-op fallback."""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterator

F = TypeVar("F", bound=Any)

logger = logging.getLogger(__name__)


class _NoopSpan:
    """Span stand-in when OpenTelemetry is not installed or disabled."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any, description: str | None = None) -> None:
        pass

    def record_exception(self, exception: BaseException) -> None:
        pass


class _NoopTracer:
    """Tracer stand-in when OpenTelemetry is not installed or disabled."""

    @contextmanager
    def start_as_current_span(
        self, *_args: Any, **_kwargs: Any
    ) -> Iterator[_NoopSpan]:
        yield _NoopSpan()


def _is_tracing_enabled() -> bool:
    """Tracing is enabled only when an explicit OTEL_TRACES_EXPORTER is set."""
    exporter = os.environ.get("OTEL_TRACES_EXPORTER", "").lower()
    return bool(exporter and exporter not in ("none", "false", "0"))


def get_tracer(name: str = "devin-orchestrator") -> Any:
    """Return an OpenTelemetry tracer or a no-op tracer."""
    if not _is_tracing_enabled():
        return _NoopTracer()

    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        return provider.get_tracer(name)
    except ImportError:
        logger.warning(
            "OTEL_TRACES_EXPORTER is set but opentelemetry-api is not installed"
        )
        return _NoopTracer()


@contextmanager
def trace_span(
    span_name: str,
    attributes: dict[str, Any] | None = None,
    tracer_name: str = "devin-orchestrator",
) -> Iterator[Any]:
    """Start a span and set attributes when tracing is enabled."""
    tracer = get_tracer(tracer_name)
    with tracer.start_as_current_span(span_name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status("ERROR")
            raise
