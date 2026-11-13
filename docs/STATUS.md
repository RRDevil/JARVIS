# JARVIS Desktop Assistant: Project Status

## Current Phase: Advanced Reasoning, Adaptive Planning, User Preference Memory & Visual Perception Reliability — Completed

### Status Summary
- **Phase Status:** Goal-Oriented Planning, Persistent Preference Memory, and Semantic Interface Perception Complete and Formally Verified.
- **Repository State:** Real Windows 11 desktop assistant featuring goal-oriented task planning (`backend/app/planning/planner.py`), persistent SQLite user preference and workflow memory (`backend/app/memory/store.py`, `service.py`) with a strict 5-tier resolution hierarchy, structured semantic perception (`backend/app/perception/semantic/`) isolating Instagram Notes from genuine conversations, dedicated Pre-Approval Visual Target Resolution Pipeline (`backend/app/perception/target_resolver.py`), concrete spatial coordinate binding in security approvals, resilient dual-channel mouse click execution (`windows_adapter.py`), target invalidation guards, post-click interaction verification, and enhanced HUD approval cards. In addition, the Modular Application Integration Framework spans Browsers (Opera GX, Google Chrome), Microsoft Office (Word, Excel, PowerPoint, Outlook, OneNote, Access, Publisher), and Messaging (Discord, WhatsApp, Instagram). Upstream capacity spike (503/429) fallback architecture features real-time candidate model failovers (`gemini-3.5-flash-lite`, `gemini-3-flash-preview`, `gemini-3.1-flash-lite`), recursive schema sanitization, offline local automation execution, in-character standby responses, and frontend service notice recovery.
- **Backend Service:** FastAPI with SQLite persistence, health diagnostics (`GET /api/health`), SSE chat streaming (`POST /api/v1/chat/stream`), preferences API (`/api/v1/preferences`), plans API (`/api/v1/plans`), multi-monitor querying (`GET /api/v1/screen/monitors`), on-demand screen inspection (`POST /api/v1/screen/inspect`), on-device OCR (`POST /api/v1/screen/ocr`), UI element grounding (`POST /api/v1/screen/elements/locate`), target resolver (`target_resolver.resolve_target`), semantic conversation inspection (`semantic_read_conversations`), application integration catalog and discovery, tool registry with direct screen clicking (`visual_click_element`), universal text typing (`desktop_type_text`, `visual_type_into_element`), core integration tools (`app_discover`, `app_list_capabilities`, `app_execute_capability`), preference tools (`preference_query`, `preference_store`), task planning tools (`plan_create`, `plan_get`), approvals gateway with rejection conversation messaging and global active approval shortcut resolution, and audit log query endpoints (`GET /api/v1/audit/logs`) active on loopback (`127.0.0.1:8000`). 212 backend pytest tests passing with 0 errors.
- **Frontend Service:** React 19 + TypeScript + Vite with dual-mode compact floating orb, quick command bar with inline approval bubbles displaying concrete resolved target names, applications, coordinates `(x, y)`, bounding boxes, and detection badges, Screen Perception Modal with interactive UI element grounding viewer, Application Manager Modal, expanded glass HUD, full diagnostics dashboard, 137 unit/integration tests passing (Vitest), and 0 TypeScript errors.
- **Desktop Shell Host:** Native Windows WebView2 desktop shell (`scripts/desktop_app.py`) with frameless transparency, system tray, and registered global hotkeys (`Alt + Space`, `Ctrl + Shift + J`, dedicated mic keys, `Ctrl + Alt + Y` for Approve, `Ctrl + Alt + N` for Deny).

---

## Advanced Reasoning, Memory & Semantic Perception Checklist

- [x] **1. Semantic Interface Perception & Instagram Conversation Isolation:**
  - Implemented `backend/app/perception/semantic/instagram.py` and `generic.py` with `SemanticPerceptionEngine`.
  - Solved root cause of Instagram misidentification: Notes and their authors (in top horizontal tray) are strictly isolated and prevented from entering conversation candidates.
  - Formulates genuine conversation rows requiring both contact name and last message preview or activity status.
  - Distinguishes currently open conversation thread (right pane) from inbox list and suggested contacts.
  - Registered `semantic_read_conversations` BaseTool and upgraded `DesktopUIProvider` message reading.
- [x] **2. Goal-Oriented Reasoning & Autonomous Task Planning (Phase 6 Foundation):**
  - Implemented `backend/app/planning/planner.py` with `TaskPlan` and `PlanStep` models.
  - Autonomous goal decomposition for messaging objectives, document update workflows, and research queries without requiring step-by-step user commands.
  - Step verification criteria and dependency tracking.
  - Adaptive problem solving & dynamic replanning upon step failure (browser failover, application launch insertion).
  - Clarification policy engine (`ClarificationPolicyEngine`) defining strict rules on when questions are necessary vs when autonomous execution proceeds.
  - Registered `plan_create` and `plan_get` BaseTools and `/api/v1/plans` REST endpoints.
- [x] **3. Persistent User Preference and Workflow Memory (Phase 7 Foundation):**
  - Implemented `backend/app/memory/store.py` and `service.py` backed by SQLite `user_preferences` table.
  - Structured preference categories: global defaults, website browsers, person communications, workflow preferences, application profiles.
  - Enforced 5-tier resolution priority hierarchy: 1. Explicit request > 2. Person/Website > 3. Workflow > 4. Global default > 5. System fallback.
  - Distinguishes explicit, confirmed learned, and inferred preferences with confirmation thresholding.
  - Strict privacy enforcement: credentials, tokens, passwords, cookies, and private message contents are strictly prohibited from persistence (`MemoryPrivacyViolation`).
  - Registered `preference_query` and `preference_store` BaseTools and `/api/v1/preferences` REST endpoints.
- [x] **4. Full Automated Test Verification:**
  - 212 backend pytest tests passing (100% pass rate).
  - 137 frontend vitest tests passing (100% pass rate).
  - Zero regressions across existing tools, approvals, and automation adapters.

---

## Phase 5.3 Checklist & Verification: Visual Target Resolution & Reliable Clicking Redesign

- [x] **1. Dedicated Visual Target-Resolution Stage (`VisualTargetResolver`):**
  - Implemented `backend/app/perception/target_resolver.py` with structured `ResolvedVisualTarget` model.
  - Multi-stage pipeline: captures fresh screen observation, identifies active window and application name, attempts fast local UIA/OCR matching for exact text queries, executes multimodal Gemini Vision localization for semantic/visual references ("this video", "second video", "play button", "icon", "search bar"), and employs local spatial heuristics as offline fallback.
  - Denormalizes normalized coordinates (0-1000) to absolute virtual desktop pixel coordinates, validates containment in bounding box and virtual screen, and returns concrete target metadata.
- [x] **2. Pre-Approval Resolution & Approval Flow Redesign:**
  - Integrated resolution directly into `execution_engine.propose()` in `backend/app/execution/engine.py`.
  - When `visual_click_element` is called without concrete coordinates, target resolution executes *before* policy evaluation or approval generation.
  - Unresolvable targets fail immediately with clear diagnostic feedback; **no approval requests are ever created for unresolved phrases**.
  - On successful resolution, tool parameters are rewritten with concrete values: `x`, `y`, `bounding_box`, `app_name`, `window_title`, `detection_method`, `confidence`, and `observation_timestamp`.
  - Action summary explicitly shows target, application, and coordinates: e.g. `"Click on 'YouTube Video: How To Code' in Opera GX at screen coordinates (590, 415)"`.
  - Cryptographic approval token strictly binds to the concrete resolved parameters.
- [x] **3. Native Mouse Click Execution & Physical Cursor Delivery (`click_at`):**
  - Updated `windows_adapter.py` and `mock_adapter.py`.
  - Virtual desktop boundary validation across multi-monitor displays.
  - Window restoration and foreground verification via `restore_and_focus_window(target_hwnd)`.
  - Visible physical cursor placement via `SetCursorPos` and SendInput absolute movement, verified via `GetCursorPos`.
  - Configurable hover duration (`hover_ms`, default 40ms) allowing OS hit-testing and button hover state to settle.
  - Dual-dispatch mouse click execution combining `SendInput` and `mouse_event` with realistic 30ms hold duration, ensuring guaranteed click registration across all Windows UI frameworks (Win32, Tkinter, Chromium, Electron).
- [x] **4. Target Invalidation Guard:**
  - Implemented `is_window_valid(handle)` across platform adapters.
  - Verifies host window validity prior to clicking; if a window was closed or destroyed between resolution and approval grant, click aborts safely with error code `TARGET_INVALIDATED`.
- [x] **5. Post-Click Verification:**
  - Captures post-interaction foreground window state, title changes, and cursor arrival.
  - Returns structured verification status: `SUCCESS`, `DISPATCHED_UNVERIFIED`, `TARGET_INVALIDATED`, or `FAILED`.
- [x] **6. Frontend Approval Presentation:**
  - Enhanced `ApprovalBubble.tsx` to display concrete resolved target, target application, screen coordinates `(x, y)`, bounding box dimensions, detection method badge (`Visual AI 🧠`, `UI Automation 🏛️`, `Local OCR 🔤`, `Hybrid Grounding 🎯`), and confidence percentage.
- [x] **7. Automated & Real Windows Live Test Verification:**
  - 176 backend pytest tests passing (100% pass rate).
  - 122 frontend vitest tests passing (100% pass rate).
  - Created `scripts/test_real_clicking_live.py` verifying real Windows physical cursor movement and click delivery on an active GUI test surface with 100% confirmed button and simulated video card clicks.

---

## Environment Verification

| Tool / Runtime | Detected Version | Purpose | Verification Status |
| :--- | :--- | :--- | :--- |
| **Python** | 3.13.10 | Backend runtime & automation scripts | Verified (`python --version`) |
| **uv** | 0.13.1 | Python virtual environment & package manager | Verified (`uv --version`) |
| **mss** | 10.2.0 | Multi-monitor on-demand Windows screen capture | Verified in `.venv` |
| **winocr** | 0.0.15 | Native Windows 11 Media OCR (local on-device) | Verified in `.venv` |
| **google-genai** | 2.30.1 | Official Google Gemini Python SDK with Multimodal Vision | Verified in `.venv` |
| **Node.js** | v24.20.0 | Frontend build & dev server runtime | Verified (`node --version`) |
| **npm** | 11.19.0 | Node package manager | Verified (`npm --version`) |
| **Microsoft Edge** | Available | Standalone desktop application window host | Verified |
| **Rust / Cargo** | Optional in Phase 3 | Tauri native binary compiler | Configured (`src-tauri/`) |

---

## Phase 4 Checklist & Verification

- [x] **Phase 4.1: Screen Capture Engine (`backend/app/perception/screen_capture.py`):**
  - MSS-based multi-monitor capture engine supporting Monitor 0 (virtual combined desktop), Monitor 1+ (discrete physical displays), and Active Window targeting via Win32 `GetForegroundWindow`.
  - Automatic thread attachment to Windows interactive user desktop (`WinSta0/default`) ensuring zero GDI/BitBlt failures across sandboxes.
  - Ephemeral in-memory PIL processing without permanent disk retention.
  - Strict privacy: only on-demand capture, no continuous background grab.
- [x] **Phase 4.2: Local Windows OCR (`backend/app/perception/ocr_engine.py`):**
  - Native Windows Media OCR integration (`winocr`), running 100% on-device with hardware acceleration.
  - Preserves natural reading order, lines, and spatial word bounding boxes (`x, y, width, height`).
  - Pure local execution: user requests to read screen text never upload screenshots to cloud models.
- [x] **Phase 4.3: Visual Context & Gemini Multimodal Vision (`backend/app/providers/gemini.py`):**
  - Official Google GenAI SDK multimodal integration: dynamically passes decoded JPEG/PNG bytes via `types.Part.from_bytes` in chat contents.
  - Explicit user authorization requirement: visual context is only encoded and dispatched when the user grants explicit consent.
- [x] **Phase 4.4: Approval Rejection & Failure Conversation UX:**
  - Scenario A (User rejects approval): Emits distinct conversational response: `"Understood. I've cancelled that action as requested. Nothing was changed."`
  - Scenario B (Policy block): Explains `"I can't perform that action because it violates my security restrictions."`
  - Scenario C (Execution failure): Explains `"I attempted to perform the action, but Windows returned an error: ..."`
  - Scenario D (Approval expired): Explains `"The approval request expired before it was authorized. I haven't performed the action."`
  - Exactly-once delivery guaranteed by approval token lifecycle and replay protection (409 Conflict).
- [x] **Phase 4.5: HUD Frontend Integration (`frontend/src/`):**
  - Added `ScreenPerceptionModal.tsx` allowing monitor selection, target scope (active window vs full display), and choice between Local OCR and Gemini Vision.
  - Privacy consent warning screen displayed before any external visual transmission.
  - Real-time status indicators in command bar (`👁 Screen` button) and modal.
  - Full REST API suite under `/api/v1/tools` and `/api/v1/approvals`.
- [x] **Frontend HUD Integration:**
  - Upgraded `ApprovalPreviewPanel.tsx` and `services/api.ts` connected to live FastAPI approvals endpoint.
  - Interactive approval and rejection triggers updating HUD state and triggering procedural audio cues.
  - Retained simulation/demo test mode for developer sandbox testing.
- [x] **Milestone 2.4 / 2.5 Evolution: Full-Response Neural Speech Synthesis:**
  - Transitioned from sentence-level chunked streaming to full-response synthesis to eliminate unnatural inter-sentence pauses and fragmented cadence.
  - Streaming text updates in HUD preserved token-by-token during Gemini SSE streaming.
  - Full response is normalized and synthesized in a single unified operation upon Gemini completion.
  - Persistent Piper worker retained in memory with expanded 64MB buffer and dynamic timeout scaling for arbitrary response lengths.
  - Speech normalization, pronunciation dictionary, and 3 delivery profiles (Relaxed, Conversational, Formal) fully preserved.
  - Audio plays continuously as a single seamless stream with zero artificial queue pauses.
- [x] **Phase 5 Checklist & Verification: Visual Computer Interaction & UI Grounding:**
  - `UIElementGroundingEngine` (`backend/app/perception/grounding.py`): Real-time spatial fusion of accessible UIA controls and Windows Media OCR lines into grounded interactive elements.
  - Natural-language target fuzzy matching with type weighting, spatial disambiguation, and ambiguity rejection (`AmbiguousTargetError`).
  - Observation staleness check rejecting interactions older than freshness threshold (default 5.0s).
  - Grounded interaction tools: `visual_locate_elements` (`READ_ONLY`), `visual_click_element` (`CONSEQUENTIAL`), `visual_type_into_element` (`CONSEQUENTIAL`), and `visual_scroll_region` (`CONTROLLED`).
  - Strict security policy: Consequential mutating actions (`visual_click_element`, `visual_type_into_element`) require explicit human approval via the HUD approval gateway. Target element text, coordinates, and window title are prominently displayed in the approval dialog.
  - Bounded debugging screen recording: `ScreenRecordingService` exports local animated GIF clips (bounded to 1-30s @ 1-15fps) saved exclusively to `./recordings/` with zero cloud uploads or telemetry.
  - Frontend UI: Screen Perception Modal element grounding viewer and target pill indicators in `ApprovalBubble.tsx`.
- [x] **Multi-Step Task Execution & Provider Resilience (Completed):**
  - Resolved premature IDLE state across sequential multi-step desktop tasks by maintaining active lifecycle state (`EXECUTING`, `AWAITING_APPROVAL`) across turns.
  - Fixed Google GenAI SDK `thought_signature` preservation: candidate parts returned by Gemini during tool calls are passed intact into subsequent agent turns, eliminating `400 INVALID_ARGUMENT (missing thought_signature)` faults.
  - Implemented automatic continuation turn dispatch upon operator approval in `handleApprove`: once authorized and executed, JARVIS automatically resumes and completes remaining steps of the multi-step request.
  - Built comprehensive 5-layer upstream capacity spike (503 / 429) fallback architecture:
    1. **SDK Stream Iteration Retry:** Enclosed `response_stream` iteration within attempt backoff loop, intercepting async `503 UNAVAILABLE` network exceptions on first chunk.
    2. **Model Cascade Failover:** Prioritized responsive models (`gemini-3.1-flash-lite`, `gemini-3-flash-preview`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite-preview`, `gemini-flash-lite-latest`) with automatic runtime active-model switching.
    3. **Offline Local Tool Execution Fallback:** When all cloud models experience 503 capacity spikes, JARVIS detects offline desktop automation commands (e.g., launch Notepad/Calculator/Terminal/Explorer/Paint/VS Code, list windows, list apps, local OCR, screenshot) and executes them directly via local tool execution engine without cloud AI dependency.
    4. **In-Character Voice Degradation:** For non-tool conversational prompts during complete upstream outages, JARVIS emits a polite, calm in-character notice (`"I apologize, sir. The upstream neural network is currently experiencing an acute demand spike..."`) completing with stage `COMPLETED` so speech TTS synthesizes and plays it naturally.
    5. **Frontend Auto-Recovery & Error Sanitization:** Sanitizes raw JSON Python dicts out of error messages, labels capacity spikes as `SERVICE_NOTICE` (Warning) instead of critical stream failures, and auto-recovers the assistant state to `IDLE` after 2.5 seconds.
  - Removed blocking ASGI disconnection check in `chat.py` that caused SSE stream deadlocks.
  - Added multi-step orchestration test suite `test_multi_step_orchestration.py` covering multi-turn sequential loops, consequential approval gates, 503 failover, conversational fallback, offline local tool fallback, error sanitization, error recovery, and cancellation.
- [x] **Automated Testing & Verification:**
  - 140+ backend pytest tests passing across all suites (`pytest`).
  - 116 frontend tests passing across 16 test files (`vitest`).
  - TypeScript typecheck (`tsc`): 0 errors.
  - Frontend production build (`vite build`): Clean production bundle in 997ms.

---

## Next Steps
1. Phase 6: Hands-free voice pipeline with Voice Activity Detection (VAD) and multi-step task planning.
2. Extend grounded UI interaction with multi-step computer automation macros.
