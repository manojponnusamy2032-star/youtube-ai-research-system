"""Dependency injection and runtime container for FastAPI API layer."""

from __future__ import annotations

import logging
import os
import threading
import uuid
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

from src.agents.analysis_agent import AnalysisAgent
from src.agents.collector_agent import CollectorAgent
from src.agents.content_generation_manager import ContentGenerationManager
from src.agents.hook_generator_agent import HookGeneratorAgent
from src.agents.knowledge_base_agent import KnowledgeBaseAgent
from src.agents.pattern_extractor_agent import PatternExtractorAgent
from src.agents.script_generator_agent import ScriptGeneratorAgent
from src.agents.seo_generator_agent import SeoGeneratorAgent
from src.agents.thumbnail_generator_agent import ThumbnailGeneratorAgent
from src.agents.title_generator_agent import TitleGeneratorAgent
from src.agents.transcript_agent import TranscriptAgent
from src.agents.workflow_manager_agent import WorkflowManagerAgent
from src.api.errors import APIConfigurationError
from src.core.agent_result import AgentResult
from src.core.context import WorkflowContext
from src.database.database_service import DatabaseService
from src.models.workflow_report import WorkflowMetrics
from src.services.analysis_service import AnalysisService, OllamaProvider
from src.services.content_generation_service import ContentGenerationService
from src.services.knowledge_service import KnowledgeService
from src.services.pattern_service import PatternService
from src.services.title_generation_service import TitleGenerationService
from src.services.script_service import ScriptService
from src.services.transcript_service import TranscriptService
from src.services.youtube_service import YouTubeService
from src.utils.logger import setup_logger

logger = logging.getLogger("yairs.api")


class APISettings(BaseModel):
    """Environment-backed API settings."""

    app_name: str = "YouTube AI Research System API"
    app_version: str = "1.0.0"
    environment: str = "production"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    api_key: str | None = None
    database_path: str = "data/database/youtube.db"
    youtube_api_key: str | None = None
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:latest"
    # runtime controls for workflow executor
    max_retries: int = 3
    stage_timeout_seconds: int = 60 * 10
    log_page_limit_default: int = 500

    @classmethod
    def from_env(cls) -> "APISettings":
        """Build settings from environment variables."""
        return cls(
            app_name=os.getenv("API_APP_NAME", "YouTube AI Research System API"),
            app_version=os.getenv("API_APP_VERSION", "1.0.0"),
            environment=os.getenv("API_ENV", "production"),
            host=os.getenv("API_HOST", "0.0.0.0"),
            port=int(os.getenv("API_PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            api_key=os.getenv("API_KEY"),
            database_path=os.getenv("DATABASE_PATH", "data/database/youtube.db"),
            youtube_api_key=os.getenv("YOUTUBE_API_KEY"),
            ollama_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:latest"),
            max_retries=int(os.getenv("WORKFLOW_MAX_RETRIES", "3")),
            stage_timeout_seconds=int(os.getenv("WORKFLOW_STAGE_TIMEOUT", str(60 * 10))),
            log_page_limit_default=int(os.getenv("WORKFLOW_LOG_PAGE_LIMIT", "500")),
        )


class WorkflowStore:
    """In-memory workflow status tracking."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}
        self._logs: dict[str, list[dict[str, Any]]] = {}

    def create(self, workflow_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Create workflow record in pending state."""
        workflow_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        record = {
            "workflow_id": workflow_id,
            "workflow_type": workflow_type,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "payload": payload,
            "result": None,
            "error": None,
        }
        with self._lock:
            self._records[workflow_id] = record
        return record

    def update(self, workflow_id: str, **changes: Any) -> dict[str, Any]:
        """Update workflow record and timestamp."""
        with self._lock:
            if workflow_id not in self._records:
                raise KeyError(workflow_id)
            self._records[workflow_id].update(changes)
            self._records[workflow_id]["updated_at"] = datetime.now(timezone.utc)
            return dict(self._records[workflow_id])

    def get(self, workflow_id: str) -> dict[str, Any] | None:
        """Get workflow record by id."""
        with self._lock:
            record = self._records.get(workflow_id)
            return dict(record) if record else None

    def metrics(self) -> dict[str, int]:
        """Aggregate workflow counters."""
        with self._lock:
            statuses = [record["status"] for record in self._records.values()]
        return {
            "workflows_total": len(statuses),
            "workflows_running": len([item for item in statuses if item == "running"]),
            "workflows_completed": len([item for item in statuses if item == "completed"]),
            "workflows_failed": len([item for item in statuses if item == "failed"]),
        }

    def insert_log(self, workflow_id: str, level: str, message: str, stage: str | None = None, status: str | None = None, error_text: str | None = None) -> int:
        """Store a log entry in-memory for the workflow. Returns index."""
        with self._lock:
            entry = {
                "workflow_id": workflow_id,
                "stage": stage,
                "status": status,
                "level": level,
                "message": message,
                "error_text": error_text,
            }
            self._logs.setdefault(workflow_id, []).append(entry)
            return len(self._logs[workflow_id]) - 1

    def get_logs(self, workflow_id: str, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            entries = list(self._logs.get(workflow_id, []))
            return entries[:limit]


@dataclass
class APIContainer:
    """Container that wires database, services, and agents."""

    settings: APISettings
    database_service: DatabaseService
    youtube_service: YouTubeService | None
    pattern_service: PatternService
    knowledge_service: KnowledgeService
    title_generation_service: TitleGenerationService
    content_generation_service: ContentGenerationService
    workflow_manager_agent: WorkflowManagerAgent
    content_generation_manager: ContentGenerationManager


class ResearchWorkflowExecutor:
    """Executes research workflows in background tasks."""

    def __init__(self, workflow_manager: WorkflowManagerAgent, workflow_store: WorkflowStore) -> None:
        self.workflow_manager = workflow_manager
        self.workflow_store = workflow_store

    def run(self, workflow_id: str, payload: dict[str, Any]) -> None:
        """Execute workflow stage-by-stage, persisting state after each stage, with retries and timeouts.

        This method reuses WorkflowManagerAgent._build_stage_calls to obtain per-stage callables and
        metric updaters, but performs execution itself to enable per-stage persistence, logging, retries,
        and progress tracking.
        """
        # initial persistence: mark running
        now = datetime.now(timezone.utc)
        try:
            self.workflow_store.update(workflow_id, status="running", started_at=now)
        except Exception:
            # fallback for in-memory store
            try:
                self.workflow_store.update(workflow_id, status="running")
            except Exception:
                pass

        context = WorkflowContext(payload)
        continue_on_error = bool(context.get("continue_on_error", False))
        # config for retries/timeouts - read from settings if available
        try:
            settings = get_settings()
            max_retries = int(getattr(settings, "max_retries", 3))
            stage_timeout_seconds = int(getattr(settings, "stage_timeout_seconds", 60 * 10))
        except Exception:
            max_retries = 3
            stage_timeout_seconds = 60 * 10  # 10 minutes per stage default
        total_stages = 0

        try:
            # Build stage callables and updaters
            metrics = None
            try:
                # Attempt to build using internal helper if available
                metrics = WorkflowMetrics()
                stages = self.workflow_manager._build_stage_calls(context, metrics)
            except Exception:
                # Fallback: call run() and persist result as single-stage
                result = self.workflow_manager.run(context)
                if isinstance(result, AgentResult):
                    if result.success:
                        self.workflow_store.update(workflow_id, status="completed", completed_at=datetime.now(timezone.utc), result=result.data)
                    else:
                        self.workflow_store.update(workflow_id, status="failed", completed_at=datetime.now(timezone.utc), error=result.message or "Workflow failed", result=result.data)
                else:
                    self.workflow_store.update(workflow_id, status="completed", completed_at=datetime.now(timezone.utc), result={"raw_result": result})
                return

            total_stages = len(stages)
            current_index = 0
            for name, call, update_metrics in stages:
                current_index += 1
                # set current stage info
                self.workflow_store.update(workflow_id, current_stage=name, progress_percentage=int((current_index - 1) / max(1, total_stages) * 100))
                insert_log = getattr(self.workflow_store, "insert_log", None)
                if callable(insert_log):
                    insert_log(workflow_id, "INFO", f"Starting stage {name} ({current_index}/{total_stages})", stage=name, status="starting")

                attempt = 0
                while True:
                    attempt += 1
                    stage_start = datetime.now(timezone.utc)
                    try:
                        # execute stage
                        result = call()
                        duration = (datetime.now(timezone.utc) - stage_start).total_seconds()

                        # update metrics and context
                        try:
                            update_metrics(result, context)
                        except Exception:
                            # metric update should not fail the workflow
                            logger.exception("Metric updater for stage %s failed", name)

                        # persist progress and counts
                        processed = int(context.get("processed_videos", 0)) if context.get("processed_videos") is not None else None
                        failed = int(context.get("failed_videos", 0)) if context.get("failed_videos") is not None else None
                        progress = int((current_index / max(1, total_stages)) * 100)
                        updates = {"current_stage": name, "progress_percentage": progress, "last_stage_at": datetime.now(timezone.utc), "duration_seconds": duration}
                        if processed is not None:
                            updates["processed_videos"] = processed
                        if failed is not None:
                            updates["failed_videos"] = failed
                        self.workflow_store.update(workflow_id, **updates)

                        # log success
                        insert_log = getattr(self.workflow_store, "insert_log", None)
                        if callable(insert_log):
                            insert_log(workflow_id, "INFO", f"Completed stage {name} in {duration:.2f}s", stage=name, status="completed")
                        break
                    except Exception as e:
                        # Determine if retryable - treat as retryable unless max attempts reached
                        is_retryable = attempt < max_retries
                        insert_log = getattr(self.workflow_store, "insert_log", None)
                        if callable(insert_log):
                            insert_log(workflow_id, "ERROR", f"Stage {name} failed on attempt {attempt}: {e}", stage=name, status="error", error_text=str(e))
                        # increment retry_count
                        # read current retry_count
                        try:
                            current = self.workflow_store.get(workflow_id).get("retry_count") or 0
                        except Exception:
                            current = 0
                        try:
                            self.workflow_store.update(workflow_id, retry_count=int(current) + 1)
                        except Exception:
                            pass

                        if is_retryable:
                            backoff = 2 ** (attempt - 1)
                            insert_log = getattr(self.workflow_store, "insert_log", None)
                            if callable(insert_log):
                                insert_log(workflow_id, "WARNING", f"Retrying stage {name} after {backoff}s (attempt {attempt})", stage=name, status="retry")
                            import time as _time

                            _time.sleep(backoff)
                            continue
                        else:
                            # final failure
                            self.workflow_store.update(workflow_id, status="failed", completed_at=datetime.now(timezone.utc), error=str(e))
                            insert_log = getattr(self.workflow_store, "insert_log", None)
                            if callable(insert_log):
                                insert_log(workflow_id, "CRITICAL", f"Stage {name} permanently failed: {e}", stage=name, status="failed", error_text=str(e))
                            # Stop workflow
                            return

            # all stages completed
            self.workflow_store.update(workflow_id, status="completed", completed_at=datetime.now(timezone.utc))
            insert_log = getattr(self.workflow_store, "insert_log", None)
            if callable(insert_log):
                insert_log(workflow_id, "INFO", "Workflow completed", stage="workflow", status="completed")
        except Exception as error:
            logger.exception("Background research workflow failed")
            try:
                self.workflow_store.update(workflow_id, status="failed", completed_at=datetime.now(timezone.utc), error=str(error))
            except Exception:
                pass
            try:
                self.workflow_store.insert_log(workflow_id, "CRITICAL", "Workflow crashed: %s" % str(error), stage="workflow", status="failed", error_text=str(error))
            except Exception:
                pass


@lru_cache(maxsize=1)
def get_settings() -> APISettings:
    """Return singleton API settings."""
    settings = APISettings.from_env()
    setup_logger(
        name="yairs",
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        log_file=os.getenv("LOG_FILE", "logs/yairs.log"),
        console_output=True,
    )
    return settings


@lru_cache(maxsize=1)
def get_container() -> APIContainer:
    """Create and cache runtime container."""
    settings = get_settings()
    database_service = DatabaseService(settings.database_path)
    database_service.connect()
    database_service.create_tables()

    pattern_service = PatternService(database_service)
    knowledge_service = KnowledgeService(database_service)
    title_generation_service = TitleGenerationService(database_service, knowledge_service, pattern_service)
    transcript_service = TranscriptService(database_service)
    analysis_service = AnalysisService(
        llm_provider=OllamaProvider(base_url=settings.ollama_url, model=settings.ollama_model),
        database_service=database_service,
    )
    # instantiate auxiliary services and wire into content generation service
    script_service = ScriptService(analysis_service)
    content_generation_service = ContentGenerationService(database_service, title_service=title_generation_service, script_service=script_service)

    if not settings.youtube_api_key:
        youtube_service = None
    else:
        youtube_service = YouTubeService(settings.youtube_api_key)

    if youtube_service is None:
        collector_agent = _MissingCollectorAgent()
    else:
        collector_agent = CollectorAgent(youtube_service, database_service)

    transcript_agent = TranscriptAgent(transcript_service, database_service)
    analysis_agent = AnalysisAgent(analysis_service, database_service)
    pattern_extractor_agent = PatternExtractorAgent(pattern_service, database_service)
    knowledge_base_agent = KnowledgeBaseAgent(database_service, knowledge_service)
    title_generator_agent = TitleGeneratorAgent(title_generation_service, database_service)

    hook_agent = HookGeneratorAgent(content_generation_service)
    thumbnail_agent = ThumbnailGeneratorAgent(content_generation_service)
    script_agent = ScriptGeneratorAgent(content_generation_service)
    seo_agent = SeoGeneratorAgent(content_generation_service)
    from src.agents.render_job_manager import RenderJobManager
    from src.agents.render_job_executor import RenderJobExecutor
    from src.agents.render_output_manager import RenderOutputManager
    from src.agents.render_pipeline_orchestrator import RenderPipelineOrchestrator
    from src.services.final_media_orchestrator import FinalMediaOrchestrator
    from src.services.video_assembler import VideoAssembler
    from src.services.media_muxer import MediaMuxer
    from src.services.tts_service import MockTTSService
    from src.services.tts_audio_renderer import TTSAudioRenderer

    tts_service = MockTTSService()
    tts_audio_renderer = TTSAudioRenderer(tts_service=tts_service)

    final_media_orchestrator = FinalMediaOrchestrator(
        video_assembler=VideoAssembler(),
        audio_renderer=tts_audio_renderer,
        media_muxer=MediaMuxer(),
    )

    render_pipeline_orchestrator = RenderPipelineOrchestrator(
        render_job_manager=RenderJobManager(),
        render_job_executor=RenderJobExecutor(audio_renderer=tts_audio_renderer),
        render_output_manager=RenderOutputManager(),
        final_media_orchestrator=final_media_orchestrator,
    )

    content_generation_manager = ContentGenerationManager(
        hook_generator_agent=hook_agent,
        thumbnail_generator_agent=thumbnail_agent,
        script_generator_agent=script_agent,
        seo_generator_agent=seo_agent,
        content_generation_service=content_generation_service,
        render_pipeline_orchestrator=render_pipeline_orchestrator,
    )

    workflow_manager_agent = WorkflowManagerAgent(
        collector_agent=collector_agent,
        transcript_agent=transcript_agent,
        analysis_agent=analysis_agent,
        pattern_extractor_agent=pattern_extractor_agent,
        knowledge_base_agent=knowledge_base_agent,
        title_generator_agent=title_generator_agent,
        content_generation_manager=content_generation_manager,
    )

    return APIContainer(
        settings=settings,
        database_service=database_service,
        youtube_service=youtube_service,
        pattern_service=pattern_service,
        knowledge_service=knowledge_service,
        title_generation_service=title_generation_service,
        content_generation_service=content_generation_service,
        workflow_manager_agent=workflow_manager_agent,
        content_generation_manager=content_generation_manager,
    )


class DBWorkflowStore:
    """Database-backed workflow store using DatabaseService.workflows table."""

    def __init__(self, database_service: DatabaseService) -> None:
        self.db = database_service

    def create(self, workflow_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        workflow_id = str(uuid.uuid4())
        # persist
        self.db.create_workflow_record(workflow_id, workflow_type, payload)
        now = datetime.now(timezone.utc)
        return {
            "workflow_id": workflow_id,
            "workflow_type": workflow_type,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "payload": payload,
            "result": None,
            "error": None,
        }

    def update(self, workflow_id: str, **changes: Any) -> dict[str, Any]:
        self.db.update_workflow_record(workflow_id, **changes)
        return self.get(workflow_id) or {}

    def get(self, workflow_id: str) -> dict[str, Any] | None:
        row = self.db.get_workflow_record(workflow_id)
        if not row:
            return None
        # Convert json fields back to objects where applicable
        payload = row.get("payload") if row.get("payload") is not None else (json.loads(row.get("payload_json")) if row.get("payload_json") else None)
        result = row.get("result") if row.get("result") is not None else (json.loads(row.get("result_json")) if row.get("result_json") else None)
        return {
            "workflow_id": row.get("workflow_id"),
            "workflow_type": row.get("workflow_type"),
            "status": row.get("status"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "completed_at": row.get("completed_at"),
            "payload": payload,
            "result": result,
            "error": row.get("error_text"),
            "progress_percentage": row.get("progress_percentage"),
            "current_stage": row.get("current_stage"),
            "processed_videos": row.get("processed_videos"),
            "failed_videos": row.get("failed_videos"),
            "started_at": row.get("started_at"),
            "duration_seconds": row.get("duration_seconds"),
            "retry_count": row.get("retry_count"),
            "timeout_reason": row.get("timeout_reason"),
        }

    def insert_log(self, workflow_id: str, level: str, message: str, stage: str | None = None, status: str | None = None, error_text: str | None = None) -> int:
        """Insert a workflow-level log entry."""
        return self.db.insert_workflow_log(workflow_id, level, message, stage=stage, status=status, error_text=error_text)

    def get_logs(self, workflow_id: str, limit: int = 500, offset: int = 0, stage: str | None = None, start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
        """Return workflow logs for a workflow id with pagination and optional filters."""
        return self.db.get_workflow_logs(workflow_id, limit=limit, offset=offset, stage=stage, start_date=start_date, end_date=end_date)

    def metrics(self) -> dict[str, int]:
        """Return aggregated counts for workflows."""
        counts = {
            'workflows_total': 0,
            'workflows_running': 0,
            'workflows_completed': 0,
            'workflows_failed': 0,
        }
        try:
            cursor = self.db.connection.cursor()
            cursor.execute("SELECT status, COUNT(*) FROM workflows GROUP BY status")
            for status, count in cursor.fetchall():
                if status == 'running':
                    counts['workflows_running'] = count
                elif status == 'completed':
                    counts['workflows_completed'] = count
                elif status == 'failed':
                    counts['workflows_failed'] = count
                counts['workflows_total'] += count
        except Exception:
            logger.exception('Failed to read workflow metrics from database')
        return counts


@lru_cache(maxsize=1)
def get_workflow_store() -> WorkflowStore | DBWorkflowStore:
    """Return singleton workflow status store.

    Prefer database-backed store when a database service is available; otherwise fall back
    to the original in-memory WorkflowStore. This preserves behavior while making
    workflows durable in production.
    """
    try:
        container = get_container()
        if container and container.database_service:
            return DBWorkflowStore(container.database_service)
    except Exception:
        # Fall back to in-memory store if anything goes wrong constructing DB store
        pass
    return WorkflowStore()


def get_workflow_executor() -> ResearchWorkflowExecutor:
    """Provide workflow executor for background tasks."""
    container = get_container()
    return ResearchWorkflowExecutor(container.workflow_manager_agent, get_workflow_store())


def get_database_service() -> DatabaseService:
    """Provide initialized database service."""
    return get_container().database_service


def get_pattern_service() -> PatternService:
    """Provide pattern service."""
    return get_container().pattern_service


def get_knowledge_service() -> KnowledgeService:
    """Provide knowledge service."""
    return get_container().knowledge_service


def get_title_generation_service() -> TitleGenerationService:
    """Provide title generation service."""
    return get_container().title_generation_service


def get_content_generation_service() -> ContentGenerationService:
    """Provide content generation service."""
    return get_container().content_generation_service


def get_content_generation_manager() -> ContentGenerationManager:
    """Provide content generation manager."""
    return get_container().content_generation_manager


class _MissingCollectorAgent:
    """Fallback collector when YOUTUBE_API_KEY is not configured."""

    def run(self, keyword: str, max_results: int = 50) -> tuple[int, int]:
        raise APIConfigurationError("YOUTUBE_API_KEY is required to run /research workflow")
