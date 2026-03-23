"""
EU AI Act Compliance Kit

Automated compliance checker for the EU AI Act (Regulation 2024/1689).
Classifies AI systems by risk tier, generates compliance checklists, and produces
audit-ready reports. Can run as CLI, GitHub Action, or Python library.

Version: derived from package metadata
License: Apache-2.0
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("eu-ai-act-compliance-kit")
except PackageNotFoundError:
    # Deterministic fallback for local, non-installed execution contexts.
    __version__ = "0.0.0+local"

__author__ = "EU AI Act Compliance Kit Contributors"
__all__ = [
    "AISystemDescriptor",
    "RiskTier",
    "UseCaseDomain",
    "RiskClassifier",
    "ComplianceChecker",
    "ChecklistGenerator",
    "DashboardGenerator",
    "ReportGenerator",
    "ExportGenerator",
    "ExportPusher",
    "ExportPushError",
    "ExportEnvelope",
    "ExportItem",
    "TransparencyFinding",
    "TransparencyChecker",
    "GPAIModelInfo",
    "GPAIAssessment",
    "GPAIAssessor",
    "SecurityMapper",
    "SecurityMappingResult",
    "SecurityMappingSummary",
    "SecurityControlResult",
    "SecurityGateEvaluator",
    "SecurityGateMode",
    "SecurityGateProfile",
    "SecurityGateResult",
    "ExportOpsGatePolicy",
    "ExportOpsGateResult",
    "ExportOpsGateEvaluator",
    "HistoryEvent",
    "append_event",
    "list_events",
    "get_event",
    "diff_events",
]

from eu_ai_act.checker import ComplianceChecker
from eu_ai_act.checklist import ChecklistGenerator
from eu_ai_act.classifier import RiskClassifier
from eu_ai_act.dashboard import DashboardGenerator
from eu_ai_act.export_ops_gate import (
    ExportOpsGateEvaluator,
    ExportOpsGatePolicy,
    ExportOpsGateResult,
)
from eu_ai_act.exporter import (
    ExportEnvelope,
    ExportGenerator,
    ExportItem,
    ExportPusher,
    ExportPushError,
)
from eu_ai_act.gpai import GPAIAssessment, GPAIAssessor, GPAIModelInfo
from eu_ai_act.history import HistoryEvent, append_event, diff_events, get_event, list_events
from eu_ai_act.reporter import ReportGenerator
from eu_ai_act.schema import AISystemDescriptor, RiskTier, UseCaseDomain
from eu_ai_act.security_gate import (
    SecurityGateEvaluator,
    SecurityGateMode,
    SecurityGateProfile,
    SecurityGateResult,
)
from eu_ai_act.security_mapping import (
    SecurityControlResult,
    SecurityMapper,
    SecurityMappingResult,
    SecurityMappingSummary,
)
from eu_ai_act.transparency import TransparencyChecker, TransparencyFinding

__all__ += [
    "AISystemDescriptor",
    "RiskTier",
    "UseCaseDomain",
]
