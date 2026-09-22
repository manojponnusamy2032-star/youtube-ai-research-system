"""Publish service - orchestrates the publish flow for a VideoJob.

Coordinates:
    1. Check for existing publish (idempotency)
    2. Evaluate publish gate (QC + video validation)
    3. Generate metadata from YAIRS artifacts
    4. Execute publish (mock or real)
    5. Persist publish_result.json
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.orchestration.publish_gate import evaluate_publish_gate
from src.orchestration.qc.models import QCReport
from src.orchestration.schemas.job import VideoJob
from src.orchestration.schemas.publish import (
    PublishedVideo,
    PublishStatus,
    PublishVisibility,
)
from src.orchestration.youtube_publisher import (
    YouTubePublisher,
    load_publish_result,
    write_publish_result,
)

logger = logging.getLogger(__name__)


class PublishService:
    """Service that orchestrates the publish flow for a VideoJob."""

    def __init__(
        self,
        publisher: YouTubePublisher | None = None,
        mock: bool = False,
        output_dir: str | Path = "output",
        visibility: PublishVisibility | str = PublishVisibility.UNLISTED,
        allow_public: bool = False,
    ) -> None:
        """Initialize the publish service.

        Args:
            publisher: Optional YouTubePublisher instance.
            mock: If True and no publisher given, use mock mode.
            output_dir: Root output directory for job artifacts.
            visibility: Requested privacy for real uploads. Day-7 safety:
                public is only honoured when ``allow_public`` is True,
                otherwise it falls back to unlisted.
            allow_public: Explicit opt-in for public uploads.
        """
        if publisher is not None:
            self._publisher = publisher
        else:
            self._publisher = YouTubePublisher(mock=mock)

        self._output_dir = Path(output_dir)
        self._visibility = visibility
        self._allow_public = allow_public

    def publish(
        self,
        job: VideoJob,
        qc_report: QCReport,
        *,
        skip_publish: bool = False,
        title: str | None = None,
        description: str | None = None,
    ) -> tuple[Any, PublishedVideo | None]:
        """Attempt to publish a job's video to YouTube.

        This method:
        1. Checks for existing publish (idempotency)
        2. Evaluates the publish gate (QC + video validation)
        3. If allowed, executes the publish
        4. Persists the result

        Args:
            job: The video job to publish.
            qc_report: The final QC report.
            skip_publish: If True, explicitly disable publishing.
            title: Optional explicit title override (used by the Day-7
                controlled verification upload). Falls back to metadata
                derived from the job artifacts when None/empty.
            description: Optional explicit description override.

        Returns:
            Tuple of (gate_result, published_video or None).
        """
        # 1. Check for existing publish (idempotency)
        existing = self.get_existing_publish(job)

        # 2. Evaluate publish gate
        artifact = job.artifact
        video_path = None
        if artifact is not None:
            video_path = artifact.output_path or None

        gate_result = evaluate_publish_gate(
            job_id=job.job_id,
            qc_report=qc_report,
            video_path=video_path,
            existing_publish=existing,
            skip_publish=skip_publish,
        )

        # 3. If not allowed, return early
        if not gate_result.allowed:
            logger.info(f"Publish gate blocked for job {job.job_id}: {gate_result.reason}")
            return gate_result, None

        # 4. If we have an existing successful publish, return it
        if existing is not None and existing.status == PublishStatus.COMPLETED:
            logger.info(
                f"Returning existing publish for job {job.job_id}: "
                f"{existing.video_id}"
            )
            return gate_result, existing

        # 5. Execute publish
        logger.info(f"Publishing job {job.job_id} to YouTube...")

        # Get metadata sources from job
        strategy = job.strategy
        script = job.script
        topic = job.topic

        published = self._publisher.publish(
            job_id=job.job_id,
            video_path=video_path or "",
            title=title or "",
            description=description or "",
            strategy=strategy,
            script=script,
            artifact=artifact,
            topic=topic,
            qc_report=qc_report,
            visibility=(
                self._visibility.value
                if isinstance(self._visibility, PublishVisibility)
                else self._visibility
            ),
            allow_public=self._allow_public,
            artifact_path=video_path,
            qc_report_path=job.qc_report_path,
            upload_attempt=1,
        )

        # 6. Persist result
        if published.status == PublishStatus.COMPLETED:
            job_dir = self._output_dir / job.job_id
            write_publish_result(published, job_dir)
            logger.info(
                f"Successfully published job {job.job_id}: "
                f"video_id={published.video_id}, url={published.video_url}"
            )
        else:
            logger.warning(
                f"Publish failed for job {job.job_id}: {published.error}"
            )

        return gate_result, published

    def get_job_dir(self, job_id: str) -> Path:
        """Get the job output directory."""
        return self._output_dir / job_id

    @property
    def publisher(self) -> YouTubePublisher:
        """The underlying YouTube publisher."""
        return self._publisher

    @property
    def mock(self) -> bool:
        """Whether publishing is in mock mode."""
        return self._publisher.mock

    def get_existing_publish(self, job: VideoJob) -> PublishedVideo | None:
        """Check for existing publish result for this job (idempotency).

        Args:
            job: The video job to check.

        Returns:
            Existing PublishedVideo if found, None otherwise.
        """
        job_dir = self._output_dir / job.job_id
        return load_publish_result(job_dir)