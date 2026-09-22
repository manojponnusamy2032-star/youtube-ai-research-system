"""Quality Control (QC) package for the orchestration pipeline.

The QC system inspects and validates the generated artifacts from the
production pipeline.  It does NOT trust that a successful stage completion
or the mere existence of an MP4 means the output is acceptable.

Architecture:

    ScriptPackage
        ↓
    Script QC
        ↓
    VisualPlan
        ↓
    Visual QC
        ↓
    Render Output
        ↓
    Media QC
        ↓
    Cross-stage QC
        ↓
    QCReport
        ↓
    PASS / WARN / FAIL
"""

from src.orchestration.qc.models import (
    QCStatus,
    QCCheck,
    QCReport,
    QCSeverity,
    QCRequest,
)
from src.orchestration.qc.qc_pipeline import QCPipeline, run_qc
from src.orchestration.qc.script_qc import run_script_qc
from src.orchestration.qc.visual_qc import run_visual_qc
from src.orchestration.qc.repetition_qc import run_repetition_qc
from src.orchestration.qc.cross_stage_qc import run_cross_stage_qc
from src.orchestration.qc.media_qc import run_media_qc
from src.orchestration.qc.render_config_qc import run_render_config_qc
from src.orchestration.qc.agent import QCAgent

__all__ = [
    "QCStatus",
    "QCSeverity",
    "QCCheck",
    "QCReport",
    "QCRequest",
    "QCPipeline",
    "run_qc",
    "run_script_qc",
    "run_visual_qc",
    "run_repetition_qc",
    "run_cross_stage_qc",
    "run_media_qc",
    "run_render_config_qc",
    "QCAgent",
]

