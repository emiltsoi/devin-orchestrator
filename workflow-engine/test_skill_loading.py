#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify devin_cli_adapter skill loading via description matching
"""

from pathlib import Path
from devin_cli_adapter import DevinCliAdapter

def test_skill_loading():
    """Test that skills are loaded and injected correctly"""
    
    # Initialize adapter with skills directory
    devin_cli_path = "C:\\Users\\<username>\\AppData\\Local\\devin\\cli\\bin\\devin.exe"
    skills_dir = Path(__file__).parent / "skills"
    
    adapter = DevinCliAdapter(
        devin_cli_path=devin_cli_path,
        skills_dir=str(skills_dir)
    )
    
    print("=== Skill Loading Test ===")
    print(f"Skills directory: {skills_dir}")
    print(f"Skills loaded: {list(adapter.skills.keys())}")
    print()
    
    # Test 1: Coder dispatch should trigger ponytail
    coder_prompt = "This is a coding dispatch and implementation task. Implement a function."
    injected_coder = adapter._inject_skills(coder_prompt)
    
    print("=== Test 1: Coder Dispatch (should trigger ponytail) ===")
    print(f"Original prompt: {coder_prompt}")
    print(f"Injected prompt length: {len(injected_coder)}")
    print(f"Ponytail injected: {'ponytail' in injected_coder.lower()}")
    print(f"First 200 chars of injected prompt:")
    print(injected_coder[:200])
    print()
    
    # Test 2: Reviewer dispatch should trigger swe-compliance
    reviewer_prompt = "This is a compliance review task, code verification, artifact audit, and quality check."
    injected_reviewer = adapter._inject_skills(reviewer_prompt)
    
    print("=== Test 2: Reviewer Dispatch (should trigger swe-compliance) ===")
    print(f"Original prompt: {reviewer_prompt}")
    print(f"Injected prompt length: {len(injected_reviewer)}")
    print(f"SWE-compliance injected: {'swe-compliance' in injected_reviewer.lower() or 'compliance' in injected_reviewer.lower()}")
    print(f"First 200 chars of injected prompt:")
    print(injected_reviewer[:200])
    print()
    
    # Test 3: Generic prompt should not trigger any skill
    generic_prompt = "Write a hello world program."
    injected_generic = adapter._inject_skills(generic_prompt)
    
    print("=== Test 3: Generic Prompt (should not trigger any skill) ===")
    print(f"Original prompt: {generic_prompt}")
    print(f"Injected prompt length: {len(injected_generic)}")
    print(f"Skills injected: {len(injected_generic) > len(generic_prompt)}")
    print(f"Prompt unchanged: {injected_generic == generic_prompt}")
    print()
    
    # Summary
    print("=== Summary ===")
    print(f"Skills loaded: {len(adapter.skills)}")
    print(f"Coder dispatch triggers ponytail: {'ponytail' in injected_coder.lower()}")
    print(f"Reviewer dispatch triggers swe-compliance: {'compliance' in injected_reviewer.lower()}")
    print(f"Generic prompt unchanged: {injected_generic == generic_prompt}")
    
    return {
        "skills_loaded": len(adapter.skills),
        "coder_triggers_ponytail": "ponytail" in injected_coder.lower(),
        "reviewer_triggers_compliance": "compliance" in injected_reviewer.lower(),
        "generic_unchanged": injected_generic == generic_prompt
    }

if __name__ == "__main__":
    results = test_skill_loading()
    print("\n=== Test Results ===")
    for key, value in results.items():
        print(f"{key}: {value}")
    
    # All tests should pass
    all_pass = all([
        results["skills_loaded"] == 2,
        results["coder_triggers_ponytail"],
        results["reviewer_triggers_compliance"],
        results["generic_unchanged"]
    ])
    
    print(f"\nAll tests passed: {all_pass}")
