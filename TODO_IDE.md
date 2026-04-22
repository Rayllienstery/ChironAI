# ChironAI IDE Integration Tasks

This file contains tasks related to IDE integration, including Xcode, Zed, and other IDE-specific features.

## 0.1) Xcode run/debug plugin for Apple scope (MVP)

### Tasks:
- [ ] Implement "IDE-execution" layer for Apple Ecosystem scope
- [ ] Open project in Xcode
- [ ] Select scheme and destination
- [ ] Run (build + launch)
- [ ] Debug (minimal)
- [ ] Cancel / Stop

### Contracts and Integration Points:
- Endpoints: `/v1/ide/open-xcode`, `/v1/ide/run`, `/v1/ide/debug`, `/v1/ide/cancel`
- Fields: `scheme`, `destination`, `configuration`, `workspace_path`/`project_path`
- Response: `status`, `build_log_preview`, `session_id`, `exit_code`

### Engineering Requirements:
- Read-only project access
- Validate paths to prevent unauthorized project execution

## 0.1.b) SwiftPM Packages + DerivedData / Build management

### Tasks:
- [ ] Discovery of `Package.resolved` and `Package.swift`
- [ ] Actions: Fetch/Resolve Packages, Show Packages, Show package content
- [ ] Diagnostics and UX: progress states, log_preview, disable actions during operations
- [ ] Open DerivedData folder
- [ ] Delete DD & Rebuild project
- [ ] Clean project + Open build folder

### Contracts/Endpoints:
- `POST /v1/ide/spm/fetch`
- `GET /v1/ide/spm/packages`
- `GET /v1/ide/spm/package-content`
- `GET /v1/ide/derived-data/path`
- `POST /v1/ide/derived-data/open`
- `POST /v1/ide/derived-data/delete-and-rebuild`
- `POST /v1/ide/project/clean`
- `POST /v1/ide/build/open-folder`

### UI Requirements:
- Unified "Build & Dependencies" block with buttons for all actions
- State machine: disable buttons during active operations, progress + log preview, clear errors

### Tests:
- Unit: derived data paths, safe deletion scope preview, command/contract formation
- Integration: delete-and-rebuild sequence, open-folder behavior

## 0.2) Plugin for Swift formatting on save (Swift-Format / SwiftLint) — MVP

### Tasks:
- [ ] Choose tool: Swift-Format, SwiftLint, or both
- [ ] Installation/Update: buttons in UI expansion
- [ ] Configuration: read `.swiftformat.yml` and `.swiftlint.yml`
- [ ] Run on save (on-save hook)
- [ ] Display results in IDE

### Contracts and Integration Points:
- JSON contract for proxy: `file_path`, `file_text`, `mode`, `formatter`, `linter`
- Response: `formatted_text`, `diff`, `diagnostics`, `tool_versions`

### Constraints:
- Read-only safety: apply changes on IDE side or strictly limited "write back"
- Performance: time limits, debounce, cache results

### Tests:
- Unit: config parsing, lint output parsing
- Integration: simulate runner on test `.swift` file

## 1) Cursor features to reproduce in Zed (Apple scope)

### 1.1 Chat in IDE with "perfect context" (chat + project aware)

### Tasks:
- [ ] Define Project Context Contract
- [ ] Implement prompt injection for `swift_mode` and IDE context block

### 1.2 Prompt preview / dev console (Cursor "show prompt / debug")

### Tasks:
- [ ] Add `rag_metadata.system_prompt_preview` to `/v1/chat/completions` response
- [ ] Include `project_context` details and `retrieval_question` in dev console payload

### 1.3 RAG "web search for frameworks" (Cursor-like: auto-select documentation)

### Tasks:
- [ ] Subordinate web search behavior in Apple scope
- [ ] Explicit "web block" in system prompt
- [ ] Use `modules/external_docs_rag` module

### 1.4 Symbol-level navigation (Cursor "Go to definition / find references")

### Tasks:
- [ ] Implement local Swift symbol indexer
- [ ] Define tool-like endpoints for Zed
- [ ] Add indexing mechanism

### 1.5 Agentic workflows (Cursor "ask to do X", multi-step)

### Tasks:
- [ ] Design server-side "tool loop" protocol
- [ ] Implement proxy-side dispatcher
- [ ] Instrument prompt for loop

### 1.6 Inline apply edits (Cursor "apply patch")

### Tasks:
- [ ] Define response format for Zed to apply
- [ ] Update system rules for diff generation

### 1.7 Settings (Cursor "model/temp/context")

### Tasks:
- [ ] Normalize input settings from Zed to proxy
- [ ] Add protection against incompatible combinations

## 2) Prompt pipeline for Apple scope

### Tasks:
- [ ] Step 1: Collect base system prompt
- [ ] Step 2: Add Swift mode header
- [ ] Step 3: Add IDE context block
- [ ] Step 4: Add retrieval hints
- [ ] Step 5: Add RAG context block
- [ ] Step 6: Add Web context block (optional)

## 3) Detectors for Apple/Xcode

### Tasks:
- [ ] Implement Xcode project analyzer
- [ ] Implement Swift version / concurrency detectors

## 4) Symbol indexer (Swift) and endpoints

### Tasks:
- [ ] Choose parsing strategy
- [ ] Store index
- [ ] Implement endpoints
- [ ] Incremental indexing

## 5) Tool loop / agent loop protocol

### Tasks:
- [ ] Define tool schema
- [ ] Implement proxy-side dispatcher
- [ ] Instrument prompt for loop

## 5.0) Cursor-like "Plan first" + token-budgeting

### Tasks:
- [ ] Build plan in compact format
- [ ] Iterative plan
- [ ] Token budget manager
- [ ] Summarize tokens
- [ ] Step-oriented RAG selection

## 6) Web search / framework docs UX (Apple scope)

### Tasks:
- [ ] Normalize triggers
- [ ] Manageable limits
- [ ] Visualize source

## 7) Observability (Cursor-like level)

### Tasks:
- [ ] Form "request timeline" for dev console
- [ ] Metrics: latency, RAG chunks, tool loop steps
- [ ] Store first N RAG fragments

## 8) Tests and QA

### Tasks:
- [ ] Unit tests for Project Context Contract
- [ ] Unit tests for prompt assembly
- [ ] Unit tests for web search gating
- [ ] Integration tests for proxy + Zed contract
