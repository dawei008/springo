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
  // host → iframe
  STATE_UPDATE: 'springo:state-update',
  CHAT_ACTION: 'springo:chat-action',
  TOOL_RESULT: 'springo:tool-result',
} as const;

export function generateBridgeSdk(initialState: Record<string, unknown>): string {
  const serializedState = JSON.stringify(initialState).replace(/<\//g, '<\\/');

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

      'window.addEventListener("message", function(event) {' +
        'var data = event.data;' +
        'if (!data || typeof data.type !== "string") { return; }' +

        'if (data.type === "springo:state-update") {' +
          'state = JSON.parse(JSON.stringify(data.payload));' +
          'for (var i = 0; i < stateUpdateHandlers.length; i++) {' +
            'try { stateUpdateHandlers[i](window.springo.getState()); } catch (e) { console.error("[springo-bridge]", e); }' +
          '}' +
        '}' +

        'if (data.type === "springo:chat-action") {' +
          'for (var j = 0; j < chatActionHandlers.length; j++) {' +
            'try { chatActionHandlers[j](data.payload); } catch (e) { console.error("[springo-bridge]", e); }' +
          '}' +
        '}' +

        'if (data.type === "springo:tool-result") {' +
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
