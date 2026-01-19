#!/usr/bin/env python3
"""
Quick component testing script
Tests each utility module individually before running full validation
"""

print("="*70)
print("COMPONENT TESTING")
print("="*70)

# Test 1: Ambiguity Detector
print("\n[1/6] Testing Ambiguity Detector...")
try:
    from src.utils.ambiguity_detector import detect_vague_terms, detect_ambiguity
    
    test_text = "The system shall be fast and user-friendly"
    vague = detect_vague_terms(test_text)
    print(f"   ✓ detect_vague_terms() works: {vague}")
    
    issues = detect_ambiguity(test_text)
    print(f"   ✓ detect_ambiguity() works: {len(issues)} issues found")
except Exception as e:
    print(f"   ✗ FAILED: {e}")

# Test 2: Consistency Checker
print("\n[2/6] Testing Consistency Checker...")
try:
    from src.utils.consistency_checker import detect_contradictions
    
    test_text = "User must login but no authentication required"
    contradictions = detect_contradictions(test_text)
    print(f"   ✓ detect_contradictions() works: {len(contradictions)} contradictions found")
except Exception as e:
    print(f"   ✗ FAILED: {e}")

# Test 3: Confidence Calculator
print("\n[3/6] Testing Confidence Calculator...")
try:
    from src.utils.confidence import calculate_confidence
    
    issues = [
        {"type": "vague_term", "severity": "medium"},
        {"type": "weak_phrase", "severity": "low"}
    ]
    confidence = calculate_confidence(issues)
    print(f"   ✓ calculate_confidence() works: {confidence}")
except Exception as e:
    print(f"   ✗ FAILED: {e}")

# Test 4: Criticality Detector
print("\n[4/6] Testing Criticality Detector...")
try:
    from src.utils.criticality import is_safety_critical
    
    critical_text = "The system shall encrypt payment data"
    non_critical_text = "The UI shall display a welcome message"
    
    is_critical = is_safety_critical(critical_text)
    is_not_critical = is_safety_critical(non_critical_text)
    
    print(f"   ✓ is_safety_critical() works: Payment={is_critical}, UI={is_not_critical}")
except Exception as e:
    print(f"   ✗ FAILED: {e}")

# Test 5: SMT Solver
print("\n[5/6] Testing SMT Solver...")
try:
    from src.utils.smt_solver_integration import check_with_smt
    
    test_text = "User must login, no authentication required"
    smt_issues = check_with_smt(test_text)
    print(f"   ✓ check_with_smt() works: {len(smt_issues)} issues found")
except Exception as e:
    print(f"   ✗ FAILED: {e}")

# Test 6: Ollama Client (Connection Check)
print("\n[6/6] Testing Ollama Client...")
try:
    from src.utils.ollama_client import OllamaClient
    
    client = OllamaClient()
    is_connected = client.check_connection()
    
    if is_connected:
        print(f"   ✓ OllamaClient connected: {client.base_url}")
    else:
        print(f"   ⚠ OllamaClient NOT connected (will use fallback suggestions)")
        print(f"     URL: {client.base_url}")
        print(f"     This is OK - rule-based suggestions will be used")
except Exception as e:
    print(f"   ✗ FAILED: {e}")

print("\n" + "="*70)
print("COMPONENT TEST COMPLETE")
print("="*70)