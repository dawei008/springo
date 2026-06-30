/**
 * Springo for Chrome — background service worker.
 *
 * Connects to the Springo backend over WebSocket, receives browser-automation
 * commands, and executes them in the user's REAL Chrome via chrome.debugger
 * (CDP) + chrome.tabs / chrome.tabGroups. All Springo-controlled tabs live in a
 * dedicated "Springo" tab group so they don't disturb the user's own tabs.
 *
 * The very first chrome.debugger.attach() triggers Chrome's native
 * "<extension> started debugging this browser" banner — that is the one-time
 * "approve debugging" prompt. After that the link stays live.
 */

const WS_URL = 'ws://localhost:8081/v1/browser';
const CDP_VERSION = '1.3';
// MV3 service workers are suspended when idle, which drops any pending
// setTimeout. chrome.alarms survive suspension and wake the worker, so we use
// an alarm — not setTimeout — to drive reconnection and keep the link alive.
const KEEPALIVE_ALARM = 'springo-keepalive';
const KEEPALIVE_PERIOD_MIN = 0.4; // ~24s, just under Chrome's ~30s idle cutoff

let ws = null;
let connected = false;
let shouldConnect = false;      // user intent (persisted)
let controlledTabId = null;     // the tab Springo drives
let tabGroupId = null;          // the "Springo" tab group
let attachedTabId = null;       // tab the debugger is currently attached to

// ── Connection state persistence ────────────────────────────────────────────

function bootstrap() {
  chrome.storage.local.get(['shouldConnect'], (r) => {
    shouldConnect = r.shouldConnect !== false; // default ON
    if (shouldConnect) {
      ensureKeepaliveAlarm();
      connect();
    }
  });
}

// Run on worker (re)start, install, and browser launch — MV3 may spin the
// worker up via any of these, and the top-level body alone is not guaranteed
// to have run recently.
bootstrap();
chrome.runtime.onInstalled.addListener(bootstrap);
chrome.runtime.onStartup.addListener(bootstrap);

function ensureKeepaliveAlarm() {
  chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: KEEPALIVE_PERIOD_MIN });
}

// The alarm both keeps the worker warm and retries a dropped connection —
// this is the MV3-safe replacement for setTimeout-based reconnect.
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== KEEPALIVE_ALARM) return;
  if (shouldConnect && !connected) connect();
});

function setShouldConnect(value) {
  shouldConnect = value;
  chrome.storage.local.set({ shouldConnect: value });
  if (value) {
    ensureKeepaliveAlarm();
    connect();
  } else {
    chrome.alarms.clear(KEEPALIVE_ALARM);
    disconnect();
  }
}

function broadcastStatus() {
  chrome.runtime.sendMessage({ type: 'status', connected, controlledTabId }).catch(() => {});
}

// ── WebSocket link ───────────────────────────────────────────────────────────

let connecting = false;       // single-flight guard: a socket is being opened
let lastConnectAt = 0;        // throttle: don't reopen faster than MIN_CONNECT_GAP
const MIN_CONNECT_GAP_MS = 5000;

function connect() {
  // Already have a live/opening socket — never open a second one.
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  if (connecting) return;
  // Anti-storm: if we opened a socket very recently, wait for the alarm tick
  // instead of hammering the backend (which caused an attach/detach loop).
  const now = Date.now();
  if (now - lastConnectAt < MIN_CONNECT_GAP_MS) return;

  connecting = true;
  lastConnectAt = now;
  try {
    ws = new WebSocket(WS_URL);
  } catch (e) {
    ws = null;
    connecting = false;
    // The keepalive alarm will retry; nothing else to do here.
    return;
  }

  const socket = ws; // capture; guards below ignore events from a stale socket

  socket.onopen = () => {
    connecting = false;
    if (socket !== ws) return;
    connected = true;
    socket.send(JSON.stringify({ type: 'hello', version: chrome.runtime.getManifest().version }));
    broadcastStatus();
  };

  socket.onmessage = async (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch { return; }
    if (msg.type === 'welcome') return;
    if (typeof msg.id === 'number' && msg.action) {
      const reply = await handleCommand(msg.action, msg.params || {});
      // Reply only if this socket is still the live one.
      if (socket === ws && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ id: msg.id, ...reply }));
      }
    }
  };

  socket.onclose = () => {
    connecting = false;
    // Ignore close events from a socket we've already replaced.
    if (socket !== ws) return;
    connected = false;
    broadcastStatus();
    // Reconnect is driven by the keepalive alarm (setTimeout is unreliable in MV3).
  };

  socket.onerror = () => { connecting = false; try { socket.close(); } catch {} };
}

function disconnect() {
  if (ws) { try { ws.close(); } catch {} ws = null; }
  connected = false;
  detachDebugger();
  broadcastStatus();
}

// ── Tab + tab-group management ───────────────────────────────────────────────

async function ensureControlledTab() {
  // Reuse the existing controlled tab if it's still alive.
  if (controlledTabId !== null) {
    try {
      await chrome.tabs.get(controlledTabId);
      return controlledTabId;
    } catch { controlledTabId = null; }
  }
  const tab = await chrome.tabs.create({ url: 'about:blank', active: false });
  controlledTabId = tab.id;
  await groupControlledTab(tab.id);
  return controlledTabId;
}

async function groupControlledTab(tabId) {
  try {
    const groupId = await chrome.tabs.group({ tabIds: [tabId] });
    tabGroupId = groupId;
    await chrome.tabGroups.update(groupId, { title: 'Springo', color: 'cyan' });
  } catch (e) {
    // tabGroups may be unavailable in rare cases; non-fatal.
  }
}

// ── chrome.debugger (CDP) plumbing ───────────────────────────────────────────

function debuggerSend(tabId, method, params = {}) {
  return new Promise((resolve, reject) => {
    chrome.debugger.sendCommand({ tabId }, method, params, (result) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve(result);
    });
  });
}

async function ensureAttached(tabId) {
  if (attachedTabId === tabId) return;
  if (attachedTabId !== null) await detachDebugger();
  await new Promise((resolve, reject) => {
    chrome.debugger.attach({ tabId }, CDP_VERSION, () => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve();
    });
  });
  attachedTabId = tabId;
  await debuggerSend(tabId, 'Page.enable');
  await debuggerSend(tabId, 'Runtime.enable');
  await debuggerSend(tabId, 'DOM.enable');
}

function detachDebugger() {
  return new Promise((resolve) => {
    if (attachedTabId === null) return resolve();
    const id = attachedTabId;
    attachedTabId = null;
    chrome.debugger.detach({ tabId: id }, () => { void chrome.runtime.lastError; resolve(); });
  });
}

// Detached externally (e.g. user closed DevTools banner) — reset state.
chrome.debugger.onDetach.addListener((source) => {
  if (source.tabId === attachedTabId) attachedTabId = null;
});

// ── Command handlers ─────────────────────────────────────────────────────────

async function handleCommand(action, params) {
  try {
    switch (action) {
      case 'navigate':   return await cmdNavigate(params);
      case 'click':      return await cmdClick(params);
      case 'type':       return await cmdType(params);
      case 'read_page':  return await cmdReadPage(params);
      case 'screenshot': return await cmdScreenshot(params);
      case 'evaluate':   return await cmdEvaluate(params);
      case 'tabs':       return await cmdTabs(params);
      default:           return { error: `Unknown action: ${action}` };
    }
  } catch (e) {
    return { error: String(e && e.message ? e.message : e) };
  }
}

async function evalInPage(tabId, expression, returnByValue = true) {
  const res = await debuggerSend(tabId, 'Runtime.evaluate', {
    expression,
    returnByValue,
    awaitPromise: true,
  });
  if (res.exceptionDetails) {
    throw new Error(res.exceptionDetails.exception?.description || 'JS evaluation failed');
  }
  return res.result?.value;
}

async function cmdNavigate({ url }) {
  const tabId = await ensureControlledTab();
  await ensureAttached(tabId);
  await debuggerSend(tabId, 'Page.navigate', { url });
  // Give the page a moment to begin loading, then settle.
  await waitForLoad(tabId, 15000);
  const title = await evalInPage(tabId, 'document.title').catch(() => '');
  const finalUrl = await evalInPage(tabId, 'location.href').catch(() => url);
  return { result: { ok: true, url: finalUrl, title } };
}

function waitForLoad(tabId, timeoutMs) {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => { if (!done) { done = true; chrome.debugger.onEvent.removeListener(listener); resolve(); } };
    const listener = (source, method) => {
      if (source.tabId === tabId && method === 'Page.loadEventFired') finish();
    };
    chrome.debugger.onEvent.addListener(listener);
    setTimeout(finish, timeoutMs);
  });
}

async function cmdClick({ selector, x, y }) {
  const tabId = await ensureControlledTab();
  await ensureAttached(tabId);
  if (selector) {
    const ok = await evalInPage(tabId, `(() => {
      const el = document.querySelector(${JSON.stringify(selector)});
      if (!el) return false;
      el.scrollIntoView({block:'center'});
      el.click();
      return true;
    })()`);
    if (!ok) return { error: `No element matched selector: ${selector}` };
    return { result: { ok: true, clicked: selector } };
  }
  // Coordinate click via synthesized mouse events.
  await debuggerSend(tabId, 'Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
  await debuggerSend(tabId, 'Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
  return { result: { ok: true, clicked: { x, y } } };
}

async function cmdType({ text, selector, submit }) {
  const tabId = await ensureControlledTab();
  await ensureAttached(tabId);
  if (selector) {
    const ok = await evalInPage(tabId, `(() => {
      const el = document.querySelector(${JSON.stringify(selector)});
      if (!el) return false;
      el.focus();
      return true;
    })()`);
    if (!ok) return { error: `No element matched selector: ${selector}` };
  }
  for (const ch of String(text)) {
    await debuggerSend(tabId, 'Input.dispatchKeyEvent', { type: 'keyDown', text: ch });
    await debuggerSend(tabId, 'Input.dispatchKeyEvent', { type: 'keyUp', text: ch });
  }
  if (submit) {
    await debuggerSend(tabId, 'Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, text: '\r' });
    await debuggerSend(tabId, 'Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  }
  return { result: { ok: true, typed: text.length } };
}

async function cmdReadPage({ format }) {
  const tabId = await ensureControlledTab();
  await ensureAttached(tabId);
  const expr = format === 'html'
    ? 'document.documentElement.outerHTML'
    : 'document.body ? document.body.innerText : ""';
  let content = await evalInPage(tabId, expr);
  const truncated = typeof content === 'string' && content.length > 50000;
  if (truncated) content = content.slice(0, 50000) + '\n... (truncated)';
  const title = await evalInPage(tabId, 'document.title').catch(() => '');
  const url = await evalInPage(tabId, 'location.href').catch(() => '');
  return { result: { title, url, format: format || 'text', content, truncated } };
}

async function cmdScreenshot({ full_page }) {
  const tabId = await ensureControlledTab();
  await ensureAttached(tabId);
  const params = { format: 'png' };
  if (full_page) params.captureBeyondViewport = true;
  const res = await debuggerSend(tabId, 'Page.captureScreenshot', params);
  return { result: { ok: true, media_type: 'image/png', data: res.data } };
}

async function cmdEvaluate({ expression }) {
  const tabId = await ensureControlledTab();
  await ensureAttached(tabId);
  const value = await evalInPage(tabId, `(() => { return (${expression}); })()`);
  return { result: { value } };
}

async function cmdTabs({ action, url, index }) {
  if (action === 'open') {
    const tab = await chrome.tabs.create({ url: url || 'about:blank', active: false });
    await groupControlledTab(tab.id);
    controlledTabId = tab.id;
    return { result: { ok: true, tabId: tab.id } };
  }
  // List tabs currently in the Springo group.
  let groupTabs = [];
  if (tabGroupId !== null) {
    try { groupTabs = await chrome.tabs.query({ groupId: tabGroupId }); } catch {}
  }
  if (action === 'close') {
    const t = groupTabs[index];
    if (!t) return { error: `No tab at index ${index}` };
    await chrome.tabs.remove(t.id);
    if (t.id === controlledTabId) controlledTabId = null;
    return { result: { ok: true } };
  }
  if (action === 'select') {
    const t = groupTabs[index];
    if (!t) return { error: `No tab at index ${index}` };
    controlledTabId = t.id;
    await chrome.tabs.update(t.id, { active: true });
    return { result: { ok: true, tabId: t.id } };
  }
  // default: list
  return {
    result: {
      tabs: groupTabs.map((t, i) => ({ index: i, title: t.title, url: t.url, active: t.id === controlledTabId })),
    },
  };
}

// ── Popup ↔ worker messaging ─────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'getStatus') {
    sendResponse({ connected, shouldConnect, controlledTabId });
  } else if (msg.type === 'setConnect') {
    setShouldConnect(!!msg.value);
    sendResponse({ ok: true });
  }
  return true;
});
