"""Lean Proof Analysis Framework (LPAF).

Scientific proof-corpus analysis with explicit evidence and source-reading tools.
Structural metrics do not constitute proof correctness or equivalence judgments.
"""
from .api import analyze_project, load_report
from .reading import (
    ReadingError, compare_declarations, dependency_slice, find_similar,
    get_declaration, list_declarations,
)
from .corpus import CorpusError, CorpusView, ProofCorpus, import_corpus, import_source_report, open_corpus
from .extraction import ExportError, export_lean
from .graph_analysis import analyze_dependencies, dependency_bottlenecks, dependency_overlap
from .term_analysis import (
    TermAnalysisError, compare_term_structure, find_repeated_subterms, profile_terms,
)

__all__ = [
    "analyze_project", "load_report", "ReadingError", "list_declarations",
    "get_declaration", "compare_declarations", "dependency_slice", "find_similar",
    "CorpusError", "CorpusView", "ProofCorpus", "import_corpus", "import_source_report", "open_corpus",
    "ExportError", "export_lean",
    "analyze_dependencies", "dependency_bottlenecks", "dependency_overlap",
    "TermAnalysisError", "compare_term_structure", "find_repeated_subterms", "profile_terms",
]
__version__ = "0.3.0"
