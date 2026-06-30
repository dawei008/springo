# Springo for Chrome

Lets Springo drive your **real, signed-in Chrome** — navigate, click, type,
read pages, and screenshot — the same way OpenAI's "Codex for Chrome" works.
Unlike the Playwright/CDP path (which launches a throwaway browser on a debug
port with no login state), this extension operates inside your actual Chrome
profile, so authenticated sites just work. All Springo-controlled tabs live in a
dedicated **Springo** tab group so they never disturb your own tabs.

## How it works

```
Springo agent ──tool call──▶ FastAPI backend ──WebSocket──▶ Chrome extension ──CDP──▶ your Chrome
   web_navigate              /v1/browser            background.js        chrome.debugger
```

- The extension's service worker dials into `ws://localhost:8081/v1/browser`.
- Backend tool handlers (`web_navigate`, `web_click`, `web_type`, `web_read_page`,
  `web_screenshot`, `web_evaluate`, `web_tabs`, `web_browser_status`) push
  commands over that socket and await the reply.
- The extension runs them via `chrome.debugger` (CDP) on a tab inside the
  Springo tab group.

The **first** action triggers Chrome's native *"Springo for Chrome started
debugging this browser"* banner — that's the one-time "approve debugging"
prompt. Leave it; the link stays live.

## Install (load unpacked)

1. Make sure the Springo backend is running (`./start.sh`) on `localhost:8081`.
2. Open Chrome → `chrome://extensions`.
3. Toggle **Developer mode** (top-right) on.
4. Click **Load unpacked** and select this folder:
   `springo-app/chrome-extension/`
5. The Springo icon appears in the toolbar. Click it → **Connect**.
6. The popup dot turns green when connected to the backend.

## Use

Ask Springo to do something in the browser, e.g. *"open my GitHub
notifications and tell me what's new"*. It will use the `web_*` tools, which
create/reuse a tab in the **Springo** tab group and act there.

Check the link any time with the `web_browser_status` tool or
`GET /v1/browser/status`.

## Available tools

| Tool | What it does |
|------|--------------|
| `web_browser_status` | Is the extension connected? |
| `web_navigate` | Go to a URL |
| `web_click` | Click by CSS selector or x/y coordinates |
| `web_type` | Type text (optionally submit with Enter) |
| `web_read_page` | Read page text or HTML |
| `web_screenshot` | PNG screenshot (base64) |
| `web_evaluate` | Run a JS expression, return its value |
| `web_tabs` | list / open / close / select tabs in the Springo group |

## Notes & limits

- **One browser at a time.** The newest extension connection wins; if you have
  Chrome open in two profiles, only the one you clicked Connect in is driven.
- **CORS doesn't gate WebSockets** — the backend checks the handshake Origin
  itself (`chrome-extension://…`, loopback, `file://`) in
  `api/routers/browser_ext.py`.
- **Security.** The extension has broad permissions (debugger, all-URLs) because
  it operates your real browser. It only ever connects to `localhost:8081`. The
  agent acts as you on logged-in sites — review what you ask it to do.
- This replaces the need for `start-playwright-cdp.sh` for browser tasks, but the
  Playwright MCP server is still available if you prefer the isolated profile.
