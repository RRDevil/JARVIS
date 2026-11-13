"""Application Registry storing structured manifests and catalog definitions (Phase 5.2)."""

import os
import threading
from typing import Dict, List, Optional

from app.integrations.models import (
    AppCategory,
    ApplicationManifest,
    CapabilitySpec,
    IntegrationHealth,
    PermissionLevel,
    ProcessRule,
    ProviderType,
)
from app.tools.base import RiskTier


def _build_default_manifests() -> List[ApplicationManifest]:
    """Construct initial catalog of supported applications."""
    localappdata = os.environ.get("LOCALAPPDATA", "")
    programfiles = os.environ.get("PROGRAMFILES", "C:\\Program Files")
    programfiles_x86 = os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")

    return [
        # --- Browsers ---
        ApplicationManifest(
            app_id="browser.opera_gx",
            display_name="Opera GX",
            vendor="Opera Software",
            category=AppCategory.BROWSER,
            description="Primary gaming and power browser with custom workspace, media, and tab features.",
            process_rule=ProcessRule(
                executable_names=["opera.exe", "launcher.exe"],
                window_title_patterns=["Opera GX", "Opera"],
                registry_app_paths_keys=["opera.exe"],
                common_install_paths=[
                    os.path.join(localappdata, "Programs", "Opera GX", "opera.exe"),
                    os.path.join(programfiles, "Opera GX", "opera.exe"),
                ],
            ),
            supported_providers=[ProviderType.BROWSER_AUTOMATION, ProviderType.DESKTOP_UI],
            capabilities=[
                CapabilitySpec(
                    id="browser.navigate",
                    name="Open URL or Search",
                    description="Navigate to a specified URL or perform a web query in Opera GX.",
                    permission_level=PermissionLevel.CONSEQUENTIAL,
                    risk_tier=RiskTier.CONSEQUENTIAL,
                    supported_providers=[ProviderType.BROWSER_AUTOMATION, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="browser.read_page",
                    name="Read Page Title & Content",
                    description="Extract visible title, URL, and page text from the active Opera GX tab.",
                    permission_level=PermissionLevel.READ_ONLY,
                    risk_tier=RiskTier.READ_ONLY,
                    supported_providers=[ProviderType.BROWSER_AUTOMATION, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="browser.manage_tabs",
                    name="Manage Browser Tabs",
                    description="Switch, create, or close tabs within the browser window.",
                    permission_level=PermissionLevel.CONTROLLED,
                    risk_tier=RiskTier.CONTROLLED,
                    supported_providers=[ProviderType.BROWSER_AUTOMATION, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="browser.submit_form",
                    name="Submit Web Form",
                    description="Submit data to an external website form. Consequential action.",
                    permission_level=PermissionLevel.CONSEQUENTIAL,
                    risk_tier=RiskTier.CONSEQUENTIAL,
                    supported_providers=[ProviderType.BROWSER_AUTOMATION, ProviderType.DESKTOP_UI],
                ),
            ],
        ),
        ApplicationManifest(
            app_id="browser.chrome",
            display_name="Google Chrome",
            vendor="Google LLC",
            category=AppCategory.BROWSER,
            description="Mainstream Google Chrome browser for standard web tasks and development.",
            process_rule=ProcessRule(
                executable_names=["chrome.exe"],
                window_title_patterns=["Google Chrome", "Chrome"],
                registry_app_paths_keys=["chrome.exe"],
                common_install_paths=[
                    os.path.join(programfiles, "Google", "Chrome", "Application", "chrome.exe"),
                    os.path.join(programfiles_x86, "Google", "Chrome", "Application", "chrome.exe"),
                    os.path.join(localappdata, "Google", "Chrome", "Application", "chrome.exe"),
                ],
            ),
            supported_providers=[ProviderType.BROWSER_AUTOMATION, ProviderType.DESKTOP_UI],
            capabilities=[
                CapabilitySpec(
                    id="browser.navigate",
                    name="Open URL or Search",
                    description="Navigate to a specified URL or perform a web query in Google Chrome.",
                    permission_level=PermissionLevel.CONSEQUENTIAL,
                    risk_tier=RiskTier.CONSEQUENTIAL,
                    supported_providers=[ProviderType.BROWSER_AUTOMATION, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="browser.read_page",
                    name="Read Page Title & Content",
                    description="Extract visible title, URL, and page text from the active Google Chrome tab.",
                    permission_level=PermissionLevel.READ_ONLY,
                    risk_tier=RiskTier.READ_ONLY,
                    supported_providers=[ProviderType.BROWSER_AUTOMATION, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="browser.manage_tabs",
                    name="Manage Browser Tabs",
                    description="Switch, create, or close tabs within Google Chrome.",
                    permission_level=PermissionLevel.CONTROLLED,
                    risk_tier=RiskTier.CONTROLLED,
                    supported_providers=[ProviderType.BROWSER_AUTOMATION, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="browser.submit_form",
                    name="Submit Web Form",
                    description="Submit data to an external website form. Consequential action.",
                    permission_level=PermissionLevel.CONSEQUENTIAL,
                    risk_tier=RiskTier.CONSEQUENTIAL,
                    supported_providers=[ProviderType.BROWSER_AUTOMATION, ProviderType.DESKTOP_UI],
                ),
            ],
        ),

        # --- Microsoft Office Family ---
        ApplicationManifest(
            app_id="office.word",
            display_name="Microsoft Word",
            vendor="Microsoft",
            category=AppCategory.OFFICE,
            description="Word processing application for drafting, reading, and editing documents.",
            process_rule=ProcessRule(
                executable_names=["winword.exe"],
                window_title_patterns=["Word", "Document"],
                registry_app_paths_keys=["winword.exe"],
                common_install_paths=[
                    os.path.join(programfiles, "Microsoft Office", "root", "Office16", "WINWORD.EXE"),
                    os.path.join(programfiles_x86, "Microsoft Office", "root", "Office16", "WINWORD.EXE"),
                ],
            ),
            supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
            capabilities=[
                CapabilitySpec(
                    id="word.read_document",
                    name="Read Document Content",
                    description="Extract text paragraphs, headings, and tables from an active or local Word document.",
                    permission_level=PermissionLevel.READ_ONLY,
                    risk_tier=RiskTier.READ_ONLY,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="word.create_document",
                    name="Create New Document",
                    description="Initialize a new Word document and draft initial text content.",
                    permission_level=PermissionLevel.CONTROLLED,
                    risk_tier=RiskTier.CONTROLLED,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="word.edit_text",
                    name="Edit Document Text",
                    description="Append, replace, or insert formatted text within a Word document.",
                    permission_level=PermissionLevel.CONTROLLED,
                    risk_tier=RiskTier.CONTROLLED,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="word.save_document",
                    name="Save Document",
                    description="Save document to filesystem. Consequential action.",
                    permission_level=PermissionLevel.CONSEQUENTIAL,
                    risk_tier=RiskTier.CONSEQUENTIAL,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
            ],
        ),
        ApplicationManifest(
            app_id="office.excel",
            display_name="Microsoft Excel",
            vendor="Microsoft",
            category=AppCategory.OFFICE,
            description="Spreadsheet application for tabular data, analysis, and calculations.",
            process_rule=ProcessRule(
                executable_names=["excel.exe"],
                window_title_patterns=["Excel", "Workbook", "Sheet"],
                registry_app_paths_keys=["excel.exe"],
                common_install_paths=[
                    os.path.join(programfiles, "Microsoft Office", "root", "Office16", "EXCEL.EXE"),
                    os.path.join(programfiles_x86, "Microsoft Office", "root", "Office16", "EXCEL.EXE"),
                ],
            ),
            supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
            capabilities=[
                CapabilitySpec(
                    id="excel.read_workbook",
                    name="Read Workbook & Sheets",
                    description="Read cell ranges, sheet names, and computed values from Excel.",
                    permission_level=PermissionLevel.READ_ONLY,
                    risk_tier=RiskTier.READ_ONLY,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="excel.modify_cells",
                    name="Write Cells & Formulas",
                    description="Enter values or formulas into specified cell ranges.",
                    permission_level=PermissionLevel.CONTROLLED,
                    risk_tier=RiskTier.CONTROLLED,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="excel.create_workbook",
                    name="Create New Workbook",
                    description="Initialize a blank Excel workbook with standard worksheet.",
                    permission_level=PermissionLevel.CONTROLLED,
                    risk_tier=RiskTier.CONTROLLED,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="excel.save_workbook",
                    name="Save Workbook",
                    description="Save workbook to disk. Consequential action.",
                    permission_level=PermissionLevel.CONSEQUENTIAL,
                    risk_tier=RiskTier.CONSEQUENTIAL,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
            ],
        ),
        ApplicationManifest(
            app_id="office.powerpoint",
            display_name="Microsoft PowerPoint",
            vendor="Microsoft",
            category=AppCategory.OFFICE,
            description="Presentation software for slide decks, diagrams, and outlines.",
            process_rule=ProcessRule(
                executable_names=["powerpnt.exe"],
                window_title_patterns=["PowerPoint", "Presentation"],
                registry_app_paths_keys=["powerpnt.exe"],
                common_install_paths=[
                    os.path.join(programfiles, "Microsoft Office", "root", "Office16", "POWERPNT.EXE"),
                    os.path.join(programfiles_x86, "Microsoft Office", "root", "Office16", "POWERPNT.EXE"),
                ],
            ),
            supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
            capabilities=[
                CapabilitySpec(
                    id="powerpoint.read_presentation",
                    name="Read Presentation Slides",
                    description="Extract text content, titles, and notes from slides in PowerPoint.",
                    permission_level=PermissionLevel.READ_ONLY,
                    risk_tier=RiskTier.READ_ONLY,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="powerpoint.create_presentation",
                    name="Create Presentation",
                    description="Initialize a new slide deck and add titled slides.",
                    permission_level=PermissionLevel.CONTROLLED,
                    risk_tier=RiskTier.CONTROLLED,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="powerpoint.save_presentation",
                    name="Save Presentation",
                    description="Save presentation file to disk. Consequential action.",
                    permission_level=PermissionLevel.CONSEQUENTIAL,
                    risk_tier=RiskTier.CONSEQUENTIAL,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
            ],
        ),
        ApplicationManifest(
            app_id="office.outlook",
            display_name="Microsoft Outlook",
            vendor="Microsoft",
            category=AppCategory.OFFICE,
            description="Email client and personal information manager.",
            process_rule=ProcessRule(
                executable_names=["outlook.exe", "olk.exe"],
                window_title_patterns=["Outlook", "Inbox", "Mail"],
                registry_app_paths_keys=["outlook.exe"],
                common_install_paths=[
                    os.path.join(programfiles, "Microsoft Office", "root", "Office16", "OUTLOOK.EXE"),
                    os.path.join(programfiles_x86, "Microsoft Office", "root", "Office16", "OUTLOOK.EXE"),
                ],
            ),
            supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
            capabilities=[
                CapabilitySpec(
                    id="outlook.read_emails",
                    name="Read Inbox & Messages",
                    description="Retrieve subject, sender, and body of authorized emails.",
                    permission_level=PermissionLevel.READ_ONLY,
                    risk_tier=RiskTier.READ_ONLY,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="outlook.draft_email",
                    name="Draft Email",
                    description="Prepare an email draft with recipient, subject, and body.",
                    permission_level=PermissionLevel.CONTROLLED,
                    risk_tier=RiskTier.CONTROLLED,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="outlook.send_email",
                    name="Send Email",
                    description="Send an email to specified recipients. Consequential action requiring explicit approval.",
                    permission_level=PermissionLevel.CONSEQUENTIAL,
                    risk_tier=RiskTier.CONSEQUENTIAL,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
            ],
        ),
        ApplicationManifest(
            app_id="office.onenote",
            display_name="Microsoft OneNote",
            vendor="Microsoft",
            category=AppCategory.OFFICE,
            description="Digital note-taking and notebook organization application.",
            process_rule=ProcessRule(
                executable_names=["onenote.exe"],
                window_title_patterns=["OneNote"],
                registry_app_paths_keys=["onenote.exe"],
            ),
            supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
            capabilities=[
                CapabilitySpec(
                    id="onenote.read_notes",
                    name="Read Notebook Pages",
                    description="Read notebook sections and page contents.",
                    permission_level=PermissionLevel.READ_ONLY,
                    risk_tier=RiskTier.READ_ONLY,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="onenote.create_note",
                    name="Create Note Page",
                    description="Create a new note in an active notebook.",
                    permission_level=PermissionLevel.CONTROLLED,
                    risk_tier=RiskTier.CONTROLLED,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
            ],
        ),
        ApplicationManifest(
            app_id="office.access",
            display_name="Microsoft Access",
            vendor="Microsoft",
            category=AppCategory.OFFICE,
            description="Relational database management application.",
            process_rule=ProcessRule(
                executable_names=["msaccess.exe"],
                window_title_patterns=["Access", "Database"],
                registry_app_paths_keys=["msaccess.exe"],
            ),
            supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
            capabilities=[
                CapabilitySpec(
                    id="access.read_structure",
                    name="Inspect Database Schema",
                    description="List tables, queries, and schema definitions.",
                    permission_level=PermissionLevel.READ_ONLY,
                    risk_tier=RiskTier.READ_ONLY,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="access.execute_query",
                    name="Execute Read-Only Query",
                    description="Run a safe SELECT query against open database.",
                    permission_level=PermissionLevel.CONTROLLED,
                    risk_tier=RiskTier.CONTROLLED,
                    supported_providers=[ProviderType.OFFICE_COM, ProviderType.DESKTOP_UI],
                ),
            ],
        ),
        ApplicationManifest(
            app_id="office.publisher",
            display_name="Microsoft Publisher",
            vendor="Microsoft",
            category=AppCategory.OFFICE,
            description="Desktop publishing application for flyers, brochures, and layouts.",
            process_rule=ProcessRule(
                executable_names=["mspub.exe"],
                window_title_patterns=["Publisher"],
                registry_app_paths_keys=["mspub.exe"],
            ),
            supported_providers=[ProviderType.DESKTOP_UI],
            capabilities=[
                CapabilitySpec(
                    id="publisher.read_publication",
                    name="Read Publication",
                    description="Inspect active publication layout and text frames.",
                    permission_level=PermissionLevel.READ_ONLY,
                    risk_tier=RiskTier.READ_ONLY,
                    supported_providers=[ProviderType.DESKTOP_UI],
                ),
            ],
        ),

        # --- Messaging Ecosystem ---
        ApplicationManifest(
            app_id="messaging.discord",
            display_name="Discord",
            vendor="Discord Inc.",
            category=AppCategory.MESSAGING,
            description="Voice, video, and text communication service.",
            process_rule=ProcessRule(
                executable_names=["discord.exe", "update.exe"],
                window_title_patterns=["Discord"],
                common_install_paths=[
                    os.path.join(localappdata, "Discord", "Update.exe"),
                ],
            ),
            supported_providers=[ProviderType.DESKTOP_UI, ProviderType.NATIVE_API],
            capabilities=[
                CapabilitySpec(
                    id="discord.read_messages",
                    name="Read Visible Messages",
                    description="Read conversation messages in active channel or authorized chat.",
                    permission_level=PermissionLevel.READ_ONLY,
                    risk_tier=RiskTier.READ_ONLY,
                    supported_providers=[ProviderType.DESKTOP_UI, ProviderType.NATIVE_API],
                ),
                CapabilitySpec(
                    id="discord.draft_message",
                    name="Draft Reply",
                    description="Stage a proposed reply without sending.",
                    permission_level=PermissionLevel.CONTROLLED,
                    risk_tier=RiskTier.CONTROLLED,
                    supported_providers=[ProviderType.DESKTOP_UI, ProviderType.NATIVE_API],
                ),
                CapabilitySpec(
                    id="discord.send_message",
                    name="Send Discord Message",
                    description="Send message to channel or recipient. Consequential action strictly bound to user approval.",
                    permission_level=PermissionLevel.CONSEQUENTIAL,
                    risk_tier=RiskTier.CONSEQUENTIAL,
                    supported_providers=[ProviderType.DESKTOP_UI, ProviderType.NATIVE_API],
                ),
            ],
        ),
        ApplicationManifest(
            app_id="messaging.whatsapp",
            display_name="WhatsApp",
            vendor="Meta",
            category=AppCategory.MESSAGING,
            description="End-to-end encrypted messaging application.",
            process_rule=ProcessRule(
                executable_names=["whatsapp.exe"],
                window_title_patterns=["WhatsApp"],
                common_install_paths=[
                    os.path.join(localappdata, "WhatsApp", "WhatsApp.exe"),
                ],
            ),
            supported_providers=[ProviderType.DESKTOP_UI],
            capabilities=[
                CapabilitySpec(
                    id="whatsapp.read_messages",
                    name="Read Visible Messages",
                    description="Read chat messages from the active conversation window.",
                    permission_level=PermissionLevel.READ_ONLY,
                    risk_tier=RiskTier.READ_ONLY,
                    supported_providers=[ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="whatsapp.draft_message",
                    name="Draft Message",
                    description="Stage a proposed text message in the active chat box.",
                    permission_level=PermissionLevel.CONTROLLED,
                    risk_tier=RiskTier.CONTROLLED,
                    supported_providers=[ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="whatsapp.send_message",
                    name="Send WhatsApp Message",
                    description="Send text to current recipient. Consequential action strictly bound to user approval.",
                    permission_level=PermissionLevel.CONSEQUENTIAL,
                    risk_tier=RiskTier.CONSEQUENTIAL,
                    supported_providers=[ProviderType.DESKTOP_UI],
                ),
            ],
        ),
        ApplicationManifest(
            app_id="messaging.instagram",
            display_name="Instagram",
            vendor="Meta",
            category=AppCategory.MESSAGING,
            description="Direct messaging and media sharing platform.",
            process_rule=ProcessRule(
                executable_names=["instagram.exe"],
                window_title_patterns=["Instagram"],
            ),
            supported_providers=[ProviderType.DESKTOP_UI],
            capabilities=[
                CapabilitySpec(
                    id="instagram.read_messages",
                    name="Read Visible DMs",
                    description="Read direct messages in visible chat window.",
                    permission_level=PermissionLevel.READ_ONLY,
                    risk_tier=RiskTier.READ_ONLY,
                    supported_providers=[ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="instagram.draft_message",
                    name="Draft Direct Message",
                    description="Draft a reply in the direct message field.",
                    permission_level=PermissionLevel.CONTROLLED,
                    risk_tier=RiskTier.CONTROLLED,
                    supported_providers=[ProviderType.DESKTOP_UI],
                ),
                CapabilitySpec(
                    id="instagram.send_message",
                    name="Send Instagram Direct Message",
                    description="Send direct message. Consequential action strictly bound to user approval.",
                    permission_level=PermissionLevel.CONSEQUENTIAL,
                    risk_tier=RiskTier.CONSEQUENTIAL,
                    supported_providers=[ProviderType.DESKTOP_UI],
                ),
            ],
        ),
    ]


class ApplicationRegistry:
    """Thread-safe registry managing application manifests and runtime statuses."""

    def __init__(self):
        self._manifests: Dict[str, ApplicationManifest] = {}
        self._lock = threading.RLock()
        self._load_defaults()

    def _load_defaults(self):
        with self._lock:
            for manifest in _build_default_manifests():
                self._manifests[manifest.app_id] = manifest

    def register(self, manifest: ApplicationManifest) -> None:
        """Register or update an application manifest."""
        with self._lock:
            self._manifests[manifest.app_id] = manifest

    def get(self, app_id: str) -> Optional[ApplicationManifest]:
        """Fetch manifest by application ID."""
        with self._lock:
            return self._manifests.get(app_id.lower().strip())

    def list_all(self, category: Optional[AppCategory] = None) -> List[ApplicationManifest]:
        """List all registered application manifests, optionally filtered by category."""
        with self._lock:
            manifests = list(self._manifests.values())
            if category:
                manifests = [m for m in manifests if m.category == category]
            return manifests

    def find_by_process_name(self, process_name: str) -> Optional[ApplicationManifest]:
        """Find matching manifest by process executable name."""
        with self._lock:
            p_clean = process_name.lower().strip()
            for m in self._manifests.values():
                for exe in m.process_rule.executable_names:
                    if exe.lower() == p_clean or exe.lower() in p_clean:
                        return m
            return None

    def find_by_window_title(self, window_title: str) -> Optional[ApplicationManifest]:
        """Find matching manifest by window title patterns."""
        with self._lock:
            wt_clean = window_title.lower()
            for m in self._manifests.values():
                for pattern in m.process_rule.window_title_patterns:
                    if pattern.lower() in wt_clean:
                        return m
            return None


# Global singleton instance
application_registry = ApplicationRegistry()
