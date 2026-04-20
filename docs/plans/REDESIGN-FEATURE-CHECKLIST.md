# Springo UI Redesign - Feature Preservation Checklist

> Reference: All features from the current UI that must be preserved (or consciously migrated) during the Claude-style redesign.
> Created: 2026-04-20 from branch `main` @ commit 0a17391

---

## 1. Layout & Navigation

### Sidebar
- [ ] Collapsible sidebar (Cmd/Ctrl+Shift+S)
- [ ] Dog logo + "Springo" branding
- [ ] **Workspace Section**
  - [ ] Multi-folder management (add/remove)
  - [ ] Active/default folder indicators
  - [ ] Drag-drop folders
  - [ ] Double-click opens native file manager
  - [ ] Single-click opens file browser panel
- [ ] **Skills & Tools Panel** (collapsible)
  - [ ] Plugins list with metadata
  - [ ] Built-in skills (/name, /rename, /clear, /terminal, /plan, /ultraplan, /design)
  - [ ] MCP servers list
  - [ ] Drag-drop skills to message input
  - [ ] Double-click skills to open SKILL.md
- [ ] **New Chat Button** (Cmd/Ctrl+N)
- [ ] **Conversation Search** (Cmd/Ctrl+K, real-time, case-insensitive)
- [ ] **Conversations List**
  - [ ] Date-grouped sessions (Today, Yesterday, Last 7 days, Older)
  - [ ] Session numbering (newest = highest)
  - [ ] Status indicators (pending, running, completed, error, compacting, completed-unseen)
  - [ ] Active session highlighting
  - [ ] Rename via double-click or context menu
  - [ ] Auto-title from last user message
  - [ ] Delegation badges (#outgoing, #incoming)
  - [ ] Delete button per session
  - [ ] Context menu: Rename, Export JSON, Copy Session ID
- [ ] **Sidebar Footer** with settings button

### Header
- [ ] Session title display
- [ ] Toggle sidebar button
- [ ] Toggle right panel button
- [ ] **Recording Button** (start/stop, replay mode integration)
- [ ] **Voice Transcription Button** (start/stop, auto-open Meeting tab)
- [ ] **Design Mode Button** (toggle design panel)

### StatusBar
- [ ] Server health polling (3s fast, 30s slow)
- [ ] Status: Ready, Running, Completed, Error, Connecting, Compacting
- [ ] Working directory display
- [ ] Working directory selector dropdown (add folder option)
- [ ] Per-session working directory override

---

## 2. Chat Features

### ChatArea
- [ ] Message list (scrollable)
- [ ] Welcome screen (empty conversation)
- [ ] Recording bar (when active)
- [ ] Tool execution panel
- [ ] Chat task board (team progress, collapsible)
- [ ] Auto-scroll to latest message
- [ ] Scroll-to-bottom button when scrolled up

### Message Rendering
- [ ] **Avatars**: Dog SVG (assistant), User icon, Delegation icon, Task icon
- [ ] **Timestamps**: Chinese locale (HH:mm or MM-DD HH:mm)
- [ ] **Content types**: Text, images, artifacts, design files
- [ ] **Tool use blocks**: Name, input params, running status with elapsed time, error display, result preview (truncated 2000 chars)
- [ ] **Tool result UI handlers**: todo_panel, schedules_panel, user_question
- [ ] **Markdown**: GFM, line breaks, syntax highlighting (github-dark), clickable file paths, code blocks, tables, lists, blockquotes
- [ ] **Image preview**: Inline display, click for fullscreen, base64 support
- [ ] **Message merging** (streaming chunks)
- [ ] **Skill message parsing** (extract skill name, clean display)
- [ ] **Team messages**: Agent output, ask_user modals, _teamChat flag

### WelcomeScreen
- [ ] Empty state with call-to-action

### RecordingBar
- [ ] Blinking dot indicator
- [ ] Recording/Paused label + timer (MM:SS)
- [ ] Pause/Resume + Stop buttons

---

## 3. MessageInput

- [ ] **Textarea**: Auto-expand, multi-line, placeholder
- [ ] **Keyboard shortcuts**: Cmd/Ctrl+Enter send, Shift+Enter newline, Escape close/stop, Double-Escape force-reset
- [ ] **File attachments**: Button + drag-drop, image/PDF/text/code/docs, preview list, remove button, image compression (max 4.5MB)
- [ ] **Send button** (disabled during streaming)
- [ ] **Model selector**: Current model display, grouped by provider, search, context window info, cache hit rate, token usage display (input/output/cache)
- [ ] **Built-in commands picker**: "/" trigger, arrow nav, Enter select, Escape close
- [ ] **Context indicator**: Usage percentage bar (green/yellow/red), click for breakdown modal
- [ ] **Memory sync status** (synced/syncing/disabled/error/checking)
- [ ] **Token usage**: Format (K/M), session tracking, debounced persistence
- [ ] **Context compaction**: Auto-compact, user notification

---

## 4. Right Panel

- [ ] **Resizable** with drag handle
- [ ] **Tab navigation**: Tasks, Team, Schedules, Meeting
- [ ] Toggle visibility (Cmd/Ctrl+/)

### Tasks Tab
- [ ] Task list: status (○ pending, ◎ in_progress, ✓ completed), subject, progress counter
- [ ] Empty state placeholder
- [ ] Per-session todo storage, auto-restore on session switch

### Team Tab
- [ ] Agent cards: role icon, name, status (idle/working/tool_calling/complete/error), purpose, findings, output (truncated 50K)
- [ ] Expandable/collapsible cards, auto-scroll output
- [ ] Team status (idle/planning/executing/synthesizing/complete/error)
- [ ] User request display
- [ ] Inter-agent messages (sender, recipient, timestamp, broadcast)
- [ ] Ask user modal (question, options, custom answer)
- [ ] Per-team state preservation

### Schedules Tab
- [ ] Task list: name, prompt, schedule description, next run, enabled toggle
- [ ] Execution count/max, status badge
- [ ] Create session toggle, working directory selector
- [ ] Execution history (timestamps, success/failure, output preview)
- [ ] Add new schedule button
- [ ] Cron/delay/once formats

### Meeting Tab
- [ ] Live transcript display (auto-scrolling, partial text)
- [ ] Language selector (ZH/EN/AUTO, cycle on click)
- [ ] LIVE indicator
- [ ] Copy/Clear buttons
- [ ] Per-session transcript storage

---

## 5. ArtifactPanel

- [ ] Resizable with drag handle
- [ ] Open/close, artifact card tabs (multiple artifacts)
- [ ] **Artifact card**: Title, preview/code toggle, download, open in browser, reveal in folder, close
- [ ] **Renderers**: HTML (iframe sandbox), Markdown (GFM + syntax highlight), SVG, Image (base64/URL, fullscreen), Draw.io (viewer.min.js), Excalidraw
- [ ] **Types**: html, markdown, image, svg, excalidraw, drawio
- [ ] Per-session artifact snapshots (save/restore on switch)

---

## 6. DesignPanel

- [ ] Resizable with drag handle, header + toolbar
- [ ] **Viewport toggle**: Desktop (1200px), Tablet (768px), Mobile (375px)
- [ ] **View mode**: Preview (live HTML) / Code (editor)
- [ ] **Extract design system** button (with loading indicator)
- [ ] **Export** button (HTML/project download)
- [ ] **Live preview**: Sandbox iframe, viewport scaling
- [ ] **Code editor**: Multi-file tabs, add/delete file, syntax highlighting, live preview sync
- [ ] **File browser**: Tree view, collapsible folders, click to select
- [ ] **Version timeline**: History list, active indicator, click to switch, revert
- [ ] Per-session design state (save/restore)
- [ ] Toggle via header button or /design command

---

## 7. PlanPanel

- [ ] Resizable, header with progress, error banner
- [ ] **Plan generation**: /plan or /ultraplan, streaming via SSE
- [ ] **Outline sidebar**: Section list with status (○ pending, ✓ approved, — rejected, ◎ in_progress, ● completed, ✗ failed)
- [ ] **Section detail**: Title, status badge, description (markdown), steps, result
- [ ] **Actions**: Approve, Revise (with feedback textarea), Skip, Approve All, Execute
- [ ] **Summary**: Initial LLM summary (markdown)
- [ ] **Progress**: Percentage + count during execution

---

## 8. Settings Modal

### General
- [ ] Default working directory, recording settings (target, dir, replay mode, speed, typing animation)
- [ ] ACP Agents management (add/remove, transport, command, URL, enable/disable)
- [ ] Theme selector (light/dark/system)

### Models
- [ ] Model + compact model selector, 1M context toggle
- [ ] Temperature + max tokens sliders
- [ ] Provider credentials (AWS, DeepSeek, Minimax) with test buttons

### Tools
- [ ] Plugins (enable/disable, metadata), Skills list, MCP Servers (add/manage)

### Memory
- [ ] AgentCore Memory toggle, Memory ID, S3 bucket, LTM strategies

### Integrations
- [ ] External service connections, API keys, test buttons

---

## 9. Recording & Replay

- [ ] Start/stop/pause/resume recording (MediaRecorder VP9, 1s chunks)
- [ ] Timer tracking, saved file path return
- [ ] Replay: Fetch messages, typing animation, speed control (1x/2x/4x/8x)
- [ ] Replay mode toggle in settings

---

## 10. Voice Transcription

- [ ] Start/stop via WebSocket (`ws://127.0.0.1:8081/v1/transcribe`)
- [ ] Microphone permissions check
- [ ] Language: ZH/EN/AUTO
- [ ] Per-session transcript storage, partial text (live updates)

---

## 11. Keyboard Shortcuts

- [ ] Cmd/Ctrl+N — New chat
- [ ] Cmd/Ctrl+K — Focus search
- [ ] Cmd/Ctrl+Shift+S — Toggle sidebar
- [ ] Cmd/Ctrl+/ — Toggle right panel
- [ ] Cmd/Ctrl+Enter — Send message
- [ ] Shift+Enter — Newline
- [ ] Escape — Close modal / stop streaming
- [ ] Double Escape — Force reset all streaming
- [ ] Double-click session — Rename
- [ ] Right-click session — Context menu

---

## 12. Global Features

- [ ] Toast notifications (info/success/warning/error, auto-dismiss)
- [ ] Modals: Settings, Image Preview (fullscreen), Ask User, Plan Approval
- [ ] Theme support (light/dark/system via data-theme)
- [ ] Session auto-title generation (from user message, strip skill wrapper, truncate 40 chars)
- [ ] SSE streaming (text, tool_use, tool_result, context compaction, usage, team events)
- [ ] Delegation system (delegate tasks, track outgoing/incoming, result aggregation)
- [ ] Team collaboration (multi-agent orchestration, role specialization, inter-agent messaging)
- [ ] Memory management (session archival, LTM strategies, S3 storage, memory sync)
- [ ] Cache statistics (creation/read tokens, hit rate, per-session tracking)

---

## 13. Stores (must preserve state management)

- [ ] chatStore — Per-session runtimes, sendMessage, streaming, tool results, usage tracking
- [ ] sessionStore — CRUD sessions, load/switch/delete/rename, status tracking
- [ ] uiStore — All UI toggles, todos, theme, toast, modals, queues
- [ ] settingsStore — Model config, working dirs, model migration
- [ ] artifactStore — Artifact display, per-session snapshots
- [ ] designStore — Design mode, versions, viewport, files, design system
- [ ] planStore — Plan generation/execution, section approval workflow
- [ ] teamStore — Multi-agent state, ask user flow, per-team preservation
- [ ] recordingStore — Recording lifecycle, MediaRecorder management
- [ ] voiceStore — Transcription lifecycle, WebSocket, language
- [ ] replayStore — Replay lifecycle, speed, typing animation
- [ ] scheduleStore — Schedule tasks, cron support, execution history
- [ ] toolsStore — Plugins, skills, MCP servers
