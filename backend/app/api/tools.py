"""JARVIS Tool Execution API Endpoints (Phase 3)."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.security import verify_secret_token
from app.db.audit import AuditRecord, audit_logger
from app.execution.approval import ApprovalRequestModel
from app.execution.engine import ToolExecutionModel, execution_engine
from app.tools.base import ToolMetadata
from app.tools.registry import tool_registry

router = APIRouter(prefix="/v1", tags=["Tool Execution & Automation"])


class ProposeToolPayload(BaseModel):
    """Payload for submitting an action proposal."""

    tool_name: str = Field(..., description="Name of the registered tool to execute.")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary of parameters conforming to the tool's schema.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session ID for context tracking.",
    )


class ProposeToolResponse(BaseModel):
    """Response returned upon proposing a tool execution."""

    execution: ToolExecutionModel
    approval_request: Optional[ApprovalRequestModel] = None


@router.get(
    "/tools",
    response_model=List[ToolMetadata],
    summary="List registered tools and schemas",
)
def list_registered_tools(
    _authorized: bool = Depends(verify_secret_token),
) -> List[ToolMetadata]:
    """Retrieve all available desktop tools, risk tiers, and JSON schemas."""
    return tool_registry.list_tools()


@router.post(
    "/tools/propose",
    response_model=ProposeToolResponse,
    summary="Propose tool execution",
)
async def propose_tool_execution(
    payload: ProposeToolPayload,
    _authorized: bool = Depends(verify_secret_token),
) -> ProposeToolResponse:
    """Propose an action. Evaluates policy, running immediately if allowed or requiring approval."""
    execution, approval = await execution_engine.propose(
        tool_name=payload.tool_name,
        raw_parameters=payload.parameters,
        session_id=payload.session_id,
    )
    return ProposeToolResponse(execution=execution, approval_request=approval)


@router.get(
    "/tools/executions/{execution_id}",
    response_model=ToolExecutionModel,
    summary="Get execution status",
)
def get_execution_status(
    execution_id: str,
    _authorized: bool = Depends(verify_secret_token),
) -> ToolExecutionModel:
    """Retrieve the current lifecycle status and results of a tool execution."""
    execution = execution_engine.get_execution(execution_id)
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool execution '{execution_id}' not found.",
        )
    return execution


@router.post(
    "/tools/executions/{execution_id}/cancel",
    summary="Cancel tool execution",
)
async def cancel_tool_execution(
    execution_id: str,
    _authorized: bool = Depends(verify_secret_token),
) -> Dict[str, Any]:
    """Cancel a pending or running tool execution."""
    cancelled = await execution_engine.cancel_execution(execution_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Execution '{execution_id}' could not be cancelled or is already finalized.",
        )
    return {"execution_id": execution_id, "status": "cancelled"}


@router.get(
    "/audit/logs",
    response_model=List[AuditRecord],
    summary="Query audit trail logs",
)
def get_audit_trail_logs(
    limit: int = 50,
    _authorized: bool = Depends(verify_secret_token),
) -> List[AuditRecord]:
    """Retrieve recent persistent audit logs for system activity streams."""
    return audit_logger.get_recent(limit=limit)

