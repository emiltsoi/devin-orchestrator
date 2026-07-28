---
name: swe-compliance
description: "Use when reviewing code for software engineering best practices, coding standards, and compliance"
---

# SWE Compliance

## Overview

Review code for software engineering best practices, coding standards, and compliance with industry conventions. This skill focuses on code quality, maintainability, and adherence to established patterns.

**Announce at start:** `Using the swe-compliance skill for code quality and standards compliance review.`

## The Iron Law

```
CODE MUST FOLLOW ESTABLISHED CONVENTIONS AND BEST PRACTICES
```

Never make subjective style judgments without referencing established standards. Always cite specific convention violations with evidence.

## When to Use

Use `swe-compliance` when:
- Reviewing code quality and style
- Checking adherence to coding standards
- Evaluating maintainability and technical debt
- Assessing security best practices
- Reviewing error handling patterns
- Checking documentation completeness

## Process Flow

```
Review code structure and organization
    │
    ▼
Check coding standards compliance
    │
    ▼
Review error handling and edge cases
    │
    ▼
Assess security best practices
    │
    ▼
Check documentation and comments
    │
    ▼
Document findings in quality_review.md
    │
    ▼
Terminal state: code quality assessment complete
```

## The Process

**1. Review code structure and organization**

- Check for proper separation of concerns
- Verify modular design and single responsibility
- Review function/class organization
- Check for code duplication
- Assess naming conventions
- Review file organization

**2. Check coding standards compliance**

- Verify adherence to project coding standards
- Check consistent formatting and style
- Review naming conventions (variables, functions, classes)
- Check for proper use of language idioms
- Verify consistent error handling patterns
- Review import organization

**3. Review error handling and edge cases**

- Check for comprehensive error handling
- Verify proper exception handling
- Review edge case coverage
- Check for null/undefined handling
- Verify input validation
- Review resource cleanup

**4. Assess security best practices**

- Check for security vulnerabilities
- Review input sanitization
- Check for hardcoded secrets
- Verify proper authentication/authorization
- Review data validation
- Check for SQL injection, XSS vulnerabilities

**5. Check documentation and comments**

- Verify function/class documentation
- Check for inline comments where needed
- Review README and setup documentation
- Check for API documentation
- Verify complex logic is explained

**6. Document findings in quality_review.md**

Create `quality_review.md` with:
- Overall quality assessment (EXCELLENT/GOOD/ACCEPTABLE/POOR)
- Code structure findings
- Standards compliance issues
- Error handling gaps
- Security concerns
- Documentation completeness
- Technical debt identified
- Specific code locations for each finding
- Recommendations for improvement

## Required Artifacts

- **quality_review.md**: Code quality and compliance assessment with specific findings

## Red Flags

- Inconsistent coding style across the codebase
- Missing error handling for critical paths
- Security vulnerabilities (hardcoded secrets, injection risks)
- Code duplication without abstraction
- Poor naming conventions
- Missing documentation for complex logic
- Inconsistent error handling patterns
- Resource leaks (unclosed files, connections)

## Done Means

You are done when:
- quality_review.md is created with complete assessment
- All findings are specific with code locations
- Security issues are clearly identified
- Technical debt is documented
- Recommendations are actionable
- The assessment is evidence-based
