const dot = document.getElementById('dot');
const stateEl = document.getElementById('state');
const tabEl = document.getElementById('tab');
const toggle = document.getElementById('toggle');

function render(status) {
  const on = status.connected;
  dot.classList.toggle('on', on);
  stateEl.textContent = on ? 'Connected' : (status.shouldConnect ? 'Connecting…' : 'Off');
  tabEl.textContent = status.controlledTabId ? `#${status.controlledTabId}` : '—';
  if (status.shouldConnect) {
    toggle.textContent = 'Disconnect';
    toggle.className = 'disconnect';
  } else {
    toggle.textContent = 'Connect';
    toggle.className = 'connect';
  }
  toggle.dataset.next = status.shouldConnect ? 'false' : 'true';
}

function refresh() {
  chrome.runtime.sendMessage({ type: 'getStatus' }, (status) => {
    if (status) render(status);
  });
}

toggle.addEventListener('click', () => {
  const next = toggle.dataset.next === 'true';
  chrome.runtime.sendMessage({ type: 'setConnect', value: next }, () => setTimeout(refresh, 300));
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'status') refresh();
});

refresh();
setInterval(refresh, 1500);
