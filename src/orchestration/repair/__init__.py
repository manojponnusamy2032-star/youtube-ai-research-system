"""Self-correction subsystem (Day 5).

QC-driven targeted regeneration:

    QCReport -> CorrectionDiagnoser -> CorrectionPlan
             -> CorrectionExecutor (smallest affected artifact)
             -> re-render -> QC (retry-limited)
"""

from src.orchestration.repair.dependency_map import (
    CORRECTION_CHAIN,
    artifact_field_for,
    downstream_of,
    invalidation_set,
    pipeline_stage_for,
)
from src.orchestration.repair.diagnoser import CorrectionDiagnoser
from src.orchestration.repair.executor import CorrectiveScriptAgent, CorrectiveVisualPlanner
from src.orchestration.repair.loop import (
    DEFAULT_MAX_CORRECTION_ATTEMPTS,
    CorrectionExecutor,
    CorrectionLoop,
)
from src.orchestration.repair.models import (
    CorrectionAction,
    CorrectionAttempt,
    CorrectionPlan,
    CorrectionReason,
    CorrectionReport,
    CorrectionSeverity,
    CorrectionTarget,
)

__all__ = [
    "CORRECTION_CHAIN",
    "CorrectionAction",
    "CorrectionAttempt",
    "CorrectionDiagnoser",
    "CorrectionPlan",
    "CorrectionReason",
    "CorrectionReport",
    "CorrectionSeverity",
    "CorrectionTarget",
    "artifact_field_for",
    "downstream_of",
    "invalidation_set",
    "pipeline_stage_for",
]
