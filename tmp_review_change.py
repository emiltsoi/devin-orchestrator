import json
import subprocess
import sys
from pathlib import Path

WORKFLOW_ENGINE_DIR = Path(__file__).resolve().parent / "workflow-engine"
sys.path.insert(0, str(WORKFLOW_ENGINE_DIR))

from stateless_orchestrator import StatelessOrchestrator

repo = Path(__file__).resolve().parent
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
base = subprocess.check_output(["git", "rev-parse", "HEAD~1"], cwd=repo, text=True).strip()
files = subprocess.check_output(["git", "diff", "--name-only", "HEAD~1"], cwd=repo, text=True).strip().splitlines()

request = f"""DESCRIPTION: Implement non-blocking human gate signal, auto-bypass/escalation, and MCP tools for the devin-orchestrator.
PLAN_OR_REQUIREMENTS:
- Human gates must not block indefinitely in an MCP server environment.
- The orchestrator should signal the calling agent with a decision file path and a continue_workflow instruction.
- A default auto-bypass mode should escalate to the agent only when specific conditions trigger (e.g. mandatory gate, stage failure, reviewer rejection, critical/security keywords, missing output, warnings/medium confidence).
- Expose gate_decision and continue_workflow MCP tools with a gate_mode parameter on workflow tools.
- Workflow continuation must skip already completed stages and honour pre-existing gate decisions.
BASE_SHA: {base}
HEAD_SHA: {head}
FILES_MODIFIED: {', '.join(files)}
"""

orchestrator = StatelessOrchestrator(
    workspace=str(repo),
    gate_mode="auto",
    demo_mode=False,
    timeout=600,
)
result = orchestrator.review(request)

output_path = repo / "tmp_review_change_result.json"
output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
