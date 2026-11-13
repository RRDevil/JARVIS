# JARVIS Desktop Assistant: Security Architecture & Policies

Security is a foundational pillar of JARVIS. Because the assistant interacts with the host operating system, automation APIs, and external language model providers, strict defense-in-depth principles are enforced across every subsystem.

---

## 1. Threat Model & Risk Vectors

| Risk Vector | Description | Mitigation Strategy |
| :--- | :--- | :--- |
| **Direct Shell Exploitation** | AI model attempts to execute arbitrary shell or PowerShell commands. | **Strictly prohibited.** The language model is never given an unrestricted shell tool. All capabilities must be discrete, typed tools. |
| **Indirect Prompt Injection** | Untrusted content (webpages, documents, OCR screen reads) injects malicious instructions into AI context. | All external data is labeled as untrusted data envelopes. Tool execution requires policy evaluation independent of AI reasoning. |
| **Unauthorized Consequential Actions** | Accidental or malicious deletion of files, killing processes, or modifying system configuration. | Tiered authorization model: `CONSEQUENTIAL` and `CRITICAL` tools require explicit human approval via HUD token handshake. |
| **Path Traversal & Filesystem Leaks** | Attacker accesses sensitive files outside of assistant workspace. | Strict path allowlisting and directory sandboxing with canonical path resolution (`os.path.realpath`). |
| **Credential & API Key Exposure** | Leakage of Gemini or user API keys via logs, errors, or prompts. | API keys stored strictly in `.env` or Windows Credential Manager; redacted from all log streams and telemetry. |
| **Local Port Hijacking** | Malicious local processes send unauthorized requests to the backend API. | Backend binds exclusively to `127.0.0.1`. CORS restricted to desktop shell origin (`localhost` / `tauri://localhost`). Optional shared secret bearer token. |

---

## 2. Core Security Invariants

1. **No Raw Shell Access:**
   No tool shall exist that passes unconstrained string arguments to `cmd.exe`, `powershell.exe`, or `subprocess.run(shell=True)`. All system commands must execute through pre-defined, parameter-validated Python functions.

2. **Decoupled Authorization:**
   The AI model determines *what it wants to do*, but the Backend Policy Engine determines *whether it is permitted to do it*. The model cannot override security tiers or grant itself permissions.

3. **Untrusted Data Isolation:**
   Screenshots, OCR output, fetched web pages, and file contents read by the assistant are wrapped in explicit boundary tags:
   ```json
   {
     "data_type": "untrusted_content",
     "source": "screen_ocr",
     "content": "..."
   }
   ```
   System prompts instruct the model never to execute instructions found inside untrusted content envelopes.

4. **Human-in-the-Loop for Consequential Actions:**
   Any action that modifies the filesystem, terminates a process, sends network traffic outside known endpoints, or moves/clicks mouse coordinates on unverified targets requires a user confirmation token issued by the frontend UI.

5. **Verification of Action Success:**
   The assistant backend must never report an action as successful based solely on tool invocation. It must verify the post-condition (e.g., verifying file existence after creation, checking window handle state after focus) before reporting status to the user.

---

## 3. Filesystem Sandboxing

Filesystem operations are strictly bound to explicit allowlisted scopes:
- **Default Allowed Paths:**
  - Application data: `%LOCALAPPDATA%\JARVIS` or `./data`
  - Workspace directory: `%USERPROFILE%\JARVIS_Workspace`
- **Enforcement Mechanism:**
  ```python
  def validate_path(target_path: Path, allowed_roots: list[Path]) -> Path:
      resolved_target = target_path.resolve()
      for root in allowed_roots:
          resolved_root = root.resolve()
          if resolved_target == resolved_root or resolved_root in resolved_target.parents:
              return resolved_target
      raise PermissionError(f"Access denied: {resolved_target} is outside allowed scopes.")
  ```
- **Forbidden Directories:** `C:\Windows`, `C:\Program Files`, root drives `C:\`, system user directories without explicit permission.

---

## 4. Secret Management & Audit Logging

- **Environment Isolation:** Secrets are loaded into memory via `pydantic-settings` from `.env`. The file `.env` is ignored by version control.
- **Audit Trails:** All tool executions are logged into an append-only SQLite table with:
  - Timestamp (UTC ISO 8601)
  - Tool name and validated arguments (sensitive values masked)
  - Approval state (Auto, User-Approved, Rejected)
  - Execution outcome and error traces (if any)

---

## 5. AI Provider Credential Isolation & Untrusted Response Handling

1. **Zero Credential Exposure:**
   - The Gemini API key (`GEMINI_API_KEY`) is read exclusively by the backend service.
   - It is never returned in any API response (including `/api/health` and `/api/info`), never passed in SSE streams, and never accessible to the frontend client.
   - If an upstream exception occurs, the error message is scrubbed to redact any accidental substring matching the API key before returning to the caller.

2. **Untrusted Model Response Rendering:**
   - Model responses are treated as untrusted data envelopes.
   - Frontend renders streaming markdown through `<SafeMarkdown />`, which translates Markdown syntax directly into native React elements with text nodes.
   - Direct execution of raw HTML, `<script>` tags, or malicious attributes (e.g., `onerror`) is strictly prohibited.

3. **Input Bounds & Denial-of-Service Defense:**
   - Conversation inputs are capped at a maximum of 20 turns and 16,000 characters.
   - Streaming calls enforce request timeouts (`AI_REQUEST_TIMEOUT_SECONDS=45.0`) to prevent hung connection slots.
   - Client disconnection triggers immediate stream abort and resource release.

---

## 6. Secure Tool Execution Framework (Phase 3 Controls)

1. **Strict Separation of Concerns:**
   - The AI model only proposes actions via structured parameters.
   - Tools are validated against strict Pydantic schemas before reaching the policy layer.
   - `PolicyEngine` evaluates the action independently of model intent.

2. **Categorical Risk Tiering:**
   - `READ_ONLY`: Safe query tools (listing apps, querying windows, finding UI controls) auto-execute without state mutation.
   - `CONTROLLED`: Low-risk operations (focusing window, minimizing window, launching pre-approved apps) execute under standard policy.
   - `CONSEQUENTIAL`: Operations that modify state (closing windows, UI clicks, text input, keyboard shortcuts) require interactive user approval.
   - `CRITICAL`: System-altering operations (arbitrary shell commands, process termination, mass deletion) are blocked unconditionally.

3. **Cryptographic & TTL Approval Tokens:**
   - Approval requests generate unique tokens bound to canonicalized tool arguments.
   - Tokens expire after 5 minutes (300 seconds); expired tokens return `409 Conflict`.
   - Single-use replay protection: once a token is approved or rejected, subsequent attempts to resolve it are rejected with `409 Conflict`.

4. **Bounded Execution & Resource Protection:**
   - All tool executions run under bounded timeouts (default 10.0 seconds).
   - Async cancellation allows the client to abort pending or running tasks without orphan background processes.

5. **Keyboard Shortcut & UI Automation Allowlisting:**
   - UI automation operates strictly on verified accessible controls (`UIControlInfo`) rather than blind coordinate guessing.
   - Keyboard shortcuts are restricted to an explicit allowlist (`ctrl+s`, `ctrl+c`, `ctrl+v`, `ctrl+z`, `tab`, `enter`, etc.). Dangerous system combinations (`ctrl+alt+del`, `win+r`, `alt+f4`) are rejected.

6. **Hermetic Test Isolation:**
   - Automated tests run against `MockPlatformAdapter` to guarantee that CI/CD runs never launch, focus, or close real applications or windows on developer or host machines.

---

## 7. Screen Perception, Vision & OCR Privacy Governance (Phase 4 Controls)

1. **Strictly On-Demand Capture:**
   - Background screenshot recording, periodic capture loops, and implicit visual monitoring are strictly prohibited.
   - Screen capture occurs only when initiated directly by the user (e.g., clicking `👁 Screen` in the HUD) or via an authorized tool invocation during an active user prompt.

2. **Local-First Processing Principle:**
   - For pure text extraction, error message reading, and screen reading requests, JARVIS prioritizes on-device Windows Media OCR (`winocr`).
   - Pure OCR workflows run 100% locally on the client/backend and do not upload images or text to cloud AI providers.

3. **Explicit External Processing Consent Gateway:**
   - Before any screen capture is transmitted to Google Gemini for multimodal reasoning, the user must explicitly authorize external processing.
   - The HUD modal presents a clear privacy warning: *"Multimodal vision sends an image of your display to Google Gemini. Please ensure no private or sensitive information is visible on screen before proceeding."*
   - Requests without `consent_given=true` are rejected by the backend perception service (`400 Bad Request: Explicit user consent is required before transmitting screen captures to external AI models`).

4. **Ephemeral In-Memory Retention:**
   - Captured screen buffers and base64 payloads exist exclusively in volatile process memory during the turn of conversation.
   - Screenshots are never written to disk, cache directories, or temporary scratch folders unless explicitly requested by the user.

5. **Sanitized Audit Trails & Log Redaction:**
   - Security audit logs record only capture metadata (timestamp, monitor index, resolution, OCR word count, SHA-256 hash of image data).
   - Raw image bytes, base64 data URIs, and full-resolution frame buffers are stripped from audit log entries and terminal outputs.

---

## 8. Visual UI Automation Grounding & Screen Recording Safeguards (Phase 5)

1. **Grounded Coordinate Verification (Zero Coordinate Guessing):**
   - The assistant is strictly prohibited from guessing or fabricating screen coordinates.
   - All desktop interactions (`click_at`, `type_text_at`, `scroll_at`) must resolve to a validated `GroundedUIElement` produced by the spatial fusion of Windows UI Automation control handles and local OCR text boundaries.
   - Coordinates outside desktop display bounds are rejected (`COORDINATES_OUT_OF_BOUNDS`).

2. **Target Ambiguity Rejection:**
   - If a natural-language query resolves to multiple distinct elements with near-identical confidence scores (e.g., two identical "Cancel" buttons in adjacent panes), the engine raises `AmbiguousTargetError`.
   - The system halts execution and requests disambiguating context from the operator rather than executing an action on the wrong control.

3. **Observation Staleness Enforced:**
   - Every grounded element carries a timestamp. If the time elapsed since capture exceeds the freshness threshold (default 5.0 seconds), interactions fail fast or force a fresh live scan to ensure controls have not moved, closed, or changed state.

4. **Consequential Action Approval Gateway:**
   - Mutating visual actions (`visual_click_element`, `visual_type_into_element`) are categorized as `CONSEQUENTIAL`.
   - The HUD approval gateway displays the target element description, visible text, resolved coordinates, and parent window title.
   - Actions cannot execute without explicit human approval.

5. **Bounded Local Screen Recording:**
   - Screen recording is restricted to short, bounded animated GIF clips (1 to 30 seconds maximum, 1 to 15 FPS).
   - Recordings are saved strictly to the local workspace `./recordings/` directory for visual debugging and operator review.
   - Clips are never uploaded to cloud AI providers, telemetry endpoints, or external servers.

---

## 9. Focus-Aware Input Safety & Input-Leakage Prevention (Phase 5.1 Controls)

1. **Target Window Activation & Foreground Verification:**
   - Before any keyboard shortcut or mouse click is dispatched, `WindowsPlatformAdapter` actively restores the target window (`SW_RESTORE`) and requests foreground focus via `AttachThreadInput` and `AllowSetForegroundWindow(-1)`.
   - The platform adapter enforces a strict verification loop polling `GetForegroundWindow()` and confirming process ID match before dispatching input.

2. **Strict Focus Mismatch Safeguard (Anti-Leakage Guard):**
   - Under no circumstances may keyboard shortcuts or text input be injected while J.A.R.V.I.S. (or any unverified background window) remains the active foreground application.
   - If `GetForegroundWindow()` does not match the target window handle or matches a J.A.R.V.I.S. window, input injection is aborted immediately with `FocusMismatchError` (`error_code="FOCUS_MISMATCH"`). Keystrokes are never lost or delivered into the assistant UI.

3. **Global Native Approval Hotkeys (`Ctrl + Alt + Y` / `Ctrl + Alt + N`):**
   - Registered at the OS level via Win32 `RegisterHotKey` with `MOD_NOREPEAT`.
   - Allows operators to approve or deny pending consequential actions without clicking the J.A.R.V.I.S. HUD or stealing foreground focus away from the intended target application.
   - Atomic resolution via `/api/v1/approvals/active/respond` ensures replay-protected, one-time execution.

---

## 10. Modular Application Integration Framework & Cryptographic Approval Binding (Phase 5.2 Controls)

1. **Strict 4-Level Permission Governance:**
   - **Level 1 (Read-Only):** Document inspection, web page reading, window enumeration (auto-permitted).
   - **Level 2 (Controlled):** Non-destructive tab switching, search queries, document drafting (policy-guided).
   - **Level 3 (Consequential):** External messaging (`discord.send_message`, `whatsapp.send_message`), email transmission (`outlook.send_email`), document overwriting (strictly approval-gated).
   - **Level 4 (Restricted):** Hard-blocked actions (credentials, master passwords, payment forms).

2. **Cryptographic Action Approval Binding (`ActionApprovalBinding`):**
   - Approvals are cryptographically bound to the canonical JSON serialization of exact execution parameters via SHA-256 (`content_hash`).
   - If an attacker, malicious prompt injection, or execution race modifies the recipient, message body, target document path, or destination domain between approval grant and dispatch, verification immediately fails and halts execution.
   - Once verified and consumed, approval tokens are marked invalid, preventing replay attacks.

3. **Untrusted Data Envelope Tagging:**
   - Text extracted from external browser tabs, web pages, Discord channels, and incoming messages is treated as untrusted external content.
   - Data envelopes are explicitly tagged as untrusted context before reaching the model or presentation layer, neutralizing prompt injection payloads embedded in third-party content.

4. **Zero Credential / Password Scraping Policy:**
   - Application integration adapters never read, scrape, or extract stored browser credentials, password manager vaults, cookies, or session tokens.
   - All browser integrations utilize standard user-directed automation without accessing encrypted credential stores on disk.

5. **COM Apartment & Process Isolation:**
   - Microsoft Office Win32 COM automation runs in dedicated STA worker threads (`asyncio.to_thread` with explicit `pythoncom.CoInitialize()` and `CoUninitialize()`).
   - Prevents COM threading collisions, memory corruptions, or async event loop blockages.





