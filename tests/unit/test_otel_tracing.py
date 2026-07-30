"""Unit tests for devin_orchestrator.otel_tracing."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from devin_orchestrator.otel_tracing import get_tracer, trace_span


class TestOtelTracing(unittest.TestCase):
    def test_get_tracer_returns_noop_without_exporter(self):
        tracer = get_tracer("test")
        # No env var set; should be no-op tracer.
        assert hasattr(tracer, "start_as_current_span")

    def test_trace_span_noop_records_and_reraises(self):
        def _boom():
            with trace_span("boom", {"key": "value"}):
                raise ValueError("boom")

        with self.assertRaises(ValueError):
            _boom()

    def test_trace_span_yields_noop_span(self):
        with trace_span("noop", {"key": "value"}) as span:
            span.set_attribute("another", "value")
            span.set_status("OK")
            span.record_exception(ValueError("test"))

    def test_trace_span_disabled_by_default(self):
        with patch(
            "devin_orchestrator.otel_tracing._is_tracing_enabled", return_value=False
        ):
            tracer = get_tracer("test")
            assert tracer.__class__.__name__ == "_NoopTracer"

    def test_trace_span_uses_tracer_when_enabled(self):
        """trace_span uses the tracer returned by get_tracer."""
        fake_tracer = MagicMock()
        fake_span = MagicMock()
        fake_cm = MagicMock()
        fake_cm.__enter__ = lambda *a: fake_span
        fake_cm.__exit__ = lambda *a: None
        fake_tracer.start_as_current_span.return_value = fake_cm

        with patch.dict(os.environ, {"OTEL_TRACES_EXPORTER": "otlp"}):
            with patch(
                "devin_orchestrator.otel_tracing.get_tracer",
                return_value=fake_tracer,
            ):
                with trace_span("test", {"k": "v"}) as span:
                    span.set_attribute("k", "v")

        fake_tracer.start_as_current_span.assert_called_once_with("test")
        fake_span.set_attribute.assert_called()
