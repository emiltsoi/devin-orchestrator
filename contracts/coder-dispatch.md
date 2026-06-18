# Coder Dispatch Contract

## Overview

The Coder agent implements code per design specification and FRAMEWORK idioms. This contract defines the inputs, outputs, quality bar, and failure response for Coder dispatches.

## Role

**Role**: Coder
**Description**: Implementation agent for coding tasks per design specification
**Default Model**: SWE-1.6

## Inputs

### design.md (required)
- **Type**: file
- **Description**: Full design document
- **Usage**: Coder reads the complete design to understand what to implement

### FRAMEWORK_*.md (required)
- **Type**: file
- **Description**: Framework files including anti-patterns section
- **Usage**: Coder must cite which idiom from FRAMEWORK was used
- **Note**: If no FRAMEWORK exists yet, Architect annotates `FRAMEWORK_<Subsystem>_NOT_YET_AUTHORED` and cites closest prior art

### target_files (required)
- **Type**: file_content
- **Description**: Current content of target files (paste-in, not just reference)
- **Usage**: Ensures dispatch is portable across transports; Coder sees actual file content

### acceptance_criteria (required)
- **Type**: list
- **Description**: AC-1..AC-N from design, copied verbatim
- **Usage**: Coder must address each AC 1:1

### cited_idioms (required)
- **Type**: list
- **Description**: Idioms from FRAMEWORK that Architect expects Coder to use
- **Usage**: Coder must cite at least one idiom in rationale

## Outputs

### code_diff (required)
- **Type**: file
- **Description**: Code diff or full file content for each target file
- **Usage**: Architect applies this to the codebase

### rationale (required)
- **Type**: text
- **Description**: Rationale citing which FRAMEWORK idiom was used
- **Usage**: Architect validates that Coder followed FRAMEWORK discipline

### assumptions (optional)
- **Type**: list
- **Description**: Flagged assumptions that weren't explicit in design.md
- **Usage**: Architect reviews these and updates design if needed

### test_expectations (required)
- **Type**: list
- **Description**: One sentence per AC describing what Test-Author should verify
- **Usage**: Test-Author uses these to write tests

## Quality Bar

Coder output must satisfy:

1. **compiles_mechanically** - No obvious syntax errors
2. **cites_at_least_one_idiom** - Rationale must cite at least one FRAMEWORK idiom
3. **no_novel_mechanisms** - Does not introduce mechanisms absent from design.md or FRAMEWORK
4. **acs_addressed_1_to_1** - Every AC from design is addressed
5. **no_test_weakening** - Does not weaken existing tests

## Failure Modes

### invents_novel_mechanism
- **Response**: reject_with_anti_pattern_reference
- **Action**: Re-dispatch with explicit anti-pattern reference + demand "which Idiom applies?"

### fails_to_cite_idiom
- **Response**: reject_ask_for_citation
- **Action**: Re-dispatch asking for citation; if Coder can't cite, escalate to user (Rule 51 likely violated)

### contradicts_design
- **Response**: update_design_or_redispatch
- **Action**: Architect updates design.md OR re-dispatches with clarified inputs

### ac_miss
- **Response**: reject_redispatch
- **Action**: Re-dispatch with explicit AC list

### silent_scope_creep
- **Response**: reject_with_allowlist
- **Action**: Re-dispatch with strict file allowlist

## Retry Budget

**Maximum retries**: 1

On 2nd failure → escalate to user (Rule 17).

## Usage Example

```yaml
# Architect creates coder prompt
coder_prompt: |
  You are a Coder agent. Implement the following design:
  
  $(cat design.md)
  
  Use the following FRAMEWORK idioms:
  $(cat cited_idioms)
  
  Target files (current content):
  $(cat target_files)
  
  Acceptance criteria:
  - AC-1: ...
  - AC-2: ...
  
  Output:
  1. Code diff for each target file
  2. Rationale citing which idiom was used
  3. Test expectations per AC
  4. Any assumptions not in design
```

## Model Selection

**Default**: SWE-1.6

**Rationale**:
- Free and allows parallelization up to 10 instances
- Target 8 parallel dispatches to leave headroom for Architect
- Cost-efficient for implementation tasks
- Can be overridden per dispatch if specific capabilities needed

## Integration with Workflow

In the `/feature` workflow:
- Step 3 (DESIGN) produces design.md with cited idioms
- Step 4 (IMPLEMENT) dispatches Coder via transport adapter
- Architect validates output against quality bar
- On failure, re-dispatch or escalate per retry budget

## Relation to Other Contracts

- **Test-Author**: Consumes Coder's test_expectations output
- **Reviewer**: Consumes Coder's code_diff and rationale outputs
- **Architect**: Orchestrates Coder dispatch and validates output
