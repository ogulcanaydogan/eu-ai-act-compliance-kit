"""Annex-specific compliance checkers for the EU AI Act.

Each module implements the section-level requirements of a specific Annex.
Currently:

- ``annex_iv``: Technical Documentation requirements (Art. 11 reference)
"""

from eu_ai_act.annexes.annex_iv import (
    AnnexIVFinding,
    AnnexIVSection,
    annex_iv_coverage_summary,
    check_annex_iv_completeness,
)

__all__ = [
    "AnnexIVFinding",
    "AnnexIVSection",
    "annex_iv_coverage_summary",
    "check_annex_iv_completeness",
]
