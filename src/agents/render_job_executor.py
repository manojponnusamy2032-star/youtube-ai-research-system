"""Render Job Executor Agent.

Executes render jobs using a renderer abstraction and collects results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.agent_result import AgentResult
from src.core.base_agent import BaseAgent
from src.core.context import WorkflowContext
from src.models.content_package import AudioRequest, RenderConfig
from src.services.audio_renderer import AudioRenderRequest, AudioRenderer
from src.services.render_asset_resolver import RenderAssetResolver


@dataclass
class RenderRequest:
    """Request object passed to renderers containing all necessary context."""
    
    job: dict[str, Any]
    render_config: RenderConfig = field(default_factory=RenderConfig)
    resolved_assets: list[str] = field(default_factory=list)
    resolved_characters: list[str] = field(default_factory=list)


class Renderer:
    """Abstract base class for renderers."""

    def render(self, request: RenderRequest) -> dict[str, Any]:
        """Render a single job.
        
        Args:
            request: Render request containing job, config, and resolved assets
            
        Returns:
            Result dictionary with job_id, status, output_reference, duration_seconds
        """
        raise NotImplementedError


class MockRenderer(Renderer):
    """Deterministic mock renderer for testing.
    
    Does not perform actual rendering. Returns deterministic mock results.
    """

    def render(self, request: RenderRequest) -> dict[str, Any]:
        """Create a deterministic mock render result.
        
        Args:
            request: Render request containing job and configuration
            
        Returns:
            Mock result with job_id, status, output_reference, duration_seconds
        """
        job_id = str(request.job["job_id"])
        duration = int(request.job.get("duration_seconds", 0))
        scene_number = request.job.get("scene_number")
        
        return {
            "job_id": job_id,
            "status": "completed",
            "output_reference": f"mock://render/{job_id}",
            "duration_seconds": duration,
            "scene_number": scene_number,
        }


class RenderJobExecutor(BaseAgent):
    """Executes render jobs using a renderer and collects results."""

    def __init__(
        self,
        renderer: Renderer | None = None,
        asset_resolver: RenderAssetResolver | None = None,
        audio_renderer: AudioRenderer | None = None,
    ) -> None:
        super().__init__("RenderJobExecutor")
        self.renderer = renderer or MockRenderer()
        self.asset_resolver = asset_resolver
        self.audio_renderer = audio_renderer

    def run(self, context: WorkflowContext) -> AgentResult:
        """Execute all render jobs and collect results.
        
        Args:
            context: Workflow context containing render_jobs
            
        Returns:
            AgentResult with render_results list or error message
        """
        self.start()
        self._context = context
        
        # Step 1: Validate render_jobs exists
        if not context.has("render_jobs"):
            self.finish()
            return AgentResult.fail("render_jobs not found in workflow context")
        
        render_jobs = context.get("render_jobs")
        
        # Step 2: Validate render_jobs is a list
        if not isinstance(render_jobs, list):
            self.finish()
            return AgentResult.fail("render_jobs must be a list")
        
        # Step 3: Validate each job has job_id
        validation_errors = self._validate_jobs(render_jobs)
        if validation_errors:
            self.finish()
            return AgentResult.fail(f"Invalid render jobs: {'; '.join(validation_errors)}")
        
        # Step 4: Execute jobs and collect results
        render_results = self._execute_jobs(render_jobs)
        
        # Step 5: Store results in context
        context.set("render_results", render_results)
        
        successful = sum(1 for r in render_results if r["status"] == "completed")
        failed = sum(1 for r in render_results if r["status"] == "failed")
        
        self.log(f"Executed {len(render_results)} render jobs: {successful} succeeded, {failed} failed")
        self.finish()
        
        return AgentResult.ok(
            render_results=render_results,
            total_jobs=len(render_results),
            successful_jobs=successful,
            failed_jobs=failed,
        )

    def _validate_jobs(self, render_jobs: list[dict[str, Any]]) -> list[str]:
        """Validate all render jobs.
        
        Args:
            render_jobs: List of render job dictionaries
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        for idx, job in enumerate(render_jobs):
            job_prefix = f"Job {idx}"
            
            if not isinstance(job, dict):
                errors.append(f"{job_prefix}: must be a dictionary")
                continue
            
            if "job_id" not in job:
                errors.append(f"{job_prefix}: missing job_id")
            elif not str(job["job_id"]).strip():
                errors.append(f"{job_prefix}: job_id cannot be empty")
        
        return errors

    def _execute_jobs(self, render_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute all render jobs through the renderer.
        
        Args:
            render_jobs: List of validated render job dictionaries
            
        Returns:
            List of render result dictionaries
        """
        results = []
        
        # Get render_config from context if available
        render_config = self._get_render_config()
        
        for job in render_jobs:
            try:
                # Resolve assets and characters if resolver is available
                resolved_assets = self._resolve_assets(job)
                resolved_characters = self._resolve_characters(job)
                
                # Construct render request
                request = RenderRequest(
                    job=job,
                    render_config=render_config,
                    resolved_assets=resolved_assets,
                    resolved_characters=resolved_characters,
                )
                
                result = self.renderer.render(request)

                # Optionally render audio for this job if an audio_request
                # is present and an audio renderer is configured.
                if self.audio_renderer is not None and "audio_request" in job:
                    result["audio_result"] = self._render_audio(job)

                results.append(result)
            except Exception as e:
                # Record failure but continue with other jobs
                results.append({
                    "job_id": str(job.get("job_id", f"unknown-{len(results)}")),
                    "status": "failed",
                    "output_reference": None,
                    "duration_seconds": 0,
                    "error": str(e),
                })
        
        return results
    
    def _render_audio(self, job: dict[str, Any]) -> dict[str, Any]:
        """Render audio for a single job using the audio renderer.

        Args:
            job: Render job dictionary containing an audio_request.

        Returns:
            Audio render result dictionary. On failure, returns a structured
            error result without raising.
        """
        audio_request = job.get("audio_request")
        if not isinstance(audio_request, AudioRequest):
            return {
                "status": "failed",
                "error": "audio_request must be an AudioRequest",
            }

        try:
            audio_render_request = AudioRenderRequest(
                audio_request=audio_request,
                job=job,
            )
            return self.audio_renderer.render(audio_render_request)  # type: ignore[union-attr]
        except Exception as e:
            return {
                "status": "failed",
                "error": f"Audio rendering failed: {str(e)}",
            }

    def _get_render_config(self) -> RenderConfig:
        """Get render configuration from context or use default.
        
        Returns:
            RenderConfig instance
        """
        # Try to get render_config from context
        render_config_data = self._context.get("render_config")
        if render_config_data is not None:
            if isinstance(render_config_data, RenderConfig):
                return render_config_data
            elif isinstance(render_config_data, dict):
                try:
                    return RenderConfig(**render_config_data)
                except Exception:
                    pass
        
        # Fallback to default RenderConfig
        return RenderConfig()
    
    def _resolve_assets(self, job: dict[str, Any]) -> list[str]:
        """Resolve asset IDs to paths using the asset resolver.
        
        Args:
            job: Render job dictionary
            
        Returns:
            List of resolved asset paths
        """
        if self.asset_resolver is None:
            return []
        
        asset_ids = job.get("asset_ids", [])
        if not isinstance(asset_ids, list):
            return []
        
        resolved = []
        for asset_id in asset_ids:
            try:
                resolved_path = self.asset_resolver.resolve_asset(str(asset_id))
                resolved.append(resolved_path)
            except Exception:
                # Skip invalid asset IDs
                pass
        
        return resolved
    
    def _resolve_characters(self, job: dict[str, Any]) -> list[str]:
        """Resolve character IDs to paths using the asset resolver.
        
        Args:
            job: Render job dictionary
            
        Returns:
            List of resolved character paths
        """
        if self.asset_resolver is None:
            return []
        
        character_ids = job.get("character_ids", [])
        if not isinstance(character_ids, list):
            return []
        
        resolved = []
        for character_id in character_ids:
            try:
                resolved_path = self.asset_resolver.resolve_character(str(character_id))
                resolved.append(resolved_path)
            except Exception:
                # Skip invalid character IDs
                pass
        
        return resolved
