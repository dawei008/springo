export const BRIDGE_MESSAGE_TYPES = {
  // iframe → host
  SET_STATE: 'springo:set-state',
  SEND_TO_CHAT: 'springo:send-to-chat',
  CALL_TOOL: 'springo:call-tool',
  NOTIFICATION: 'springo:notification',
  CLIPBOARD: 'springo:clipboard',
  READY: 'springo:ready',
  RESIZE: 'springo:resize',
  ELEMENT_PINNED: 'springo:element-pinned',
  SELECTION_CONTEXT: 'springo:selection-context',
  // host → iframe
  STATE_UPDATE: 'springo:state-update',
  CHAT_ACTION: 'springo:chat-action',
  TOOL_RESULT: 'springo:tool-result',
} as const;

export function generateBridgeSdk(initialState: Record<string, unknown>): string {
  const serializedState = JSON.stringify(initialState).replace(/<\//g, '<\\/');
  const STATE_UPDATE = JSON.stringify(BRIDGE_MESSAGE_TYPES.STATE_UPDATE);
  const CHAT_ACTION = JSON.stringify(BRIDGE_MESSAGE_TYPES.CHAT_ACTION);
  const TOOL_RESULT = JSON.stringify(BRIDGE_MESSAGE_TYPES.TOOL_RESULT);

  return '<script>' +
    '(function() {' +
      'var __INITIAL_STATE__ = ' + serializedState + ';' +
      'var state = JSON.parse(JSON.stringify(__INITIAL_STATE__));' +
      'var stateUpdateHandlers = [];' +
      'var chatActionHandlers = [];' +
      'var pendingToolCalls = {};' +

      'function postToParent(type, payload) {' +
        'if (window.parent && window.parent !== window) {' +
          'window.parent.postMessage({ type: type, payload: payload }, "*");' +
        '}' +
      '}' +

      'function generateId() {' +
        'return Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);' +
      '}' +

      'window.springo = {' +
        'setState: function(data) {' +
          'if (data && typeof data === "object") {' +
            'for (var key in data) {' +
              'if (data.hasOwnProperty(key)) {' +
                'state[key] = data[key];' +
              '}' +
            '}' +
          '}' +
          'postToParent("springo:set-state", JSON.parse(JSON.stringify(state)));' +
        '},' +

        'getState: function() {' +
          'return JSON.parse(JSON.stringify(state));' +
        '},' +

        'replaceState: function(data) {' +
          'state = JSON.parse(JSON.stringify(data));' +
          'postToParent("springo:set-state", JSON.parse(JSON.stringify(state)));' +
        '},' +

        'onStateUpdate: function(handler) {' +
          'if (typeof handler === "function") {' +
            'stateUpdateHandlers.push(handler);' +
          '}' +
        '},' +

        'sendToChat: function(message) {' +
          'postToParent("springo:send-to-chat", { message: message });' +
        '},' +

        'onChatAction: function(handler) {' +
          'if (typeof handler === "function") {' +
            'chatActionHandlers.push(handler);' +
          '}' +
        '},' +

        'callTool: function(name, input) {' +
          'var id = generateId();' +
          'return new Promise(function(resolve, reject) {' +
            'pendingToolCalls[id] = { resolve: resolve, reject: reject };' +
            'postToParent("springo:call-tool", { id: id, name: name, input: input });' +
          '});' +
        '},' +

        'readFile: function(path) {' +
          'return window.springo.callTool("read_file", { path: path });' +
        '},' +

        'writeFile: function(path, content) {' +
          'return window.springo.callTool("write_file", { path: path, content: content });' +
        '},' +

        'showNotification: function(msg) {' +
          'postToParent("springo:notification", { message: msg });' +
        '},' +

        'copyToClipboard: function(text) {' +
          'postToParent("springo:clipboard", { text: text });' +
        '},' +

        'ready: function() {' +
          'postToParent("springo:ready", {});' +
        '},' +

        'requestResize: function(width, height) {' +
          'postToParent("springo:resize", { width: width, height: height });' +
        '}' +
      '};' +

      // Selection-to-context: notify host whenever the artifact has a stable
      // text selection. Debounced so dragging doesn't spam.
      'var _selTimer = null;' +
      'function _emitSelection() {' +
        'var sel = document.getSelection ? document.getSelection() : null;' +
        'if (!sel || sel.isCollapsed) {' +
          'postToParent("springo:selection-context", null);' +
          'return;' +
        '}' +
        'var text = String(sel.toString() || "").trim();' +
        'if (text.length < 2) {' +
          'postToParent("springo:selection-context", null);' +
          'return;' +
        '}' +
        'var clamped = text.length > 4000 ? text.slice(0, 4000) + "…" : text;' +
        'var rect = null;' +
        'try {' +
          'var range = sel.getRangeAt(0);' +
          'var r = range.getBoundingClientRect();' +
          'if (r && (r.width || r.height)) rect = { x: r.x, y: r.y, width: r.width, height: r.height };' +
        '} catch (e) {}' +
        'postToParent("springo:selection-context", { text: clamped, rect: rect });' +
      '}' +
      'function _scheduleSelection() {' +
        'if (_selTimer) clearTimeout(_selTimer);' +
        '_selTimer = setTimeout(_emitSelection, 220);' +
      '}' +
      'document.addEventListener("selectionchange", _scheduleSelection);' +
      'document.addEventListener("mouseup", _scheduleSelection);' +
      'document.addEventListener("keyup", function(e) {' +
        'if (e.key === "Shift" || e.shiftKey) _scheduleSelection();' +
      '});' +

      'window.addEventListener("message", function(event) {' +
        // Only accept messages from the host that mounted us.
        'if (event.source !== window.parent) { return; }' +
        'var data = event.data;' +
        'if (!data || typeof data.type !== "string") { return; }' +
        // Allowlist host→iframe message types.
        'if (data.type !== ' + STATE_UPDATE + ' && data.type !== ' + CHAT_ACTION + ' && data.type !== ' + TOOL_RESULT + ') { return; }' +

        'if (data.type === ' + STATE_UPDATE + ') {' +
          'state = JSON.parse(JSON.stringify(data.payload));' +
          'for (var i = 0; i < stateUpdateHandlers.length; i++) {' +
            'try { stateUpdateHandlers[i](window.springo.getState()); } catch (e) { console.error("[springo-bridge]", e); }' +
          '}' +
        '}' +

        'if (data.type === ' + CHAT_ACTION + ') {' +
          'for (var j = 0; j < chatActionHandlers.length; j++) {' +
            'try { chatActionHandlers[j](data.payload); } catch (e) { console.error("[springo-bridge]", e); }' +
          '}' +
        '}' +

        'if (data.type === ' + TOOL_RESULT + ') {' +
          'var payload = data.payload;' +
          'if (payload && payload.id && pendingToolCalls[payload.id]) {' +
            'var pending = pendingToolCalls[payload.id];' +
            'delete pendingToolCalls[payload.id];' +
            'if (payload.error) {' +
              'pending.reject(new Error(payload.error));' +
            '} else {' +
              'pending.resolve(payload.result);' +
            '}' +
          '}' +
        '}' +
      '});' +
    '})();' +
  '</script>';
}
