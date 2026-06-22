# Systematic Debugging

## Overview

Systematically investigate incidents, bugs, or failures through evidence gathering, analysis, root cause identification, and fix proposal. This skill follows a structured debugging methodology to ensure thorough investigation.

**Announce at start:** `Using the systematic-debugging skill for structured incident investigation.`

## The Iron Law

```
INVESTIGATION MUST BE EVIDENCE-BASED AND SYSTEMATIC
```

Never jump to conclusions without evidence. Always follow the systematic process: gather evidence → analyze → identify root cause → propose fixes.

## When to Use

Use `systematic-debugging` when:
- Investigating incidents or bugs
- Analyzing failures in production
- Debugging complex issues
- Performing root cause analysis (RCA)
- Investigating test failures
- Analyzing performance issues

## Process Flow

```
Gather evidence from logs, code, and reproduction steps
    │
    ▼
Analyze evidence to identify potential causes
    │
    ▼
Identify the root cause of the incident
    │
    ▼
Propose fixes for the identified root cause
    │
    ▼
Document findings and recommendations
    │
    ▼
Terminal state: investigation complete with fix recommendations
```

## The Process

**1. Gather evidence from logs, code, and reproduction steps**

- Collect relevant logs and error messages
- Review code changes around the failure
- Identify reproduction steps
- Check system state at time of failure
- Review configuration and environment
- Collect metrics and monitoring data
- Document timeline of events

**2. Analyze evidence to identify potential causes**

- Correlate events and error patterns
- Identify common factors across failures
- Analyze code paths that could lead to failure
- Review recent changes
- Check for environmental factors
- Identify data anomalies
- Document potential causes with evidence

**3. Identify the root cause of the incident**

- Apply the "5 Whys" technique
- Trace the failure to its origin
- Identify the fundamental issue
- Distinguish symptoms from root cause
- Verify the root cause explains all symptoms
- Document the root cause with supporting evidence

**4. Propose fixes for the identified root cause**

- Design fixes that address the root cause
- Consider short-term mitigations
- Design long-term solutions
- Assess fix impact and risk
- Consider testing requirements
- Document fix recommendations with rationale

**5. Document findings and recommendations**

Create investigation documentation with:
- Executive summary
- Timeline of events
- Evidence gathered
- Analysis performed
- Root cause identified
- Fix recommendations
- Prevention measures
- Lessons learned

## Required Artifacts

- **evidence.md**: Collected evidence from logs, code, and reproduction
- **analysis.md**: Analysis of evidence and potential causes
- **root_cause.md**: Identified root cause with supporting evidence
- **fix_recommendations.md**: Proposed fixes with rationale

## Red Flags

- Jumping to conclusions without evidence
- Treating symptoms as root cause
- Missing evidence collection
- Incomplete analysis
- Fixes that don't address root cause
- Missing documentation of investigation

## Done Means

You are done when:
- evidence.md is created with complete evidence collection
- analysis.md documents thorough analysis of potential causes
- root_cause.md identifies the fundamental issue with evidence
- fix_recommendations.md proposes fixes addressing the root cause
- All findings are evidence-based
- Investigation is fully documented
