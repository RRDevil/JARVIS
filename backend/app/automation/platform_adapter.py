"""Abstract Platform Adapter Interface for Desktop OS Automation."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AutomationError(Exception):
    """Base exception for platform automation failures."""
    pass


class FocusMismatchError(AutomationError):
    """Raised when the target window cannot be verified as the active foreground window."""
    pass


class ApprovedApp(BaseModel):
    """Specification of a pre-authorized desktop application."""

    app_id: str
    display_name: str
    executable: str
    description: str
    default_args: List[str] = Field(default_factory=list)


class WindowInfo(BaseModel):
    """Information regarding an open desktop window."""

    handle: int
    title: str
    process_id: int
    process_name: str
    is_visible: bool
    is_minimized: bool


class UIControlInfo(BaseModel):
    """Information regarding an accessible UI control inside a window."""

    control_id: str
    name: str
    control_type: str  # e.g. "button", "edit", "menu_item", "pane", "text"
    is_enabled: bool = True
    value: Optional[str] = None


class PlatformAdapter(ABC):
    """Abstract interface defining operating system interactions."""

    def is_permission_granted(self) -> bool:
        """Check if process has required OS automation/accessibility permissions.
        
        Defaults to True on Windows and mock environments; overridden on macOS to check TCC.
        """
        return True

    @abstractmethod
    def get_approved_apps(self) -> List[ApprovedApp]:
        """Return the list of pre-authorized applications."""
        pass

    @abstractmethod
    def launch_app(self, app_id: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """Launch an allowlisted application by ID."""
        pass

    @abstractmethod
    def list_windows(self) -> List[WindowInfo]:
        """Enumerate active visible desktop windows."""
        pass

    @abstractmethod
    def get_active_window(self) -> Optional[WindowInfo]:
        """Return the current active foreground desktop window."""
        pass

    @abstractmethod
    def is_window_valid(self, handle: int) -> bool:
        """Check if a window handle represents an active, valid desktop window."""
        pass

    @abstractmethod
    def focus_window(self, handle: int) -> bool:
        """Bring target window to foreground."""
        pass

    @abstractmethod
    def restore_and_focus_window(
        self,
        handle: int,
        expected_pid: Optional[int] = None,
        timeout: float = 0.6,
    ) -> bool:
        """Restore window if minimized, activate to foreground, and verify focus."""
        pass

    @abstractmethod
    def minimize_window(self, handle: int) -> bool:
        """Minimize the target window."""
        pass

    @abstractmethod
    def close_window(self, handle: int) -> bool:
        """Send graceful close signal (WM_CLOSE) to target window."""
        pass

    @abstractmethod
    def open_folder(self, folder_path: str) -> bool:
        """Open the specified directory in the system file manager."""
        pass

    @abstractmethod
    def find_controls(
        self,
        handle: int,
        name: Optional[str] = None,
        control_type: Optional[str] = None,
    ) -> List[UIControlInfo]:
        """Find accessible controls inside the specified window matching criteria."""
        pass

    @abstractmethod
    def click_control(self, handle: int, control_id: str) -> bool:
        """Click the identified UI control in the target window."""
        pass

    @abstractmethod
    def set_control_text(self, handle: int, control_id: str, text: str) -> bool:
        """Set the text value of the identified UI control."""
        pass

    @abstractmethod
    def send_shortcut(
        self,
        handle: int,
        shortcut: str,
        expected_pid: Optional[int] = None,
    ) -> bool:
        """Send an allowlisted keyboard shortcut to the specified window after focus verification."""
        pass

    @abstractmethod
    def scroll_window(self, handle: int, direction: str, amount: int) -> bool:
        """Scroll the specified window up or down."""
        pass

    @abstractmethod
    def click_at(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        target_hwnd: Optional[int] = None,
    ) -> bool:
        """Move cursor to display coordinates (x, y) and perform mouse click."""
        pass

    @abstractmethod
    def type_text(
        self,
        text: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
        target_hwnd: Optional[int] = None,
        clear_first: bool = False,
        press_enter: bool = False,
        use_clipboard: Optional[bool] = None,
    ) -> bool:
        """Focus target window/coordinates and enter text, supporting both Unicode typing and clipboard paste."""
        pass

    @abstractmethod
    def type_text_at(
        self,
        x: int,
        y: int,
        text: str,
        clear_first: bool = False,
        press_enter: bool = False,
        use_clipboard: Optional[bool] = None,
    ) -> bool:
        """Focus display coordinates (x, y) and enter text via native keyboard input."""
        pass

    @abstractmethod
    def scroll_at(self, x: int, y: int, direction: str = "down", amount: int = 3) -> bool:
        """Move cursor to display coordinates (x, y) and execute mouse wheel scrolling."""
        pass

    @abstractmethod
    def get_window_bounds(self, handle: int) -> Optional[Dict[str, int]]:
        """Retrieve the bounding rectangle {left, top, width, height} of target window."""
        pass

    @abstractmethod
    def get_virtual_desktop_bounds(self) -> tuple[int, int, int, int]:
        """Retrieve virtual desktop bounding rectangle (left, top, width, height) spanning all monitors."""
        pass


