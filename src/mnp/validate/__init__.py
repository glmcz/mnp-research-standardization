"""The validation system (docs/DESIGN_2026-10-18_hypotheses-method-evaluation.md §3).

A model reads, code decides, a second reader challenges. Each question is one module:
`sign` (Q2, values that contradict their surface label) and `judge` (the independent judges).
"""
