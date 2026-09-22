"""Minimal VideoPipelineOrchestrator.

Executes a VideoJob through the registered pipeline stages in order:

    research -> strategy -> script -> visual_plan -> render

Every stage runs through the common ``StageAgent`` interface; the render stage
is backed by the real YAIRS render pipeline via ``YairsRendererAdapter``.
A stage failure stops execution, records the failed stage + error on the job,
and persists the snapshot.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.orchestration.base import PipelineStageError, StageAgent
from src.orchestration.pipeline import (
    PIPELINE_STAGES,
    STAGE_QC,
    STAGE_RENDER,
    STAGE_RESEARCH,
    STAGE_SCRIPT,
    STAGE_STRATEGY,
    STAGE_VISUAL_PLAN,
)
from src.orchestration.qc.models import QCReport
from src.orchestration.registry import PipelineRegistry
from src.orchestration.schemas.job import (
    QCJobStatus,
    JobStatus,
    StageRecord,
    StageStatus,
    VideoJob,
)
from src.orchestration.schemas.production import ProductionRequest, VideoArtifact
from src.orchestration.schemas.research import ResearchRequest
from src.orchestration.schemas.visual import VisualPlan
from src.orchestration.state import VideoJobStore, write_json_artifact

# Which result field on VideoJob each stage writes into.
_STAGE_RESULT_FIELD = {
    STAGE_RESEARCH: "research",
    STAGE_STRATEGY: "strategy",
    STAGE_SCRIPT: "script",
    STAGE_VISUAL_PLAN: "visual_plan",
    STAGE_RENDER: "artifact",
}
class VideoPipelineOrchestrator:
    """Coordinates one Topic -> ... -> MP4 production graph."""

    def __init__(
        self,
        registry: PipelineRegistry | None = None,
        store: VideoJobStore | None = None,
        output_dir: str | Path = "output",
        stages: list[str] | None = None,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            registry: Stage registry (defaults to a fresh empty registry).
            store: VideoJob state store (defaults to ``output/jobs``).
            output_dir: Root directory for per-job artifacts.
            stages: Ordered stage list (defaults to PIPELINE_STAGES).
        """
        self.registry = registry if registry is not None else PipelineRegistry()
        self.store = store if store is not None else VideoJobStore(Path(output_dir) / "jobs")
        self.output_dir = Path(output_dir)
        self.stages = list(stages or PIPELINE_STAGES)
        self._render_config: dict[str, Any] = {}

    @property
    def render_config(self) -> dict[str, Any]:
        """Render config forwarded to the renderer adapter (width/height/fps/...)."""
        return self._render_config

    @render_config.setter
    def render_config(self, value: dict[str, Any] | None) -> None:
        self._render_config = dict(value or {})

    # -- public API ----------------------------------------------------------

    def create_job(self, topic: str, niche: str = "", audience: str = "general") -> VideoJob:
        """Create and persist a new VideoJob in PENDING state."""
        job = VideoJob(
            job_id=self._next_job_id(),
            topic=topic,
            niche=niche,
            audience=audience,
            status=JobStatus.PENDING,
            stages={stage: StageRecord(stage=stage) for stage in self.stages},
        )
        self.store.save(job)
        write_json_artifact(self._job_dir(job.job_id) / "job.json", job)
        return job

    def execute(self, topic: str, niche: str = "", audience: str = "general") -> VideoJob:
        """Create a job and run the full pipeline.  Returns the final job."""
        job = self.create_job(topic, niche=niche, audience=audience)
        return self.execute_job(job)

    def run_stages(self, job: VideoJob, stages: list[str]) -> VideoJob:
        """Run ONLY the given stages (in list order) for an existing job.

        Day-5 targeted regeneration entry point: correction code invokes this
        with just the invalidated stages so upstream artifacts are preserved
        untouched.  Execution stops at the first failed stage and the job is
        persisted after every state change.
        """
        try:
            for stage in stages:
                agent = self.registry.get(stage)
                job.current_stage = stage
                if agent is None:
                    raise PipelineStageError(stage, f"no agent registered for stage: {stage}")

                record = self._stage_record(job, stage)
                record.status = StageStatus.RUNNING
                record.started_at = self._now()
                record.error = None
                self.store.save(job)

                result = self._run_stage(stage, agent, job)
                self._store_result(job, stage, result)
        except Exception as exc:  # noqa: BLE001 - orchestrator boundary
            self._fail_job(job, stage if job.current_stage else "", exc)
        return job

    def run_qc(self, job: VideoJob) -> QCReport:
        """Run the QC gate only and return the fresh ``QCReport``.

        Raises ``RuntimeError`` when the QC stage has no registered agent.
        """
        agent = self.registry.get(STAGE_QC)
        if agent is None:
            raise RuntimeError("no QC agent registered")
        report = self._run_stage(STAGE_QC, agent, job)
        self._store_result(job, STAGE_QC, report)
        return report

    def execute_job(self, job: VideoJob) -> VideoJob:
        """Run every registered stage for an existing job.

        Execution stops at the first failed stage.  The job is persisted after
        every state change, so a crash keeps the last good snapshot.
        """
        job.status = JobStatus.RUNNING
        job.current_stage = self.stages[0] if self.stages else None
        self.store.save(job)
        write_json_artifact(self._job_dir(job.job_id) / "job.json", job)
        job = self.run_stages(job, self.stages)
        if job.status != JobStatus.FAILED:
            job.status = JobStatus.COMPLETED
            job.completed_at = self._now()
            job.current_stage = None
            job.error = None
            self.store.save(job)
            write_json_artifact(self._job_dir(job.job_id) / "job.json", job)
        return job

    # -- stage plumbing ------------------------------------------------------

    def _run_stage(self, stage: str, agent: StageAgent[Any, Any], job: VideoJob) -> Any:
        """Build the typed request for a stage and delegate to its agent."""
        if stage == STAGE_RESEARCH:
            return agent.run(ResearchRequest(topic=job.topic, niche=job.niche, audience=job.audience))
        if stage == STAGE_STRATEGY:
            if job.research is None:
                raise PipelineStageError(stage, "research result missing")
            return agent.run(job.research)
        if stage == STAGE_SCRIPT:
            if job.strategy is None:
                raise PipelineStageError(stage, "strategy result missing")
            return agent.run(job.strategy)
        if stage == STAGE_VISUAL_PLAN:
            if job.script is None:
                raise PipelineStageError(stage, "script result missing")
            return agent.run(job.script)
        if stage == STAGE_RENDER:
            if job.visual_plan is None:
                raise PipelineStageError(stage, "visual plan missing")
            visual_plan: VisualPlan = job.visual_plan
            request = ProductionRequest(
                job_id=job.job_id,
                visual_plan=visual_plan,
                output_path=str(self._job_dir(job.job_id) / "video.mp4"),
                render_config=self._render_config,
            )
            artifact = agent.run(request)
            if artifact.status != "completed":
                error = artifact.details.get("error") if artifact.details else None
                raise PipelineStageError(stage, error or f"render failed with status {artifact.status!r}")
            return artifact
        if stage == STAGE_QC:
            if job.script is None or job.visual_plan is None:
                raise PipelineStageError(stage, "script or visual plan missing for QC")
            from src.orchestration.qc.models import QCRequest

            request = QCRequest(
                job_id=job.job_id,
                script=job.script,
                visual_plan=job.visual_plan,
                artifact=job.artifact,
                render_config=dict(self._render_config),
                output_dir=str(self._job_dir(job.job_id)),
            )
            return agent.run(request)
        raise PipelineStageError(stage, f"unknown stage: {stage}")

    def _store_result(self, job: VideoJob, stage: str, result: Any) -> None:
        """Attach a stage result to the job and persist its artifact file."""
        job_dir = self._job_dir(job.job_id)
        record = self._stage_record(job, stage)

        if stage == STAGE_QC:
            self._store_qc_result(job, stage, result)
            return

        field_name = _STAGE_RESULT_FIELD[stage]
        setattr(job, field_name, result)

        if stage == STAGE_RENDER:
            artifact: VideoArtifact = result
            record.artifact_path = artifact.output_path or None
        else:
            artifact_path = write_json_artifact(job_dir / f"{stage}.json", result)
            record.artifact_path = str(artifact_path)

        record.status = StageStatus.SUCCEEDED
        record.finished_at = self._now()
        self.store.save(job)
        # Mirror the full serialized job next to the stage artifacts so every
        # job directory is self-describing (output/<job_id>/job.json).
        write_json_artifact(job_dir / "job.json", job)

    def _store_qc_result(self, job: VideoJob, stage: str, result: Any) -> None:
        """Persist a ``QCReport`` as ``qc_report.json`` and update job QC status.

        QC is a gate, not a stage failure: the render already produced a
        completed artifact.  The report is persisted and ``job.qc_status`` /
        ``job.qc_report_path`` reflect the outcome without altering
        ``job.status`` (which remains COMPLETED).
        """
        from src.orchestration.qc.agent import qc_job_status_for
        from src.orchestration.qc.models import QCReport

        report: QCReport = result
        job_dir = self._job_dir(job.job_id)
        report_path = write_json_artifact(job_dir / "qc_report.json", report)

        job.qc_status = qc_job_status_for(report)
        job.qc_report_path = str(report_path)

        record = self._stage_record(job, stage)
        record.artifact_path = str(report_path)
        record.status = StageStatus.SUCCEEDED
        record.finished_at = self._now()
        self.store.save(job)
        write_json_artifact(job_dir / "job.json", job)

    def _fail_job(self, job: VideoJob, stage: str, exc: Exception) -> None:
        """Record a failed stage, then persist the failed snapshot."""
        record = self._stage_record(job, stage)
        record.status = StageStatus.FAILED
        record.finished_at = self._now()
        record.error = str(exc)

        job.status = JobStatus.FAILED
        job.current_stage = stage or None
        job.completed_at = self._now()
        job.error = f"stage '{stage}' failed: {exc}"
        self.store.save(job)
        write_json_artifact(self._job_dir(job.job_id) / "job.json", job)
        return job

    # -- helpers -------------------------------------------------------------

    def _stage_record(self, job: VideoJob, stage: str) -> StageRecord:
        record = job.stages.get(stage)
        if record is None:
            record = StageRecord(stage=stage)
            job.stages[stage] = record
        return record

    def _job_dir(self, job_id: str) -> Path:
        return self.output_dir / job_id

    def _next_job_id(self) -> str:
        existing = set(self.store.list_job_ids())
        index = 1
        while f"job_{index:03d}" in existing:
            index += 1
        return f"job_{index:03d}"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)