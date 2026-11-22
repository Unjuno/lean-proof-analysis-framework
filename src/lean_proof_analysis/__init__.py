"""Lean Proof Analysis Framework (LPAF).

Human- and agent-accessible *source-level* Lean analysis utilities.
No claim of semantic equivalence, elaborated dependencies, or proof checking.
"""
from .api import analyze_project, load_report

__all__ = ["analyze_project", "load_report"]
__version__ = "0.1.0"
