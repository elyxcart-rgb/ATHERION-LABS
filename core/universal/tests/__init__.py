"""SONIC AI — Universal Agent Self-Test Suite.

Verifies:
  1. All foundation modules import cleanly
  2. TargetSpec parses common intents correctly
  3. ActionValidator blocks malformed actions
  4. TargetResolver ranks candidates correctly
  5. VerificationEngine catches success/failure conditions
  6. RecoveryEngine classifies failures and picks strategies
  7. ToolPerformanceMemory persists across instances
  8. UniversalAgent.plan() decomposes natural-language goals
  9. UniversalAgent handles "destructive action needs confirmation"
 10. JarvisBrain.load still works after additive integration (zero-break)

Public API:
    python -m core.universal.tests.run_all
"""
