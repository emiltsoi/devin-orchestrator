# Code Review

## Overview

Review code for spec compliance and code quality with objective, evidence-based findings. This skill performs a three-stage review: spec compliance, code quality, and human verdict.

**Announce at start:** `Using the code-review skill for spec-compliance and code-quality review.`

## The Iron Law

```
REVIEW MUST BE OBJECTIVE AND EVIDENCE-BASED
```

Never make subjective claims without evidence. Always cite specific code locations. Every finding must be backed by specific code references or test results.

## When to Use

Use `code-review` when:
- Before merging code
- After implementation is complete
- During code review phase
- When verification-before-completion has passed

## Process Flow

```
Review spec compliance
    │
    ▼
Document spec compliance findings in review-spec.md
    │
    ▼
Review code quality
    │
    ▼
Document code quality findings in review-quality.md
    │
    ▼
Provide human verdict in human-verdict.md
    │
    ▼
Terminal state: workflow complete
```

## The Process

**1. Review spec compliance**

- Read the requirement.md or spec document
- Read the design.md for architecture decisions
- Review the implementation code
- Check that all acceptance criteria are met
- Verify the implementation matches the design
- Identify any deviations from the spec
- Note any missing features or incomplete implementations
- Check that out-of-scope items were not implemented

**2. Document spec compliance findings in review-spec.md**

Create `review-spec.md` with:
- Summary of spec compliance (PASS/FAIL/PARTIAL)
- List of acceptance criteria and their status
- Evidence for each criterion (code locations, test results)
- Deviations from the spec with justification
- Missing features or incomplete implementations
- Out-of-scope items that were accidentally included
- Overall spec compliance assessment

**3. Review code quality**

- Check code readability and maintainability
- Verify proper error handling
- Check for security vulnerabilities
- Review performance considerations
- Check for code duplication
- Verify proper documentation
- Review test coverage
- Check for adherence to coding standards
- Identify technical debt

**4. Document code quality findings in review-quality.md**

Create `review-quality.md` with:
- Summary of code quality (EXCELLENT/GOOD/ACCEPTABLE/POOR)
- Code readability assessment
- Error handling review
- Security review findings
- Performance considerations
- Code duplication issues
- Documentation completeness
- Test coverage assessment
- Coding standards compliance
- Technical debt identified
- Specific code locations for each finding

**5. Provide human verdict in human-verdict.md**

Create `human-verdict.md` with:
- Overall verdict (APPROVE/REQUEST CHANGES/REJECT)
- Reasoning for the verdict
- Required changes before approval (if any)
- Optional improvements (not blocking)
- Confidence level in the verdict
- Any concerns or risks
- Recommendation for next steps

**6. Terminal state**

- The review is complete
- All three artifacts are created
- The workflow can proceed to completion or return for changes

## Required Artifacts

- **review-spec.md**: Spec compliance review with evidence-based findings
- **review-quality.md**: Code quality review with specific code locations
- **human-verdict.md**: Human verdict with approval decision

## Red Flags

- Making subjective claims without evidence
- Not citing specific code locations
- Not checking all acceptance criteria
- Skipping the code quality review
- Not providing a clear verdict
- Missing required artifacts
- Approving code that doesn't meet the spec

## Done Means

You are done when:
- review-spec.md is created with complete spec compliance assessment
- review-quality.md is created with code quality findings
- human-verdict.md is created with a clear verdict
- All findings are evidence-based with code locations
- The workflow can proceed based on the verdict
