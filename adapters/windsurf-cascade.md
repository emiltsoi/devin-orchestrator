# Windsurf Cascade Transport Adapter

## Overview

Transport adapter for Windsurf Cascade using fresh session copy-paste mechanism. This adapter provides context isolation and fresh agent context per dispatch by having the user copy-paste prompts between Cascade sessions.

## Capabilities

- **fresh_session_spawn**: Can spawn fresh Cascade sessions
- **context_isolation**: Each dispatch gets isolated context
- **file_operations**: Can read/write files via Cascade tools
- **terminal_commands**: Can execute terminal commands via Cascade tools

## Dispatch Contract

### Inputs

- `prompt_file` - Path to prompt file containing dispatch instructions
- `workspace_path` - Path to target workspace
- `model_config` - Model configuration (default: SWE-1.6)

### Outputs

- `stdout_file` - Path to file containing agent stdout
- `stderr_file` - Path to file containing agent stderr
- `session_metadata` - Session metadata (tokens, time, etc.)

### Quality Bar

- `exit_code_zero` - Process exited successfully
- `no_timeout` - Completed within time limit
- `artifact_exists` - Expected output artifact exists

## Limitations

- **max_prompt_tokens**: 200,000 tokens
- **max_session_duration**: 3600 seconds (1 hour)
- **requires_user_copy_paste**: User must manually copy-paste between sessions
- **manual_round_trip**: Requires manual intervention for each dispatch

## Usage Pattern

1. Architect creates prompt file in session work directory
2. User opens new Cascade session
3. User copies prompt from file and pastes into new session
4. Sub-agent executes and produces output
5. User copies output back to original session
6. Architect validates output against quality bar

## Advantages

- **Context isolation**: Fresh context per dispatch prevents contamination
- **No tooling dependencies**: Works with standard Cascade UI
- **Model flexibility**: Can use any model supported by Cascade
- **Cost control**: User can see and approve each dispatch

## Disadvantages

- **Manual overhead**: Copy-paste round-trip per dispatch
- **Slow**: ~1-3 minutes per dispatch for user interaction
- **Error-prone**: Manual copy-paste can introduce errors
- **Not scalable**: Limited by user patience for manual round-trips

## When to Use

- **Small to medium tasks**: Bounded Coder/Test-Author dispatches
- **Prototype phase**: Testing contract shapes before automation
- **Low-volume sessions**: When dispatch count is low
- **Debugging**: When you need to see each dispatch interactively

## When NOT to Use

- **High-volume sessions**: Many dispatches would be tedious
- **Production automation**: Requires automated dispatch mechanism
- **Parallel dispatches**: Manual copy-paste doesn't scale to parallel

## Future Improvements

- **Direct sub-Cascade spawn**: Remove manual copy-paste requirement
- **Session pooling**: Reuse sessions for multiple dispatches
- **Automated round-trip**: Scripted prompt/output transfer
- **Parallel dispatch**: Support concurrent sub-agent sessions

## Model Configuration

Default model: SWE-1.6

Rationale:
- Free and allows parallelization up to 10 instances
- Target 8 parallel dispatches to leave headroom for Architect
- Cost-efficient for sub-agent roles
- Can be overridden per dispatch if needed

## Example Dispatch

```bash
# Architect creates prompt
cat > work/FEATURE-001/coder-prompt-T1.md << EOF
You are a Coder agent. Implement the following design:
$(cat work/FEATURE-001/design.md)

Use SWE-1.6 model. Output code diff and rationale.
EOF

# User opens new Cascade session, copies prompt, executes
# User copies output back to work/FEATURE-001/coder-output-T1.md

# Architect validates
if [ -f work/FEATURE-001/coder-output-T1.md ]; then
  echo "Dispatch completed successfully"
else
  echo "Dispatch failed - output missing"
fi
```
