"""Microsoft Office Native COM Integration Provider (Phase 5.2).

Provides high-fidelity, structured automation for Word, Excel, PowerPoint,
and Outlook via official Windows COM dispatch interfaces with STA apartment safety.
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional, Set

from app.integrations.models import (
    ApplicationManifest,
    CapabilitySpec,
    IntegrationHealth,
    ProviderType,
)
from app.integrations.providers.base import (
    BaseIntegrationProvider,
    IntegrationProviderError,
)
from app.tools.base import ExecutionContext

logger = logging.getLogger("jarvis.integrations.providers.office_com")

# Safe dynamic import of Windows COM libraries
try:
    import pythoncom
    import win32com.client
    HAS_COM = True
except ImportError:
    pythoncom = None
    win32com = None
    HAS_COM = False


class OfficeCOMProvider(BaseIntegrationProvider):
    """Integrates with Microsoft Office desktop applications via native COM automation."""

    def __init__(self):
        self._active_operations: Set[str] = set()

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OFFICE_COM

    async def initialize(self) -> bool:
        return HAS_COM

    async def health_check(self, manifest: Optional[ApplicationManifest] = None) -> IntegrationHealth:
        if not HAS_COM:
            return IntegrationHealth.UNAVAILABLE
        if manifest and not manifest.is_installed:
            return IntegrationHealth.NOT_INSTALLED
        return IntegrationHealth.HEALTHY

    def is_available_for(self, manifest: ApplicationManifest) -> bool:
        if not HAS_COM:
            return False
        return ProviderType.OFFICE_COM in manifest.supported_providers and manifest.is_installed

    async def execute_capability(
        self,
        manifest: ApplicationManifest,
        capability: CapabilitySpec,
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """Execute Office capability within an isolated STA thread."""
        if not HAS_COM:
            raise IntegrationProviderError("Windows COM automation is not available on this platform.")

        op_id = context.execution_id
        self._active_operations.add(op_id)

        try:
            # Dispatch to worker thread to preserve COM apartment threading isolation
            return await asyncio.to_thread(
                self._dispatch_com_operation,
                manifest,
                capability,
                parameters,
            )
        finally:
            self._active_operations.discard(op_id)

    def _dispatch_com_operation(
        self,
        manifest: ApplicationManifest,
        capability: CapabilitySpec,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Worker thread entrypoint initializing pythoncom and dispatching by app."""
        pythoncom.CoInitialize()
        try:
            app_id = manifest.app_id.lower()
            cap_id = capability.id.lower()

            if "word" in app_id:
                return self._handle_word(cap_id, parameters)
            elif "excel" in app_id:
                return self._handle_excel(cap_id, parameters)
            elif "powerpoint" in app_id:
                return self._handle_powerpoint(cap_id, parameters)
            elif "outlook" in app_id:
                return self._handle_outlook(cap_id, parameters)
            else:
                raise IntegrationProviderError(f"COM provider has no handler for '{app_id}'.")
        finally:
            pythoncom.CoUninitialize()

    # --- Word Handler ---
    def _handle_word(self, cap_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        word = None
        doc = None
        try:
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = True

            if "read" in cap_id:
                # Open existing file or read active document
                file_path = params.get("document_path") or params.get("file_path")
                if file_path and os.path.exists(file_path):
                    doc = word.Documents.Open(os.path.abspath(file_path))
                elif word.Documents.Count > 0:
                    doc = word.ActiveDocument
                else:
                    return {"action": "word_read", "content": "", "word_count": 0, "message": "No open documents found in Word."}

                text_content = doc.Content.Text if doc else ""
                word_count = doc.Words.Count if doc else 0
                doc_name = doc.Name if doc else "Document"
                return {
                    "action": "word_read",
                    "document_name": doc_name,
                    "content": text_content[:5000],  # bounded read snippet
                    "word_count": word_count,
                    "character_count": len(text_content),
                }

            elif "create" in cap_id:
                doc = word.Documents.Add()
                initial_text = params.get("text") or params.get("content") or ""
                if initial_text:
                    doc.Content.Text = initial_text
                return {
                    "action": "word_create",
                    "document_name": doc.Name,
                    "word_count": doc.Words.Count,
                    "status": "created",
                }

            elif "edit" in cap_id:
                if word.Documents.Count > 0:
                    doc = word.ActiveDocument
                else:
                    doc = word.Documents.Add()
                new_text = params.get("text") or params.get("content") or ""
                # Append to end of document
                doc.Content.InsertAfter(new_text)
                return {
                    "action": "word_edit",
                    "document_name": doc.Name,
                    "appended_length": len(new_text),
                    "total_words": doc.Words.Count,
                }

            elif "save" in cap_id:
                if word.Documents.Count == 0:
                    raise IntegrationProviderError("No active Word document to save.")
                doc = word.ActiveDocument
                save_path = params.get("save_path") or params.get("file_path")
                if save_path:
                    abs_path = os.path.abspath(save_path)
                    doc.SaveAs2(abs_path)
                    return {"action": "word_save", "saved_path": abs_path, "status": "saved"}
                else:
                    doc.Save()
                    return {"action": "word_save", "saved_path": doc.FullName, "status": "saved"}

            raise IntegrationProviderError(f"Unsupported Word COM capability: '{cap_id}'.")
        except Exception as exc:
            raise IntegrationProviderError(f"Word COM operation failed: {str(exc)}") from exc

    # --- Excel Handler ---
    def _handle_excel(self, cap_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        excel = None
        wb = None
        try:
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = True

            if "read" in cap_id:
                file_path = params.get("workbook_path") or params.get("file_path")
                if file_path and os.path.exists(file_path):
                    wb = excel.Workbooks.Open(os.path.abspath(file_path))
                elif excel.Workbooks.Count > 0:
                    wb = excel.ActiveWorkbook
                else:
                    return {"action": "excel_read", "sheets": [], "message": "No open workbooks found in Excel."}

                sheet = wb.ActiveSheet
                sheet_names = [s.Name for s in wb.Sheets]
                # Read sample range
                used_range = sheet.UsedRange
                preview_data = []
                max_rows = min(15, used_range.Rows.Count)
                max_cols = min(8, used_range.Columns.Count)
                for r in range(1, max_rows + 1):
                    row_vals = [str(sheet.Cells(r, c).Value or "") for c in range(1, max_cols + 1)]
                    if any(row_vals):
                        preview_data.append(row_vals)

                return {
                    "action": "excel_read",
                    "workbook_name": wb.Name,
                    "active_sheet": sheet.Name,
                    "sheet_names": sheet_names,
                    "rows_detected": used_range.Rows.Count,
                    "columns_detected": used_range.Columns.Count,
                    "preview_data": preview_data,
                }

            elif "create" in cap_id:
                wb = excel.Workbooks.Add()
                sheet = wb.ActiveSheet
                return {
                    "action": "excel_create",
                    "workbook_name": wb.Name,
                    "sheet_name": sheet.Name,
                    "status": "created",
                }

            elif "modify" in cap_id or "write" in cap_id:
                if excel.Workbooks.Count == 0:
                    wb = excel.Workbooks.Add()
                else:
                    wb = excel.ActiveWorkbook
                sheet = wb.ActiveSheet

                cell_ref = params.get("cell", "A1")
                value = params.get("value", "")
                formula = params.get("formula")

                if formula:
                    sheet.Range(cell_ref).Formula = formula
                else:
                    sheet.Range(cell_ref).Value = value

                return {
                    "action": "excel_modify",
                    "workbook_name": wb.Name,
                    "sheet_name": sheet.Name,
                    "cell": cell_ref,
                    "value_written": str(formula or value),
                }

            elif "save" in cap_id:
                if excel.Workbooks.Count == 0:
                    raise IntegrationProviderError("No active Excel workbook to save.")
                wb = excel.ActiveWorkbook
                save_path = params.get("save_path") or params.get("file_path")
                if save_path:
                    abs_path = os.path.abspath(save_path)
                    wb.SaveAs(abs_path)
                    return {"action": "excel_save", "saved_path": abs_path, "status": "saved"}
                else:
                    wb.Save()
                    return {"action": "excel_save", "saved_path": wb.FullName, "status": "saved"}

            raise IntegrationProviderError(f"Unsupported Excel COM capability: '{cap_id}'.")
        except Exception as exc:
            raise IntegrationProviderError(f"Excel COM operation failed: {str(exc)}") from exc

    # --- PowerPoint Handler ---
    def _handle_powerpoint(self, cap_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        ppt = None
        pres = None
        try:
            ppt = win32com.client.Dispatch("PowerPoint.Application")

            if "read" in cap_id:
                if ppt.Presentations.Count == 0:
                    return {"action": "powerpoint_read", "slides_count": 0, "message": "No open presentations found in PowerPoint."}
                pres = ppt.ActivePresentation
                slides_summary = []
                for idx in range(1, min(10, pres.Slides.Count + 1)):
                    slide = pres.Slides(idx)
                    title = ""
                    try:
                        title = slide.Shapes.Title.TextFrame.TextRange.Text.strip()
                    except Exception:
                        pass
                    slides_summary.append({"slide_number": idx, "title": title})

                return {
                    "action": "powerpoint_read",
                    "presentation_name": pres.Name,
                    "total_slides": pres.Slides.Count,
                    "slides": slides_summary,
                }

            elif "create" in cap_id:
                pres = ppt.Presentations.Add()
                # Add title slide (Layout 1 = ppLayoutTitle)
                slide = pres.Slides.Add(1, 1)
                title_text = params.get("title", "New Presentation")
                try:
                    slide.Shapes.Title.TextFrame.TextRange.Text = title_text
                except Exception:
                    pass
                return {
                    "action": "powerpoint_create",
                    "presentation_name": pres.Name,
                    "slides_count": pres.Slides.Count,
                    "status": "created",
                }

            elif "save" in cap_id:
                if ppt.Presentations.Count == 0:
                    raise IntegrationProviderError("No active presentation to save.")
                pres = ppt.ActivePresentation
                save_path = params.get("save_path") or params.get("file_path")
                if save_path:
                    abs_path = os.path.abspath(save_path)
                    pres.SaveAs(abs_path)
                    return {"action": "powerpoint_save", "saved_path": abs_path, "status": "saved"}
                else:
                    pres.Save()
                    return {"action": "powerpoint_save", "saved_path": pres.FullName, "status": "saved"}

            raise IntegrationProviderError(f"Unsupported PowerPoint COM capability: '{cap_id}'.")
        except Exception as exc:
            raise IntegrationProviderError(f"PowerPoint COM operation failed: {str(exc)}") from exc

    # --- Outlook Handler ---
    def _handle_outlook(self, cap_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
            mapi = outlook.GetNamespace("MAPI")

            if "read" in cap_id:
                # 6 = olFolderInbox
                inbox = mapi.GetDefaultFolder(6)
                messages = inbox.Items
                messages.Sort("[ReceivedTime]", True)

                emails = []
                for i in range(1, min(10, messages.Count + 1)):
                    msg = messages.Item(i)
                    emails.append({
                        "subject": getattr(msg, "Subject", ""),
                        "sender": getattr(msg, "SenderName", ""),
                        "received_time": str(getattr(msg, "ReceivedTime", "")),
                        "snippet": str(getattr(msg, "Body", ""))[:200],
                    })

                return {
                    "action": "outlook_read_emails",
                    "inbox_unread_count": inbox.UnReadItemCount,
                    "emails": emails,
                }

            elif "draft" in cap_id:
                # 0 = olMailItem
                mail = outlook.CreateItem(0)
                mail.To = params.get("recipient", "")
                mail.Subject = params.get("subject", "Draft Message")
                mail.Body = params.get("body", "")
                mail.Save()

                return {
                    "action": "outlook_draft_email",
                    "recipient": mail.To,
                    "subject": mail.Subject,
                    "status": "draft_saved",
                }

            elif "send" in cap_id:
                recipient = params.get("recipient")
                subject = params.get("subject")
                body = params.get("body", "")
                if not recipient or not subject:
                    raise IntegrationProviderError("Outlook send requires 'recipient' and 'subject'.")

                mail = outlook.CreateItem(0)
                mail.To = recipient
                mail.Subject = subject
                mail.Body = body
                mail.Send()

                return {
                    "action": "outlook_send_email",
                    "recipient": recipient,
                    "subject": subject,
                    "status": "sent",
                }

            raise IntegrationProviderError(f"Unsupported Outlook COM capability: '{cap_id}'.")
        except Exception as exc:
            raise IntegrationProviderError(f"Outlook COM operation failed: {str(exc)}") from exc

    async def cancel(self, operation_id: str) -> bool:
        if operation_id in self._active_operations:
            self._active_operations.discard(operation_id)
            return True
        return False

    async def cleanup(self) -> None:
        self._active_operations.clear()
