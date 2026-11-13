"""JARVIS Approvals API Endpoints (Phase 3)."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.security import verify_secret_token
from app.tools.base import ToolStatus
from app.execution.approval import (
    ApprovalAlreadyResolvedError,
    ApprovalError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
    ApprovalRequestModel,
    approval_manager,
)
from app.execution.engine import ToolExecutionModel, execution_engine

router = APIRouter(prefix="/v1/approvals", tags=["Security & Approvals"])


class RespondApprovalPayload(BaseModel):
    """Payload for submitting an approval decision."""

    approved: bool = Field(
        ...,
        description="True to authorize execution; False to reject.",
    )
    expected_request_id: Optional[str] = Field(
        default=None,
        description="Optional expected approval request ID to ensure decision binds strictly to the intended action.",
    )


class RespondApprovalResponse(BaseModel):
    """Response returned after resolving an approval request."""

    approval: ApprovalRequestModel
    execution: Optional[ToolExecutionModel] = None
    conversation_message: str = Field(
        ...,
        description="Structured conversational response from JARVIS explaining the outcome.",
    )


@router.get(
    "/pending",
    response_model=List[ApprovalRequestModel],
    summary="List pending approval requests",
)
def list_pending_approvals(
    _authorized: bool = Depends(verify_secret_token),
) -> List[ApprovalRequestModel]:
    """Retrieve all active, non-expired authorization requests awaiting human confirmation."""
    return approval_manager.get_pending()


@router.get(
    "/active",
    response_model=ApprovalRequestModel,
    summary="Get current active pending approval request",
)
def get_active_approval(
    _authorized: bool = Depends(verify_secret_token),
) -> ApprovalRequestModel:
    """Retrieve the current active pending approval request, or 404 if none."""
    req = approval_manager.get_latest_pending()
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active approval request awaiting decision.",
        )
    return req


@router.post(
    "/active/respond",
    response_model=RespondApprovalResponse,
    summary="Respond to the currently active pending approval request",
)
async def respond_to_active_approval(
    payload: RespondApprovalPayload,
    _authorized: bool = Depends(verify_secret_token),
) -> RespondApprovalResponse:
    """Approve or reject the currently active pending approval request via global shortcut."""
    req = approval_manager.get_latest_pending()
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active approval request awaiting decision.",
        )
    if payload.expected_request_id and req.id != payload.expected_request_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active approval changed (expected '{payload.expected_request_id}', but found '{req.id}').",
        )
    return await respond_to_approval(approval_id=req.id, payload=payload, _authorized=_authorized)


@router.get(
    "/{approval_id}",
    response_model=ApprovalRequestModel,
    summary="Get approval request by ID",
)
def get_approval_request(
    approval_id: str,
    _authorized: bool = Depends(verify_secret_token),
) -> ApprovalRequestModel:
    """Retrieve a specific approval request."""
    req = approval_manager.get_request(approval_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request '{approval_id}' not found.",
        )
    return req


@router.post(
    "/{approval_id}/respond",
    response_model=RespondApprovalResponse,
    summary="Respond to pending approval request",
)
async def respond_to_approval(
    approval_id: str,
    payload: RespondApprovalPayload,
    _authorized: bool = Depends(verify_secret_token),
) -> RespondApprovalResponse:
    """Approve or reject a pending consequential tool execution."""
    try:
        approval, execution = await execution_engine.resolve_approval(
            approval_id=approval_id,
            approved=payload.approved,
        )

        if not payload.approved:
            conversation_message = "Understood. I've cancelled that action as requested. Nothing was changed."
        else:
            if execution and execution.status == ToolStatus.SUCCESS:
                conversation_message = f"Action authorized and executed: {approval.actionSummary}."
            elif execution and execution.status == ToolStatus.FAILED:
                conversation_message = f"I attempted to perform the action, but Windows returned an error: {execution.error or 'Execution failed'}."
            else:
                conversation_message = f"Action authorized: {approval.actionSummary}."

        return RespondApprovalResponse(
            approval=approval,
            execution=execution,
            conversation_message=conversation_message,
        )
    except ApprovalNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
    except ApprovalExpiredError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The approval request expired before it was authorized. I haven't performed the action.",
        )
    except ApprovalAlreadyResolvedError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Approval processing error: {str(err)}",
        )

