"""JARVIS Desktop Assistant - Tool Registry."""

import threading
from typing import Dict, List, Optional
from pydantic import BaseModel, ValidationError

from app.tools.base import BaseTool, ToolMetadata


class ToolRegistryError(Exception):
    """Base exception for tool registry operations."""
    pass


class ToolNotFoundError(ToolRegistryError):
    """Raised when an unregistered tool is requested."""
    pass


class ToolValidationError(ToolRegistryError):
    """Raised when tool parameters fail schema validation."""
    pass


class ToolRegistry:
    """Thread-safe registry maintaining the catalog of authorized JARVIS tools."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._lock = threading.RLock()

    def register(self, tool: BaseTool, overwrite: bool = False) -> None:
        """Register a validated tool instance into the catalog."""
        with self._lock:
            if not isinstance(tool, BaseTool):
                raise TypeError(f"Expected BaseTool instance, got {type(tool).__name__}")
            if not tool.name or not tool.name.isidentifier():
                raise ValueError(f"Tool name '{tool.name}' must be a valid Python identifier.")
            if tool.name in self._tools and not overwrite:
                raise ValueError(
                    f"Tool '{tool.name}' is already registered. Set overwrite=True to replace."
                )
            self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        """Remove a tool from the catalog."""
        with self._lock:
            return self._tools.pop(name, None) is not None

    def get(self, name: str) -> BaseTool:
        """Retrieve a registered tool by its unique name."""
        with self._lock:
            tool = self._tools.get(name)
            if not tool:
                raise ToolNotFoundError(f"Tool '{name}' is not registered.")
            return tool

    def has_tool(self, name: str) -> bool:
        """Check whether a tool exists in the registry."""
        with self._lock:
            return name in self._tools

    def list_tools(self) -> List[ToolMetadata]:
        """Return metadata for all registered tools."""
        with self._lock:
            return [tool.get_metadata() for tool in self._tools.values()]

    def validate_parameters(self, name: str, raw_params: dict) -> BaseModel:
        """Validate input arguments against the tool's Pydantic parameters schema."""
        tool = self.get(name)
        try:
            return tool.parameters_schema.model_validate(raw_params)
        except ValidationError as err:
            raise ToolValidationError(
                f"Parameter validation failed for tool '{name}': {err}"
            ) from err

    def clear(self) -> None:
        """Clear all registered tools (used primarily for test isolation)."""
        with self._lock:
            self._tools.clear()


# Default global tool registry instance
tool_registry = ToolRegistry()

