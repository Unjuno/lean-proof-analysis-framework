"""Lean Proof Analysis Framework (LPAF).

Human- and agent-accessible *source-level* Lean analysis utilities.
No claim of semantic equivalence, elaborated dependencies, or proof checking.
"""
from .api import analyze_project, load_report
from .reading import (
    ReadingError, compare_declarations, dependency_slice, find_similar,
    get_declaration, list_declarations,
)

__all__ = [
    "analyze_project", "load_report", "ReadingError", "list_declarations",
    "get_declaration", "compare_declarations", "dependency_slice", "find_similar",
]
__version__ = "0.2.0"
