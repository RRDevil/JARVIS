"""JARVIS Desktop Assistant - Tool Framework Base Specifications."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field


class RiskTier(str, Enum):
    """Risk tiers governing tool execution authorization."""

    READ_ONLY = "READ_ONLY"          # Pure inspect/query, non-mutating
    CONTROLLED = "CONTROLLED"        # Low-risk UI or desktop operations (focus window, launch allowlisted app)
    CONSEQUENTIAL = "CONSEQUENTIAL"  # Mutating desktop operations (close window, send keystroke/click, write file)
    CRITICAL = "CRITICAL"            # Destructive operations (raw commands, terminate processes) - blocked by default


class ToolStatus(str, Enum):
    """Lifecycle state of a tool execution."""

    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PolicyDecision(str, Enum):
    """Decision produced by the PolicyEngine for a tool call proposal."""

    ALLOW_AUTO = "ALLOW_AUTO"              # Permitted without human approval
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"  # Requires explicit human approval via UI/API
    BLOCK = "BLOCK"                        # Disallowed by security policy


class ToolResult(BaseModel):
    """Standardized result returned by all tools."""

    success: bool = Field(..., description="Whether the tool operation succeeded.")
    data: Optional[Any] = Field(default=None, description="Structured return data.")
    error: Optional[str] = Field(default=None, description="User-facing error message if failed.")
    error_code: Optional[str] = Field(default=None, description="Categorized machine-readable error code.")
    verified: bool = Field(default=False, description="Whether the post-execution state was verified.")
    execution_time_ms: float = Field(default=0.0, description="Duration of tool execution in milliseconds.")


class ExecutionContext(BaseModel):
    """Contextual metadata passed to tool execution."""

    execution_id: str
    session_id: Optional[str] = None
    approval_id: Optional[str] = None
    dry_run: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolMetadata(BaseModel):
    """Metadata describing a registered tool for discovery and AI schema generation."""

    name: str
    description: str
    risk_tier: RiskTier
    parameters_schema: Dict[str, Any]


class BaseTool(ABC):
    """Abstract base class for all JARVIS desktop tools."""

    name: str
    description: str
    risk_tier: RiskTier
    parameters_schema: Type[BaseModel]

    @abstractmethod
    async def execute(self, params: BaseModel, context: ExecutionContext) -> ToolResult:
        """Execute the tool operation."""
        pass

    async def verify(self, params: BaseModel, result: ToolResult, context: ExecutionContext) -> bool:
        """Verify the outcome of the execution. Default implementation considers success verified."""
        return result.success

    def get_metadata(self) -> ToolMetadata:
        """Return the metadata and JSON schema for this tool."""
        return ToolMetadata(
            name=self.name,
            description=self.description,
            risk_tier=self.risk_tier,
            parameters_schema=self.parameters_schema.model_json_schema(),
        )

