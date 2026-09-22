"""YouTube publisher - mock and real adapter for publishing videos to YouTube.

Provides a single YouTubePublisher facade that can operate in two modes:

* Mock mode - deterministic, no network, no credentials. Used by
  --mock-publish and by tests.
* Real mode - uses the existing YouTubeUploadService + OAuth credentials
  loaded from environment variables. Used by --publish.

Also provides small persistence helpers used by PublishService and tests:

* write_publish_result(published, job_dir)
* load_publish_result(job_dir)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.orchestration.schemas.publish import (
    PublishedVideo,
    PublishRequest,
    PublishStatus,
    PublishVisibility,
)
from src.orchestration.schemas.production import VideoArtifact
from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.strategy import StrategyPackage
from src.services.youtube_upload_service import (
    OAuthCredentials,
    UploadRequest,
    YouTubeUploadError,
    YouTubeUploadService,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _deterministic_mock_video_id(job_id: str, video_path: str, title: str) -> str:
    """Derive a deterministic 11-char mock video ID from the publish inputs.

    Same (job_id, video_path, title) always yields the same ID.
    Different jobs yield different IDs.
    """
    digest = hashlib.sha256(
        ":".join([job_id, video_path, title]).encode("utf-8")
    ).hexdigest()
    return digest[:11]


def _normalize_video_path(video_path: str | None, artifact: VideoArtifact | None) -> str:
    """Pick the best available video path from the artifact or the passed argument."""
    if video_path:
        return str(video_path)
    if artifact is not None and artifact.output_path:
        return str(artifact.output_path)
    return ""


def _derive_title(
    strategy: StrategyPackage | None,
    script: ScriptPackage | None,
    topic: str,
) -> str:
    """Best-effort title fallback when title is not passed explicitly."""
    from src.orchestration.publish_metadata import generate_publish_metadata

    metadata = generate_publish_metadata(
        strategy=strategy, script=script, topic=topic
    )
    return metadata.get("title", topic.strip() or "Untitled Video")


def resolve_real_upload_visibility(
    visibility: PublishVisibility | str = PublishVisibility.UNLISTED,
    *,
    allow_public: bool = False,
) -> str:
    """Return the safe privacy status for a real upload.

    Day-7 safety rule: the first real upload MUST be ``unlisted``.
    ``public`` is only honoured when ``allow_public`` is explicitly True;
    otherwise any request (including ``public``) falls back to ``unlisted``.
    ``private`` is always honoured as-is.
    """
    requested = str(
        visibility.value if isinstance(visibility, PublishVisibility) else visibility
    ).lower()
    if requested == PublishVisibility.PUBLIC.value and not allow_public:
        logger.warning(
            "Public visibility requested without explicit opt-in; forcing unlisted."
        )
        return PublishVisibility.UNLISTED.value
    if requested in (
        PublishVisibility.PRIVATE.value,
        PublishVisibility.UNLISTED.value,
        PublishVisibility.PUBLIC.value,
    ):
        return requested
    logger.warning("Unknown visibility %r; forcing unlisted.", visibility)
    return PublishVisibility.UNLISTED.value


class YouTubePublisher:
    """Publishes rendered videos to YouTube (mock or real).

    Parameters
    ----------
    mock:
        If True, run in mock mode (no network, no credentials).
    credentials:
        Optional pre-built OAuthCredentials. When provided and mock is
        False, these are used instead of loading from the environment.
    """

    def __init__(
        self,
        *,
        mock: bool = False,
        credentials: OAuthCredentials | None = None,
    ) -> None:
        self.mock = mock
        self.credentials = credentials
        self.upload_called = False
        self._upload_attempts: list[dict[str, Any]] = []
        self._credentials_error: str | None = None
        if not self.mock:
            self._credentials: OAuthCredentials | None = credentials

    def publish(
        self,
        *,
        job_id: str,
        video_path: str,
        title: str = "",
        description: str = "",
        tags: list[str] | None = None,
        category_id: str = "22",
        visibility: str | PublishVisibility = PublishVisibility.UNLISTED,
        made_for_kids: bool = False,
        thumbnail_path: str | None = None,
        strategy: StrategyPackage | None = None,
        script: ScriptPackage | None = None,
        artifact: VideoArtifact | None = None,
        topic: str = "",
        qc_report: Any | None = None,
        upload_attempt: int = 1,
        artifact_path: str | None = None,
        qc_report_path: str | None = None,
        allow_public: bool = False,
    ) -> PublishedVideo:
        """Publish a video (mock or real) and return a PublishedVideo."""
        tags = tags or []
        video_path = _normalize_video_path(video_path, artifact)

        try:
            request = PublishRequest(
                job_id=job_id,
                video_path=video_path,
                title=title or _derive_title(strategy, script, topic),
                description=description,
                tags=tags,
                category_id=category_id,
                visibility=visibility if isinstance(visibility, PublishVisibility) else PublishVisibility(visibility),
                made_for_kids=made_for_kids,
                thumbnail_path=thumbnail_path,
                artifact_path=artifact_path,
                qc_report_path=qc_report_path,
            )
        except Exception as exc:
            return PublishedVideo(
                job_id=job_id, video_id=None, video_url=None,
                title=title or "Untitled Video",
                visibility=visibility if isinstance(visibility, PublishVisibility) else PublishVisibility.UNLISTED,
                status=PublishStatus.FAILED, error=f"Invalid publish request: {exc}",
            )

        if not video_path or not os.path.exists(video_path):
            return PublishedVideo(
                job_id=job_id, video_id=None, video_url=None,
                title=request.title, visibility=request.visibility,
                status=PublishStatus.FAILED, error=f"video_path does not exist: {video_path}",
            )

        if self.mock:
            return self._publish_mock(request=request, upload_attempt=upload_attempt)
        return self._publish_real(
            request=request, upload_attempt=upload_attempt, allow_public=allow_public
        )


    def _publish_mock(self, *, request: PublishRequest, upload_attempt: int = 1) -> PublishedVideo:
        """Deterministic mock publish. Never touches the network."""
        self.upload_called = True
        video_id = _deterministic_mock_video_id(
            request.job_id, request.video_path, request.title
        )
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        service_response: dict[str, Any] = {
            "status": "completed",
            "video_id": video_id,
            "video_url": video_url,
            "privacy_status": request.visibility.value,
            "mode": "mock",
            "mock_video_id": video_id,
        }

        published = PublishedVideo(
            job_id=request.job_id,
            video_id=video_id,
            video_url=video_url,
            title=request.title,
            visibility=request.visibility,
            status=PublishStatus.COMPLETED,
            published_at=_utcnow(),
            upload_attempt=upload_attempt,
            artifact_path=request.artifact_path,
            description=request.description,
            tags=request.tags,
            category_id=request.category_id,
            thumbnail_result=None,
            error=None,
            service_response=service_response,
        )

        self._upload_attempts.append(
            {
                "job_id": request.job_id,
                "video_id": video_id,
                "title": request.title,
                "video_path": request.video_path,
            }
        )
        logger.info(
            "Mock publish succeeded for job %s: video_id=%s", request.job_id, video_id
        )
        return published


    def _get_credentials(self) -> OAuthCredentials | None:
        """Load OAuth credentials for real publishing.

        On failure, a *safe* reason (variable names only, never secret values)
        is stored on ``self._credentials_error`` for the caller to surface.
        """
        self._credentials_error = None
        if self._credentials is not None:
            return self._credentials
        if self.credentials is not None:
            self._credentials = self.credentials
            return self._credentials
        try:
            self._credentials = OAuthCredentials.from_env()
            return self._credentials
        except YouTubeUploadError as exc:
            # from_env messages contain only variable names, never values.
            self._credentials_error = str(exc)
            logger.warning("Failed to load OAuth credentials from environment: %s", exc)
            return None
        except Exception as exc:
            self._credentials_error = "credentials could not be loaded"
            logger.warning("Failed to load OAuth credentials from environment: %s", exc)
            return None


    def _publish_real(
        self, *, request: PublishRequest, upload_attempt: int = 1, allow_public: bool = False
    ) -> PublishedVideo:
        """Real publish using the existing YouTubeUploadService."""
        credentials = self._get_credentials()
        if credentials is None:
            detail = self._credentials_error or "no YouTube OAuth configuration found"
            return PublishedVideo(
                job_id=request.job_id, video_id=None, video_url=None,
                title=request.title, visibility=request.visibility,
                status=PublishStatus.FAILED,
                error=f"OAuth credentials unavailable for real publish ({detail})",
            )

        try:
            upload_service = YouTubeUploadService(credentials=credentials)
        except Exception as exc:
            return PublishedVideo(
                job_id=request.job_id, video_id=None, video_url=None,
                title=request.title, visibility=request.visibility,
                status=PublishStatus.FAILED, error=f"Failed to build YouTube upload service: {exc}",
            )

        try:
            upload_request = UploadRequest(
                video_path=request.video_path,
                title=request.title,
                description=request.description,
                tags=request.tags,
                category_id=request.category_id,
                privacy_status=resolve_real_upload_visibility(
                    request.visibility, allow_public=allow_public
                ),
                made_for_kids=request.made_for_kids,
                thumbnail_path=request.thumbnail_path,
            )
        except Exception as exc:
            return PublishedVideo(
                job_id=request.job_id, video_id=None, video_url=None,
                title=request.title, visibility=request.visibility,
                status=PublishStatus.FAILED, error=f"Invalid upload request: {exc}",
            )

        try:
            response = upload_service.upload(upload_request)
        except YouTubeUploadError as exc:
            return PublishedVideo(
                job_id=request.job_id, video_id=None, video_url=None,
                title=request.title, visibility=request.visibility,
                status=PublishStatus.FAILED, error=f"YouTube upload failed: {exc}",
                service_response={"error": str(exc)},
            )
        except Exception as exc:
            return PublishedVideo(
                job_id=request.job_id, video_id=None, video_url=None,
                title=request.title, visibility=request.visibility,
                status=PublishStatus.FAILED, error=f"Unexpected upload error: {exc}",
                service_response={"error": str(exc)},
            )

        self.upload_called = True
        video_id = response.get("video_id")
        video_url = response.get("video_url")
        privacy_status = str(
            response.get("privacy_status")
            or resolve_real_upload_visibility(request.visibility, allow_public=allow_public)
        )
        try:
            resolved_visibility = PublishVisibility(privacy_status)
        except ValueError:
            resolved_visibility = PublishVisibility.UNLISTED

        if not video_id:
            return PublishedVideo(
                job_id=request.job_id, video_id=None, video_url=None,
                title=request.title, visibility=request.visibility,
                status=PublishStatus.FAILED, error=f"Upload returned no video id: {response}",
                service_response=response,
            )

        published = PublishedVideo(
            job_id=request.job_id,
            video_id=video_id,
            video_url=video_url,
            title=request.title,
            visibility=resolved_visibility,
            status=PublishStatus.COMPLETED,
            published_at=_utcnow(),
            upload_attempt=upload_attempt,
            artifact_path=request.artifact_path,
            description=request.description,
            tags=request.tags,
            category_id=request.category_id,
            thumbnail_result=response.get("thumbnail"),
            error=None,
            service_response={**response, "privacy_status": privacy_status},
        )

        logger.info(
            "Real publish succeeded for job %s: video_id=%s", request.job_id, video_id
        )
        return published


def _publish_result_path(job_dir: str | Path) -> Path:
    """Return the canonical path for a job's publish_result.json."""
    return Path(job_dir) / "publish_result.json"


def write_publish_result(published: PublishedVideo, job_dir: str | Path) -> Path:
    """Persist a PublishedVideo to ``<job_dir>/publish_result.json``."""
    path = _publish_result_path(job_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_id": published.job_id,
        "video_id": published.video_id,
        "video_url": published.video_url,
        "title": published.title,
        "visibility": published.visibility.value,
        "status": published.status.value,
        "published_at": published.published_at.isoformat() if published.published_at else None,
        "upload_attempt": published.upload_attempt,
        "artifact_path": published.artifact_path,
        "description": published.description,
        "tags": published.tags,
        "category_id": published.category_id,
        "thumbnail_result": published.thumbnail_result,
        "error": published.error,
        "service_response": published.service_response,
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def load_publish_result(job_dir: str | Path) -> PublishedVideo | None:
    """Load a PublishedVideo from ``<job_dir>/publish_result.json``.

    Returns None when the file is missing. Returns None for corrupted JSON
    (with a warning logged) so corruption is never treated as a successful
    publication.
    """
    path = _publish_result_path(job_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Corrupted publish_result.json at %s: %s", path, exc)
        return None
    return PublishedVideo(
        job_id=data.get("job_id", ""),
        video_id=data.get("video_id"),
        video_url=data.get("video_url"),
        title=data.get("title", ""),
        visibility=PublishVisibility(data.get("visibility", "private")),
        status=PublishStatus(data.get("status", "pending")),
        published_at=datetime.fromisoformat(data["published_at"]) if data.get("published_at") else None,
        upload_attempt=data.get("upload_attempt", 1),
        artifact_path=data.get("artifact_path"),
        description=data.get("description"),
        tags=data.get("tags"),
        category_id=data.get("category_id"),
        thumbnail_result=data.get("thumbnail_result"),
        error=data.get("error"),
        service_response=data.get("service_response"),
    )


# Global mock publisher instance for tests and CLI convenience.
_mock_publisher_instance: YouTubePublisher | None = None


def get_or_create_mock_publisher() -> YouTubePublisher:
    """Return the shared global mock publisher, creating it if needed."""
    global _mock_publisher_instance
    if _mock_publisher_instance is None:
        _mock_publisher_instance = YouTubePublisher(mock=True)
    return _mock_publisher_instance

