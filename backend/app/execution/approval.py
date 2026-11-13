"""Approval Request Management and Security Handshake (Phase 3.4)."""

import hashlib
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from app.tools.base import RiskTier


def compute_action_payload_hash(tool_name: str, parameters: Dict[str, Any]) -> str:
    """Deterministic SHA-256 cryptographic hash of canonical tool name and parameters."""
    canonical = json.dumps({"tool": tool_name, "params": parameters}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ApprovalRequestModel(BaseModel):
    """Pydantic model representing an explicit approval request.

    Conforms to frontend ApprovalRequest integration contract.
    """

    id: str
    toolExecutionId: str
    actionSummary: str
    toolName: str
    riskTier: RiskTier
    parameters: Dict[str, Any]
    payloadHash: Optional[str] = None
    requestedAt: str
    expiresAt: str
    status: Literal["pending", "approved", "rejected", "expired"] = "pending"


class ApprovalError(Exception):
    """Base exception for approval processing errors."""
    pass


class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval ID cannot be found."""
    pass


class ApprovalExpiredError(ApprovalError):
    """Raised when an approval token has exceeded its TTL."""
    pass


class ApprovalAlreadyResolvedError(ApprovalError):
    """Raised when attempting to reuse an already resolved approval token."""
    pass


class ApprovalIntegrityError(ApprovalError):
    """Raised when approval payload hash fails verification due to parameter tampering."""
    pass


class ApprovalManager:
    """Manages authorization lifecycles, replay protection, and time-bounded validity."""

    def __init__(self, default_ttl_seconds: int = 300):
        self._requests: Dict[str, ApprovalRequestModel] = {}
        self._lock = threading.RLock()
        self.default_ttl_seconds = default_ttl_seconds

    def create_request(
        self,
        execution_id: str,
        tool_name: str,
        risk_tier: RiskTier,
        parameters: Dict[str, Any],
        action_summary: str,
        ttl_seconds: Optional[int] = None,
    ) -> ApprovalRequestModel:
        """Create a new time-bounded approval request bound to specific action parameters."""
        with self._lock:
            now = datetime.now(timezone.utc)
            ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
            expires = now + timedelta(seconds=ttl)

            approval_id = f"appr-{uuid.uuid4().hex[:10]}"
            payload_hash = compute_action_payload_hash(tool_name, parameters)
            req = ApprovalRequestModel(
                id=approval_id,
                toolExecutionId=execution_id,
                actionSummary=action_summary,
                toolName=tool_name,
                riskTier=risk_tier,
                parameters=parameters,
                payloadHash=payload_hash,
                requestedAt=now.isoformat(),
                expiresAt=expires.isoformat(),
                status="pending",
            )
            self._requests[approval_id] = req
            return req

    def get_request(self, approval_id: str) -> Optional[ApprovalRequestModel]:
        """Fetch request by ID, checking expiration state."""
        with self._lock:
            req = self._requests.get(approval_id)
            if not req:
                return None
            self._check_and_update_expiry(req)
            return req

    def get_pending(self) -> List[ApprovalRequestModel]:
        """Return all active, non-expired pending approval requests."""
        with self._lock:
            pending: List[ApprovalRequestModel] = []
            for req in self._requests.values():
                self._check_and_update_expiry(req)
                if req.status == "pending":
                    pending.append(req)
            return pending

    def get_latest_pending(self) -> Optional[ApprovalRequestModel]:
        """Return the most recently created active, non-expired pending approval request."""
        with self._lock:
            pending = self.get_pending()
            if not pending:
                return None
            pending.sort(key=lambda r: r.requestedAt, reverse=True)
            return pending[0]

    def invalidate_for_execution(self, execution_id: str) -> None:
        """Mark any pending approval bound to the given execution_id as expired/cancelled."""
        with self._lock:
            for req in self._requests.values():
                if req.toolExecutionId == execution_id and req.status == "pending":
                    req.status = "expired"

    def respond(self, approval_id: str, approved: bool) -> ApprovalRequestModel:
        """Resolve a pending approval token with replay and expiry protections."""
        with self._lock:
            req = self._requests.get(approval_id)
            if not req:
                raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

            self._check_and_update_expiry(req)

            if req.status == "expired":
                raise ApprovalExpiredError(
                    f"Approval token '{approval_id}' has expired and can no longer be used."
                )

            if req.status in ("approved", "rejected"):
                raise ApprovalAlreadyResolvedError(
                    f"Approval token '{approval_id}' was already resolved as '{req.status}'."
                )

            req.status = "approved" if approved else "rejected"
            return req

    def _check_and_update_expiry(self, req: ApprovalRequestModel) -> None:
        """Mark status as expired if the token's TTL has elapsed."""
        if req.status == "pending":
            expires_at = datetime.fromisoformat(req.expiresAt)
            if datetime.now(timezone.utc) > expires_at:
                req.status = "expired"

    def clear(self) -> None:
        """Clear all stored approvals (primarily for tests)."""
        with self._lock:
            self._requests.clear()


# Singleton approval manager
approval_manager = ApprovalManager()

