"""
Tests for transport_adapter.py

Covers the abstract TransportAdapter contract and the InvocationResult
dataclass.
"""

import json
import sys
from dataclasses import fields
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from transport_adapter import InvocationResult, TransportAdapter


class TestInvocationResult:
    def test_dataclass_fields(self):
        names = {f.name for f in fields(InvocationResult)}
        assert names == {"success", "output", "error", "exit_code"}

    def test_default_construction(self):
        # All fields are required (no defaults) -> must be passed in.
        result = InvocationResult(success=True, output="ok", error="", exit_code=0)
        assert result.success is True
        assert result.output == "ok"
        assert result.error == ""
        assert result.exit_code == 0

    def test_failure_construction(self):
        result = InvocationResult(
            success=False, output="", error="boom", exit_code=1
        )
        assert result.success is False
        assert result.exit_code == 1


class TestTransportAdapterContract:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            TransportAdapter("path")  # type: ignore[abstract]

    def test_subclass_must_implement_all_abstract_methods(self):
        # Missing capabilities() -> still abstract.
        class Incomplete(TransportAdapter):
            def __init__(self, adapter_path, workspace=None, **kwargs):
                pass

            def invoke(self, prompt, timeout=120, focused_context=None,
                       correction_artifact=None, enable_skills=True):
                return InvocationResult(True, "", "", 0)

        with pytest.raises(TypeError):
            Incomplete("path")  # type: ignore[abstract]

    def test_complete_subclass_can_be_constructed_and_invoked(self):
        class DummyAdapter(TransportAdapter):
            def __init__(self, adapter_path, workspace=None, **kwargs):
                self.adapter_path = adapter_path
                self.workspace = workspace
                self.kwargs = kwargs

            def invoke(self, prompt, timeout=120, focused_context=None,
                       correction_artifact=None, enable_skills=True):
                return InvocationResult(
                    success=True,
                    output=f"ran: {prompt}",
                    error="",
                    exit_code=0,
                )

            def capabilities(self):
                return ["invoke", "capabilities"]

        adapter = DummyAdapter("path", workspace="ws", foo="bar")
        assert adapter.workspace == "ws"
        assert adapter.kwargs == {"foo": "bar"}
        result = adapter.invoke("hello")
        assert result.success is True
        assert "hello" in result.output
        assert adapter.capabilities() == ["invoke", "capabilities"]

    def test_invoke_signature_accepts_optional_kwargs(self):
        class DummyAdapter(TransportAdapter):
            def __init__(self, adapter_path, workspace=None, **kwargs):
                pass

            def invoke(self, prompt, timeout=120, focused_context=None,
                       correction_artifact=None, enable_skills=True):
                return InvocationResult(
                    True,
                    json.dumps({
                        "timeout": timeout,
                        "focused_context": focused_context,
                        "correction_artifact": correction_artifact,
                        "enable_skills": enable_skills,
                    }),
                    "",
                    0,
                )

            def capabilities(self):
                return []

        adapter = DummyAdapter("p")
        result = adapter.invoke(
            "prompt",
            timeout=30,
            focused_context=["a.md", "b.md"],
            correction_artifact="corr.md",
            enable_skills=False,
        )
        payload = json.loads(result.output)
        assert payload["timeout"] == 30
        assert payload["focused_context"] == ["a.md", "b.md"]
        assert payload["correction_artifact"] == "corr.md"
        assert payload["enable_skills"] is False
