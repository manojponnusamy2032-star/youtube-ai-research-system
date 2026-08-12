"""Research workflow routes."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
import json

from src.api.auth import require_api_key
from src.api.dependencies import ResearchWorkflowExecutor, get_workflow_executor, get_workflow_store, get_database_service
from src.api.schemas.research import ResearchRequest, WorkflowAcceptedResponse, WorkflowStatusResponse
from src.api.schemas.content import WorkflowLogsResponse, WorkflowLogEntry
from src.database.database_service import DatabaseService

router = APIRouter(tags=["Research"], dependencies=[Depends(require_api_key)])


@router.post(
    "/research",
    response_model=WorkflowAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run full research workflow",
)
def run_research_workflow(
    payload: ResearchRequest,
    background_tasks: BackgroundTasks,
    executor: ResearchWorkflowExecutor = Depends(get_workflow_executor),
) -> WorkflowAcceptedResponse:
    """Schedule full research workflow in the background."""
    workflow_store = get_workflow_store()
    record = workflow_store.create("research", payload.model_dump())
    background_tasks.add_task(executor.run, record["workflow_id"], payload.model_dump())
    return WorkflowAcceptedResponse(
        workflow_id=record["workflow_id"],
        status=record["status"],
        created_at=record["created_at"],
    )


@router.get(
    "/research/{workflow_id}",
    response_model=WorkflowStatusResponse,
    summary="Get workflow status",
)
def get_research_status(workflow_id: str) -> WorkflowStatusResponse:
    """Return state and outputs for a scheduled workflow."""
    record = get_workflow_store().get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowStatusResponse(
        workflow_id=record["workflow_id"],
        status=record["status"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        completed_at=record["completed_at"],
        result=record["result"],
        error=record["error"],
    )


@router.get("/research", summary="List research workflows")
def list_research_workflows(
    status: str | None = Query(default=None, description="Filter workflows by status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    database: DatabaseService = Depends(get_database_service),
) -> dict[str, object]:
    """Return a paginated list of research workflows."""
    query = "SELECT workflow_id, workflow_type, status, payload_json, result_json, error_text, progress_percentage, current_stage, processed_videos, failed_videos, timeout_reason, started_at, last_stage_at, duration_seconds, created_at, updated_at, completed_at FROM workflows"
    params: list[object] = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor = database.connection.cursor()
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    items = []
    for row in rows:
        item = dict(row)
        if item.get("payload_json"):
            try:
                item["payload"] = json.loads(item["payload_json"])
            except Exception:
                item["payload"] = item["payload_json"]
        else:
            item["payload"] = None
        if item.get("result_json"):
            try:
                item["result"] = json.loads(item["result_json"])
            except Exception:
                item["result"] = item["result_json"]
        else:
            item["result"] = None
        item.pop("payload_json", None)
        item.pop("result_json", None)
        items.append(item)
    return {"total": len(items), "items": items}


@router.get(
    "/research/{workflow_id}/logs",
    response_model=WorkflowLogsResponse,
    summary="Get workflow logs",
)
def get_research_logs(
    workflow_id: str,
    limit: int = 100,
    offset: int = 0,
    stage: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> WorkflowLogsResponse:
    """Return persisted logs for a workflow with pagination and optional filters.

    Query parameters:
    - limit: number of log entries to return (default 100)
    - offset: pagination offset
    - stage: filter logs to a specific stage
    - start_date / end_date: ISO date strings to filter created_at range
    """
    store = get_workflow_store()
    record = store.get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="Workflow not found")
    # attempt to read logs from store
    logs: list[WorkflowLogEntry] = []
    retry_count = 0
    if hasattr(store, "get_logs"):
        try:
            raw = store.get_logs(workflow_id, limit=limit, offset=offset, stage=stage, start_date=start_date, end_date=end_date)
            for row in raw:
                logs.append(
                    WorkflowLogEntry(
                        created_at=row.get("created_at") or row.get("timestamp") or "",
                        stage=row.get("stage"),
                        status=row.get("status"),
                        message=row.get("message"),
                        error_text=row.get("error_text"),
                    )
                )
        except Exception:
            # fallback: empty
            logs = []
    # include retry_count if available on record
    retry_count = record.get("retry_count") if isinstance(record.get("retry_count"), int) else 0
    return WorkflowLogsResponse(workflow_id=workflow_id, retry_count=retry_count, logs=logs)
