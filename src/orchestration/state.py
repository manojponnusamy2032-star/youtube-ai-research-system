"""Video job state persistence (Principle 2).

``VideoJobStore`` persists ``VideoJob`` objects as JSON files under an output
root (``output/jobs/`` by default).  JSON keeps the state human-readable,
dependency-free and trivially swappable for SQLite later behind this same
interface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.orchestration.schemas.job import VideoJob


def write_json_artifact(path: str | Path, payload: Any) -> Path:
    """Write an arbitrary JSON-serializable payload to a file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(payload, "model_dump"):
        text = json.dumps(payload.model_dump(mode="json"), indent=2, ensure_ascii=False)
    else:
        text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    target.write_text(text, encoding="utf-8")
    return target


class VideoJobStore:
    """JSON-file backed store for VideoJob state snapshots."""

    def __init__(self, root_dir: str | Path = "output/jobs") -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def job_path(self, job_id: str) -> Path:
        """Return the filesystem path for a job id."""
        return self.root_dir / f"{job_id}.json"

    def save(self, job: VideoJob) -> Path:
        """Persist a job snapshot and return its path."""
        path = self.job_path(job.job_id)
        path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        job.updated_at  # noqa: B018 -- touch access for clarity in debuggers
        return path

    def load(self, job_id: str) -> VideoJob | None:
        """Load a previously saved job, or None when it does not exist."""
        path = self.job_path(job_id)
        if not path.exists():
            return None
        return VideoJob.model_validate_json(path.read_text(encoding="utf-8"))

    def list_job_ids(self) -> list[str]:
        """Return all persisted job ids sorted by name."""
        ids = [p.stem for p in self.root_dir.glob("*.json") if p.suffix == ".json"]
        return sorted(ids)