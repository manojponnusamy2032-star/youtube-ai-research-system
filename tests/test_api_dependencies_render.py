"""Tests for render pipeline dependency injection."""

from src.api.dependencies import get_container
from src.agents.render_pipeline_orchestrator import RenderPipelineOrchestrator
from src.services.final_media_orchestrator import FinalMediaOrchestrator

def test_container_provides_render_pipeline_orchestrator():
    """Verify that get_container() wires the render pipeline orchestrator with a final media orchestrator."""
    container = get_container()
    
    # Check that ContentGenerationManager has the pipeline orchestrator injected
    assert container.content_generation_manager.render_pipeline_orchestrator is not None
    assert isinstance(container.content_generation_manager.render_pipeline_orchestrator, RenderPipelineOrchestrator)
    
    # Check that RenderPipelineOrchestrator has the FinalMediaOrchestrator injected
    render_orchestrator = container.content_generation_manager.render_pipeline_orchestrator
    assert render_orchestrator.final_media_orchestrator is not None
    assert isinstance(render_orchestrator.final_media_orchestrator, FinalMediaOrchestrator)
