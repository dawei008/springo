        // API Base URL - for Electron app
        const BASE_URL = 'http://127.0.0.1:8080';

        // HTML Sanitization helper using DOMPurify
        function sanitizeHTML(html) {
            if (typeof DOMPurify !== 'undefined') {
                return DOMPurify.sanitize(html, {
                    ALLOWED_TAGS: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'hr',
                        'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'span', 'div',
                        'a', 'strong', 'em', 'b', 'i', 'u', 's', 'del', 'ins', 'mark',
                        'sub', 'sup', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
                        'img', 'svg', 'path', 'circle', 'ellipse', 'rect', 'line', 'polyline', 'polygon'],
                    ALLOWED_ATTR: ['href', 'target', 'rel', 'class', 'id', 'style',
                        'src', 'alt', 'width', 'height', 'title',
                        'viewBox', 'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin',
                        'd', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'x1', 'y1', 'x2', 'y2', 'points'],
                    ALLOW_DATA_ATTR: false
                });
            }
            // Fallback: basic escape if DOMPurify not loaded
            return html.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }

        // Escape HTML for plain text contexts
        function escapeHTML(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // ==================== Toast Notification System ====================
        // User-friendly toast notifications for errors and status updates
        function showToast(message, type = 'info', duration = 5000) {
            // Remove existing toast if any
            const existing = document.querySelector('.toast-notification');
            if (existing) existing.remove();

            const toast = document.createElement('div');
            toast.className = `toast-notification toast-${type}`;

            const icons = {
                error: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
                warning: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
                success: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
                info: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
            };

            toast.innerHTML = `
                <span class="toast-icon">${icons[type] || icons.info}</span>
                <span class="toast-message">${escapeHTML(message)}</span>
                <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
            `;

            document.body.appendChild(toast);

            // Auto-remove after duration
            if (duration > 0) {
                setTimeout(() => {
                    if (toast.parentElement) {
                        toast.classList.add('toast-fade-out');
                        setTimeout(() => toast.remove(), 300);
                    }
                }, duration);
            }

            return toast;
        }

        // Reset stuck conversation state - call when network recovers
        function resetStuckConversations() {
            let resetCount = 0;
            for (const convId in convRuntime) {
                const runtime = convRuntime[convId];
                if (runtime.isStreaming) {
                    console.log(`[Recovery] Resetting stuck conversation: ${convId}`);
                    runtime.isStreaming = false;

                    // Remove any thinking indicators
                    const thinkingIdx = runtime.messages.findIndex(m => m.isThinking);
                    if (thinkingIdx >= 0) {
                        runtime.messages.splice(thinkingIdx, 1);
                    }

                    updateConversationStatus(convId, 'error');
                    resetCount++;
                }
            }

            if (resetCount > 0) {
                updateSendButtonState();
                renderMessages();
                showToast(`Connection recovered. ${resetCount} stuck task(s) reset.`, 'warning', 8000);
            }

            return resetCount;
        }

        // Check if error is a network/connection error
        function isNetworkError(error) {
            const msg = error?.message?.toLowerCase() || '';
            return msg.includes('failed to fetch') ||
                   msg.includes('network') ||
                   msg.includes('connection') ||
                   msg.includes('net::err') ||
                   msg.includes('econnrefused') ||
                   msg.includes('enotfound') ||
                   error?.name === 'TypeError' && msg.includes('fetch');
        }

        // Welcome template HTML (stored on load, used when creating new chats)
        let welcomeTemplate = '';

        // Sessions are stored only in backend JSONL (localStorage not used for sessions)
        let conversations = [];
        let currentConversationId = null;

        let settings = {};
        try {
            const storedSettings = localStorage.getItem('settings');
            if (storedSettings) {
                settings = JSON.parse(storedSettings);
                if (typeof settings !== 'object' || settings === null) {
                    settings = {};
                }
            }
        } catch (e) {
            console.error('Failed to parse settings from localStorage, resetting:', e);
            settings = {};
            localStorage.removeItem('settings');
        }
        // OPTIMIZATION: Server-side auto tool execution (eliminates frontend round-trips)
        // When enabled, tools are executed on the server, saving ~1-3 seconds per tool
        const AUTO_TOOL_EXECUTION = true;

        // ==================== Session Storage API ====================
        // Use backend JSONL storage instead of localStorage (like Claude Code)
        // Note: Session ID is just the conversation ID (without hash prefix)
        // Tool results use getSessionId(convId) which adds hash prefix
        const SessionAPI = {
            // Save session to backend (uses convId directly as session_id)
            async save(convId, messages, metadata = {}) {
                try {
                    const response = await fetch(`${BASE_URL}/v1/sessions/${convId}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ messages, metadata })
                    });
                    return response.ok;
                } catch (e) {
                    console.error('SessionAPI.save error:', e);
                    return false;
                }
            },

            // Load session from backend
            async load(sessionId) {
                try {
                    const response = await fetch(`${BASE_URL}/v1/sessions/${sessionId}`);
                    if (response.ok) {
                        const data = await response.json();
                        return data.messages || [];
                    }
                    return [];
                } catch (e) {
                    console.error('SessionAPI.load error:', e);
                    return [];
                }
            },

            // List all sessions
            async list(workingDir = null) {
                try {
                    const url = workingDir
                        ? `${BASE_URL}/v1/sessions?working_dir=${encodeURIComponent(workingDir)}`
                        : `${BASE_URL}/v1/sessions`;
                    const response = await fetch(url);
                    if (response.ok) {
                        const data = await response.json();
                        return data.sessions || [];
                    }
                    return [];
                } catch (e) {
                    console.error('SessionAPI.list error:', e);
                    return [];
                }
            },

            // Delete session
            async delete(sessionId) {
                try {
                    const response = await fetch(`${BASE_URL}/v1/sessions/${sessionId}`, {
                        method: 'DELETE'
                    });
                    return response.ok;
                } catch (e) {
                    console.error('SessionAPI.delete error:', e);
                    return false;
                }
            }
        };

        // OPTIMIZATION 3: Debounced streaming UI updates
        const streamingUIDebounce = {
            timers: {},  // convId -> timer
            pending: {}, // convId -> { text, tools }
            DELAY_MS: 50 // Update UI at most every 50ms
        };

        function debouncedUpdateAssistantMessage(convId, text, tools, isFinal) {
            // Always update immediately if final
            if (isFinal) {
                if (streamingUIDebounce.timers[convId]) {
                    clearTimeout(streamingUIDebounce.timers[convId]);
                    delete streamingUIDebounce.timers[convId];
                }
                delete streamingUIDebounce.pending[convId];
                updateAssistantMessage(convId, text, tools, true);
                return;
            }

            // Store pending update
            streamingUIDebounce.pending[convId] = { text, tools };

            // If no timer, start one
            if (!streamingUIDebounce.timers[convId]) {
                streamingUIDebounce.timers[convId] = setTimeout(() => {
                    const pending = streamingUIDebounce.pending[convId];
                    if (pending && currentConversationId === convId) {
                        updateAssistantMessage(convId, pending.text, pending.tools, false);
                    }
                    delete streamingUIDebounce.timers[convId];
                }, streamingUIDebounce.DELAY_MS);
            }
        }

        // Per-conversation runtime state (not persisted to localStorage)
        // Each conversation has: { isStreaming: bool, attachments: [], messages: [] }
        let convRuntime = {};

        // Cross-session event bus for delegation communication
        const crossSessionEvents = {
            _listeners: {},
            on(event, callback) {
                if (!this._listeners[event]) this._listeners[event] = [];
                this._listeners[event].push(callback);
            },
            off(event, callback) {
                if (!this._listeners[event]) return;
                this._listeners[event] = this._listeners[event].filter(cb => cb !== callback);
            },
            emit(event, data) {
                if (!this._listeners[event]) return;
                this._listeners[event].forEach(cb => cb(data));
            }
        };

        // Get or create runtime state for a conversation
        function getConvRuntime(convId) {
            if (!convId) return { isStreaming: false, attachments: [], messages: [], delegatedTasks: {}, incomingTasks: {}, delegationQueue: [], todos: [] };
            if (!convRuntime[convId]) {
                // Initialize from saved conversation if exists
                const saved = conversations.find(c => c.id === convId);
                convRuntime[convId] = {
                    isStreaming: false,
                    attachments: [],
                    messages: saved?.messages || [],
                    // Cross-session delegation state
                    delegatedTasks: {},   // Tasks delegated to other sessions
                    incomingTasks: {},    // Tasks received from other sessions
                    delegationQueue: [],  // Queue of pending delegations when busy
                    todos: saved?.todos || []  // Restore todos from saved conversation
                };
            }
            return convRuntime[convId];
        }

        // Check if current conversation is streaming
        function isCurrentStreaming() {
            return getConvRuntime(currentConversationId).isStreaming;
        }

        // Get set of all streaming conversation IDs
        function getStreamingConvIds() {
            return Object.keys(convRuntime).filter(id => convRuntime[id].isStreaming);
        }

        // Abort controllers per conversation for stopping tasks
        let abortControllers = {};

        // Get or create abort controller for a conversation
        function getAbortController(convId) {
            if (!abortControllers[convId]) {
                abortControllers[convId] = new AbortController();
            }
            return abortControllers[convId];
        }

        // Reset abort controller for a conversation (call before starting new task)
        function resetAbortController(convId) {
            abortControllers[convId] = new AbortController();
            return abortControllers[convId];
        }

        // Stop the current task
        function stopCurrentTask() {
            if (!currentConversationId) return;

            const runtime = getConvRuntime(currentConversationId);
            if (!runtime.isStreaming) return;

            console.log('Stopping task for conversation:', currentConversationId);

            // Abort the fetch request
            const controller = abortControllers[currentConversationId];
            if (controller) {
                controller.abort();
            }

            // Mark as stopped
            runtime.isStreaming = false;
            runtime.wasStopped = true;

            // Remove thinking indicator if present
            const thinkingIdx = runtime.messages.findIndex(m => m.isThinking);
            if (thinkingIdx >= 0) {
                runtime.messages.splice(thinkingIdx, 1);
            }

            // Update UI
            updateStatus('stopped', 'Task stopped by user');
            updateConversationStatus(currentConversationId, 'idle');
            updateSendButtonState();
            hideToolPanel();
            hideTodoPanel();  // Close Tasks panel when stopped
            renderMessages();

            // Save conversation state
            saveConversation(currentConversationId);
        }

        // Legacy compatibility - will be removed after refactor
        let attachments = [];

        // Projects state
        let projects = JSON.parse(localStorage.getItem('projects') || '[]');
        let currentProjectId = null;

        // Working folders state
        let workingFolders = JSON.parse(localStorage.getItem('workingFolders') || '[]');
        let currentWorkingDir = localStorage.getItem('currentWorkingDir') || ''; // 当前选中的工作目录
        let defaultWorkingFolder = localStorage.getItem('defaultWorkingFolder') || '~/Downloads'; // 默认工作目录，新建会话时自动使用


        // Skills state
        let availableSkills = [];
        let activeSkill = null;  // Currently active skill for the conversation
        let showSkillPicker = false;

        // Initialize
        document.addEventListener('DOMContentLoaded', async () => {
            // Global link click handler - open external URLs in default browser (Chrome new tab)
            // Note: Only intercepts <a href> elements with external URLs, does not affect buttons
            document.addEventListener('click', (e) => {
                // Only handle actual <a> element clicks, not buttons or other elements
                const link = e.target.closest('a[href]');
                if (!link) return;  // Not a link click, let it pass through

                const href = link.getAttribute('href');
                // Only handle external HTTP/HTTPS URLs
                if (href && (href.startsWith('http://') || href.startsWith('https://'))) {
                    e.preventDefault();  // Prevent default navigation
                    // Note: No stopPropagation needed since we're at document level
                    if (window.electronAPI && window.electronAPI.openExternal) {
                        window.electronAPI.openExternal(href);
                    } else {
                        // Fallback for non-Electron environment
                        window.open(href, '_blank');
                    }
                }
            });

            // Store welcome template for later use (before it gets replaced)
            const welcomeEl = document.getElementById('welcome');
            if (welcomeEl) {
                welcomeTemplate = welcomeEl.outerHTML;
            }

            // Load available skills
            loadSkills();
            // Handle Electron IPC if available
            if (window.electronAPI) {
                window.electronAPI.onNewChat(() => newConversation());
                window.electronAPI.onClearChat(() => newConversation());
                window.electronAPI.onOpenSettings(() => openSettings());
            }

            loadSettings();

            // Initialize context indicator (will be updated when conversation loads)
            updateContextIndicator(null);

            // Start Memory sync status updates
            startMemorySyncStatusUpdates();

            // Ensure default working folder is in workspace list
            ensureDefaultFolderInWorkspace();

            renderWorkingFolders();

            // Load conversations from backend JSONL storage
            console.log('[JSONL] Loading conversations from backend...');
            const loadStart = performance.now();
            try {
                const sessions = await SessionAPI.list();
                const loadEnd = performance.now();
                console.log(`[JSONL] Loaded ${sessions.length} sessions in ${(loadEnd - loadStart).toFixed(2)}ms`);

                // Convert backend sessions to conversation format
                // Backend returns: session_id, file, size, modified, metadata
                conversations = sessions.map(s => {
                    const createdAt = s.metadata?.createdAt || s.createdAt || (s.modified ? new Date(s.modified).getTime() : Date.now());
                    const updatedAt = s.modified ? new Date(s.modified).getTime() : createdAt;
                    return {
                        id: s.session_id || s.id,
                        title: s.metadata?.title || s.title || 'Untitled',
                        createdAt: createdAt,
                        updatedAt: updatedAt,  // CRITICAL: Required for cleanupOldConversations()
                        status: 'idle',
                        workingDir: s.metadata?.workingDir || s.workingDir || '',
                        isCustomTitle: s.metadata?.isCustomTitle || false,
                        messages: [] // Messages loaded on demand
                    };
                });

                // Sort by createdAt descending
                conversations.sort((a, b) => b.createdAt - a.createdAt);
                console.log(`[JSONL] Converted ${conversations.length} conversations`);
            } catch (e) {
                console.error('[JSONL] Failed to load from backend:', e);
            }

            renderConversations();
            // Initialize workdir selector and display
            updateWorkdirSelector();
            updateWorkingDirDisplay();
            // Add event listener for workdir selector
            const workdirSelect = document.getElementById('status-workdir-select');
            if (workdirSelect) {
                workdirSelect.addEventListener('change', function(e) {
                    const value = e.target.value;
                    console.log('Workdir selector changed to:', value);
                    if (value === '__add__') {
                        addWorkingFolder().then(() => {
                            updateWorkdirSelector();
                        });
                    } else if (value) {
                        // Change working directory and open file browser
                        selectWorkingDir(value);
                        openFileBrowser(value);
                    }
                });
            }
            // Sync working directory with server if one was saved
            if (currentWorkingDir) {
                updateServerWorkingDir(currentWorkingDir);
            }
            // Start connection check - run immediately and more frequently until connected
            checkConnection();
            // Fast retry interval for startup (every 3 seconds until connected)
            const startupCheckInterval = setInterval(() => {
                if (lastConnectionHealthy) {
                    clearInterval(startupCheckInterval);
                } else {
                    checkConnection();
                }
            }, 3000);
            // Regular interval for ongoing monitoring (every 30 seconds)
            setInterval(checkConnection, 30000);

            // Warmup interval - keeps backend ready to prevent cold starts (every 60 seconds)
            setInterval(async () => {
                try {
                    const res = await fetch(`${BASE_URL}/v1/warmup`, { method: 'POST' });
                    if (res.ok) {
                        const data = await res.json();
                        console.log('[Warmup]', data);
                    }
                } catch (e) {
                    // Warmup failed silently - not critical
                }
            }, 60000);

            // Auto-resize textarea
            const input = document.getElementById('message-input');
            input.addEventListener('input', (e) => {
                input.style.height = 'auto';
                input.style.height = Math.min(input.scrollHeight, 200) + 'px';
                document.getElementById('send-btn').disabled = !input.value.trim() && attachments.length === 0;

                // Detect slash command for skill picker
                const value = input.value;
                if (value.startsWith('/') && !value.includes(' ')) {
                    const query = value.substring(1).toLowerCase();
                    showSkillPickerUI(query);
                    hideSessionPicker();
                } else {
                    hideSkillPicker();
                }

                // Detect session reference with # (e.g., #36, 查看#12)
                const hashMatch = value.match(/#(\d*)$/);
                if (hashMatch) {
                    const query = hashMatch[1];  // The number after #
                    showSessionPickerUI(query);
                } else {
                    hideSessionPicker();
                }
            });

            // Update send button state on focus (catches programmatic value changes)
            input.addEventListener('focus', () => {
                updateSendButtonState();
            });

            // Also update on click anywhere in the input area
            input.addEventListener('click', () => {
                updateSendButtonState();
            });

            input.addEventListener('keydown', (e) => {
                // Check isComposing to prevent sending during IME composition (Chinese/Japanese input)
                if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
                    e.preventDefault();
                    // If session picker is visible, select the first/highlighted item instead of sending
                    if (sessionPickerVisible) {
                        const firstItem = document.querySelector('.session-picker-item');
                        if (firstItem) {
                            firstItem.click();
                            return;
                        }
                    }
                    // If skill picker is visible, select the first item
                    if (showSkillPicker) {
                        const firstSkill = document.querySelector('.skill-picker-item');
                        if (firstSkill) {
                            firstSkill.click();
                            return;
                        }
                    }
                    sendMessage();
                }
            });

            // Handle paste event for images from clipboard
            input.addEventListener('paste', (e) => {
                const clipboardData = e.clipboardData || window.clipboardData;
                if (!clipboardData) return;

                const items = clipboardData.items;
                if (!items) return;

                for (let i = 0; i < items.length; i++) {
                    const item = items[i];

                    // Check if the item is an image
                    if (item.type.startsWith('image/')) {
                        e.preventDefault(); // Prevent default paste behavior for images

                        const file = item.getAsFile();
                        if (file) {
                            handlePastedImage(file);
                        }
                        return; // Only handle one image at a time
                    }
                }
                // If no image found, let the default text paste happen
            });

            // Drag and drop support for images
            const chatArea = document.getElementById('chat');
            const inputArea = document.querySelector('.input-area');

            // Prevent default drag behaviors on the whole document
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                document.body.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                }, false);
            });

            // Highlight drop zone when dragging over
            ['dragenter', 'dragover'].forEach(eventName => {
                inputArea.addEventListener(eventName, () => {
                    inputArea.classList.add('drag-over');
                }, false);
            });

            ['dragleave', 'drop'].forEach(eventName => {
                inputArea.addEventListener(eventName, () => {
                    inputArea.classList.remove('drag-over');
                }, false);
            });

            // Handle dropped files
            inputArea.addEventListener('drop', (e) => {
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    handleFiles(files);
                }
            }, false);

            // Initialize todo panel dragging
            initTodoPanelDrag();

            // Global Escape key to stop current task
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    // If streaming, stop the task
                    if (isCurrentStreaming()) {
                        e.preventDefault();
                        stopCurrentTask();
                    }
                    // Also hide any open pickers
                    hideSkillPicker();
                    hideSessionPicker();
                }
            });

            // Temperature slider
            document.getElementById('settings-temperature').addEventListener('input', (e) => {
                document.getElementById('temp-value').textContent = e.target.value;
            });
        });

        // ==================== Skill 管理函数 ====================

        // Load available skills from backend
        async function loadSkills() {
            try {
                const res = await fetch(`${BASE_URL}/v1/skills`);
                const data = await res.json();
                availableSkills = data.skills || [];
                console.log('Loaded skills:', availableSkills.map(s => s.name));
            } catch (e) {
                console.error('Failed to load skills:', e);
                availableSkills = [];
            }
        }

        // Built-in commands for the picker (defined here for scope access)
        const pickerBuiltInCommands = [
            { name: 'name', description: 'Rename current session (usage: /name New Title)', isBuiltIn: true },
            { name: 'rename', description: 'Alias for /name', isBuiltIn: true },
            { name: 'clear', description: 'Clear current session messages', isBuiltIn: true },
        ];

        // Show skill picker UI
        function showSkillPickerUI(query) {
            let picker = document.getElementById('skill-picker');
            if (!picker) {
                picker = document.createElement('div');
                picker.id = 'skill-picker';
                picker.className = 'skill-picker';
                document.querySelector('.input-area').appendChild(picker);
            }

            // Filter built-in commands
            const filteredBuiltIn = pickerBuiltInCommands.filter(c =>
                c.name.toLowerCase().includes(query) ||
                c.description.toLowerCase().includes(query)
            );

            // Filter skills based on query
            const filtered = availableSkills.filter(s =>
                s.name.toLowerCase().includes(query) ||
                s.description.toLowerCase().includes(query)
            );

            const allItems = [...filteredBuiltIn, ...filtered];

            if (allItems.length === 0) {
                picker.innerHTML = '<div class="skill-picker-empty">No commands found</div>';
            } else {
                picker.innerHTML = allItems.map(item => {
                    if (item.isBuiltIn) {
                        return `
                            <div class="skill-picker-item built-in" onclick="selectBuiltInCommand('${item.name}')">
                                <div class="skill-picker-name">/${item.name} <span style="font-size:10px;color:var(--text-tertiary);">(local)</span></div>
                                <div class="skill-picker-desc">${item.description}</div>
                            </div>
                        `;
                    } else {
                        return `
                            <div class="skill-picker-item" onclick="selectSkill('${item.name}')">
                                <div class="skill-picker-name">/${item.name}</div>
                                <div class="skill-picker-desc">${item.description.substring(0, 80)}...</div>
                            </div>
                        `;
                    }
                }).join('');
            }

            picker.style.display = 'block';
            showSkillPicker = true;
        }

        // Select a built-in command from the picker
        function selectBuiltInCommand(cmdName) {
            const input = document.getElementById('message-input');
            input.value = `/${cmdName} `;
            hideSkillPicker();
            input.focus();
            // Place cursor at end
            input.setSelectionRange(input.value.length, input.value.length);
        }

        // Hide skill picker
        function hideSkillPicker() {
            const picker = document.getElementById('skill-picker');
            if (picker) {
                picker.style.display = 'none';
            }
            showSkillPicker = false;
        }

        // Select a skill from the picker
        async function selectSkill(skillName) {
            const input = document.getElementById('message-input');
            const skill = availableSkills.find(s => s.name === skillName);

            if (skill) {
                activeSkill = skill;
                // Replace slash command with skill indicator
                input.value = '';
                input.placeholder = `Using /${skillName} skill - Enter your request...`;

                // Show active skill indicator
                showActiveSkillIndicator(skill);
            }

            hideSkillPicker();
            input.focus();
        }

        // Show active skill indicator above input
        function showActiveSkillIndicator(skill) {
            let indicator = document.getElementById('active-skill-indicator');
            if (!indicator) {
                indicator = document.createElement('div');
                indicator.id = 'active-skill-indicator';
                indicator.className = 'active-skill-indicator';
                document.querySelector('.input-area').insertBefore(
                    indicator,
                    document.querySelector('.input-wrapper')
                );
            }

            indicator.innerHTML = `
                <span class="skill-badge">
                    <span class="skill-icon">⚡</span>
                    /${skill.name}
                </span>
                <span class="skill-desc">${skill.description.substring(0, 60)}...</span>
                <button class="skill-clear" onclick="clearActiveSkill()">×</button>
            `;
            indicator.style.display = 'flex';
        }

        // Clear active skill
        function clearActiveSkill() {
            activeSkill = null;
            const input = document.getElementById('message-input');
            input.placeholder = 'Type your message... (/ for skills)';

            const indicator = document.getElementById('active-skill-indicator');
            if (indicator) {
                indicator.style.display = 'none';
            }
        }

        // ==================== Session Reference (#N) Functions ====================

        let sessionPickerVisible = false;

        // Show session picker UI when user types #
        function showSessionPickerUI(query) {
            let picker = document.getElementById('session-picker');
            if (!picker) {
                picker = document.createElement('div');
                picker.id = 'session-picker';
                picker.className = 'session-picker';
                document.querySelector('.input-area').appendChild(picker);
            }

            const totalCount = conversations.length;

            // Filter sessions based on query (session number)
            let filtered = conversations.map((conv, index) => ({
                ...conv,
                sessionNumber: totalCount - index
            }));

            if (query) {
                // Filter by session number starting with the query
                filtered = filtered.filter(c =>
                    c.sessionNumber.toString().startsWith(query)
                );
            }

            // Limit to 8 results
            filtered = filtered.slice(0, 8);

            if (filtered.length === 0) {
                picker.innerHTML = '<div class="session-picker-empty">No matching sessions</div>';
            } else {
                picker.innerHTML = filtered.map(conv => {
                    let title = conv.title || 'Untitled Chat';
                    if (title.length > 35) title = title.substring(0, 35) + '...';
                    const isCurrent = conv.id === currentConversationId;
                    return `
                        <div class="session-picker-item ${isCurrent ? 'current' : ''}"
                             onclick="selectSessionReference('${conv.id}', ${conv.sessionNumber})">
                            <span class="session-picker-number">#${conv.sessionNumber}</span>
                            <span class="session-picker-title">${title}</span>
                            ${isCurrent ? '<span class="session-picker-badge">current</span>' : ''}
                        </div>
                    `;
                }).join('');
            }

            picker.style.display = 'block';
            sessionPickerVisible = true;
        }

        // Hide session picker
        function hideSessionPicker() {
            const picker = document.getElementById('session-picker');
            if (picker) {
                picker.style.display = 'none';
            }
            sessionPickerVisible = false;
        }

        // Select a session reference
        function selectSessionReference(convId, sessionNumber) {
            const input = document.getElementById('message-input');
            const value = input.value;

            // Replace the #number pattern with the complete reference
            const newValue = value.replace(/#\d*$/, `#${sessionNumber} `);
            input.value = newValue;

            hideSessionPicker();
            input.focus();
        }

        // Resolve session references in message (returns context to include)
        function resolveSessionReferences(message) {
            const references = [];
            const pattern = /#(\d+)/g;
            let match;

            const totalCount = conversations.length;

            while ((match = pattern.exec(message)) !== null) {
                const sessionNumber = parseInt(match[1]);
                const index = totalCount - sessionNumber;

                if (index >= 0 && index < conversations.length) {
                    const conv = conversations[index];
                    // Get working directory from conversation runtime or saved state
                    const runtime = convRuntime[conv.id];
                    const workingDir = runtime?.workingDir || conv.workingDir || null;

                    references.push({
                        sessionNumber,
                        convId: conv.id,
                        title: conv.title,
                        messages: conv.messages || [],
                        workingDir: workingDir
                    });
                }
            }

            return references;
        }

        // Format referenced session content for inclusion in the message
        function formatSessionContext(references) {
            if (references.length === 0) return '';

            let context = '\n\n---\n**Referenced Sessions:**\n';

            for (const ref of references) {
                context += `\n### Session #${ref.sessionNumber}: ${ref.title}\n`;

                // Include working directory if available
                if (ref.workingDir) {
                    context += `**Working Directory:** \`${ref.workingDir}\`\n\n`;
                    context += `> Note: If the user asks to execute commands in this session's context, use the working directory above.\n\n`;
                }

                // Include last few messages from the referenced session
                const messages = ref.messages.slice(-6);  // Last 6 messages
                for (const msg of messages) {
                    const role = msg.role === 'user' ? 'User' : 'Assistant';
                    let content = msg.content;
                    if (typeof content === 'object') {
                        content = JSON.stringify(content);
                    }
                    // Truncate long messages
                    if (content && content.length > 500) {
                        content = content.substring(0, 500) + '...';
                    }
                    context += `**${role}:** ${content}\n\n`;
                }
            }

            context += '---\n';
            return context;
        }

        // Get skill instructions to prepend to message
        async function getSkillInstructions(skillName) {
            try {
                const res = await fetch(`${BASE_URL}/v1/skills/${skillName}/instructions`);
                const data = await res.json();
                return data.instructions || '';
            } catch (e) {
                console.error('Failed to get skill instructions:', e);
                return '';
            }
        }

        // Keyword to skill mapping for auto-detection
        const SKILL_KEYWORDS = {
            'pptx': ['ppt', 'pptx', '幻灯片', '演示文稿', 'powerpoint', 'presentation', 'slides'],
            'docx': ['docx', 'word', '文档', 'document', '报告'],
            'xlsx': ['xlsx', 'excel', '表格', 'spreadsheet', '电子表格', '数据分析'],
            'pdf': ['pdf', '填表', 'form', '表单填写'],
        };

        // Auto-detect skill from message content
        function detectSkillFromMessage(message) {
            const lowerMsg = message.toLowerCase();
            for (const [skillName, keywords] of Object.entries(SKILL_KEYWORDS)) {
                for (const keyword of keywords) {
                    if (lowerMsg.includes(keyword)) {
                        // Check if skill is available
                        const skill = availableSkills.find(s => s.name === skillName);
                        if (skill) {
                            console.log(`Auto-detected skill: ${skillName} (keyword: ${keyword})`);
                            return skill;
                        }
                    }
                }
            }
            return null;
        }

        // ==================== Connection check ====================
        // Update status bar display
        function updateStatus(state, message = '') {
            const status = document.getElementById('status');
            switch (state) {
                case 'ready':
                    status.textContent = '● Ready';
                    status.className = 'status-connected';
                    break;
                case 'running':
                    status.textContent = '◐ Running...';
                    status.className = 'status-running';
                    break;
                case 'tool':
                    status.textContent = '◐ Executing tools...';
                    status.className = 'status-running';
                    break;
                case 'completed':
                    status.textContent = '✓ Completed';
                    status.className = 'status-completed';
                    // Reset to Ready after 2 seconds
                    setTimeout(() => updateStatus('ready'), 2000);
                    break;
                case 'error':
                    status.textContent = '✕ Error' + (message ? ': ' + message : '');
                    status.className = 'status-error';
                    break;
                case 'stopped':
                    status.textContent = '■ Stopped';
                    status.className = 'status-stopped';
                    // Reset to Ready after 2 seconds
                    setTimeout(() => updateStatus('ready'), 2000);
                    break;
                case 'disconnected':
                    status.textContent = '○ Disconnected';
                    status.className = 'status-error';
                    break;
                default:
                    status.textContent = message || state;
            }
        }

        // ==================== Context Management (Claude Code Style) ====================

        // Session ID for persistence (generated from conversation ID + working dir)
        function getSessionId(convId) {
            const projectHash = currentWorkingDir ?
                currentWorkingDir.split('').reduce((a, b) => ((a << 5) - a) + b.charCodeAt(0), 0).toString(16).slice(-8) :
                'default';
            return `${projectHash}-${convId}`;
        }

        // Update context indicator UI with status levels (Claude Code style)
        function updateContextIndicator(stats, convId = null) {
            const indicator = document.getElementById('context-indicator');
            const textEl = document.getElementById('context-text');
            const iconEl = indicator.querySelector('.context-icon');

            // Only show for current conversation
            if (convId && convId !== currentConversationId) {
                return;
            }

            // Always show indicator (clickable for breakdown)
            indicator.style.display = 'flex';

            if (!stats || !stats.total_tokens) {
                // Show default state when no stats available
                textEl.textContent = 'Context: 0%';
                indicator.className = 'context-indicator';
                indicator.title = 'Click for context breakdown';
                return;
            }

            const percent = stats.usage_percent || 0;
            const status = stats.status || 'normal';

            // Update indicator class and text based on status
            indicator.className = 'context-indicator';

            switch (status) {
                case 'critical':
                    indicator.classList.add('critical');
                    textEl.textContent = `Context: ${Math.round(percent)}% - Compacting`;
                    break;
                case 'warning':
                    indicator.classList.add('warning');
                    textEl.textContent = `Context: ${Math.round(percent)}%`;
                    break;
                default:
                    textEl.textContent = `Context: ${Math.round(percent)}%`;
            }

            // Show token count on hover (tooltip)
            indicator.title = `Tokens: ${stats.total_tokens.toLocaleString()} / ${stats.max_tokens.toLocaleString()}`;
        }

        // Set context indicator to compacting state
        function setContextCompacting(isCompacting) {
            const indicator = document.getElementById('context-indicator');
            const textEl = document.getElementById('context-text');

            if (isCompacting) {
                indicator.style.display = 'flex';
                indicator.className = 'context-indicator';
                textEl.textContent = 'Context: Compacting...';
            }
        }

        // Hide context indicator
        function hideContextIndicator() {
            const indicator = document.getElementById('context-indicator');
            indicator.style.display = 'none';
        }

        // Refresh context stats for current conversation
        async function refreshContextStats() {
            if (!currentConversationId) {
                updateContextIndicator(null);
                return;
            }

            const runtime = convRuntime[currentConversationId];
            if (!runtime || !runtime.messages || runtime.messages.length === 0) {
                updateContextIndicator(null);
                return;
            }

            try {
                const safeMessages = runtime.messages.map(msg => {
                    try {
                        JSON.stringify(msg);
                        return msg;
                    } catch (e) {
                        return { role: msg.role || 'user', content: '[Non-serializable]' };
                    }
                });

                const response = await fetch(`${BASE_URL}/v1/context/breakdown`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        messages: safeMessages,
                        system: '',
                        tools: window.cachedTools || [],
                        skills: window.loadedSkills || [],
                        memory_files: []
                    })
                });

                if (response.ok) {
                    const data = await response.json();
                    updateContextIndicator({
                        total_tokens: data.total_tokens,
                        max_tokens: data.max_tokens,
                        usage_percent: data.usage_percent,
                        status: data.usage_percent >= 80 ? 'critical' :
                                data.usage_percent >= 60 ? 'warning' : 'normal'
                    }, currentConversationId);
                }
            } catch (e) {
                console.error('Failed to refresh context stats:', e);
            }
        }

        // Toggle context breakdown popup (like Claude Code /context)
        function toggleContextBreakdown(event) {
            if (event) event.stopPropagation();
            const popup = document.getElementById('context-breakdown-popup');
            if (popup.classList.contains('visible')) {
                popup.classList.remove('visible');
            } else {
                fetchAndDisplayContextBreakdown();
                popup.classList.add('visible');
            }
        }

        // Fetch and display context breakdown
        async function fetchAndDisplayContextBreakdown() {
            const content = document.getElementById('breakdown-content');

            // Check if we have conversation data
            if (!currentConversationId) {
                content.innerHTML = '<div class="breakdown-empty">No active conversation</div>';
                return;
            }

            const runtime = convRuntime[currentConversationId];
            if (!runtime || !runtime.messages || runtime.messages.length === 0) {
                content.innerHTML = '<div class="breakdown-empty">Start a conversation to see context usage</div>';
                return;
            }

            try {
                content.innerHTML = '<div class="breakdown-loading">Loading...</div>';

                // Get current tools from cache if available
                const tools = window.cachedTools || [];

                // Get loaded skills (stored in skillsData if available)
                const skills = window.loadedSkills || [];

                // Memory files would be CLAUDE.md content, but we don't have direct access
                // The backend can estimate from system prompt structure
                const memory_files = [];

                // Safely serialize messages (handle any non-serializable content)
                const safeMessages = runtime.messages.map(msg => {
                    try {
                        JSON.stringify(msg);
                        return msg;
                    } catch (e) {
                        return { role: msg.role || 'user', content: '[Non-serializable content]' };
                    }
                });

                console.log('[Context] Sending breakdown request:', {
                    messagesCount: safeMessages.length,
                    toolsCount: tools.length
                });

                const response = await fetch(`${BASE_URL}/v1/context/breakdown`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        messages: safeMessages,
                        system: '', // System prompt is handled by backend
                        tools: tools,
                        skills: skills,
                        memory_files: memory_files
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.error || `HTTP ${response.status}`);
                }

                const data = await response.json();
                console.log('[Context] Breakdown data:', data);
                renderContextBreakdown(data);
            } catch (e) {
                console.error('Context breakdown error:', e);
                // Check if it's a network error
                if (e.name === 'TypeError' && e.message.includes('fetch')) {
                    content.innerHTML = `<div class="breakdown-error">Cannot connect to server</div>`;
                } else {
                    content.innerHTML = `<div class="breakdown-error">Error: ${e.message}</div>`;
                }
            }
        }

        // Render context breakdown in popup (Claude Code style)
        function renderContextBreakdown(data) {
            const content = document.getElementById('breakdown-content');
            const breakdown = data.breakdown;

            // Categories ordered like Claude Code's /context
            const categories = [
                { key: 'system_prompt', label: 'System Prompt', cssClass: 'system' },
                { key: 'system_tools', label: 'System Tools', cssClass: 'tools' },
                { key: 'skills', label: 'Skills', cssClass: 'skills' },
                { key: 'memory_files', label: 'Memory Files', cssClass: 'memory' },
                { key: 'user_text', label: 'User', cssClass: 'user' },
                { key: 'assistant_text', label: 'Assistant', cssClass: 'assistant' },
                { key: 'tool_use', label: 'Tool Use', cssClass: 'tool-use' },
                { key: 'tool_result', label: 'Tool Result', cssClass: 'tool-result' },
                { key: 'images', label: 'Images', cssClass: 'images' }
            ];

            let html = '';
            for (const cat of categories) {
                const catData = breakdown[cat.key];
                if (!catData) continue;
                if (catData.count > 0 || catData.tokens > 0) {
                    const tokensStr = catData.tokens >= 1000
                        ? `${(catData.tokens / 1000).toFixed(1)}k`
                        : catData.tokens;
                    html += `
                        <div class="breakdown-row">
                            <span class="breakdown-label">${cat.label}</span>
                            <div class="breakdown-bar-container">
                                <div class="breakdown-bar ${cat.cssClass}" style="width: ${Math.min(catData.percent, 100)}%"></div>
                            </div>
                            <span class="breakdown-percent">${catData.percent.toFixed(1)}% (${tokensStr})</span>
                        </div>
                    `;
                }
            }

            // Calculate free space
            const usedPercent = data.usage_percent;
            const freePercent = Math.max(0, 100 - usedPercent);
            const freeTokens = data.max_tokens - data.total_tokens;
            const freeStr = freeTokens >= 1000 ? `${(freeTokens / 1000).toFixed(1)}k` : freeTokens;

            html += `
                <div class="breakdown-row breakdown-free">
                    <span class="breakdown-label">Free Space</span>
                    <div class="breakdown-bar-container">
                        <div class="breakdown-bar free" style="width: ${freePercent}%"></div>
                    </div>
                    <span class="breakdown-percent">${freePercent.toFixed(1)}% (${freeStr})</span>
                </div>
            `;

            html += `
                <div class="breakdown-total">
                    <span class="breakdown-total-label">Total</span>
                    <span class="breakdown-total-value">${data.total_tokens.toLocaleString()} / ${data.max_tokens.toLocaleString()} (${data.usage_percent}%)</span>
                </div>
            `;

            content.innerHTML = html;
        }

        // Close breakdown popup when clicking outside
        document.addEventListener('click', (e) => {
            const indicator = document.getElementById('context-indicator');
            const popup = document.getElementById('context-breakdown-popup');
            if (!indicator.contains(e.target)) {
                popup.classList.remove('visible');
            }
        });

        // Show brief notification for context events
        function showContextNotification(message, type = 'info') {
            const notification = document.createElement('div');
            notification.className = `context-notification ${type}`;
            notification.textContent = message;
            notification.style.cssText = `
                position: fixed;
                bottom: 80px;
                right: 20px;
                background: ${type === 'success' ? 'var(--success)' : 'var(--accent)'};
                color: white;
                padding: 10px 16px;
                border-radius: 8px;
                font-size: 13px;
                z-index: 1000;
                animation: fadeIn 0.3s ease;
            `;
            document.body.appendChild(notification);

            setTimeout(() => {
                notification.style.animation = 'fadeOut 0.3s ease';
                setTimeout(() => notification.remove(), 300);
            }, 3000);
        }

        // Check and auto-summarize context if needed (Claude Code style - automatic)
        async function checkAndSummarizeContext(messages, convId) {
            try {
                const sessionId = getSessionId(convId);

                // Use the new auto-check endpoint (combines stats check + summarization)
                const response = await fetch(`${BASE_URL}/v1/context/auto-check`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        messages,
                        session_id: sessionId
                    })
                });
                const result = await response.json();

                // Handle different actions
                switch (result.action) {
                    case 'none':
                        // No summarization needed, just update stats
                        updateContextIndicator(result.stats, convId);
                        return { summarized: false, messages };

                    case 'summarized':
                        // Auto-summarization was performed
                        console.log(`[${convId}] Auto-compaction complete: ${result.old_stats.total_tokens} -> ${result.new_stats.total_tokens} tokens`);
                        updateContextIndicator(result.new_stats, convId);
                        showContextNotification('Context compacted automatically', 'success');

                        // Log structured info for debugging
                        if (result.structured_info) {
                            console.log(`[${convId}] Structured info:`, result.structured_info);
                        }

                        return {
                            summarized: true,
                            messages: result.messages,
                            stats: result.new_stats,
                            summary: result.summary
                        };

                    case 'failed':
                        console.error(`[${convId}] Auto-compaction failed:`, result.reason);
                        return { summarized: false, messages };

                    default:
                        return { summarized: false, messages };
                }

            } catch (error) {
                console.error(`[${convId}] Context check error:`, error);
                hideContextIndicator();
                return { summarized: false, messages };
            }
        }

        // Save conversation to session (JSONL persistence)
        async function saveToSession(convId, messages) {
            try {
                const sessionId = getSessionId(convId);
                await fetch(`${BASE_URL}/v1/sessions/${sessionId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ messages })
                });
            } catch (error) {
                console.error('Failed to save session:', error);
            }
        }

        // Load conversation from session
        async function loadFromSession(convId) {
            try {
                const sessionId = getSessionId(convId);
                const response = await fetch(`${BASE_URL}/v1/sessions/${sessionId}`);
                const data = await response.json();
                return data.messages || [];
            } catch (error) {
                console.error('Failed to load session:', error);
                return [];
            }
        }

        // List all sessions for current project
        async function listProjectSessions() {
            try {
                const url = currentWorkingDir ?
                    `${BASE_URL}/v1/sessions?working_dir=${encodeURIComponent(currentWorkingDir)}` :
                    `${BASE_URL}/v1/sessions`;
                const response = await fetch(url);
                const data = await response.json();
                return data.sessions || [];
            } catch (error) {
                console.error('Failed to list sessions:', error);
                return [];
            }
        }

        // ==================== Connection Check ====================

        let lastConnectionHealthy = false; // Track connection state
        let connectionCheckAttempts = 0; // Track failed attempts for startup

        async function checkConnection() {
            try {
                const res = await fetch(`${BASE_URL}/health`);
                // Check if response is JSON before parsing
                const contentType = res.headers.get('content-type') || '';
                if (!contentType.includes('application/json')) {
                    throw new Error('Server returned non-JSON response');
                }
                const data = await res.json();
                if (data.status === 'healthy') {
                    const wasDisconnected = !lastConnectionHealthy;
                    connectionCheckAttempts = 0; // Reset counter on success

                    // On reconnection, check for and reset stuck conversations
                    if (wasDisconnected) {
                        console.log('Connection recovered, checking for stuck conversations...');
                        // Small delay to let UI stabilize
                        setTimeout(() => resetStuckConversations(), 500);

                        // Trigger immediate warmup to pre-load skills and check MCP servers
                        fetch(`${BASE_URL}/v1/warmup`, { method: 'POST' })
                            .then(res => res.json())
                            .then(data => console.log('[Warmup on connect]', data))
                            .catch(() => {}); // Ignore warmup errors
                    }

                    // Always verify and sync working directory on first connection or reconnection
                    if (wasDisconnected && currentWorkingDir) {
                        console.log('Connection established, syncing working directory:', currentWorkingDir);
                        await updateServerWorkingDir(currentWorkingDir);
                    } else if (currentWorkingDir) {
                        // Periodically verify backend working directory matches frontend
                        try {
                            const wdRes = await fetch(`${BASE_URL}/v1/config/working-dir`);
                            const wdContentType = wdRes.headers.get('content-type') || '';
                            if (wdContentType.includes('application/json')) {
                                const wdData = await wdRes.json();
                                if (wdData.working_dir !== currentWorkingDir) {
                                    console.log('Working directory mismatch detected, syncing:', currentWorkingDir);
                                    await updateServerWorkingDir(currentWorkingDir);
                                }
                            }
                        } catch (e) {
                            console.warn('Failed to verify working directory:', e.message);
                        }
                    }
                    lastConnectionHealthy = true;

                    const currentStreaming = isCurrentStreaming();

                    // Only update to ready if current conversation is not streaming
                    if (!currentStreaming) {
                        const conv = conversations.find(c => c.id === currentConversationId);
                        if (conv && conv.status === 'completed') {
                            // Don't override completed status
                        } else {
                            updateStatus('ready');
                        }
                    }
                    // Update send button based on current conversation
                    updateSendButtonState();
                }
            } catch (e) {
                lastConnectionHealthy = false;
                connectionCheckAttempts++;
                // Show "Starting..." for first 60 seconds (60 attempts at 1/sec, or 2 at 30/sec)
                // Then show "Disconnected" if still failing
                if (connectionCheckAttempts <= 2) {
                    updateStatus('error', 'Server starting...');
                } else {
                    updateStatus('disconnected');
                }
            }
        }

        // Token counting
        async function updateTokenCount() {
            const tokenCountEl = document.getElementById('token-count');
            const messages = getConvRuntime(currentConversationId).messages;

            if (messages.length === 0) {
                if (tokenCountEl) tokenCountEl.textContent = '';
                return;
            }

            try {
                const apiMessages = messages
                    .filter(m => !m.isThinking)
                    .filter(m => m.content);

                const res = await fetch(`${BASE_URL}/v1/context/stats`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ messages: apiMessages })
                });
                const stats = await res.json();

                if (tokenCountEl && stats.total_tokens > 0) {
                    const percent = stats.usage_percent;
                    let color = 'var(--text-secondary)';
                    if (percent > 75) color = 'var(--error)';
                    else if (percent > 50) color = '#f59e0b';

                    tokenCountEl.innerHTML = `<span style="color: ${color}">~${stats.total_tokens.toLocaleString()} tokens (${percent}%)</span>`;

                    if (stats.needs_summarization) {
                        tokenCountEl.innerHTML += ' <span style="color: var(--error)">[需要摘要]</span>';
                    }
                } else if (tokenCountEl) {
                    tokenCountEl.textContent = '';
                }
            } catch (e) {
                console.error('Token count error:', e);
            }
        }

        // Conversations
        // workingDir: optional working directory for the new conversation
        // promptForDir: if true and no workingDir, prompt user to select
        // Lock to prevent race conditions during rapid conversation creation
        let isCreatingConversation = false;

        async function newConversation(workingDir = null, promptForDir = true) {
            // Prevent race condition - if already creating, wait or return
            if (isCreatingConversation) {
                console.log('Conversation creation already in progress, skipping');
                return null;
            }
            isCreatingConversation = true;

            try {
                // If no workingDir and should prompt, check for default folder first
                if (!workingDir && promptForDir) {
                    // Use default folder if set (no longer requires it to be in workingFolders)
                    if (defaultWorkingFolder) {
                        workingDir = defaultWorkingFolder;
                        console.log('Using default folder:', workingDir);
                        // Ensure it's in workspace and set as active
                        ensureDefaultFolderInWorkspace();
                        currentWorkingDir = workingDir;
                        localStorage.setItem('currentWorkingDir', workingDir);
                        renderWorkingFolders();
                    } else if (workingFolders.length > 0) {
                        // Has workspace folders but no default - show selector dialog
                        console.log('No default folder, showing workspace selector');
                        isCreatingConversation = false; // Release lock for selector
                        const result = await showWorkdirSelector();
                        if (result && result.folder) {
                            // User selected a folder from the list or set as default
                            await createConversationWithFolder(result.folder);
                            return currentConversationId;
                        } else {
                            // User cancelled or chose to select new folder (handled by selectNewFolderForChat)
                            return null;
                        }
                    } else {
                        // No workspace folders at all, prompt user to select
                        const folders = await window.electronAPI.selectFolder();
                        if (folders && folders.length > 0) {
                            workingDir = folders[0];
                            // Add selected folder to workspace if not already there
                            if (!workingFolders.includes(workingDir)) {
                                workingFolders.push(workingDir);
                                localStorage.setItem('workingFolders', JSON.stringify(workingFolders));
                                renderWorkingFolders();
                                console.log('Added folder to workspace:', workingDir);
                            }
                        } else {
                            // User cancelled, don't create conversation
                            return null;
                        }
                    }
                }

                // Use unique ID with random suffix to avoid collisions
                const newId = Date.now().toString() + '-' + Math.random().toString(36).substr(2, 9);
                currentConversationId = newId;

                // Initialize runtime state for new conversation with workingDir
                convRuntime[newId] = {
                    isStreaming: false,
                    attachments: [],
                    messages: [],
                    workingDir: workingDir || ''
                };

                // Immediately add to conversations array to prevent race conditions
                const newConv = {
                    id: newId,
                    title: 'New Chat',
                    messages: [],
                    workingDir: workingDir || '',
                    createdAt: Date.now()
                };
                conversations.unshift(newConv);

                // Use stored welcome template (original element may have been replaced)
                document.getElementById('chat-content').innerHTML = welcomeTemplate;
                document.getElementById('header-title').textContent = 'New Chat';
                const tokenCountEl = document.getElementById('token-count');
                if (tokenCountEl) tokenCountEl.textContent = '';
                updateSendButtonState();
                syncStatusBarWithConversation(newId);
                renderConversations();
                hideContextIndicator(); // Reset context indicator for new conversation
                removeInlineChatToolPanel(); // Remove inline tool panel for new conversation

                // Update status bar path display for new conversation
                updateWorkingDirDisplay(workingDir);

                return newId;
            } finally {
                isCreatingConversation = false;
            }
        }

        async function loadConversation(id) {
            const conv = conversations.find(c => c.id === id);
            if (conv) {
                // Store the previous conversation ID before switching
                const previousConvId = currentConversationId;
                const previousRuntime = previousConvId ? convRuntime[previousConvId] : null;

                // If the previous conversation is streaming, handle gracefully
                if (previousRuntime && previousRuntime.isStreaming) {
                    console.log(`Switching away from streaming conversation ${previousConvId}`);
                    // Don't abort the stream - let it continue in background
                    // Just update the UI state for the previous conversation
                    const prevConv = conversations.find(c => c.id === previousConvId);
                    if (prevConv) {
                        prevConv.status = 'running'; // Mark as still running
                    }
                }

                currentConversationId = id;
                // Ensure runtime state exists (load from saved if needed)
                const runtime = getConvRuntime(id);

                // Restore workingDir to runtime from saved conversation
                if (conv.workingDir && !runtime.workingDir) {
                    runtime.workingDir = conv.workingDir;
                }

                // Load messages from backend JSONL storage
                let rawMessages = conv.messages || runtime.messages || [];
                if (rawMessages.length === 0) {
                    console.log(`[JSONL] Loading messages for conversation ${id}...`);
                    const loadStart = performance.now();
                    const backendMessages = await SessionAPI.load(id);
                    const loadEnd = performance.now();
                    console.log(`[JSONL] Loaded ${backendMessages.length} messages in ${(loadEnd - loadStart).toFixed(2)}ms`);
                    rawMessages = backendMessages;
                }

                // Validate and clean up messages (fixes orphaned tool_results from interrupted sessions)
                runtime.messages = validateConversationMessages(rawMessages);

                // Update saved conversation if messages were cleaned up
                if (runtime.messages.length !== rawMessages.length) {
                    conv.messages = runtime.messages;
                    console.log(`Cleaned up ${rawMessages.length - runtime.messages.length} invalid messages from conversation ${id}`);
                }

                // Restore image references - load base64 from stored files
                runtime.messages = await restoreImageReferences(runtime.messages, id);

                document.getElementById('header-title').textContent = conv.title || 'Chat';

                // Reset running status if not actually streaming this conversation
                // (handles case where app was closed during a request)
                if (conv.status === 'running' && !runtime.isStreaming) {
                    conv.status = 'idle';
                }

                // Sync status bar and send button with loaded conversation
                syncStatusBarWithConversation(id);
                updateSendButtonState();

                // Update working directory display for this conversation
                const convWorkingDir = conv.workingDir || runtime.workingDir;
                updateWorkingDirDisplay(convWorkingDir);
                renderWorkingFolders(); // Update active state in workspace sidebar

                // CRITICAL: Sync working directory to backend when switching conversations
                // This ensures file operations use the correct directory for THIS conversation
                if (convWorkingDir) {
                    currentWorkingDir = convWorkingDir;
                    updateServerWorkingDir(convWorkingDir);
                }

                renderMessages();
                renderConversations();
                updateTokenCount();
                renderToolExecutionSidebar(); // Update right sidebar for this conversation
                refreshContextStats(); // Update context indicator for this conversation
                removeInlineChatToolPanel(); // Remove inline tool panel when switching conversations

                // Restore inline tasks for this conversation
                updateInlineTasks(runtime.todos);
            }
        }

        // Update send button based on current conversation's streaming state
        function updateSendButtonState() {
            const btn = document.getElementById('send-btn');
            const stopBtn = document.getElementById('stop-btn');
            const input = document.getElementById('message-input');
            const streaming = isCurrentStreaming();

            if (btn) {
                // Disable if streaming OR if input is empty and no attachments OR if server is not connected
                const hasContent = input && input.value.trim().length > 0;
                const hasAttachments = attachments && attachments.length > 0;
                const serverDisconnected = !lastConnectionHealthy;
                btn.disabled = streaming || serverDisconnected || (!hasContent && !hasAttachments);
                btn.style.display = streaming ? 'none' : 'flex';
                // Show title hint when disabled due to disconnection
                if (serverDisconnected) {
                    btn.title = 'Server is starting up, please wait...';
                } else {
                    btn.title = '';
                }
            }
            if (stopBtn) {
                stopBtn.classList.toggle('visible', streaming);
            }
        }

        // Sync status bar with a specific conversation's status
        function syncStatusBarWithConversation(conversationId) {
            const runtime = getConvRuntime(conversationId);

            // If this conversation is actively streaming, show running
            if (runtime.isStreaming) {
                updateStatus('running');
                return;
            }

            // Otherwise, show the conversation's saved status or ready
            const conv = conversations.find(c => c.id === conversationId);
            if (conv) {
                if (conv.status === 'completed') {
                    updateStatus('completed');
                } else if (conv.status === 'error') {
                    updateStatus('error');
                } else {
                    updateStatus('ready');
                }
            } else {
                updateStatus('ready');
            }
        }

        // Helper to extract text from message content (handles string or array)
        function getTextFromContent(content) {
            if (!content) return '';
            if (typeof content === 'string') return content;
            if (Array.isArray(content)) {
                const textPart = content.find(c => c.type === 'text');
                return textPart?.text || '';
            }
            return '';
        }

        // Prepare messages for saving to JSONL - convert base64 images to references
        // This optimizes storage by keeping only image references in JSONL
        function prepareMessagesForSaving(messages) {
            return messages.map(msg => {
                if (!msg.content || !Array.isArray(msg.content)) {
                    return msg;
                }

                // Deep copy the message
                const newMsg = { ...msg };
                newMsg.content = msg.content.map(block => {
                    // Check if this is an image with imageRef
                    if (block.type === 'image' && block._imageRef) {
                        // Replace base64 with reference
                        return {
                            type: 'image',
                            source: {
                                type: 'file_ref',
                                media_type: block.source?.media_type || 'image/png',
                                image_ref: block._imageRef
                            }
                        };
                    }
                    return block;
                });

                return newMsg;
            });
        }

        // Restore image references when loading - convert file_ref back to base64
        async function restoreImageReferences(messages, sessionId) {
            const restoredMessages = [];

            for (const msg of messages) {
                if (!msg.content || !Array.isArray(msg.content)) {
                    restoredMessages.push(msg);
                    continue;
                }

                // Check if any content block has file_ref
                const hasFileRef = msg.content.some(
                    block => block.type === 'image' && block.source?.type === 'file_ref'
                );

                if (!hasFileRef) {
                    restoredMessages.push(msg);
                    continue;
                }

                // Deep copy and restore image references
                const newMsg = { ...msg };
                newMsg.content = await Promise.all(msg.content.map(async (block) => {
                    if (block.type === 'image' && block.source?.type === 'file_ref') {
                        const imageRef = block.source.image_ref;
                        if (!imageRef) return block;

                        // Fetch base64 from backend
                        const filename = imageRef.relative_path?.split('/').pop();
                        if (!filename) return block;

                        const base64Data = await fetchImageBase64(sessionId, filename);
                        if (!base64Data) {
                            console.warn(`Failed to restore image: ${filename}`);
                            return block; // Keep original if fetch fails
                        }

                        // Restore to base64 format with _imageRef for future saves
                        return {
                            type: 'image',
                            source: {
                                type: 'base64',
                                media_type: block.source.media_type || 'image/png',
                                data: base64Data
                            },
                            _imageRef: imageRef
                        };
                    }
                    return block;
                }));

                restoredMessages.push(newMsg);
            }

            return restoredMessages;
        }

        // Save conversation - can specify ID to save a specific conversation (for background saves)
        // Sessions are saved to backend JSONL only (localStorage not used for sessions)
        function saveConversation(convId = null) {
            const targetId = convId || currentConversationId;
            if (!targetId) return;

            const runtime = getConvRuntime(targetId);
            const msgs = runtime.messages;
            const idx = conversations.findIndex(c => c.id === targetId);

            // Check if this conversation has a user-customized title
            const existingConv = idx >= 0 ? conversations[idx] : null;
            const hasCustomTitle = existingConv?.isCustomTitle || false;

            let title;
            if (hasCustomTitle && existingConv?.title) {
                // Preserve user-customized title
                title = existingConv.title;
            } else {
                // Auto-generate title from last user message
                let lastUserContent = '';
                for (let i = msgs.length - 1; i >= 0; i--) {
                    if (msgs[i]?.role === 'user') {
                        lastUserContent = getTextFromContent(msgs[i].content);
                        if (lastUserContent) break;
                    }
                }
                // Fallback to first message if no user message found
                const titleContent = lastUserContent || getTextFromContent(msgs[0]?.content);
                title = titleContent.substring(0, 30) || 'New Chat';
                if (title.length >= 30) title += '...';
            }

            // Preserve existing status if any
            const existingStatus = existingConv?.status || 'idle';

            // Preserve workingDir from existing conversation or runtime
            const existingWorkingDir = existingConv?.workingDir || runtime.workingDir;

            const conv = {
                id: targetId,
                title: title,
                messages: msgs,
                status: existingStatus,
                workingDir: existingWorkingDir || '',
                isCustomTitle: hasCustomTitle,  // Preserve the custom title flag
                updatedAt: Date.now()
            };

            if (idx >= 0) {
                conversations[idx] = conv;
            } else {
                conversations.unshift(conv);
            }

            renderConversations();

            // Prepare messages for saving - convert image base64 to references
            const msgsForSaving = prepareMessagesForSaving(msgs);

            // Save to backend JSONL (persistent, full message history)
            SessionAPI.save(targetId, msgsForSaving, {
                title: title,
                workingDir: existingWorkingDir || '',
                updatedAt: Date.now()
            }).then(success => {
                if (success) {
                    console.log(`[${targetId}] Session saved to backend JSONL`);
                }
            });

            // Only update token count if this is the current conversation
            if (targetId === currentConversationId) {
                updateTokenCount();
            }

            // Auto cleanup old conversations (30 days retention)
            cleanupOldConversations();
        }

        // Cleanup conversations older than 30 days
        const RETENTION_DAYS = 30;
        function cleanupOldConversations() {
            const now = Date.now();
            const maxAge = RETENTION_DAYS * 24 * 60 * 60 * 1000; // 30 days in ms

            const oldConversations = conversations.filter(c => {
                const age = now - (c.updatedAt || 0);
                return age > maxAge;
            });

            if (oldConversations.length === 0) return;

            console.log(`[Cleanup] Found ${oldConversations.length} conversations older than ${RETENTION_DAYS} days`);

            // Remove old conversations
            const oldIds = new Set(oldConversations.map(c => c.id));
            conversations = conversations.filter(c => !oldIds.has(c.id));

            // Delete from backend JSONL
            oldConversations.forEach(c => {
                SessionAPI.delete(c.id).then(success => {
                    if (success) {
                        console.log(`[Cleanup] Deleted old session: ${c.id} (${c.title})`);
                    }
                });
                // Clean up runtime if exists
                if (convRuntime[c.id]) {
                    delete convRuntime[c.id];
                }
            });

            console.log(`[Cleanup] Removed ${oldConversations.length} old conversations`);
            renderConversations();
        }

        function deleteConversation(id, e) {
            e.stopPropagation();

            // Remove from conversations list
            conversations = conversations.filter(c => c.id !== id);

            // Delete from backend JSONL
            SessionAPI.delete(id).then(success => {
                if (success) {
                    console.log(`[${id}] Session deleted from backend`);
                }
            });

            // Clean up runtime state (messages, streaming state, etc.)
            if (convRuntime[id]) {
                delete convRuntime[id];
                console.log(`[${id}] Cleaned up runtime state`);
            }

            // If deleting current conversation, create a new one
            if (currentConversationId === id) {
                newConversation();
            }

            renderConversations();
        }

        function renderConversations() {
            const list = document.getElementById('conversations-list');
            const totalCount = conversations.length;
            list.innerHTML = conversations.map((c, index) => {
                const status = c.status || 'idle';
                const sessionNumber = totalCount - index;  // Newest first, so reverse numbering
                // Escape title for HTML - prevent XSS
                const safeTitle = escapeHtml(c.title || '');
                const escapedTitleAttr = (c.title || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
                // Get delegation badges HTML
                const delegationBadges = getDelegationBadgesHtml(c.id);
                return `
                <div class="conversation-item ${c.id === currentConversationId ? 'active' : ''}"
                     onclick="loadConversation('${c.id}')"
                     data-id="${c.id}"
                     ondragover="handleConvDragOver(event)"
                     ondragleave="handleConvDragLeave(event)"
                     ondrop="handleConvDrop(event, '${c.id}')">
                    <div class="conversation-status ${status}" title="${getStatusTitle(status)}"></div>
                    <span class="session-number">#${sessionNumber}</span>
                    <span class="title" ondblclick="startRenameConversation('${c.id}', event)" title="Double-click to rename">${safeTitle}</span>
                    ${delegationBadges}
                    <button class="delete-btn" onclick="deleteConversation('${c.id}', event)">
                        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M3 3l8 8M11 3l-8 8"/>
                        </svg>
                    </button>
                </div>
            `}).join('');
        }

        // Generate delegation badges HTML for a conversation
        function getDelegationBadgesHtml(convId) {
            const runtime = convRuntime[convId];
            if (!runtime) return '';

            const badges = [];

            // Check for outgoing (delegated) tasks
            const delegatedTasks = Object.values(runtime.delegatedTasks || {});
            const activeDelegations = delegatedTasks.filter(t => t.status === 'pending' || t.status === 'executing');
            if (activeDelegations.length > 0) {
                const executing = activeDelegations.some(t => t.status === 'executing');
                badges.push(`<span class="delegation-badge outgoing ${executing ? 'executing' : ''}" title="Delegated ${activeDelegations.length} task(s)">\u2192${activeDelegations.length}</span>`);
            }

            // Check for incoming tasks
            const incomingTasks = Object.values(runtime.incomingTasks || {});
            const activeIncoming = incomingTasks.filter(t => t.status === 'pending' || t.status === 'executing');
            if (activeIncoming.length > 0) {
                const executing = activeIncoming.some(t => t.status === 'executing');
                badges.push(`<span class="delegation-badge incoming ${executing ? 'executing' : ''}" title="Executing ${activeIncoming.length} delegated task(s)">\u2190${activeIncoming.length}</span>`);
            }

            if (badges.length === 0) return '';
            return `<div class="delegation-badges">${badges.join('')}</div>`;
        }

        function getStatusTitle(status) {
            const titles = {
                'idle': 'Ready',
                'running': 'Running...',
                'completed': 'Completed',
                'error': 'Error'
            };
            return titles[status] || 'Ready';
        }

        // ==================== Session Rename Functions ====================

        // Start renaming a conversation (double-click handler)
        function startRenameConversation(convId, event) {
            event.stopPropagation();
            event.preventDefault();

            const conv = conversations.find(c => c.id === convId);
            if (!conv) return;

            const item = document.querySelector(`.conversation-item[data-id="${convId}"]`);
            if (!item) return;

            const titleSpan = item.querySelector('.title');
            if (!titleSpan) return;

            // Create input element
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'rename-input';
            input.value = conv.title || '';
            input.setAttribute('data-conv-id', convId);

            // Replace title span with input
            titleSpan.style.display = 'none';
            titleSpan.parentNode.insertBefore(input, titleSpan.nextSibling);

            // Focus and select all text
            input.focus();
            input.select();

            // Handle input events
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    finishRenameConversation(convId, input.value.trim());
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    cancelRenameConversation(convId);
                }
            });

            input.addEventListener('blur', () => {
                // Small delay to allow click events to process
                setTimeout(() => {
                    if (document.querySelector(`.rename-input[data-conv-id="${convId}"]`)) {
                        finishRenameConversation(convId, input.value.trim());
                    }
                }, 100);
            });

            // Prevent click from propagating to parent (would load conversation)
            input.addEventListener('click', (e) => e.stopPropagation());
        }

        // Finish renaming and save
        function finishRenameConversation(convId, newName) {
            // Limit title length to prevent UI overflow (max 200 characters)
            const MAX_TITLE_LENGTH = 200;
            if (newName && newName.length > MAX_TITLE_LENGTH) {
                newName = newName.slice(0, MAX_TITLE_LENGTH) + '...';
                console.log(`Title truncated to ${MAX_TITLE_LENGTH} characters`);
            }

            let conv = conversations.find(c => c.id === convId);

            // If conversation doesn't exist in array yet (new unsaved conversation), create it
            if (!conv) {
                const runtime = convRuntime[convId];
                if (!runtime) return;  // No runtime means invalid convId

                conv = {
                    id: convId,
                    title: newName || 'New Chat',
                    messages: runtime.messages || [],
                    workingDir: runtime.workingDir || '',
                    isCustomTitle: true,
                    createdAt: Date.now()
                };
                conversations.unshift(conv);
            } else {
                // Use old name if empty
                if (!newName) {
                    newName = conv.title;
                }
                conv.title = newName;
                conv.isCustomTitle = true;  // Mark that user manually named this session
            }

            // Save renamed title to backend
            const runtime = convRuntime[convId];
            SessionAPI.save(convId, runtime?.messages || conv.messages || [], {
                title: conv.title,
                workingDir: conv.workingDir || '',
                isCustomTitle: conv.isCustomTitle,
                updatedAt: Date.now()
            });

            // Update header if this is current conversation
            if (convId === currentConversationId) {
                document.getElementById('header-title').textContent = newName || conv.title;
            }

            // Re-render to remove input and show updated title
            renderConversations();
        }

        // Cancel renaming
        function cancelRenameConversation(convId) {
            renderConversations();
        }

        // Rename current conversation (for /name command)
        function renameCurrentConversation(newName) {
            if (!currentConversationId) {
                updateStatus('error', 'No active conversation to rename');
                return;
            }

            if (!newName || !newName.trim()) {
                // Prompt for name if not provided
                promptRenameCurrentConversation();
                return;
            }

            finishRenameConversation(currentConversationId, newName.trim());
            updateStatus('completed', `Renamed to "${newName.trim()}"`);
        }

        // Show rename prompt for current conversation
        function promptRenameCurrentConversation() {
            if (!currentConversationId) {
                updateStatus('error', 'No active conversation to rename');
                return;
            }

            const conv = conversations.find(c => c.id === currentConversationId);
            if (!conv) return;

            // Find the item in the sidebar and trigger rename
            const item = document.querySelector(`.conversation-item[data-id="${currentConversationId}"]`);
            if (item) {
                const titleSpan = item.querySelector('.title');
                if (titleSpan) {
                    // Simulate double-click
                    startRenameConversation(currentConversationId, { stopPropagation: () => {}, preventDefault: () => {} });
                }
            }
        }

        function updateConversationStatus(conversationId, status) {
            const conv = conversations.find(c => c.id === conversationId);
            if (conv) {
                conv.status = status;
                // Update DOM directly for smooth animation
                const item = document.querySelector(`.conversation-item[data-id="${conversationId}"]`);
                if (item) {
                    const statusEl = item.querySelector('.conversation-status');
                    if (statusEl) {
                        statusEl.className = `conversation-status ${status}`;
                        statusEl.title = getStatusTitle(status);
                    }
                }
                // Session saved to backend via SessionAPI

                // Also sync status bar if this is the currently viewed conversation
                if (currentConversationId === conversationId) {
                    if (status === 'running') {
                        updateStatus('running');
                    } else if (status === 'completed') {
                        updateStatus('completed');
                    } else if (status === 'error') {
                        updateStatus('error');
                    } else {
                        updateStatus('ready');
                    }
                }
            }
        }

        // Messages
        function renderMessages() {
            const container = document.getElementById('chat-content');
            const messages = getConvRuntime(currentConversationId).messages;

            if (messages.length === 0) {
                container.innerHTML = document.getElementById('welcome')?.outerHTML || '';
                return;
            }

            // Filter out internal messages for display
            const filteredMessages = messages.filter((m, idx) => {
                // Skip tool_result user messages
                if (m.role === 'user' && Array.isArray(m.content)) {
                    return !m.content.some(c => c.type === 'tool_result');
                }
                // Skip assistant messages that only have tool_use (no text)
                // BUT don't skip the last message (it's the active streaming message)
                if (m.role === 'assistant' && m.hasToolUse && idx < messages.length - 1) {
                    const display = m.displayContent || '';
                    if (!display.trim()) return false; // Hide if no text content
                }
                // Skip thinking indicators
                if (m.isThinking) return false;
                return true;
            });

            // Helper to extract text from content (handles string or array)
            function extractTextContent(content) {
                if (!content) return '';
                if (typeof content === 'string') return content;
                if (Array.isArray(content)) {
                    return content.map(c => {
                        if (typeof c === 'string') return c;
                        if (c.type === 'text') return c.text || '';
                        if (c.type === 'image') return '[Image]';
                        if (c.type === 'tool_use') return ''; // Skip tool_use blocks
                        if (c.type === 'tool_result') return ''; // Skip tool_result blocks
                        return '';
                    }).filter(Boolean).join('\n');
                }
                return '';
            }

            // Merge consecutive assistant messages for display
            // BUT don't merge delegation result messages - they should stay separate
            const displayMessages = [];
            for (const m of filteredMessages) {
                const lastDisplayMsg = displayMessages[displayMessages.length - 1];
                const shouldMerge = m.role === 'assistant' &&
                    lastDisplayMsg && lastDisplayMsg.role === 'assistant' &&
                    !m.isDelegationResult &&  // Don't merge delegation results
                    !lastDisplayMsg.isDelegationResult &&  // Don't merge into delegation results
                    !m.isTaskResult &&  // Don't merge task results
                    !lastDisplayMsg.isTaskResult;  // Don't merge into task results

                if (shouldMerge) {
                    // Merge with previous assistant message - extract text properly
                    const prevContent = lastDisplayMsg.mergedContent || extractTextContent(lastDisplayMsg.displayContent) || extractTextContent(lastDisplayMsg.content) || '';
                    const currContent = extractTextContent(m.displayContent) || extractTextContent(m.content) || '';
                    if (currContent) {
                        lastDisplayMsg.mergedContent = prevContent + '\n\n' + currContent;
                    }
                } else {
                    // Add new message (clone to avoid modifying original)
                    displayMessages.push({ ...m });
                }
            }

            container.innerHTML = displayMessages.map((m, i) => {
                // Use mergedContent if available (for merged assistant messages), otherwise displayContent
                const contentToRender = m.mergedContent || m.displayContent || m.content;

                // Check message types for special styling
                const isDelegationResult = m.isDelegationResult || false;
                const isTaskResult = m.isTaskResult || false;

                let extraClass = '';
                let avatar = 'C';
                let label = 'Springo';

                if (isDelegationResult) {
                    extraClass = ' delegation-result';
                    avatar = '↩';
                    label = 'Delegation Result';
                } else if (isTaskResult) {
                    extraClass = ' task-result';
                    avatar = '📋';
                    label = 'Task Result';
                } else if (m.role === 'user') {
                    avatar = 'U';
                    label = 'You';
                }

                // Format timestamp - show date if not today
                let timeStr = '';
                if (m.timestamp) {
                    const msgDate = new Date(m.timestamp);
                    const today = new Date();
                    const isToday = msgDate.toDateString() === today.toDateString();
                    if (isToday) {
                        timeStr = msgDate.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
                    } else {
                        // Show month-day + time for older messages
                        timeStr = msgDate.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) + ' ' +
                                  msgDate.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
                    }
                }

                return `
                    <div class="message message-${m.role}${extraClass}">
                        <div class="message-header">
                            <div class="message-avatar">${avatar}</div>
                            <span class="message-label">${label}</span>
                            ${timeStr ? `<span class="message-time">${timeStr}</span>` : ''}
                        </div>
                        <div class="message-content">${formatContent(contentToRender)}</div>
                    </div>
                `;
            }).join('');

            // Highlight code blocks
            container.querySelectorAll('pre code').forEach(block => {
                hljs.highlightElement(block);
            });

            // Add copy buttons to code blocks (not tool call pre elements)
            container.querySelectorAll('.message-content > pre, .message-content pre:not(.tool-input pre):not(.tool-output pre)').forEach(pre => {
                if (!pre.closest('.tool-call') && !pre.querySelector('.copy-code-btn')) {
                    const btn = document.createElement('button');
                    btn.className = 'copy-code-btn';
                    btn.textContent = 'Copy';
                    btn.onclick = () => {
                        navigator.clipboard.writeText(pre.textContent);
                        btn.textContent = 'Copied!';
                        setTimeout(() => btn.textContent = 'Copy', 2000);
                    };
                    pre.appendChild(btn);
                }
            });

            scrollToBottom();
        }

        // Make file paths clickable in HTML (applied AFTER markdown parsing)
        // This processes HTML and finds file paths that are NOT already inside anchor tags
        function linkifyFilePaths(html) {
            if (!html || typeof html !== 'string') return html;

            // Use DOM parsing for safe HTML manipulation
            const temp = document.createElement('div');
            temp.innerHTML = html;

            // Walk through all text nodes and linkify paths
            const walker = document.createTreeWalker(temp, NodeFilter.SHOW_TEXT, null, false);
            const nodesToProcess = [];

            while (walker.nextNode()) {
                const node = walker.currentNode;
                // Skip if inside an anchor tag (already a link)
                // But DO process code blocks - file paths in code should still be clickable
                let parent = node.parentNode;
                let skip = false;
                while (parent && parent !== temp) {
                    if (parent.tagName === 'A') {
                        skip = true;
                        break;
                    }
                    parent = parent.parentNode;
                }
                if (!skip && node.textContent) {
                    nodesToProcess.push(node);
                }
            }

            // Patterns for file paths
            const pathPattern = /(\/(?:Users|home|tmp|var|etc|opt|Downloads|Documents|Desktop)[^\s"'`)<>\n]+|~\/[^\s"'`)<>\n]+)/g;

            // Process each text node
            for (const node of nodesToProcess) {
                const text = node.textContent;
                // Reset regex state before testing
                pathPattern.lastIndex = 0;
                if (!pathPattern.test(text)) continue;

                // Reset again for exec loop
                pathPattern.lastIndex = 0;

                // Create a fragment with linkified paths
                const fragment = document.createDocumentFragment();
                let lastIndex = 0;
                let match;

                while ((match = pathPattern.exec(text)) !== null) {
                    // Add text before match
                    if (match.index > lastIndex) {
                        fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
                    }

                    // Clean up path (remove trailing punctuation)
                    let cleanPath = match[0].replace(/[.,;:!?)\]]+$/, '');
                    const trailing = match[0].slice(cleanPath.length);

                    // Create clickable link
                    const link = document.createElement('a');
                    link.href = '#';
                    link.className = 'clickable-path';
                    link.setAttribute('data-path', cleanPath);
                    link.title = 'Click to open';
                    link.textContent = cleanPath;
                    fragment.appendChild(link);

                    // Add trailing punctuation as text
                    if (trailing) {
                        fragment.appendChild(document.createTextNode(trailing));
                    }

                    lastIndex = match.index + match[0].length;
                }

                // Add remaining text
                if (lastIndex < text.length) {
                    fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
                }

                // Replace the text node with the fragment
                node.parentNode.replaceChild(fragment, node);
            }

            return temp.innerHTML;
        }

        // Escape HTML to prevent XSS
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Handle clicks on URLs and paths
        document.addEventListener('click', (e) => {
            const urlLink = e.target.closest('.clickable-url');
            const pathLink = e.target.closest('.clickable-path');

            if (urlLink) {
                e.preventDefault();
                const url = urlLink.getAttribute('data-url');
                if (url && window.electronAPI?.openExternal) {
                    window.electronAPI.openExternal(url);
                } else if (url) {
                    window.open(url, '_blank');
                }
            } else if (pathLink) {
                e.preventDefault();
                const path = pathLink.getAttribute('data-path');
                if (path && window.electronAPI?.openPath) {
                    // Expand ~ to home directory is handled by backend
                    window.electronAPI.openPath(path);
                }
            }
        });

        function formatContent(content) {
            if (!content) return '';

            // Helper to parse markdown and make file paths clickable
            // Order: marked.parse → linkifyFilePaths (on rendered HTML)
            const parseAndLinkify = (text) => {
                if (!text || !text.trim()) return '';
                // 1. Parse markdown (this also handles URLs)
                const parsed = marked.parse(text);
                // 2. Linkify file paths in the rendered HTML
                return linkifyFilePaths(parsed);
            };

            // If content contains chat-tool-container (new tool display), preserve it
            if (typeof content === 'string' && content.includes('<div class="chat-tool-container"')) {
                // Split by tool container using END marker for reliable matching
                const parts = content.split(/(<div class="chat-tool-container">[\s\S]*?<!-- END_TOOL_CONTAINER -->)/g);
                return parts.map(part => {
                    if (part.includes('<div class="chat-tool-container"')) {
                        return part;
                    }
                    return parseAndLinkify(part);
                }).join('');
            }

            // If content is already HTML (contains tool-call divs), return as-is
            if (typeof content === 'string' && content.includes('<div class="tool-call"')) {
                // Parse the text part with markdown, keep tool calls as-is
                const parts = content.split(/(<div class="tool-call"[\s\S]*?<\/div>\s*<\/div>\s*<\/div>)/g);
                return parts.map(part => {
                    if (part.startsWith('<div class="tool-call"')) {
                        return part;
                    }
                    return parseAndLinkify(part);
                }).join('');
            }

            // If it's a thinking indicator, return as-is
            if (typeof content === 'string' && content.includes('thinking-dot')) {
                return content;
            }

            // Handle array content (complex messages with images etc)
            if (Array.isArray(content)) {
                return content.map(c => {
                    if (c.type === 'text') return parseAndLinkify(c.text);
                    if (c.type === 'image') return '[Image]';
                    return '';
                }).join('');
            }

            // Configure marked for standard markdown
            marked.setOptions({
                highlight: (code, lang) => {
                    if (lang && hljs.getLanguage(lang)) {
                        return hljs.highlight(code, { language: lang }).value;
                    }
                    return hljs.highlightAuto(code).value;
                },
                breaks: true
            });
            return parseAndLinkify(content);
        }

        function scrollToBottom() {
            const container = document.getElementById('chat-container');
            container.scrollTop = container.scrollHeight;
        }

        // Generic fetch with retry logic for network errors
        // externalSignal: optional AbortSignal to allow external cancellation
        async function fetchWithRetry(url, options, maxRetries = 3, timeout = 180000, externalSignal = null) {
            let lastError;
            for (let attempt = 0; attempt <= maxRetries; attempt++) {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), timeout);

                // If external signal aborts, also abort this request
                const externalAbortHandler = () => controller.abort();
                if (externalSignal) {
                    if (externalSignal.aborted) {
                        clearTimeout(timeoutId);
                        throw new DOMException('Request aborted by user', 'AbortError');
                    }
                    externalSignal.addEventListener('abort', externalAbortHandler);
                }

                try {
                    const response = await fetch(url, {
                        ...options,
                        signal: controller.signal
                    });
                    clearTimeout(timeoutId);
                    if (externalSignal) {
                        externalSignal.removeEventListener('abort', externalAbortHandler);
                    }
                    return response;
                } catch (e) {
                    clearTimeout(timeoutId);
                    if (externalSignal) {
                        externalSignal.removeEventListener('abort', externalAbortHandler);
                    }
                    lastError = e;

                    // Check if aborted by user (external signal)
                    const isUserAbort = externalSignal && externalSignal.aborted;
                    if (isUserAbort) {
                        throw new DOMException('Request aborted by user', 'AbortError');
                    }

                    // Only retry on network errors, not on abort
                    const isNetworkError = e.message === 'Failed to fetch' || e.name === 'TypeError';
                    const isTimeout = e.name === 'AbortError';

                    if (attempt < maxRetries && (isNetworkError || isTimeout)) {
                        const waitTime = Math.min(1000 * Math.pow(2, attempt), 5000); // Exponential backoff, max 5s
                        console.warn(`[fetchWithRetry] Attempt ${attempt + 1} failed (${e.message}), retrying in ${waitTime}ms...`);
                        await new Promise(r => setTimeout(r, waitTime));
                        continue;
                    }
                    throw e;
                }
            }
            throw lastError;
        }

        // SSE Stream Parser for handling streaming responses
        async function* parseSSEStream(reader) {
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Split on double newlines (SSE event separator)
                const events = buffer.split('\n\n');
                buffer = events.pop() || ''; // Keep incomplete event in buffer

                for (const eventBlock of events) {
                    if (!eventBlock.trim()) continue;

                    const lines = eventBlock.split('\n');
                    let eventType = null;
                    let eventData = null;

                    for (const line of lines) {
                        if (line.startsWith('event: ')) {
                            eventType = line.slice(7).trim();
                        } else if (line.startsWith('data: ')) {
                            eventData = line.slice(6);
                        }
                    }

                    if (eventType && eventData) {
                        try {
                            yield { event: eventType, data: JSON.parse(eventData) };
                        } catch (e) {
                            console.warn('SSE parse error:', e, eventData);
                        }
                    }
                }
            }
        }

        // Process streaming response and update UI progressively
        async function processStreamingResponse(response, convId, onTextUpdate, onComplete) {
            const reader = response.body.getReader();
            let textContent = '';
            let toolUses = [];
            let currentToolUse = null;
            let currentToolInput = '';

            try {
                for await (const { event, data } of parseSSEStream(reader)) {
                    // Check if conversation switched
                    const runtime = getConvRuntime(convId);
                    if (!runtime) break;

                    switch (event) {
                        case 'message_start':
                            // Message started
                            console.log(`[${convId}] Stream: message_start`);
                            break;

                        case 'content_block_start':
                            const block = data.content_block;
                            if (block.type === 'tool_use') {
                                currentToolUse = {
                                    id: block.id,
                                    name: block.name,
                                    input: {}
                                };
                                currentToolInput = '';
                                console.log(`[${convId}] Stream: tool_use started - ${block.name}`);
                            }
                            break;

                        case 'content_block_delta':
                            const delta = data.delta;
                            if (delta.type === 'text_delta') {
                                textContent += delta.text;
                                onTextUpdate(textContent, toolUses, false);
                            } else if (delta.type === 'input_json_delta' && currentToolUse) {
                                currentToolInput += delta.partial_json;
                                console.log(`[${convId}] input_json_delta for ${currentToolUse.name}: +${delta.partial_json.length} chars`);
                            }
                            break;

                        case 'content_block_stop':
                            if (currentToolUse) {
                                try {
                                    currentToolUse.input = JSON.parse(currentToolInput || '{}');
                                    console.log(`[${convId}] Parsed input for ${currentToolUse.name}:`, JSON.stringify(currentToolUse.input).substring(0, 100));
                                } catch (e) {
                                    console.error(`[${convId}] Failed to parse tool input: ${e.message}, raw: ${currentToolInput.substring(0, 100)}`);
                                    currentToolUse.input = {};
                                }
                                toolUses.push(currentToolUse);
                                console.log(`[${convId}] Stream: tool_use complete - ${currentToolUse.name}`);
                                currentToolUse = null;
                                currentToolInput = '';
                                onTextUpdate(textContent, toolUses, false);
                            }
                            break;

                        case 'message_stop':
                            console.log(`[${convId}] Stream: message_stop`);
                            break;

                        // Server-side auto tool execution events
                        case 'tool_execution_start':
                            console.log(`[${convId}] Server executing tools:`, data.tools?.map(t => t.name));
                            // Add tools to sidebar in running state (now includes input from server)
                            if (currentConversationId === convId && data.tools) {
                                for (const tool of data.tools) {
                                    addToolExecution({ id: tool.id, name: tool.name, input: tool.input || {} });
                                }
                            }
                            break;

                        case 'tool_executing':
                            console.log(`[${convId}] Executing: ${data.name}`);
                            break;

                        case 'tool_result':
                            // Backend sends: tool_use_id, tool_name, result
                            console.log(`[${convId}] Tool result: ${data.tool_name}`);
                            // Update sidebar with result
                            if (currentConversationId === convId) {
                                updateToolExecution(data.tool_use_id, data.result);
                            }
                            // Store result in toolUses array for chat display
                            const matchingTool = toolUses.find(tu => tu.id === data.tool_use_id);
                            if (matchingTool) {
                                matchingTool.result = data.result;
                            }
                            break;

                        case 'tool_execution_complete':
                            console.log(`[${convId}] All ${data.count} tools executed on server`);
                            // Tool details are shown in the inline panel, no need to embed in chat
                            break;

                        case 'context_compact':
                            // Claude Code 风格：context 接近限制时自动 compact
                            console.log(`[${convId}] Context compacted: ${data.reason}`);
                            // 可选：显示通知给用户
                            if (currentConversationId === convId) {
                                updateStatus('ready');  // Brief status update
                                console.log('Context window approaching limit, conversation compacted to continue');
                            }
                            break;

                        case 'error':
                            throw new Error(data.error?.message || 'Stream error');
                    }
                }

                onComplete(textContent, toolUses);
                return { textContent, toolUses };

            } catch (e) {
                console.error(`[${convId}] Stream error:`, e);
                throw e;
            }
        }

        // Execute a tool via the API with timeout and retry
        // OPTIMIZATION: Reduced timeout and retries to avoid long waits
        // - 45 second timeout (MCP server has 30s internal timeout)
        // - 1 retry only (max 90s total instead of 8 minutes)
        async function executeTool(toolName, toolInput) {
            try {
                console.log(`[executeTool] Starting: ${toolName}`);
                const response = await fetchWithRetry(`${BASE_URL}/v1/tools/execute`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: toolName, input: toolInput })
                }, 1, 45000); // 1 retry, 45 second timeout (max 90s total)

                const data = await response.json();
                const result = data.result || data;

                // Check for truncation errors and add helpful context
                if (result.truncated) {
                    console.warn(`[executeTool] Truncation detected for ${toolName}:`, result);
                    result.error = `${result.error}\n\nTip: The model tried to generate too much content. It will retry with smaller output.`;
                }

                console.log(`[executeTool] Completed: ${toolName}`);
                return result;
            } catch (e) {
                const errorMsg = e.name === 'AbortError'
                    ? `Tool timeout after 45s - the external service may be slow or unavailable`
                    : e.message;
                console.error(`[executeTool] Error for ${toolName}: ${errorMsg}`);
                return { error: errorMsg };
            }
        }

        // Track tool start times for elapsed time display
        const toolStartTimes = {};

        // Store tool data for detail modal
        let toolDataStore = {};

        // Helper to get status key for a tool use
        function getToolStatusKey(tu) {
            if (tu.result?.error) return 'error';
            if (tu.result) return 'complete';
            return 'running';
        }

        // updateToolPanel - disabled, using inline panel instead
        function updateToolPanel(toolUses) {
            // No-op: tool details now shown in inline panel
        }

        // ==================== Inline Chat Tool Panel ====================
        // This panel is embedded in the chat content area, showing tool execution status
        // as part of the conversation flow

        let inlinePanelRenderedIds = new Set();
        let inlinePanelLastStatus = {};

        // Create or update the inline tool panel in chat area
        function updateInlineChatToolPanel(toolUses) {
            if (!toolUses || toolUses.length === 0) return;

            const chatContent = document.getElementById('chat-content');
            if (!chatContent) return;

            // Find or create the inline panel
            let panel = document.getElementById('inline-chat-tool-panel');
            if (!panel) {
                panel = document.createElement('div');
                panel.id = 'inline-chat-tool-panel';
                panel.className = 'inline-chat-tool-panel';
                panel.innerHTML = `
                    <div class="inline-panel-header" onclick="toggleInlineChatToolPanel()">
                        <svg class="inline-panel-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/>
                        </svg>
                        <span class="inline-panel-status">Running tools...</span>
                        <svg class="inline-panel-toggle" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                        </svg>
                    </div>
                    <div class="inline-panel-list"></div>
                `;
                chatContent.appendChild(panel);
                // Reset tracking
                inlinePanelRenderedIds.clear();
                inlinePanelLastStatus = {};
            }

            const statusEl = panel.querySelector('.inline-panel-status');
            const listEl = panel.querySelector('.inline-panel-list');

            const allComplete = toolUses.every(t => t.result);
            const completedCount = toolUses.filter(t => t.result).length;
            const runningCount = toolUses.length - completedCount;

            // Update status text
            if (allComplete) {
                statusEl.textContent = `✓ ${completedCount} tools completed`;
            } else {
                statusEl.textContent = `Running ${runningCount} tool${runningCount > 1 ? 's' : ''}...`;
            }

            // Update items
            for (const tu of toolUses) {
                const toolId = tu.id || 'tool_' + Math.random().toString(36).substr(2, 9);

                // Track start time
                if (!tu.result && !toolStartTimes[toolId]) {
                    toolStartTimes[toolId] = Date.now();
                }
                if (tu.result && toolStartTimes[toolId]) {
                    delete toolStartTimes[toolId];
                }

                // Store for detail view
                toolDataStore[toolId] = tu;

                const currentStatus = getToolStatusKey(tu);
                const existingItem = listEl.querySelector(`[data-tool-id="${toolId}"]`);

                if (!existingItem) {
                    const itemHTML = createInlinePanelItemHTML(tu, toolId);
                    listEl.insertAdjacentHTML('beforeend', itemHTML);
                    inlinePanelRenderedIds.add(toolId);
                    inlinePanelLastStatus[toolId] = currentStatus;
                    // Auto-scroll
                    setTimeout(() => { listEl.scrollTop = listEl.scrollHeight; }, 50);
                } else if (inlinePanelLastStatus[toolId] !== currentStatus) {
                    const itemHTML = createInlinePanelItemHTML(tu, toolId);
                    existingItem.outerHTML = itemHTML;
                    inlinePanelLastStatus[toolId] = currentStatus;
                    setTimeout(() => { listEl.scrollTop = listEl.scrollHeight; }, 50);
                }
            }

            // Scroll chat container to bottom to show the panel
            scrollToBottom();
        }

        // Create HTML for inline panel item
        function createInlinePanelItemHTML(tu, toolId) {
            let statusClass = '';
            let statusIcon;
            if (tu.result?.error) {
                statusClass = 'error';
                statusIcon = `<svg class="item-status-icon error" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>`;
            } else if (tu.result) {
                statusClass = 'complete';
                statusIcon = `<svg class="item-status-icon success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>`;
            } else {
                statusClass = 'running';
                statusIcon = `<svg class="item-status-icon running" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                </svg>`;
            }

            const paramsStr = JSON.stringify(tu.input || {});
            const truncatedParams = paramsStr.length > 60 ? paramsStr.substring(0, 60) + '...' : paramsStr;

            let elapsedTime = '';
            if (!tu.result && toolStartTimes[toolId]) {
                const elapsed = Math.floor((Date.now() - toolStartTimes[toolId]) / 1000);
                elapsedTime = elapsed >= 60 ? `${Math.floor(elapsed/60)}m ${elapsed%60}s` : `${elapsed}s`;
            }

            return `
                <div class="inline-panel-item ${statusClass}" data-tool-id="${toolId}" onclick="showToolDetail('${toolId}')">
                    ${statusIcon}
                    <span class="item-name">${tu.name}</span>
                    ${elapsedTime ? `<span class="item-elapsed">${elapsedTime}</span>` : ''}
                    <span class="item-params">${truncatedParams}</span>
                </div>
            `;
        }

        // Toggle inline panel collapsed state
        function toggleInlineChatToolPanel() {
            const panel = document.getElementById('inline-chat-tool-panel');
            if (panel) {
                panel.classList.toggle('collapsed');
            }
        }

        // Collapse inline panel after completion
        function collapseInlineChatToolPanel() {
            setTimeout(() => {
                const panel = document.getElementById('inline-chat-tool-panel');
                if (panel) {
                    panel.classList.add('collapsed');
                }
            }, 1500);
        }

        // Remove inline panel (for new conversation)
        function removeInlineChatToolPanel() {
            const panel = document.getElementById('inline-chat-tool-panel');
            if (panel) panel.remove();
            inlinePanelRenderedIds.clear();
            inlinePanelLastStatus = {};
        }

        // Show tool detail modal
        function showToolDetail(toolId) {
            const tu = toolDataStore[toolId];
            if (!tu) return;

            // Remove existing modal
            document.querySelector('.tool-detail-modal')?.remove();

            const modal = document.createElement('div');
            modal.className = 'tool-detail-modal active';
            modal.onclick = (e) => { if (e.target === modal) modal.remove(); };

            modal.innerHTML = `
                <div class="tool-detail-content">
                    <div class="tool-detail-header">
                        <h3>
                            <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/>
                            </svg>
                            ${tu.name}
                        </h3>
                        <button class="icon-btn" onclick="this.closest('.tool-detail-modal').remove()">
                            <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M4 4l10 10M14 4L4 14"/>
                            </svg>
                        </button>
                    </div>
                    <div class="tool-detail-body">
                        <div class="tool-detail-section">
                            <div class="tool-detail-section-label">Input</div>
                            <pre>${JSON.stringify(tu.input, null, 2)}</pre>
                        </div>
                        ${tu.result ? `
                        <div class="tool-detail-section">
                            <div class="tool-detail-section-label">Output</div>
                            <pre>${JSON.stringify(tu.result, null, 2)}</pre>
                        </div>
                        ` : `
                        <div class="tool-detail-section">
                            <div class="tool-detail-section-label">Status</div>
                            <p style="color: var(--text-secondary);">Running...</p>
                        </div>
                        `}
                    </div>
                </div>
            `;

            document.body.appendChild(modal);
        }

        // Legacy function for compatibility - now renders container
        function renderToolCall(toolUse, result = null, status = 'running') {
            // This is kept for compatibility but the container version is preferred
            toolUse.result = result;
            return ''; // Return empty, container handles rendering
        }

        // Format tool calls for display in chat messages (fixed height, scrollable)
        function formatToolCallsForChat(toolUses) {
            if (!toolUses || toolUses.length === 0) return '';

            const toolsHtml = toolUses.map(tu => {
                const hasResult = tu.result !== undefined && tu.result !== null;
                const hasError = tu.result?.error;

                // Status indicator
                let statusHtml;
                if (hasError) {
                    statusHtml = '<span class="tool-status error">✗ Error</span>';
                } else if (hasResult) {
                    statusHtml = '<span class="tool-status success">✓ Done</span>';
                } else {
                    statusHtml = '<span class="tool-status running">⟳ Running</span>';
                }

                // Format input
                let inputStr = '';
                if (tu.input) {
                    try {
                        inputStr = JSON.stringify(tu.input, null, 2);
                    } catch {
                        inputStr = String(tu.input);
                    }
                }

                // Format output (truncate if too long)
                let outputStr = '';
                if (hasResult) {
                    try {
                        const resultData = hasError ? tu.result.error : tu.result;
                        if (typeof resultData === 'string') {
                            outputStr = resultData;
                        } else {
                            outputStr = JSON.stringify(resultData, null, 2);
                        }
                        // Truncate very long outputs
                        if (outputStr.length > 2000) {
                            outputStr = outputStr.substring(0, 2000) + '\n... (truncated)';
                        }
                    } catch {
                        outputStr = String(tu.result);
                    }
                }

                return `
                    <div class="chat-tool-item ${hasError ? 'error' : hasResult ? 'success' : 'running'}">
                        <div class="chat-tool-header">
                            <span class="chat-tool-name">${tu.name}</span>
                            ${statusHtml}
                        </div>
                        <div class="chat-tool-body">
                            <div class="chat-tool-section">
                                <div class="chat-tool-label">Input</div>
                                <pre class="chat-tool-code">${escapeHtml(inputStr)}</pre>
                            </div>
                            ${hasResult ? `
                            <div class="chat-tool-section">
                                <div class="chat-tool-label">${hasError ? 'Error' : 'Output'}</div>
                                <pre class="chat-tool-code ${hasError ? 'error' : ''}">${escapeHtml(outputStr)}</pre>
                            </div>
                            ` : ''}
                        </div>
                    </div>
                `;
            }).join('');

            // Use marker comment for reliable splitting in formatContent
            return `
                <div class="chat-tool-container">
                    <div class="chat-tool-header-bar">
                        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                        </svg>
                        <span>${toolUses.length} Tool${toolUses.length > 1 ? 's' : ''} Executed</span>
                    </div>
                    <div class="chat-tool-list">
                        ${toolsHtml}
                    </div>
                </div><!-- END_TOOL_CONTAINER -->`;
        }

        // Helper to escape HTML
        function escapeHtml(str) {
            if (!str) return '';
            return str
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }

        // Send message with tool support
        // Built-in slash commands (handled locally, not sent to server)
        const builtInCommands = {
            'name': { description: 'Rename current session', handler: handleNameCommand },
            'rename': { description: 'Rename current session', handler: handleNameCommand },
            'clear': { description: 'Clear current session messages', handler: handleClearCommand },
        };

        // Handle /name command
        function handleNameCommand(args) {
            const newName = args.trim();
            if (newName) {
                renameCurrentConversation(newName);
            } else {
                promptRenameCurrentConversation();
            }
            return true; // Command handled
        }

        // Handle /clear command
        function handleClearCommand(args) {
            if (currentConversationId) {
                const runtime = getConvRuntime(currentConversationId);
                runtime.messages = [];
                const conv = conversations.find(c => c.id === currentConversationId);
                if (conv) {
                    conv.messages = [];
                    // Session saved to backend via SessionAPI
                }
                renderMessages();
                updateStatus('completed', 'Messages cleared');
            }
            return true;
        }

        async function sendMessage() {
            const input = document.getElementById('message-input');
            let content = input.value.trim();

            // Check if CURRENT conversation is streaming (allow other conversations to stream)
            if ((!content && attachments.length === 0) || isCurrentStreaming()) return;

            // Handle built-in slash commands (local commands, not sent to server)
            if (content.startsWith('/')) {
                const spaceIdx = content.indexOf(' ');
                const cmdName = spaceIdx > 0 ? content.substring(1, spaceIdx).toLowerCase() : content.substring(1).toLowerCase();
                const cmdArgs = spaceIdx > 0 ? content.substring(spaceIdx + 1) : '';

                if (builtInCommands[cmdName]) {
                    input.value = '';
                    input.style.height = 'auto';
                    hideSkillPicker();
                    builtInCommands[cmdName].handler(cmdArgs);
                    return;
                }
            }

            // Handle explicit skill selection (via /skillname)
            // Note: Implicit skill invocation is now model-driven via the use_skill tool
            let skillInstructions = '';
            if (activeSkill) {
                skillInstructions = await getSkillInstructions(activeSkill.name);
                if (skillInstructions) {
                    // Wrap skill instructions in a clear format for explicit invocation
                    content = `<skill name="${activeSkill.name}">\n${skillInstructions}\n</skill>\n\nUser request: ${content}\n\nPlease follow the skill instructions above to complete this task.`;
                }
                // Clear active skill after use
                clearActiveSkill();
            }
            // For implicit invocation, Claude will detect the need and call use_skill tool

            // Resolve session references (#N) and include context from referenced sessions
            const sessionRefs = resolveSessionReferences(content);
            if (sessionRefs.length > 0) {
                const sessionContext = formatSessionContext(sessionRefs);
                content = content + sessionContext;
            }

            // Hide session picker if visible
            hideSessionPicker();

            // Capture the conversation ID at the start
            const thisConvId = currentConversationId || Date.now().toString();
            if (!currentConversationId) {
                currentConversationId = thisConvId;
                convRuntime[thisConvId] = { isStreaming: false, attachments: [], messages: [] };
            }
            const runtime = getConvRuntime(thisConvId);

            // Hide welcome
            const welcome = document.getElementById('welcome');
            if (welcome) welcome.style.display = 'none';

            // Build message content
            let messageContent = [];
            let fileAttachments = [];
            if (attachments.length > 0) {
                for (const att of attachments) {
                    if (att.type.startsWith('image/')) {
                        // Check if this is an image reference (optimized storage)
                        if (att.imageRef) {
                            // Store reference for JSONL, but need base64 for API
                            // Fetch base64 from backend for sending to Claude
                            const imageBase64 = await fetchImageBase64(
                                att.imageRef.session_id,
                                att.imageRef.relative_path.split('/').pop()
                            );
                            messageContent.push({
                                type: 'image',
                                source: { type: 'base64', media_type: att.type, data: imageBase64 },
                                // Store imageRef for later extraction when saving to JSONL
                                _imageRef: att.imageRef
                            });
                        } else {
                            // Legacy: direct base64
                            messageContent.push({
                                type: 'image',
                                source: { type: 'base64', media_type: att.type, data: att.data }
                            });
                        }
                    } else {
                        fileAttachments.push({
                            name: att.name,
                            type: att.type,
                            path: att.path || att.name
                        });
                    }
                }
            }

            // Build text content with file references
            let textContent = content || '';
            if (fileAttachments.length > 0) {
                const fileList = fileAttachments.map(f => `- ${f.name} (${f.path})`).join('\n');
                textContent = `[Attached files - use read_file tool to access them]:\n${fileList}\n\n${textContent}`;
            }
            if (textContent) {
                messageContent.push({ type: 'text', text: textContent });
            }

            // Add user message to THIS conversation's messages
            const userMsg = {
                role: 'user',
                content: attachments.length > 0 ? messageContent : content,
                timestamp: Date.now()
            };
            runtime.messages.push(userMsg);

            // Clear input
            input.value = '';
            input.style.height = 'auto';
            attachments = [];
            document.getElementById('attachments').innerHTML = '';

            // Render if viewing this conversation
            if (currentConversationId === thisConvId) {
                renderMessages();
            }

            try {
                // Save conversation to backend JSONL
                saveConversation(thisConvId);
                console.log('Conversation saved, ID:', thisConvId);

                // Mark THIS conversation as streaming
                runtime.isStreaming = true;
                updateConversationStatus(thisConvId, 'running');

                // Update UI if viewing this conversation
                if (currentConversationId === thisConvId) {
                    updateStatus('running');
                    updateSendButtonState();
                }
                console.log('Starting continueConversation for:', thisConvId);

                // Conversation loop for tool use - pass the conversation ID
                await continueConversation(thisConvId);
                console.log('continueConversation completed for:', thisConvId);

                // Update status
                updateConversationStatus(thisConvId, 'completed');
                if (currentConversationId === thisConvId) {
                    updateStatus('completed');
                }
            } catch (e) {
                console.error('sendMessage error:', e);

                // Check if this is an intentional abort (user switched conversations)
                const isAbortError = e.name === 'AbortError' || e.message?.includes('aborted');

                if (isAbortError) {
                    // User switched away from this conversation - not a real error
                    console.log(`[${thisConvId}] Stream aborted (user switched away)`);
                    // Set to 'running' to indicate it was interrupted but not failed
                    updateConversationStatus(thisConvId, 'running');
                } else {
                    // Real error
                    updateConversationStatus(thisConvId, 'error');
                    if (currentConversationId === thisConvId) {
                        updateStatus('error', e.message);
                        hideToolPanel(); // Clean up tool panel on error
                    }
                }

                // Clean up any incomplete tool execution state
                // Remove orphaned tool_result if present at the end
                const lastMsg = runtime.messages[runtime.messages.length - 1];
                if (lastMsg && lastMsg.role === 'user' && Array.isArray(lastMsg.content)) {
                    const hasToolResult = lastMsg.content.some(c => c.type === 'tool_result');
                    if (hasToolResult) {
                        console.log('Removing orphaned tool_result after error');
                        runtime.messages.pop();
                    }
                }
            } finally {
                // Mark THIS conversation as not streaming
                runtime.isStreaming = false;
                if (currentConversationId === thisConvId) {
                    updateSendButtonState();
                    hideTodoPanel();  // Close Tasks panel when task ends
                }

                // Clear any running tool update intervals
                if (toolUpdateInterval) {
                    clearInterval(toolUpdateInterval);
                    toolUpdateInterval = null;
                }

                // Save final state
                saveConversation(thisConvId);
            }
        }

        // Interval for updating tool elapsed time
        let toolUpdateInterval = null;

        // Sanitize messages for API - validate tool_result/tool_use pairing
        // This fixes ValidationException for both:
        // 1. "unexpected tool_use_id found in tool_result blocks" (orphaned tool_result)
        // 2. "tool_use ids were found without tool_result blocks" (orphaned tool_use)
        function sanitizeMessagesForAPI(messages) {
            // OPTIMIZATION 4: Quick check - skip sanitization if no tool_use/tool_result blocks
            let hasToolBlocks = false;
            for (const msg of messages) {
                if (Array.isArray(msg.content)) {
                    for (const block of msg.content) {
                        if (block.type === 'tool_use' || block.type === 'tool_result') {
                            hasToolBlocks = true;
                            break;
                        }
                    }
                    if (hasToolBlocks) break;
                }
            }
            if (!hasToolBlocks) {
                // No tool blocks, return messages as-is (fast path)
                return messages;
            }

            // First pass: collect all tool_use IDs and tool_result IDs
            const allToolUseIds = new Set();
            const allToolResultIds = new Set();

            for (const msg of messages) {
                if (msg.role === 'assistant' && Array.isArray(msg.content)) {
                    for (const block of msg.content) {
                        if (block.type === 'tool_use' && block.id) {
                            allToolUseIds.add(block.id);
                        }
                    }
                } else if (msg.role === 'user' && Array.isArray(msg.content)) {
                    for (const block of msg.content) {
                        if (block.type === 'tool_result' && block.tool_use_id) {
                            allToolResultIds.add(block.tool_use_id);
                        }
                    }
                }
            }

            // Find orphaned tool_use IDs (tool_use without matching tool_result)
            const orphanedToolUseIds = new Set();
            for (const id of allToolUseIds) {
                if (!allToolResultIds.has(id)) {
                    orphanedToolUseIds.add(id);
                    console.warn(`Found orphaned tool_use with id: ${id}`);
                }
            }

            // Second pass: build sanitized message list
            const sanitized = [];

            for (let i = 0; i < messages.length; i++) {
                const msg = messages[i];

                if (msg.role === 'assistant' && Array.isArray(msg.content)) {
                    // Filter out orphaned tool_use blocks from assistant messages
                    const filteredContent = msg.content.filter(block => {
                        if (block.type === 'tool_use' && block.id) {
                            if (orphanedToolUseIds.has(block.id)) {
                                console.warn(`Removing orphaned tool_use: ${block.id}`);
                                return false;
                            }
                        }
                        return true;
                    });

                    // Only add the message if it has content left
                    if (filteredContent.length > 0) {
                        // Check if only text content remains (no tool_use)
                        const hasToolUse = filteredContent.some(b => b.type === 'tool_use');
                        if (hasToolUse) {
                            sanitized.push({ role: msg.role, content: filteredContent });
                        } else {
                            // If only text blocks remain, flatten to string if possible
                            const textOnly = filteredContent.filter(b => b.type === 'text');
                            if (textOnly.length === filteredContent.length && textOnly.length === 1) {
                                sanitized.push({ role: msg.role, content: textOnly[0].text });
                            } else if (filteredContent.length > 0) {
                                sanitized.push({ role: msg.role, content: filteredContent });
                            }
                        }
                    }
                }
                // Validate tool_result messages - only include if tool_use_id exists and is not orphaned
                else if (msg.role === 'user' && Array.isArray(msg.content)) {
                    const hasToolResult = msg.content.some(c => c.type === 'tool_result');
                    if (hasToolResult) {
                        // Filter to only valid tool_results (matching tool_use exists and isn't orphaned)
                        const validResults = msg.content.filter(c => {
                            if (c.type !== 'tool_result') return true; // Keep non-tool_result items
                            const isValid = allToolUseIds.has(c.tool_use_id) && !orphanedToolUseIds.has(c.tool_use_id);
                            if (!isValid) {
                                console.warn(`Removing orphaned tool_result with tool_use_id: ${c.tool_use_id}`);
                            }
                            return isValid;
                        });

                        // Only add if there are valid results
                        if (validResults.length > 0) {
                            sanitized.push({ role: msg.role, content: validResults });
                        } else {
                            console.warn('Skipping message with all orphaned tool_results');
                        }
                    } else {
                        sanitized.push(msg);
                    }
                } else {
                    sanitized.push(msg);
                }
            }

            return sanitized;
        }

        // Validate and clean up conversation messages on load
        function validateConversationMessages(messages) {
            if (!messages || !Array.isArray(messages)) return [];

            // Remove thinking indicators and empty messages
            let cleaned = messages.filter(m => {
                if (m.isThinking) return false;
                if (!m.content) return false;
                if (typeof m.content === 'string' && m.content.trim() === '') return false;
                if (Array.isArray(m.content) && m.content.length === 0) return false;
                return true;
            });

            // Check for orphaned tool_results at the end (incomplete tool execution)
            if (cleaned.length > 0) {
                const lastMsg = cleaned[cleaned.length - 1];
                if (lastMsg.role === 'user' && Array.isArray(lastMsg.content)) {
                    const hasToolResult = lastMsg.content.some(c => c.type === 'tool_result');
                    if (hasToolResult) {
                        // This conversation was interrupted during tool execution
                        // Remove the tool_result message so user can retry
                        console.warn('Removing orphaned tool_result message from interrupted conversation');
                        cleaned = cleaned.slice(0, -1);
                    }
                }
            }

            return sanitizeMessagesForAPI(cleaned);
        }

        // Continue conversation (handles tool use loop) - works with specific conversation
        async function continueConversation(convId) {
            const runtime = getConvRuntime(convId);
            const messages = runtime.messages;
            const isViewing = currentConversationId === convId;

            // Reset abort controller for this conversation
            const abortController = resetAbortController(convId);
            const abortSignal = abortController.signal;

            const model = settings.model || 'claude-opus-4-5-20251101';  // Fixed to Opus 4.5
            const maxTokens = parseInt(settings.maxTokens || 16384);
            const temperature = parseFloat(settings.temperature || 0.7);

            // Add thinking indicator
            messages.push({
                role: 'assistant',
                content: '<div class="thinking"><span class="thinking-dot"></span><span class="thinking-dot"></span><span class="thinking-dot"></span></div>',
                isThinking: true
            });
            if (isViewing) renderMessages();

            // Prepare messages for API (exclude thinking indicators, empty content, and sanitize tool_use/tool_result pairing)
            const filteredMessages = messages
                .filter(m => !m.isThinking)
                .filter(m => {
                    if (!m.content) return false;
                    if (typeof m.content === 'string' && m.content.trim() === '') return false;
                    if (Array.isArray(m.content) && m.content.length === 0) return false;
                    return true;
                })
                .map(m => ({
                    role: m.role,
                    content: m.content
                }));

            // Sanitize to ensure tool_result/tool_use pairing is valid
            let apiMessages = sanitizeMessagesForAPI(filteredMessages);
            console.log(`[${convId}] Sending ${apiMessages.length} messages to API (filtered from ${filteredMessages.length})`);

            // OPTIMIZATION 1: Skip context check when message count is low
            // Only check context when there are enough messages to potentially need summarization
            const MIN_MESSAGES_FOR_CONTEXT_CHECK = 10;
            if (apiMessages.length >= MIN_MESSAGES_FOR_CONTEXT_CHECK) {
                const contextResult = await checkAndSummarizeContext(apiMessages, convId);
                if (contextResult.summarized) {
                    console.log(`[${convId}] Context was compacted, updating messages`);
                    apiMessages = contextResult.messages;
                    // Update runtime messages with summarized version
                    runtime.messages.length = 0;
                    runtime.messages.push(...apiMessages);
                    // Re-render to show compacted state
                    if (isViewing) renderMessages();
                }
            }

            try {
                // NOTE: Tools are managed by backend - no need to fetch from frontend
                // This prevents tool loading failures from causing hallucination issues
                // Backend will auto-add tools via get_tool_definitions()

                // System prompt to encourage tool usage
                // NOTE: System prompt is kept static for KV cache efficiency
                // Dynamic time is injected into the first user message by the backend
                const systemPrompt = `You are Springo, a helpful AI assistant with access to various tools.

**IMPORTANT: Do NOT use emojis in your responses or generated files.** Keep all output clean and text-based.

IMPORTANT: When answering questions about current events, recent news, technical documentation, or anything that requires up-to-date information:
1. ALWAYS use the available tools to search for information first
2. DO NOT make up or guess answers - use tools to verify facts
3. If you're unsure about something, use a search tool to find accurate information

**CRITICAL - Time-sensitive searches:**
When user asks for "最新"/"latest"/"recent"/"newest" content:

RULES (MUST follow ALL):
1. Use ENGLISH keywords only (never Chinese)
2. Use freshness="pw" on EVERY search call - including follow-up searches for details
3. Include the current year in query to find recent content
4. NEVER search for old content names like "Building Effective Agents" without freshness
5. Trust the FIRST search results - don't second-guess by searching for older content

Example workflow:
- User: "anthropic最新的agent博客"
- Search 1: brave_web_search(query="Anthropic agent blog ${new Date().getFullYear()} latest", freshness="pw") [CORRECT]
- If need details: brave_web_search(query="<title from result> details", freshness="pw") [CORRECT]
- WRONG: brave_web_search(query="Building Effective Agents") [WRONG - finds OLD content]

WITHOUT freshness="pw", search returns OLD but popular results instead of newest!

Available MCP tool categories:
- Web search: web-search__brave_web_search (USE freshness="pw" for latest content!)
- News search: web-search__brave_news_search (for news articles)
- Documentation: strands-agents, bedrock-agentcore, context7
- File operations: read_file, write_file, glob, grep, etc.

NOTE: All web searches use MCP servers. DO NOT use built-in web_search (removed).

Be concise and helpful in your responses.`;

                const requestBody = {
                    model: model,
                    max_tokens: maxTokens,
                    temperature: temperature,
                    system: systemPrompt,  // System prompt to guide behavior
                    messages: apiMessages,
                    // NOTE: tools not sent - backend manages tools via get_tool_definitions()
                    stream: true,  // Enable streaming
                    compact_model: settings.compactModel || 'claude-haiku-4-5-20251001',  // Model for context compaction
                    session_id: convId  // Session ID for tool-results storage (matches session directory)
                };
                console.log(`[${convId}] Request body (streaming):`, JSON.stringify(requestBody).substring(0, 200));

                // Use native fetch for streaming (no retry wrapper)
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 minute timeout for streaming

                // Link external abort signal
                if (abortSignal) {
                    abortSignal.addEventListener('abort', () => controller.abort());
                }

                // Use auto mode for server-side tool execution (faster)
                const apiEndpoint = AUTO_TOOL_EXECUTION ? '/v1/messages-auto' : '/v1/messages';
                const response = await fetch(`${BASE_URL}${apiEndpoint}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'anthropic-version': '2023-06-01'
                    },
                    body: JSON.stringify(requestBody),
                    signal: controller.signal
                });

                clearTimeout(timeoutId);
                console.log(`[${convId}] Streaming response status:`, response.status);

                if (!response.ok) {
                    // Check if response is JSON before parsing
                    const contentType = response.headers.get('content-type') || '';
                    let errorMessage = `HTTP ${response.status}`;
                    if (contentType.includes('application/json')) {
                        try {
                            const errorData = await response.json();
                            errorMessage = errorData.error?.message || errorMessage;
                        } catch (e) {
                            console.warn(`[${convId}] Failed to parse error response as JSON`);
                        }
                    } else {
                        // Non-JSON response (likely HTML error page)
                        const text = await response.text();
                        if (text.includes('<!doctype') || text.includes('<html')) {
                            errorMessage = `Server returned HTML instead of JSON (status ${response.status}). The server may still be starting up - please wait a moment and try again.`;
                        }
                    }
                    throw new Error(errorMessage);
                }

                // Remove thinking message from THIS conversation
                const thinkingIdx = messages.findIndex(m => m.isThinking);
                if (thinkingIdx >= 0) messages.splice(thinkingIdx, 1);

                // Process streaming response with progressive UI updates
                let textContent = '';
                let toolUses = [];

                const { textContent: finalText, toolUses: finalTools } = await processStreamingResponse(
                    response,
                    convId,
                    // onTextUpdate - called for each text chunk
                    (text, tools, isFinal) => {
                        textContent = text;
                        toolUses = tools;
                        // OPTIMIZATION 3: Debounced UI updates (only if viewing this conversation)
                        if (currentConversationId === convId) {
                            debouncedUpdateAssistantMessage(convId, text, tools, false);
                        }
                    },
                    // onComplete - called when stream ends
                    (text, tools) => {
                        console.log(`[${convId}] Stream complete: text=${text.length} chars, tools=${tools.length}`);
                    }
                );

                textContent = finalText;
                toolUses = finalTools;

                if (toolUses.length > 0) {
                    console.log(`[${convId}] Tool uses:`, toolUses.map(t => t.name));
                    const withResults = toolUses.filter(t => t.result !== undefined);
                    console.log(`[${convId}] Tools with results: ${withResults.length}/${toolUses.length}`);
                }
                console.log(`[${convId}] Final textContent length: ${textContent.length}`);

                // Final UI update
                const stillViewing = currentConversationId === convId;
                if (stillViewing && toolUses.length > 0) {
                    updateToolPanel(toolUses);
                }
                // Clear any pending debounced updates to prevent them from overwriting the final content
                if (streamingUIDebounce.timers[convId]) {
                    clearTimeout(streamingUIDebounce.timers[convId]);
                    delete streamingUIDebounce.timers[convId];
                }
                delete streamingUIDebounce.pending[convId];
                updateAssistantMessage(convId, textContent, toolUses, true);
                console.log(`[${convId}] Called updateAssistantMessage with isFinal=true`);

                // Collapse inline panel after stream ends
                if (stillViewing) {
                    collapseInlineChatToolPanel();
                }

                // Execute tools if any were detected
                // When AUTO_TOOL_EXECUTION is enabled, tools are already executed on server
                // so we skip frontend execution and just save the conversation
                if (toolUses.length > 0 && !AUTO_TOOL_EXECUTION) {
                    if (stillViewing) updateStatus('tool');

                    // Start interval to update elapsed time display
                    if (toolUpdateInterval) clearInterval(toolUpdateInterval);
                    if (stillViewing) {
                        toolUpdateInterval = setInterval(() => {
                            if (currentConversationId === convId) {
                                updateToolPanel(toolUses);
                            }
                        }, 1000);
                    }

                    // Execute tools and collect results
                    // OPTIMIZATION: Execute tools in parallel for better performance
                    const toolResults = [];

                    // Add all tools to sidebar first
                    for (const tu of toolUses) {
                        if (currentConversationId === convId) {
                            addToolExecution(tu);
                        }
                    }

                    // Execute all tools in parallel
                    const executePromises = toolUses.map(async (tu) => {
                        let result = await executeTool(tu.name, tu.input);

                        // Handle delegation tool specially - initiate the actual delegation
                        if (tu.name === 'delegate_task' && result.ui_action === 'delegate_to_session') {
                            result = await handleDelegation(convId, result);
                        }

                        // Handle task tool - launch background task in new session
                        if (tu.name === 'task' && result.ui_action === 'launch_background_task') {
                            result = await handleBackgroundTask(convId, result);
                        }

                        tu.result = result;
                        // Update right sidebar with result
                        if (currentConversationId === convId) {
                            updateToolExecution(tu.id, result);
                            updateToolPanel(toolUses);
                        }
                        // Handle special UI actions from tool results (Todo, AskUser, PlanMode, etc.)
                        handleToolResultUI(tu.name, result, convId);
                        return {
                            type: 'tool_result',
                            tool_use_id: tu.id,
                            content: JSON.stringify(result)
                        };
                    });

                    // Wait for all tools to complete
                    const results = await Promise.all(executePromises);
                    toolResults.push(...results);

                    // Stop the update interval
                    if (toolUpdateInterval) {
                        clearInterval(toolUpdateInterval);
                        toolUpdateInterval = null;
                    }

                    // Update chat display with tool results (non-AUTO mode)
                    const toolsWithResults = toolUses.filter(tu => tu.result !== undefined);
                    if (toolsWithResults.length > 0 && currentConversationId === convId) {
                        const toolHtml = formatToolCallsForChat(toolsWithResults);
                        const displayContent = toolHtml + (textContent ? '\n\n' + textContent : '');
                        const lastMsg = messages[messages.length - 1];
                        if (lastMsg && lastMsg.role === 'assistant') {
                            lastMsg.displayContent = displayContent;
                            updateLastMessageContent(displayContent);
                        }
                    }

                    // Add tool results as user message and continue
                    messages.push({ role: 'user', content: toolResults });
                    await continueConversation(convId);
                } else if (toolUses.length > 0 && AUTO_TOOL_EXECUTION) {
                    // AUTO MODE: Tools were executed on server
                    // CRITICAL: Build tool_result message from collected results
                    // Without this, tool_use blocks become "orphaned" on reload and get stripped
                    console.log(`[${convId}] Auto mode: ${toolUses.length} tools executed on server`);

                    // Build tool_results from toolUses array (results came via SSE tool_result events)
                    const toolsWithResults = toolUses.filter(tu => tu.result !== undefined);
                    if (toolsWithResults.length > 0) {
                        const toolResults = toolsWithResults.map(tu => ({
                            type: 'tool_result',
                            tool_use_id: tu.id,
                            content: typeof tu.result === 'string' ? tu.result : JSON.stringify(tu.result)
                        }));

                        // Add tool_result as user message (matches Claude API message format)
                        messages.push({ role: 'user', content: toolResults });
                        console.log(`[${convId}] Added ${toolResults.length} tool_result entries to messages`);

                        // Update chat display with tool results
                        if (currentConversationId === convId) {
                            const toolHtml = formatToolCallsForChat(toolsWithResults);
                            const displayContent = toolHtml + (textContent ? '\n\n' + textContent : '');
                            const lastMsg = messages[messages.length - 2]; // Assistant message before tool_result
                            if (lastMsg && lastMsg.role === 'assistant') {
                                lastMsg.displayContent = displayContent;
                                updateLastMessageContent(displayContent);
                            }
                        }
                    }

                    if (stillViewing) hideToolPanel();
                    saveConversation(convId);
                    if (currentConversationId === convId) refreshContextStats();
                } else {
                    // No tools - save and hide panel
                    if (currentConversationId === convId) hideToolPanel();
                    saveConversation(convId);
                    if (currentConversationId === convId) refreshContextStats();
                }

            } catch (e) {
                console.error(`[${convId}] Error:`, e);

                // Clean up tool update interval
                if (toolUpdateInterval) {
                    clearInterval(toolUpdateInterval);
                    toolUpdateInterval = null;
                }

                // Check if this is an intentional abort (user switched conversations)
                const isAbortError = e.name === 'AbortError' || e.message?.includes('aborted');
                if (isAbortError) {
                    // User switched away - not a real error, just re-throw to let sendMessage handle it
                    throw e;
                }

                // Remove thinking message
                const thinkingIdx = messages.findIndex(m => m.isThinking);
                if (thinkingIdx >= 0) messages.splice(thinkingIdx, 1);

                // For ValidationException, actually clean up the message state
                const isValidationError = e.message?.includes('ValidationException');
                if (isValidationError) {
                    console.warn('ValidationException detected - cleaning up message state');

                    // Remove any incomplete assistant message with tool_use at the end
                    while (messages.length > 0) {
                        const lastMsg = messages[messages.length - 1];

                        // Remove orphaned tool_result messages (user messages with only tool_result)
                        if (lastMsg.role === 'user' && Array.isArray(lastMsg.content)) {
                            const hasToolResult = lastMsg.content.some(c => c.type === 'tool_result');
                            if (hasToolResult) {
                                console.warn('Removing orphaned tool_result message');
                                messages.pop();
                                continue;
                            }
                        }

                        // Remove assistant messages with orphaned tool_use
                        if (lastMsg.role === 'assistant' && Array.isArray(lastMsg.content)) {
                            const hasToolUse = lastMsg.content.some(c => c.type === 'tool_use');
                            if (hasToolUse) {
                                console.warn('Removing assistant message with orphaned tool_use');
                                messages.pop();
                                continue;
                            }
                        }

                        break; // Stop if we hit a clean message
                    }
                }

                // Add user-friendly error message (but avoid duplicate error messages)
                // Parse structured error response from backend
                let errorMessage;
                let statusMessage;

                try {
                    // Try to parse as JSON error response
                    const errorData = JSON.parse(e.message);
                    if (errorData.error) {
                        const err = errorData.error;
                        errorMessage = `⚠️ ${err.message}\n\n${err.suggestion || ''}`;
                        statusMessage = err.message;
                        if (err.retry_after) {
                            errorMessage += `\n\n建议等待 ${err.retry_after} 秒后重试`;
                        }
                    } else {
                        throw new Error('Not structured error');
                    }
                } catch {
                    // Fallback to string matching for legacy errors
                    const isNetworkErr = isNetworkError(e);
                    const isThrottlingError = e.message?.includes('ThrottlingException') || e.message?.includes('Too many tokens') || e.message?.includes('请求频率限制');
                    const isRateLimitError = e.message?.includes('rate') && e.message?.includes('limit');
                    const isAccessDenied = e.message?.includes('AccessDenied') || e.message?.includes('访问被拒绝');
                    const isValidationErr = e.message?.includes('Validation') || e.message?.includes('格式错误');
                    const isServiceUnavailable = e.message?.includes('ServiceUnavailable') || e.message?.includes('服务暂时不可用');
                    const isOverloaded = e.message?.includes('overload') || e.message?.includes('过载');
                    const isTimeout = e.message?.includes('timeout') || e.message?.includes('超时');

                    if (isNetworkErr) {
                        // Network/connection error - show toast and don't add error message to chat
                        errorMessage = null; // Don't add to chat - transient error
                        statusMessage = 'Connection error';
                        showToast('Connection lost. Please check your network and try again.', 'error', 8000);
                        lastConnectionHealthy = false; // Mark connection as unhealthy
                    } else if (isValidationError || isValidationErr) {
                        errorMessage = `⚠️ 消息格式错误\n\n对话已清理，请重试。`;
                        statusMessage = '消息格式错误';
                    } else if (isThrottlingError || isRateLimitError) {
                        errorMessage = `⚠️ 请求频率限制\n\nAWS Bedrock API 暂时限流。\n\n可能原因：\n• 短时间内发送了过多请求\n• 消息内容过长\n\n建议：等待 1-2 分钟后重试`;
                        statusMessage = '请求频率限制';
                    } else if (isAccessDenied) {
                        errorMessage = `⚠️ 访问被拒绝\n\nAWS 凭证无效或无权限访问模型。\n\n建议：检查 AWS 凭证配置`;
                        statusMessage = '访问被拒绝';
                    } else if (isServiceUnavailable || isOverloaded) {
                        errorMessage = `⚠️ 服务暂时不可用\n\nClaude API 当前负载过高或正在维护。\n\n建议：等待 1-2 分钟后重试`;
                        statusMessage = '服务暂时不可用';
                    } else if (isTimeout) {
                        errorMessage = `⚠️ 请求超时\n\n服务器响应时间过长。\n\n建议：简化请求内容或稍后重试`;
                        statusMessage = '请求超时';
                    } else {
                        errorMessage = `⚠️ 错误: ${e.message}`;
                        statusMessage = e.message;
                    }
                }

                // Check if the last message is already this error message to avoid duplicates
                // For network errors, errorMessage is null - don't add to chat
                if (errorMessage) {
                    const lastMsg = messages[messages.length - 1];
                    const isDuplicateError = lastMsg &&
                        lastMsg.role === 'assistant' &&
                        typeof lastMsg.content === 'string' &&
                        lastMsg.content.includes('⚠️');

                    if (!isDuplicateError) {
                        messages.push({ role: 'assistant', content: errorMessage });
                    }
                }

                if (currentConversationId === convId) {
                    hideToolPanel(); // Clean up tool panel
                    renderMessages();
                    updateStatus('error', statusMessage);
                }
                updateConversationStatus(convId, 'error');

                // Save the cleaned up state
                saveConversation(convId);

                throw e; // Re-throw to be handled by sendMessage
            }
        }

        // Update assistant message display - works with specific conversation
        function updateAssistantMessage(convId, text, toolUses, isFinal = false) {
            const runtime = getConvRuntime(convId);
            const messages = runtime.messages;
            const isViewing = currentConversationId === convId;

            let displayContent = text || '';

            // Tool details are shown in the inline panel, so we don't embed them in chat
            // Just ensure there's some text if tools completed without a response
            if (isFinal && toolUses && toolUses.length > 0) {
                const toolsWithResults = toolUses.filter(tu => tu.result !== undefined);
                if (toolsWithResults.length > 0 && !displayContent) {
                    // If no text response but tools completed, add a brief indicator
                    displayContent = `✓ Task completed with ${toolsWithResults.length} tool${toolsWithResults.length > 1 ? 's' : ''} executed.`;
                }
            }

            // Show/update inline tool panel in chat area (only if viewing)
            if (isViewing && toolUses && toolUses.length > 0) {
                updateInlineChatToolPanel(toolUses);
                if (isFinal) {
                    console.log('[Inline Panel] isFinal=true, collapsing panel');
                    collapseInlineChatToolPanel();
                }
            }

            // Build proper API content (keep tool_use structure for API calls)
            let apiContent = text || '';
            if (toolUses && toolUses.length > 0) {
                apiContent = [];
                if (text) {
                    apiContent.push({ type: 'text', text: text });
                }
                for (const tu of toolUses) {
                    apiContent.push({
                        type: 'tool_use',
                        id: tu.id,
                        name: tu.name,
                        input: tu.input || {}
                    });
                }
            }

            // Don't add empty messages
            if (!text && toolUses.length === 0 && !isFinal) {
                return;
            }

            // Update or add assistant message to THIS conversation
            const lastMsg = messages[messages.length - 1];

            if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.isThinking) {
                // Update existing assistant message
                lastMsg.displayContent = displayContent;
                if (apiContent || toolUses.length > 0) {
                    lastMsg.content = apiContent;
                    lastMsg.hasToolUse = toolUses.length > 0;
                }
                // Update UI - always update when isFinal to show final result
                if (isViewing && (displayContent || isFinal)) {
                    updateLastMessageContent(displayContent || '');
                }
            } else if (text || toolUses.length > 0 || isFinal) {
                // Remove thinking indicator if present (it has isThinking=true)
                const thinkingIdx = messages.findIndex(m => m.isThinking);
                if (thinkingIdx >= 0) {
                    messages.splice(thinkingIdx, 1);
                }

                // Push new assistant message
                messages.push({
                    role: 'assistant',
                    content: apiContent || text || '',
                    displayContent: displayContent,
                    hasToolUse: toolUses.length > 0,
                    timestamp: Date.now()
                });

                // ALWAYS render to create the DOM element when pushing new message
                if (isViewing) {
                    renderMessages();
                }
            }
        }

        // Update only the last message content without re-rendering everything
        function updateLastMessageContent(displayContent) {
            const chatContent = document.querySelector('.chat-content');
            // Find the last .message element (not :last-child, because inline panel may be after it)
            const messages = chatContent?.querySelectorAll('.message');
            const lastMessage = messages?.[messages.length - 1];
            const lastMessageEl = lastMessage?.querySelector('.message-content');
            if (lastMessageEl) {
                // Use formatContent to preserve tool HTML while parsing markdown
                lastMessageEl.innerHTML = formatContent(displayContent);
                // Re-apply code highlighting
                lastMessageEl.querySelectorAll('pre code').forEach(block => {
                    hljs.highlightElement(block);
                });
                // Add copy buttons to code blocks
                lastMessageEl.querySelectorAll('pre').forEach(pre => {
                    if (!pre.querySelector('.copy-code-btn')) {
                        const btn = document.createElement('button');
                        btn.className = 'copy-code-btn';
                        btn.textContent = 'Copy';
                        btn.onclick = () => {
                            navigator.clipboard.writeText(pre.querySelector('code').textContent);
                            btn.textContent = 'Copied!';
                            setTimeout(() => btn.textContent = 'Copy', 2000);
                        };
                        pre.appendChild(btn);
                    }
                });
                // Auto-scroll to bottom as content updates
                scrollToBottom();
            }
        }

        // Handle pasted image from clipboard
        // Optimized: compress and upload to backend, store reference instead of base64
        async function handlePastedImage(file) {
            if (!file || !file.type.startsWith('image/')) return;

            // Check file size (max 10MB)
            if (file.size > 10 * 1024 * 1024) {
                alert('Image too large (max 10MB)');
                return;
            }

            try {
                // Compress image before uploading
                const compressedData = await compressImage(file, {
                    maxWidth: 1920,
                    maxHeight: 1920,
                    quality: 0.8
                });

                // Generate filename
                const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
                const fileName = `pasted-image-${timestamp}`;

                // Upload to backend
                const uploadResult = await uploadImageToBackend(
                    currentConversationId,
                    compressedData.base64,
                    compressedData.mediaType,
                    fileName
                );

                if (uploadResult.error) {
                    console.error('Failed to upload image:', uploadResult.error);
                    // Fallback to base64 storage
                    attachments.push({
                        name: fileName + '.png',
                        type: file.type,
                        data: compressedData.base64,
                        path: fileName,
                        isPasted: true
                    });
                } else {
                    // Store reference instead of base64
                    attachments.push({
                        name: uploadResult.filename,
                        type: uploadResult.media_type,
                        imageRef: {
                            image_id: uploadResult.image_id,
                            relative_path: uploadResult.relative_path,
                            session_id: currentConversationId
                        },
                        isPasted: true
                    });
                    console.log(`Image uploaded: ${uploadResult.filename} (${(uploadResult.size / 1024).toFixed(1)} KB)`);
                }

                renderAttachments();
                document.getElementById('send-btn').disabled = false;

            } catch (e) {
                console.error('Failed to process pasted image:', e);
                alert('Failed to process pasted image');
            }
        }

        // Compress image using canvas
        function compressImage(file, options = {}) {
            return new Promise((resolve, reject) => {
                const maxWidth = options.maxWidth || 1920;
                const maxHeight = options.maxHeight || 1920;
                const quality = options.quality || 0.8;

                const img = new Image();
                img.onload = () => {
                    let { width, height } = img;

                    // Calculate new dimensions
                    if (width > maxWidth || height > maxHeight) {
                        const ratio = Math.min(maxWidth / width, maxHeight / height);
                        width = Math.round(width * ratio);
                        height = Math.round(height * ratio);
                    }

                    // Create canvas and draw resized image
                    const canvas = document.createElement('canvas');
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);

                    // Convert to JPEG for better compression (unless PNG is needed for transparency)
                    const mediaType = file.type === 'image/png' ? 'image/png' : 'image/jpeg';
                    const dataUrl = canvas.toDataURL(mediaType, quality);
                    const base64 = dataUrl.split(',')[1];

                    resolve({
                        base64,
                        mediaType,
                        width,
                        height
                    });
                };
                img.onerror = () => reject(new Error('Failed to load image'));

                // Read file as data URL
                const reader = new FileReader();
                reader.onload = (e) => { img.src = e.target.result; };
                reader.onerror = () => reject(new Error('Failed to read file'));
                reader.readAsDataURL(file);
            });
        }

        // Upload image to backend
        async function uploadImageToBackend(sessionId, base64Data, mediaType, filename) {
            try {
                const response = await fetch(`${BASE_URL}/v1/images/upload`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: sessionId,
                        image_data: base64Data,
                        media_type: mediaType,
                        filename: filename
                    })
                });

                if (!response.ok) {
                    const error = await response.json();
                    return { error: error.error || 'Upload failed' };
                }

                return await response.json();
            } catch (e) {
                return { error: e.message };
            }
        }

        // Fetch image base64 from backend (for sending to Claude API)
        async function fetchImageBase64(sessionId, imageFilename) {
            try {
                const response = await fetch(
                    `${BASE_URL}/v1/images/${sessionId}/${imageFilename}?format=base64`
                );

                if (!response.ok) {
                    console.error('Failed to fetch image:', response.status);
                    return null;
                }

                const data = await response.json();
                return data.data;
            } catch (e) {
                console.error('Failed to fetch image base64:', e);
                return null;
            }
        }

        // File handling
        function handleFiles(files) {
            for (const file of files) {
                if (file.size > 10 * 1024 * 1024) {
                    alert('File too large (max 10MB)');
                    continue;
                }

                // For non-image files, just store the path (Electron provides file.path)
                const isImage = file.type.startsWith('image/');

                if (isImage) {
                    const reader = new FileReader();
                    reader.onload = (e) => {
                        const base64 = e.target.result.split(',')[1];
                        attachments.push({
                            name: file.name,
                            type: file.type,
                            data: base64,
                            path: file.path || file.name
                        });
                        renderAttachments();
                        document.getElementById('send-btn').disabled = false;
                    };
                    reader.readAsDataURL(file);
                } else {
                    // For documents, just store the path - Claude will read via tools
                    attachments.push({
                        name: file.name,
                        type: file.type || 'application/octet-stream',
                        path: file.path || file.name,
                        data: null
                    });
                    renderAttachments();
                    document.getElementById('send-btn').disabled = false;
                }
            }
        }

        // Validate base64 image data
        function isValidBase64Image(data) {
            if (!data || typeof data !== 'string') return false;
            // Check if it's valid base64 (only contains valid base64 characters)
            const base64Regex = /^[A-Za-z0-9+/=]+$/;
            if (!base64Regex.test(data)) return false;
            // Check minimum length (a valid image should have some data)
            if (data.length < 100) return false;
            // Try to decode a small portion to verify it's valid base64
            try {
                atob(data.slice(0, 100));
                return true;
            } catch (e) {
                return false;
            }
        }

        function renderAttachments() {
            const container = document.getElementById('attachments');

            // Filter out invalid image attachments
            const validAttachments = attachments.filter((a, i) => {
                const isImage = a.type && a.type.startsWith('image/');
                if (isImage && a.data && !isValidBase64Image(a.data)) {
                    console.warn(`Invalid image data for attachment: ${a.name}`);
                    return false; // Remove invalid image
                }
                return true;
            });

            // Update attachments array if we filtered any out
            if (validAttachments.length !== attachments.length) {
                attachments.length = 0;
                attachments.push(...validAttachments);
            }

            container.innerHTML = attachments.map((a, i) => {
                const isImage = a.type && a.type.startsWith('image/');

                if (isImage && a.data) {
                    // Show image thumbnail for images with data
                    return `
                        <div class="attachment image-attachment" title="${a.name}">
                            <img src="data:${a.type};base64,${a.data}" class="attachment-thumbnail" alt="${a.name}">
                            <span class="attachment-name">${a.name.length > 20 ? a.name.slice(0, 17) + '...' : a.name}</span>
                            <span class="remove" onclick="removeAttachment(${i})">×</span>
                        </div>
                    `;
                } else {
                    // Show icon for other files
                    return `
                        <div class="attachment ${a.isContextFile ? 'context-file' : ''}">
                            <svg class="file-icon" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                                ${a.isContextFile && a.type === 'inode/directory'
                                    ? '<path d="M3 7v6a2 2 0 002 2h10a2 2 0 002-2V9a2 2 0 00-2-2h-5l-2-2H5a2 2 0 00-2 2z"/>'
                                    : '<path d="M14 2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2Z"/>'}
                            </svg>
                            ${a.name}
                            <span class="remove" onclick="removeAttachment(${i})">×</span>
                        </div>
                    `;
                }
            }).join('');
        }

        function removeAttachment(index) {
            attachments.splice(index, 1);
            renderAttachments();
            document.getElementById('send-btn').disabled = !document.getElementById('message-input').value.trim() && attachments.length === 0;
        }

        // Settings
        function openSettings() {
            document.getElementById('settings-modal').classList.add('active');
            // Load default working directory
            document.getElementById('settings-default-workdir').value = defaultWorkingFolder || '~/Downloads';
            document.getElementById('settings-model').value = settings.model || 'claude-sonnet-4-5-20250929';
            document.getElementById('settings-max-tokens').value = settings.maxTokens || 16384;
            document.getElementById('settings-temperature').value = settings.temperature || 0.7;
            document.getElementById('temp-value').textContent = settings.temperature || 0.7;
            // Compact model setting (default to Haiku 4.5)
            document.getElementById('settings-compact-model').value = settings.compactModel || 'claude-haiku-4-5-20251001';
            // Load AWS credentials settings
            loadAwsSettings();
            // Load Memory settings
            loadMemorySettings();
            // Load Skills and MCP servers lists
            loadSkillsList();
            loadMcpServersList();
        }

        function closeSettings() {
            document.getElementById('settings-modal').classList.remove('active');
            // Save default working directory
            const newDefaultWorkdir = document.getElementById('settings-default-workdir').value.trim();
            if (newDefaultWorkdir && newDefaultWorkdir !== defaultWorkingFolder) {
                defaultWorkingFolder = newDefaultWorkdir;
                localStorage.setItem('defaultWorkingFolder', defaultWorkingFolder);
                console.log('Default working directory updated to:', defaultWorkingFolder);
                // Add to workspace if not already there
                ensureDefaultFolderInWorkspace();
                renderWorkingFolders();
            }
            settings.model = document.getElementById('settings-model').value;
            settings.maxTokens = document.getElementById('settings-max-tokens').value;
            settings.temperature = document.getElementById('settings-temperature').value;
            settings.compactModel = document.getElementById('settings-compact-model').value;
            localStorage.setItem('settings', JSON.stringify(settings));
            // Model select was removed - model is fixed to Opus 4.5
            // Save AWS credentials
            saveAwsSettings();
            // Save Memory settings
            saveMemorySettings();
        }

        function loadSettings() {
            // Migrate old model settings to 4.5 defaults
            migrateSettings();

            // Model select was removed - model is fixed to Opus 4.5
            // Always use light theme by default
            setTheme('light');
        }

        function migrateSettings() {
            let needsSave = false;

            // Migrate compact model: 3.5 Haiku -> 4.5 Haiku
            if (settings.compactModel === 'claude-3-5-haiku-20241022' ||
                settings.compactModel === 'claude-3-haiku-20240307') {
                settings.compactModel = 'claude-haiku-4-5-20251001';
                needsSave = true;
                console.log('[Settings Migration] compactModel upgraded to Haiku 4.5');
            }

            // Migrate main model: 3.5 Sonnet -> 4.5 Sonnet
            if (settings.model === 'claude-3-5-sonnet-20241022') {
                settings.model = 'claude-sonnet-4-5-20250929';
                needsSave = true;
                console.log('[Settings Migration] model upgraded to Sonnet 4.5');
            }

            if (needsSave) {
                localStorage.setItem('settings', JSON.stringify(settings));
                console.log('[Settings Migration] Settings saved');
            }
        }

        function saveSettings() {
            // Model is fixed to Opus 4.5, no need to save from selector
            localStorage.setItem('settings', JSON.stringify(settings));
        }

        // ==================== AWS Credentials Management ====================
        async function loadAwsSettings() {
            try {
                const res = await fetch(`${BASE_URL}/v1/config/aws`);
                const data = await res.json();
                const statusEl = document.getElementById('aws-connection-status');

                if (data.connected) {
                    // Show connection status with source
                    let source = '';
                    if (data.method === 'aws_profile') {
                        source = `via ~/.aws/credentials`;
                    } else if (data.method === 'env_vars') {
                        source = `via env vars`;
                    } else if (data.method === 'env_file') {
                        source = `via ~/.springo/.env`;
                    }
                    statusEl.innerHTML = `<span style="color: #22c55e;">✓ Connected (${data.identity?.account || ''}) ${source}</span>`;
                } else {
                    statusEl.innerHTML = '<span style="color: var(--text-tertiary);">Not connected</span>';
                }
            } catch (e) {
                console.log('Failed to load AWS settings:', e);
                document.getElementById('aws-connection-status').innerHTML = '';
            }
        }

        async function saveAwsSettings() {
            const accessKey = document.getElementById('settings-aws-access-key').value;
            const secretKey = document.getElementById('settings-aws-secret-key').value;

            // Only save if user entered credentials
            if (!accessKey || !secretKey) {
                return;
            }

            try {
                await fetch(`${BASE_URL}/v1/config/aws`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        method: 'env_file',
                        access_key_id: accessKey,
                        secret_access_key: secretKey,
                        region: 'us-east-1'
                    })
                });
            } catch (e) {
                console.log('Failed to save AWS settings:', e);
            }
        }

        async function testAwsConnection() {
            const btn = document.getElementById('test-aws-btn');
            const statusEl = document.getElementById('aws-connection-status');

            btn.disabled = true;
            btn.textContent = 'Testing...';
            statusEl.innerHTML = '';

            // Save settings first if user entered credentials
            await saveAwsSettings();

            try {
                const res = await fetch(`${BASE_URL}/v1/config/aws/test`);
                const data = await res.json();

                if (data.valid) {
                    statusEl.innerHTML = `<span style="color: #22c55e;">✓ Connected (${data.account})</span>`;
                    // Reload to show auto-detected state
                    loadAwsSettings();
                } else {
                    statusEl.innerHTML = `<span style="color: #ef4444;">✗ ${data.error || 'Connection failed'}</span>`;
                }
            } catch (e) {
                statusEl.innerHTML = `<span style="color: #ef4444;">✗ ${e.message}</span>`;
            } finally {
                btn.disabled = false;
                btn.textContent = 'Test Connection';
            }
        }

        // ==================== Memory Settings ====================

        async function loadMemorySettings() {
            try {
                const res = await fetch(`${BASE_URL}/v1/config/memory`);
                const data = await res.json();

                document.getElementById('settings-memory-enabled').checked = data.memory_enabled !== false;
                document.getElementById('settings-memory-id').value = data.memory_id || '';
                document.getElementById('settings-memory-region').value = data.memory_region || 'us-west-2';

                // Show status
                const statusEl = document.getElementById('memory-connection-status');
                if (data.memory_id && data.memory_enabled) {
                    statusEl.innerHTML = '<span style="color: var(--text-tertiary);">Configured</span>';
                } else if (!data.memory_enabled) {
                    statusEl.innerHTML = '<span style="color: var(--text-tertiary);">Disabled</span>';
                } else {
                    statusEl.innerHTML = '<span style="color: var(--text-tertiary);">Not configured</span>';
                }
            } catch (e) {
                console.log('Failed to load Memory settings:', e);
                document.getElementById('memory-connection-status').innerHTML = '';
            }
        }

        async function saveMemorySettings() {
            const enabled = document.getElementById('settings-memory-enabled').checked;
            const memoryId = document.getElementById('settings-memory-id').value.trim();
            const region = document.getElementById('settings-memory-region').value;

            try {
                await fetch(`${BASE_URL}/v1/config/memory`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        memory_enabled: enabled,
                        memory_id: memoryId,
                        memory_region: region
                    })
                });
                console.log('Memory settings saved');
            } catch (e) {
                console.error('Failed to save Memory settings:', e);
            }
        }

        async function testMemoryConnection() {
            const btn = document.getElementById('test-memory-btn');
            const statusEl = document.getElementById('memory-connection-status');

            btn.disabled = true;
            btn.textContent = 'Testing...';
            statusEl.innerHTML = '';

            // Save settings first
            await saveMemorySettings();

            try {
                const res = await fetch(`${BASE_URL}/v1/config/memory/test`);
                const data = await res.json();

                if (data.success) {
                    statusEl.innerHTML = `<span style="color: #22c55e;">✓ Connected</span>`;
                } else {
                    statusEl.innerHTML = `<span style="color: #ef4444;">✗ ${data.error || 'Connection failed'}</span>`;
                }
            } catch (e) {
                statusEl.innerHTML = `<span style="color: #ef4444;">✗ ${e.message}</span>`;
            } finally {
                btn.disabled = false;
                btn.textContent = 'Test Connection';
            }
        }

        // ==================== Memory Sync Status ====================
        let memorySyncStatusInterval = null;

        async function updateMemorySyncStatus() {
            const iconEl = document.getElementById('sync-icon');
            const textEl = document.getElementById('sync-text');

            console.log('[Memory] Updating sync status, elements:', !!iconEl, !!textEl);

            if (!iconEl || !textEl) {
                console.log('[Memory] Elements not found, skipping');
                return;
            }

            try {
                const res = await fetch(`${BASE_URL}/v1/memory/status`);
                const data = await res.json();
                console.log('[Memory] Status response:', data);

                // Update icon class
                iconEl.className = 'sync-icon';

                switch (data.status) {
                    case 'synced':
                        iconEl.classList.add('synced');
                        textEl.textContent = `Synced: ${data.sessions_synced} sessions`;
                        break;
                    case 'syncing':
                        iconEl.classList.add('syncing');
                        textEl.textContent = `Syncing... (${data.pending} pending)`;
                        break;
                    case 'disabled':
                        iconEl.classList.add('disabled');
                        textEl.textContent = 'Memory: off';
                        break;
                    case 'not_running':
                        iconEl.classList.add('disabled');
                        textEl.textContent = 'Memory: stopped';
                        break;
                    case 'error':
                        iconEl.classList.add('error');
                        textEl.textContent = 'Memory: error';
                        break;
                    default:
                        iconEl.classList.add('disabled');
                        textEl.textContent = 'Memory: --';
                }

                // Add tooltip with details
                document.getElementById('memory-sync-status').title =
                    `AgentCore Memory Sync\n` +
                    `Memory ID: ${data.memory_id || 'N/A'}\n` +
                    `Region: ${data.region || 'N/A'}\n` +
                    `Sessions: ${data.sessions_synced || 0}\n` +
                    `Total Events: ${data.total_events || 0}`;

            } catch (e) {
                console.error('[Memory] Error fetching status:', e);
                iconEl.className = 'sync-icon error';
                textEl.textContent = 'Memory: offline';
            }
        }

        function startMemorySyncStatusUpdates() {
            console.log('[Memory] Starting sync status updates');
            // Update immediately
            updateMemorySyncStatus();
            // Then update every 10 seconds
            if (memorySyncStatusInterval) {
                clearInterval(memorySyncStatusInterval);
            }
            memorySyncStatusInterval = setInterval(updateMemorySyncStatus, 10000);
        }

        // ==================== Skills Management ====================
        async function openSkillsFolder() {
            try {
                // Get skills directory path from backend
                const res = await fetch(`${BASE_URL}/v1/skills/path`);
                const data = await res.json();
                if (data.path) {
                    // Use Electron to open in Finder
                    if (window.electronAPI && window.electronAPI.openPath) {
                        window.electronAPI.openPath(data.path);
                    } else {
                        // Fallback: show path to user
                        alert('Skills directory: ' + data.path);
                    }
                }
            } catch (e) {
                console.error('Failed to open skills folder:', e);
            }
        }

        async function loadSkillsList() {
            const listEl = document.getElementById('skills-list');
            try {
                const res = await fetch(`${BASE_URL}/v1/skills`);
                const data = await res.json();
                const skills = data.skills || [];

                if (skills.length === 0) {
                    listEl.innerHTML = '<div class="settings-list-empty">No skills found in skills/ directory</div>';
                    return;
                }

                listEl.innerHTML = skills.map(skill => `
                    <div class="settings-list-item">
                        <div class="item-icon">
                            <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                                <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
                            </svg>
                        </div>
                        <div class="item-info">
                            <div class="item-name">${skill.name}</div>
                            <div class="item-desc">${skill.description || 'No description'}</div>
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                listEl.innerHTML = '<div class="settings-list-empty">Failed to load skills</div>';
                console.error('Failed to load skills:', e);
            }
        }

        async function reloadSkills() {
            const listEl = document.getElementById('skills-list');
            listEl.innerHTML = '<div class="settings-list-empty">Reloading skills...</div>';
            try {
                await fetch(`${BASE_URL}/v1/skills/reload`, { method: 'POST' });
                await loadSkillsList();
            } catch (e) {
                listEl.innerHTML = '<div class="settings-list-empty">Failed to reload skills</div>';
            }
        }

        // ==================== MCP Servers Management ====================
        async function loadMcpServersList() {
            const listEl = document.getElementById('mcp-servers-list');
            try {
                const res = await fetch(`${BASE_URL}/v1/mcp/servers`);
                const data = await res.json();
                const servers = data.servers || [];  // Now an array

                if (servers.length === 0) {
                    listEl.innerHTML = '<div class="settings-list-empty">No MCP servers configured</div>';
                    return;
                }

                listEl.innerHTML = servers.map(server => {
                    const name = server.name;
                    const isRunning = server.running;
                    const isEnabled = server.enabled !== false;
                    const status = server.status || 'configured';
                    const toolCount = server.tools || 0;
                    const description = server.description || server.command || '';

                    // Status display
                    let statusClass = 'stopped';
                    let statusText = 'Ready';
                    if (!isEnabled) {
                        statusClass = 'disabled';
                        statusText = 'Disabled';
                    } else if (isRunning) {
                        statusClass = 'running';
                        statusText = `Running (${toolCount} tools)`;
                    } else if (status === 'error') {
                        statusClass = 'error';
                        statusText = 'Error';
                    }

                    return `
                        <div class="settings-list-item ${!isEnabled ? 'disabled' : ''}">
                            <div class="item-icon">
                                <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                                    <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                                    <line x1="8" y1="21" x2="16" y2="21"/>
                                    <line x1="12" y1="17" x2="12" y2="21"/>
                                </svg>
                            </div>
                            <div class="item-info">
                                <div class="item-name">${escapeHTML(name)}</div>
                                <div class="item-desc">${escapeHTML(description)}</div>
                            </div>
                            <span class="item-status ${statusClass}">${statusText}</span>
                            <div class="item-actions">
                                <button class="danger" onclick="removeMcpServer('${escapeHTML(name)}')">Remove</button>
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (e) {
                listEl.innerHTML = '<div class="settings-list-empty">Failed to load MCP servers</div>';
                console.error('Failed to load MCP servers:', e);
            }
        }

        function toggleMcpAddForm() {
            const form = document.getElementById('mcp-add-form');
            form.style.display = form.style.display === 'none' ? 'block' : 'none';
            if (form.style.display === 'block') {
                document.getElementById('mcp-server-name').focus();
            }
        }

        async function addMcpServer() {
            const name = document.getElementById('mcp-server-name').value.trim();
            const command = document.getElementById('mcp-server-command').value.trim();
            const argsStr = document.getElementById('mcp-server-args').value.trim();
            const envStr = document.getElementById('mcp-server-env').value.trim();

            if (!name || !command) {
                alert('Please enter server name and command');
                return;
            }

            // Parse args
            const args = argsStr ? argsStr.split(',').map(s => s.trim()) : [];

            // Parse env
            const env = {};
            if (envStr) {
                envStr.split(',').forEach(pair => {
                    const [key, value] = pair.split('=').map(s => s.trim());
                    if (key && value) env[key] = value;
                });
            }

            try {
                const res = await fetch(`${BASE_URL}/v1/mcp/servers`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, command, args, env })
                });
                const data = await res.json();

                if (data.error) {
                    alert('Failed to add server: ' + data.error);
                } else {
                    // Clear form and hide
                    document.getElementById('mcp-server-name').value = '';
                    document.getElementById('mcp-server-command').value = '';
                    document.getElementById('mcp-server-args').value = '';
                    document.getElementById('mcp-server-env').value = '';
                    toggleMcpAddForm();
                    await loadMcpServersList();
                }
            } catch (e) {
                alert('Failed to add server: ' + e.message);
            }
        }

        async function removeMcpServer(name) {
            if (!confirm(`Remove MCP server "${name}"?`)) return;

            try {
                await fetch(`${BASE_URL}/v1/mcp/servers/${name}`, { method: 'DELETE' });
                await loadMcpServersList();
            } catch (e) {
                alert('Failed to remove server: ' + e.message);
            }
        }

        // Theme - always use light
        function setTheme() {
            document.body.setAttribute('data-theme', 'light');
        }

        function toggleSidebar() {
            const sidebar = document.querySelector('.sidebar');
            if (window.innerWidth <= 768) {
                sidebar.classList.toggle('open');
            } else {
                sidebar.classList.toggle('collapsed');
            }
        }

        function showWorkspacesPanel() {
            // Make sure sidebar is visible
            const sidebar = document.querySelector('.sidebar');
            if (sidebar.classList.contains('collapsed')) {
                sidebar.classList.remove('collapsed');
            }
            // Scroll to workspace section if exists
            const workspaceSection = document.querySelector('.working-folders-section');
            if (workspaceSection) {
                workspaceSection.scrollIntoView({ behavior: 'smooth' });
            }
        }

        // Helper
        function setPrompt(text) {
            document.getElementById('message-input').value = text;
            document.getElementById('message-input').focus();
            document.getElementById('send-btn').disabled = false;
        }

        // ========== Right Sidebar Functions (REMOVED - using inline panel) ==========
        // These are kept as no-op stubs for compatibility

        function toggleRightSidebar() {}
        function openRightSidebar() {}
        function hideToolPanel() {}
        function addToolExecution(toolUse) {}
        function updateToolExecution(toolId, result) {}
        function renderToolExecutionSidebar() {}
        function clearToolExecutions() {}

        // Ensure default working folder is in workspace list
        function ensureDefaultFolderInWorkspace() {
            if (!defaultWorkingFolder) return;

            // Check if the default folder (or its expanded version) is already in workspace
            const isInWorkspace = workingFolders.some(f => {
                // Direct match
                if (f === defaultWorkingFolder) return true;
                // Check if one is ~ version and other is expanded
                const fNorm = f.startsWith('~/') ? f : f;
                const defNorm = defaultWorkingFolder.startsWith('~/') ? defaultWorkingFolder : defaultWorkingFolder;
                return fNorm === defNorm;
            });

            if (!isInWorkspace) {
                workingFolders.unshift(defaultWorkingFolder); // Add to beginning
                localStorage.setItem('workingFolders', JSON.stringify(workingFolders));
                console.log('Added default working folder to workspace:', defaultWorkingFolder);
            }
        }

        // ========== Workspace Functions ==========

        function renderWorkingFolders() {
            const list = document.getElementById('working-folders-list');
            let empty = document.getElementById('working-folders-empty');

            // Recreate empty element if it was destroyed
            if (!empty) {
                empty = document.createElement('div');
                empty.className = 'working-folders-empty';
                empty.id = 'working-folders-empty';
                empty.textContent = 'Click + to add folders';
            }

            if (workingFolders.length === 0) {
                empty.style.display = 'block';
                list.innerHTML = '';
                list.appendChild(empty);
                updateWorkingDirDisplay();
                updateWorkdirSelector();
                return;
            }

            empty.style.display = 'none';
            // Build folder items HTML - with drag support for dropping on conversations
            // Get the actual working directory (conversation's workdir takes priority)
            let actualWorkdir = currentWorkingDir;
            if (currentConversationId) {
                const conv = conversations.find(c => c.id === currentConversationId);
                const runtime = convRuntime[currentConversationId];
                const convWorkdir = conv?.workingDir || runtime?.workingDir;
                if (convWorkdir) {
                    actualWorkdir = convWorkdir;
                }
            }
            const foldersHtml = workingFolders.map((folder, index) => {
                const name = folder.split('/').pop() || folder;
                const isActive = folder === actualWorkdir;
                const isDefault = folder === defaultWorkingFolder;
                const isBrowsing = fileBrowserOpen && fileBrowserCurrentPath === folder;
                // Escape folder path for use in HTML attributes
                const escapedFolder = folder.replace(/'/g, "\\'");
                return `
                    <div class="folder-item ${isActive ? 'active' : ''} ${isDefault ? 'default' : ''} ${isBrowsing ? 'browsing' : ''}"
                         draggable="true"
                         ondragstart="handleWorkspaceFolderDragStart(event, '${escapedFolder}')"
                         ondragend="handleWorkspaceFolderDragEnd(event)"
                         onclick="handleFolderClick('${escapedFolder}', event)"
                         ondblclick="openFolderInFinder('${escapedFolder}')">
                        <span class="status-dot"></span>
                        <svg class="folder-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                        </svg>
                        <span class="folder-name" title="${folder}">${name}</span>
                        ${isDefault ? '' : `<button class="remove-folder" onclick="removeWorkingFolder(${index}, event)" title="Remove folder">
                            <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M2 2l8 8M10 2l-8 8"/>
                            </svg>
                        </button>`}
                    </div>
                `;
            }).join('');
            list.innerHTML = foldersHtml;
            updateWorkingDirDisplay();
            updateWorkdirSelector();
        }

        // 选择工作目录
        function selectWorkingDir(folder) {
            currentWorkingDir = folder;
            localStorage.setItem('currentWorkingDir', folder);

            // 同时更新当前会话的工作目录
            if (currentConversationId) {
                const conv = conversations.find(c => c.id === currentConversationId);
                if (conv) {
                    conv.workingDir = folder;
                    // Session saved to backend via SessionAPI
                }
                const runtime = getConvRuntime(currentConversationId);
                if (runtime) {
                    runtime.workingDir = folder;
                }
            }

            renderWorkingFolders();
            updateWorkdirSelector();
            updateWorkingDirDisplay();  // Update path display in status bar
            // 通知后端更新工作目录
            updateServerWorkingDir(folder);
        }

        // 设置默认工作目录（新建会话时自动使用）
        function setDefaultFolder(folder, event) {
            if (event) {
                event.stopPropagation();
            }
            // Toggle: if already default, unset it; otherwise set it
            if (defaultWorkingFolder === folder) {
                defaultWorkingFolder = '';
                localStorage.removeItem('defaultWorkingFolder');
                console.log('Default folder cleared');
            } else {
                defaultWorkingFolder = folder;
                localStorage.setItem('defaultWorkingFolder', folder);
                console.log('Default folder set to:', folder);
            }
            renderWorkingFolders();
        }

        // Browse for default working directory (Settings dialog)
        async function browseDefaultWorkdir() {
            if (window.electronAPI?.selectFolder) {
                const folders = await window.electronAPI.selectFolder();
                if (folders && folders.length > 0) {
                    const folder = folders[0];
                    document.getElementById('settings-default-workdir').value = folder;
                    // Also update the variable and localStorage immediately
                    defaultWorkingFolder = folder;
                    localStorage.setItem('defaultWorkingFolder', folder);
                    console.log('Default working directory selected:', folder);
                    // Add to workspace if not already there
                    ensureDefaultFolderInWorkspace();
                    renderWorkingFolders();
                }
            } else {
                // Fallback: use the text input directly
                alert('Folder selection not available. Please enter the path manually.');
            }
        }

        // 工作目录选择器变更处理
        async function onWorkdirSelectChange(value) {
            if (value === '__add__') {
                // 添加新工作目录
                await addWorkingFolder();
                // Reset selector to current working dir if add was cancelled
                updateWorkdirSelector();
            } else if (value) {
                selectWorkingDir(value);
            }
        }

        // 更新工作目录选择器（状态栏）
        function updateWorkdirSelector() {
            const select = document.getElementById('status-workdir-select');
            if (!select) return;

            // 获取当前应该选中的值（优先使用会话的工作目录）
            let currentValue = currentWorkingDir;
            if (currentConversationId) {
                const conv = conversations.find(c => c.id === currentConversationId);
                const runtime = convRuntime[currentConversationId];
                const convWorkdir = conv?.workingDir || runtime?.workingDir;
                if (convWorkdir) {
                    currentValue = convWorkdir;
                }
            }

            // 清空并重新填充选项
            select.innerHTML = '';

            // 添加 workspace 中的文件夹
            workingFolders.forEach(folder => {
                const option = document.createElement('option');
                option.value = folder;
                const name = folder.split('/').pop() || folder;
                option.textContent = name;
                option.title = folder;
                if (folder === currentValue) {
                    option.selected = true;
                }
                select.appendChild(option);
            });

            // 添加分隔线和"添加"选项
            if (workingFolders.length > 0) {
                const separator = document.createElement('option');
                separator.disabled = true;
                separator.textContent = '──────────';
                select.appendChild(separator);
            }

            const addOpt = document.createElement('option');
            addOpt.value = '__add__';
            addOpt.textContent = '+ Add folder...';
            select.appendChild(addOpt);
        }

        // 更新服务器的工作目录 (with retry for robustness)
        async function updateServerWorkingDir(folder, retries = 3) {
            for (let i = 0; i < retries; i++) {
                try {
                    const response = await fetch(`${BASE_URL}/v1/config/working-dir`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ working_dir: folder })
                    });
                    if (response.ok) {
                        const data = await response.json();
                        console.log('Working directory synced to server:', data.working_dir);
                        return true;
                    } else {
                        console.warn(`Failed to sync working directory (attempt ${i+1}):`, response.status);
                    }
                } catch (e) {
                    console.warn(`Failed to sync working directory (attempt ${i+1}):`, e.message);
                }
                // Wait before retry
                if (i < retries - 1) {
                    await new Promise(r => setTimeout(r, 1000));
                }
            }
            console.error('Failed to sync working directory after', retries, 'attempts');
            return false;
        }

        // 更新状态栏显示当前会话的工作目录
        // 如果传入 workingDir 参数，使用它；否则从当前会话获取
        function updateWorkingDirDisplay(workingDir = null) {
            // 获取当前会话的工作目录
            let displayDir = workingDir;
            if (!displayDir && currentConversationId) {
                const conv = conversations.find(c => c.id === currentConversationId);
                const runtime = getConvRuntime(currentConversationId);
                displayDir = conv?.workingDir || runtime?.workingDir || '';
            }
            // Fallback to global currentWorkingDir if conversation has none
            if (!displayDir && currentWorkingDir) {
                displayDir = currentWorkingDir;
            }

            // 更新状态栏中的路径显示
            const pathDisplay = document.getElementById('workdir-path-display');
            if (pathDisplay) {
                if (displayDir) {
                    pathDisplay.textContent = displayDir;
                    pathDisplay.title = displayDir;
                    pathDisplay.style.display = 'inline';
                    pathDisplay.style.color = '';  // Reset to default color
                } else {
                    pathDisplay.textContent = '(No working directory)';
                    pathDisplay.title = 'Click to select working directory';
                    pathDisplay.style.display = 'inline';
                    pathDisplay.style.color = 'var(--text-tertiary)';
                }
            }

            // 同步到服务器
            if (displayDir) {
                updateServerWorkingDir(displayDir);
            }

            // 同步更新下拉选择器的选中状态
            const select = document.getElementById('status-workdir-select');
            if (select && displayDir) {
                select.value = displayDir;
            }
        }

        async function addWorkingFolder() {
            // Try to use Electron dialog if available
            let newFolder = null;
            if (window.electronAPI?.selectFolder) {
                const folders = await window.electronAPI.selectFolder();
                if (folders && folders.length > 0) {
                    for (const folder of folders) {
                        if (!workingFolders.includes(folder)) {
                            workingFolders.push(folder);
                            newFolder = folder;
                        }
                    }
                    localStorage.setItem('workingFolders', JSON.stringify(workingFolders));
                    renderWorkingFolders();
                    // 自动选中最后添加的目录
                    if (newFolder) {
                        selectWorkingDir(newFolder);
                    }
                }
            } else {
                // Fallback: prompt for path
                const path = prompt('Enter folder path:');
                if (path && path.trim()) {
                    const trimmedPath = path.trim();
                    if (!workingFolders.includes(trimmedPath)) {
                        workingFolders.push(trimmedPath);
                        localStorage.setItem('workingFolders', JSON.stringify(workingFolders));
                        renderWorkingFolders();
                        // 自动选中新添加的目录
                        selectWorkingDir(trimmedPath);
                    }
                }
            }
        }

        function removeWorkingFolder(index, event) {
            event.stopPropagation();
            workingFolders.splice(index, 1);
            localStorage.setItem('workingFolders', JSON.stringify(workingFolders));
            renderWorkingFolders();
        }

        function openFolderInFinder(path) {
            if (window.electronAPI?.openFolder) {
                window.electronAPI.openFolder(path);
            }
        }

        // ==================== File Browser Panel (macOS Finder style) ====================

        let fileBrowserOpen = false;
        let fileBrowserCurrentPath = '';
        let fileBrowserHistory = [];
        let fileBrowserWidth = 380; // Default width

        // File Browser Resize functionality
        function initFileBrowserResize() {
            const panel = document.getElementById('file-browser-panel');
            const handle = document.getElementById('file-browser-resize-handle');

            if (!panel || !handle) return;

            let isResizing = false;
            let startX = 0;
            let startWidth = 0;

            handle.addEventListener('mousedown', (e) => {
                if (!panel.classList.contains('open')) return;

                isResizing = true;
                startX = e.clientX;
                startWidth = panel.offsetWidth;

                panel.classList.add('resizing');
                handle.classList.add('dragging');
                document.body.style.cursor = 'col-resize';
                document.body.style.userSelect = 'none';

                e.preventDefault();
            });

            document.addEventListener('mousemove', (e) => {
                if (!isResizing) return;

                const deltaX = e.clientX - startX;
                const newWidth = Math.max(250, Math.min(600, startWidth + deltaX));

                panel.style.width = newWidth + 'px';
                fileBrowserWidth = newWidth;
            });

            document.addEventListener('mouseup', () => {
                if (!isResizing) return;

                isResizing = false;
                panel.classList.remove('resizing');
                handle.classList.remove('dragging');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            });
        }

        // Initialize resize on page load
        document.addEventListener('DOMContentLoaded', initFileBrowserResize);

        // Handle folder click - only opens file browser for browsing
        // Does NOT change session's working directory
        function handleFolderClick(folder, event) {
            // Prevent double-click from triggering single-click twice
            if (event && event.detail > 1) return;

            // Only browse the folder, do NOT change session's working directory
            // Session's working directory is set only when:
            // 1. Creating new session via right-click on folder
            // 2. Creating new session via "New Chat" button (prompts user)
            // 3. Dropping files on "New Chat" button
            openFileBrowser(folder);
        }

        function openFileBrowser(folderPath) {
            fileBrowserCurrentPath = folderPath;
            fileBrowserHistory = [folderPath];

            // Open the panel with remembered width
            const panel = document.getElementById('file-browser-panel');
            panel.style.width = fileBrowserWidth + 'px';
            panel.classList.add('open');
            fileBrowserOpen = true;

            // Re-render folder list to show browsing state
            renderWorkingFolders();

            // Load folder contents
            loadFolderContents(folderPath);
        }

        function closeFileBrowser() {
            const panel = document.getElementById('file-browser-panel');
            panel.classList.remove('open');
            // Reset inline width for proper closing animation
            panel.style.width = '';
            fileBrowserOpen = false;
            // Re-render folder list to remove browsing state
            renderWorkingFolders();
        }

        function toggleFileBrowser(folderPath) {
            if (fileBrowserOpen && fileBrowserCurrentPath === folderPath) {
                closeFileBrowser();
            } else {
                openFileBrowser(folderPath);
            }
        }

        async function loadFolderContents(folderPath) {
            fileBrowserCurrentPath = folderPath;

            // Update header
            const folderName = folderPath.split('/').pop() || folderPath;
            document.getElementById('file-browser-folder-name').textContent = folderName;

            // Update breadcrumb
            updateBreadcrumb(folderPath);

            // Show loading state
            const content = document.getElementById('file-browser-content');
            content.innerHTML = '<div class="file-browser-empty"><p>Loading...</p></div>';

            try {
                const response = await fetch(`${BASE_URL}/v1/tools/execute`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: 'list_directory',
                        input: { path: folderPath, show_hidden: false }
                    })
                });

                const data = await response.json();
                const result = data.result || data;

                if (result.error) {
                    content.innerHTML = `
                        <div class="file-browser-empty">
                            <svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
                                <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                            </svg>
                            <p>${result.error}</p>
                        </div>
                    `;
                    document.getElementById('file-browser-count').textContent = '0 items';
                    return;
                }

                const entries = result.entries || [];
                document.getElementById('file-browser-count').textContent = `${entries.length} item${entries.length !== 1 ? 's' : ''}`;

                if (entries.length === 0) {
                    content.innerHTML = `
                        <div class="file-browser-empty">
                            <svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
                                <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                            </svg>
                            <p>Empty folder</p>
                        </div>
                    `;
                    return;
                }

                // Render entries
                content.innerHTML = entries.map(entry => {
                    const isDir = entry.type === 'directory';
                    const size = isDir ? '' : formatFileSize(entry.size || 0);
                    const fullPath = `${folderPath}/${entry.name}`.replace(/\/+/g, '/');
                    const escapedPath = fullPath.replace(/'/g, "\\'");

                    return `
                        <div class="file-browser-item ${isDir ? 'is-directory' : ''}"
                             data-path="${fullPath}"
                             data-is-dir="${isDir}"
                             data-name="${entry.name}"
                             draggable="true"
                             onclick="selectFileItem(this, event)"
                             ondblclick="${isDir ? `navigateToFolder('${escapedPath}')` : `openFileWithSystem('${escapedPath}')`}"
                             oncontextmenu="showFileContextMenu(event, '${escapedPath}', ${isDir})"
                             ondragstart="handleFileDragStart(event, this)"
                             ondragend="handleFileDragEnd(event, this)">
                            <svg class="item-icon ${isDir ? 'folder' : 'file'}" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                                ${isDir
                                    ? '<path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>'
                                    : '<path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/>'
                                }
                            </svg>
                            <span class="item-name" title="${entry.name}">${entry.name}</span>
                            <span class="item-info">${size}</span>
                            ${isDir ? `
                                <svg class="item-arrow" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                                    <path d="M9 18l6-6-6-6"/>
                                </svg>
                            ` : ''}
                        </div>
                    `;
                }).join('');

            } catch (error) {
                content.innerHTML = `
                    <div class="file-browser-empty">
                        <svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
                            <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                        </svg>
                        <p>Failed to load: ${error.message}</p>
                    </div>
                `;
            }
        }

        function navigateToFolder(path) {
            fileBrowserHistory.push(path);
            loadFolderContents(path);
        }

        function navigateToBreadcrumb(path) {
            // Find index in history and truncate
            const index = fileBrowserHistory.indexOf(path);
            if (index !== -1) {
                fileBrowserHistory = fileBrowserHistory.slice(0, index + 1);
            }
            loadFolderContents(path);
        }

        function updateBreadcrumb(folderPath) {
            const breadcrumb = document.getElementById('file-browser-breadcrumb');
            const parts = folderPath.split('/').filter(p => p);

            let currentPath = '';
            const items = parts.map((part, index) => {
                currentPath += '/' + part;
                const isLast = index === parts.length - 1;
                return `
                    <span class="breadcrumb-item ${isLast ? 'current' : ''}"
                          onclick="${isLast ? '' : `navigateToBreadcrumb('${currentPath}')`}">
                        ${part}
                    </span>
                    ${isLast ? '' : '<span class="breadcrumb-separator">/</span>'}
                `;
            });

            breadcrumb.innerHTML = items.join('');
        }

        function refreshFileBrowser() {
            if (fileBrowserCurrentPath) {
                loadFolderContents(fileBrowserCurrentPath);
            }
        }

        function openCurrentFolderInFinder() {
            if (fileBrowserCurrentPath) {
                openFolderInFinder(fileBrowserCurrentPath);
            }
        }

        function openFileInEditor(path) {
            // Set the prompt to ask Claude to read the file
            const fileName = path.split('/').pop();
            setPrompt(`请读取并分析这个文件: ${path}`);
        }

        // ==================== File Browser Click & Context Menu ====================

        // Multi-select support
        let selectedFiles = []; // Array of {path, isDir, name}

        function selectFileItem(element, event) {
            const path = element.dataset.path;
            const isDir = element.dataset.isDir === 'true';
            const name = element.querySelector('.item-name')?.textContent || path.split('/').pop();

            // Check for multi-select (Cmd/Ctrl + click)
            const isMultiSelect = event && (event.metaKey || event.ctrlKey);

            if (isMultiSelect) {
                // Toggle selection
                const existingIndex = selectedFiles.findIndex(f => f.path === path);
                if (existingIndex >= 0) {
                    selectedFiles.splice(existingIndex, 1);
                    element.classList.remove('selected');
                } else {
                    selectedFiles.push({ path, isDir, name });
                    element.classList.add('selected');
                }
            } else {
                // Single select - clear others
                document.querySelectorAll('.file-browser-item.selected').forEach(el => {
                    el.classList.remove('selected');
                });
                selectedFiles = [{ path, isDir, name }];
                element.classList.add('selected');
            }
        }

        function openFileWithSystem(path) {
            // Use Electron shell to open file/folder with system default application
            if (window.electronAPI?.openPath) {
                window.electronAPI.openPath(path).then(error => {
                    if (error) {
                        console.error('Failed to open:', error);
                    }
                });
            } else {
                console.warn('electronAPI.openPath not available');
            }
        }

        function showFileContextMenu(event, path, isDir) {
            event.preventDefault();
            event.stopPropagation();

            const item = event.currentTarget;
            const name = item.querySelector('.item-name')?.textContent || path.split('/').pop();

            // If right-clicked item is not in selection, make it the only selection
            const isInSelection = selectedFiles.some(f => f.path === path);
            if (!isInSelection) {
                document.querySelectorAll('.file-browser-item.selected').forEach(el => {
                    el.classList.remove('selected');
                });
                selectedFiles = [{ path, isDir, name }];
                item.classList.add('selected');
            }

            // Update file count header
            const countHeader = document.getElementById('context-menu-file-count');
            const fileCount = selectedFiles.length;
            countHeader.textContent = fileCount === 1
                ? `${selectedFiles[0].name}`
                : `${fileCount} files selected`;

            // Populate chat list from conversations array
            const chatSection = document.getElementById('context-menu-chats');
            const totalCount = conversations.length;

            if (!conversations || totalCount === 0) {
                chatSection.innerHTML = '<div class="file-context-menu-item" style="color: var(--text-tertiary); cursor: default;">No existing chats</div>';
            } else {
                chatSection.innerHTML = conversations.slice(0, 10).map((conv, index) => {
                    const convId = conv.id;
                    let title = conv.title || 'Untitled Chat';
                    if (title.length > 25) {
                        title = title.substring(0, 25) + '...';
                    }
                    const isCurrent = convId === currentConversationId;
                    const sessionNumber = totalCount - index;  // Newest first, reverse numbering
                    return `
                        <div class="file-context-menu-item" onclick="contextMenuAddToChat('${convId}')">
                            <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                            </svg>
                            <span class="context-menu-session-number">#${sessionNumber}</span>
                            <span class="chat-title">${isCurrent ? '● ' : ''}${title}</span>
                        </div>
                    `;
                }).join('');
            }

            // Position and show menu
            const menu = document.getElementById('file-context-menu');
            const menuWidth = 220;
            const menuHeight = 300;

            let x = event.clientX;
            let y = event.clientY;

            // Adjust if menu would go off screen
            if (x + menuWidth > window.innerWidth) {
                x = window.innerWidth - menuWidth - 10;
            }
            if (y + menuHeight > window.innerHeight) {
                y = window.innerHeight - menuHeight - 10;
            }

            menu.style.left = x + 'px';
            menu.style.top = y + 'px';
            menu.classList.add('show');

            // Close menu when clicking outside
            setTimeout(() => {
                document.addEventListener('click', handleContextMenuOutsideClick, { once: true });
            }, 0);
        }

        function handleContextMenuOutsideClick(e) {
            const menu = document.getElementById('file-context-menu');
            // If click is inside menu, don't close it yet - let the item's onclick run first
            if (menu.contains(e.target)) {
                // Re-add listener to close on next outside click
                setTimeout(() => {
                    document.addEventListener('click', handleContextMenuOutsideClick, { once: true });
                }, 0);
                return;
            }
            hideFileContextMenu();
        }

        function hideFileContextMenu() {
            document.getElementById('file-context-menu').classList.remove('show');
        }

        // Generate file reference prompt for selected files
        function generateFilePrompt() {
            if (selectedFiles.length === 0) return '';

            if (selectedFiles.length === 1) {
                const file = selectedFiles[0];
                if (file.isDir) {
                    return `请列出并分析这个目录的内容: ${file.path}`;
                } else {
                    return `请读取并分析这个文件: ${file.path}`;
                }
            } else {
                // Multiple files
                const filePaths = selectedFiles.map(f => f.path).join('\n- ');
                return `请读取并分析以下 ${selectedFiles.length} 个文件:\n- ${filePaths}`;
            }
        }

        // Add selected files from file browser to attachments
        function addSelectedFilesToAttachments() {
            if (selectedFiles.length === 0) return;

            for (const file of selectedFiles) {
                // Check if already attached
                const alreadyAttached = attachments.some(a => a.path === file.path);
                if (alreadyAttached) continue;

                // Get file name from path if not provided
                const fileName = file.name || file.path.split('/').pop();

                // Determine file type from extension
                const ext = fileName.split('.').pop().toLowerCase();
                const typeMap = {
                    'txt': 'text/plain',
                    'md': 'text/markdown',
                    'json': 'application/json',
                    'csv': 'text/csv',
                    'py': 'text/x-python',
                    'js': 'text/javascript',
                    'ts': 'text/typescript',
                    'html': 'text/html',
                    'css': 'text/css',
                    'xml': 'text/xml',
                    'yaml': 'text/yaml',
                    'yml': 'text/yaml'
                };
                const mimeType = file.isDir ? 'inode/directory' : (typeMap[ext] || 'application/octet-stream');

                attachments.push({
                    name: file.isDir ? `📁 ${fileName}` : `@ ${fileName}`,
                    type: mimeType,
                    path: file.path,
                    data: null,
                    isContextFile: true  // Mark as context file from file browser
                });
            }

            renderAttachments();
            document.getElementById('send-btn').disabled = false;

            // Clear selection
            selectedFiles = [];
            document.querySelectorAll('.file-browser-item.selected').forEach(el => {
                el.classList.remove('selected');
            });
        }

        async function contextMenuNewChat() {
            hideFileContextMenu();
            // Capture selected files first (before they might be cleared)
            const filesToAdd = [...selectedFiles];

            // Determine working directory:
            // - If a folder is selected, use it
            // - If files are selected, use the current browse path
            // - Fall back to file browser current path
            let workingDir = fileBrowserCurrentPath || '';
            const selectedFolder = filesToAdd.find(f => f.isDir);
            if (selectedFolder) {
                workingDir = selectedFolder.path;
            }

            // Create new conversation with the working directory (don't prompt)
            await newConversation(workingDir, false);

            // Restore selected files and add as attachments
            selectedFiles = filesToAdd;
            addSelectedFilesToAttachments();
            // Auto-focus on input
            document.getElementById('message-input')?.focus();
        }

        function contextMenuAddToChat(convId) {
            hideFileContextMenu();
            // Capture selected files first (before they might be cleared)
            const filesToAdd = [...selectedFiles];

            // Switch to that conversation
            if (convId !== currentConversationId) {
                loadConversation(convId);
                // Clear attachments from previous conversation - start fresh
                attachments = [];
                renderAttachments();
            }

            // Set selected files to ONLY the files we want to add (not any previous selection)
            selectedFiles = filesToAdd;
            addSelectedFilesToAttachments();
            // Auto-focus on input
            document.getElementById('message-input')?.focus();
        }

        // ========== Drag and Drop for File Browser ==========

        // Store dragged files data
        let draggedFiles = [];

        // Workspace folder drag handlers (for dragging folders from sidebar to conversations)
        function handleWorkspaceFolderDragStart(event, folderPath) {
            const name = folderPath.split('/').pop() || folderPath;
            draggedFiles = [{ path: folderPath, isDir: true, name: name }];

            // Set drag data
            event.dataTransfer.setData('text/plain', JSON.stringify(draggedFiles));
            event.dataTransfer.effectAllowed = 'copy';

            // Add dragging class
            event.target.classList.add('dragging');
        }

        function handleWorkspaceFolderDragEnd(event) {
            event.target.classList.remove('dragging');
            draggedFiles = [];
        }

        function handleFileDragStart(event, element) {
            // Get all selected files, or just the dragged one if not selected
            const path = element.dataset.path;
            const isDir = element.dataset.isDir === 'true';
            const name = element.dataset.name;

            // If the dragged item is selected, drag all selected files
            if (selectedFiles.some(f => f.path === path)) {
                draggedFiles = [...selectedFiles];
            } else {
                // Otherwise just drag this single file
                draggedFiles = [{ path, isDir, name }];
            }

            // Set drag data
            event.dataTransfer.setData('text/plain', JSON.stringify(draggedFiles));
            event.dataTransfer.effectAllowed = 'copy';

            // Add dragging class
            element.classList.add('dragging');
        }

        function handleFileDragEnd(event, element) {
            element.classList.remove('dragging');
            draggedFiles = [];
        }

        // Conversation item drop handlers
        function handleConvDragOver(event) {
            event.preventDefault();
            event.dataTransfer.dropEffect = 'copy';
            event.currentTarget.classList.add('drag-over');
        }

        function handleConvDragLeave(event) {
            event.currentTarget.classList.remove('drag-over');
        }

        function handleConvDrop(event, convId) {
            event.preventDefault();
            event.currentTarget.classList.remove('drag-over');

            // Get dragged files
            const data = event.dataTransfer.getData('text/plain');
            if (!data) return;

            try {
                const files = JSON.parse(data);
                if (files.length === 0) return;

                // Switch to that conversation
                if (convId !== currentConversationId) {
                    loadConversation(convId);
                    // Clear attachments from previous conversation - start fresh
                    attachments = [];
                    renderAttachments();
                }

                // Add files to attachments
                selectedFiles = files;
                addSelectedFilesToAttachments();

                // Focus input
                document.getElementById('message-input')?.focus();
            } catch (e) {
                console.error('Failed to parse dragged files:', e);
            }
        }

        // New Chat button drop handlers
        function handleNewChatDragOver(event) {
            event.preventDefault();
            event.dataTransfer.dropEffect = 'copy';
            event.currentTarget.classList.add('drag-over');
        }

        function handleNewChatDragLeave(event) {
            event.currentTarget.classList.remove('drag-over');
        }

        async function handleNewChatDrop(event) {
            event.preventDefault();
            event.currentTarget.classList.remove('drag-over');

            // Get dragged files
            const data = event.dataTransfer.getData('text/plain');
            if (!data) return;

            try {
                const files = JSON.parse(data);
                if (files.length === 0) return;

                // Determine working directory from dropped files
                let workingDir = fileBrowserCurrentPath || '';
                const droppedFolder = files.find(f => f.isDir);
                if (droppedFolder) {
                    workingDir = droppedFolder.path;
                }

                // Create new conversation with working directory (don't prompt)
                await newConversation(workingDir, false);

                // Add files to attachments
                selectedFiles = files;
                addSelectedFilesToAttachments();

                // Focus input
                document.getElementById('message-input')?.focus();
            } catch (e) {
                console.error('Failed to parse dragged files:', e);
            }
        }

        // Input area drop handlers (for current conversation)
        function handleInputDragOver(event) {
            event.preventDefault();
            event.dataTransfer.dropEffect = 'copy';
            event.currentTarget.classList.add('drag-over');
        }

        function handleInputDragLeave(event) {
            event.currentTarget.classList.remove('drag-over');
        }

        function handleInputDrop(event) {
            event.preventDefault();
            event.currentTarget.classList.remove('drag-over');

            // Get dragged files
            const data = event.dataTransfer.getData('text/plain');
            if (!data) return;

            try {
                const files = JSON.parse(data);
                if (files.length === 0) return;

                // Add files to attachments in current conversation
                selectedFiles = files;
                addSelectedFilesToAttachments();

                // Focus input
                document.getElementById('message-input')?.focus();
            } catch (e) {
                console.error('Failed to parse dragged files:', e);
            }
        }

        function formatFileSize(bytes) {
            if (bytes === 0) return '';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }

        // Get working folders for API context
        function getWorkingFoldersContext() {
            if (workingFolders.length === 0) return '';
            return `\n\nWorking folders: ${workingFolders.join(', ')}`;
        }

        // ========== Projects Functions ==========

        // ==================== Claude Code Pattern: Todo Panel ====================

        // Panel dragging state
        let todoPanelDragging = false;
        let todoPanelOffsetX = 0;
        let todoPanelOffsetY = 0;

        function updateTodoPanel(todos) {
            // Hide floating panel - we use inline tasks now
            const panel = document.getElementById('todo-panel');
            panel.classList.remove('visible');

            // Store todos in current conversation's runtime
            if (currentConversationId) {
                const runtime = getConvRuntime(currentConversationId);
                runtime.todos = todos || [];

                // Also persist to conversation object for page refresh
                const conv = conversations.find(c => c.id === currentConversationId);
                if (conv) {
                    conv.todos = todos || [];
                    // Session saved to backend via SessionAPI
                }
            }

            // Update inline tasks in chat
            updateInlineTasks(todos);
        }

        function updateInlineTasks(todos) {
            const chatContent = document.getElementById('chat-content');
            if (!chatContent) return;

            // Find or create inline tasks container
            let inlineTasks = document.getElementById('inline-tasks');

            if (!todos || todos.length === 0) {
                // Remove inline tasks if no todos
                if (inlineTasks) {
                    inlineTasks.remove();
                }
                return;
            }

            // Generate tasks HTML
            const completed = todos.filter(t => t.status === 'completed').length;
            const tasksHtml = todos.map(todo => {
                const icon = todo.status === 'completed' ? '✅' :
                            todo.status === 'in_progress' ? '🔄' : '○';
                const text = todo.status === 'in_progress' ? todo.activeForm : todo.content;
                return `
                    <div class="todo-item ${todo.status}">
                        <span class="todo-icon">${icon}</span>
                        <span class="todo-text">${text}</span>
                    </div>
                `;
            }).join('');

            const fullHtml = `
                <div class="inline-tasks-header">
                    <h4>📋 Tasks</h4>
                    <span class="inline-tasks-progress">${completed}/${todos.length}</span>
                </div>
                <div class="inline-tasks-list">${tasksHtml}</div>
            `;

            if (!inlineTasks) {
                // Create new inline tasks container
                inlineTasks = document.createElement('div');
                inlineTasks.id = 'inline-tasks';
                inlineTasks.className = 'inline-tasks';
                chatContent.appendChild(inlineTasks);
            }

            inlineTasks.innerHTML = fullHtml;
            scrollToBottom();
        }

        function hideTodoPanel() {
            document.getElementById('todo-panel').classList.remove('visible');
            // Also remove inline tasks
            const inlineTasks = document.getElementById('inline-tasks');
            if (inlineTasks) {
                inlineTasks.remove();
            }
        }

        // Initialize todo panel dragging
        function initTodoPanelDrag() {
            const panel = document.getElementById('todo-panel');
            const header = panel.querySelector('.todo-panel-header');

            header.addEventListener('mousedown', (e) => {
                todoPanelDragging = true;
                const rect = panel.getBoundingClientRect();
                todoPanelOffsetX = e.clientX - rect.left;
                todoPanelOffsetY = e.clientY - rect.top;
                panel.style.transition = 'none';
            });

            document.addEventListener('mousemove', (e) => {
                if (!todoPanelDragging) return;

                const newX = e.clientX - todoPanelOffsetX;
                const newY = e.clientY - todoPanelOffsetY;

                // Keep panel within viewport
                const maxX = window.innerWidth - panel.offsetWidth;
                const maxY = window.innerHeight - panel.offsetHeight;

                panel.style.left = Math.max(0, Math.min(newX, maxX)) + 'px';
                panel.style.top = Math.max(0, Math.min(newY, maxY)) + 'px';
                panel.style.right = 'auto';
            });

            document.addEventListener('mouseup', () => {
                if (todoPanelDragging) {
                    todoPanelDragging = false;
                    panel.style.transition = '';
                }
            });
        }

        // ==================== Claude Code Pattern: Ask User Dialog ====================

        let pendingUserAnswer = null;
        let askUserResolve = null;

        function showAskUserDialog(question, options, allowCustom = true) {
            const modal = document.getElementById('ask-user-modal');
            const questionEl = document.getElementById('ask-user-question');
            const optionsEl = document.getElementById('ask-user-options');
            const customEl = document.getElementById('ask-user-custom');
            const inputEl = document.getElementById('ask-user-input');

            questionEl.textContent = question;

            optionsEl.innerHTML = options.map(opt => `
                <button class="ask-user-option" onclick="selectUserOption('${opt.label.replace(/'/g, "\\'")}')">
                    <div class="option-label">${opt.label}</div>
                    ${opt.description ? `<div class="option-desc">${opt.description}</div>` : ''}
                </button>
            `).join('');

            customEl.style.display = allowCustom ? 'block' : 'none';
            inputEl.value = '';

            modal.classList.add('active');

            // Handle Enter key in custom input
            inputEl.onkeydown = (e) => {
                if (e.key === 'Enter' && inputEl.value.trim()) {
                    selectUserOption(inputEl.value.trim());
                }
            };

            return new Promise(resolve => {
                askUserResolve = resolve;
            });
        }

        function selectUserOption(answer) {
            const modal = document.getElementById('ask-user-modal');
            modal.classList.remove('active');

            if (askUserResolve) {
                askUserResolve(answer);
                askUserResolve = null;
            }

            // Send the answer back as a user message
            pendingUserAnswer = answer;
            const input = document.getElementById('message-input');
            input.value = answer;
            sendMessage();
        }

        function hideAskUserDialog() {
            document.getElementById('ask-user-modal').classList.remove('active');
        }

        // ==================== Claude Code Pattern: Plan Mode ====================

        let planModeActive = false;
        let pendingPlanData = null;

        function showPlanModeIndicator() {
            planModeActive = true;
            document.getElementById('plan-mode-indicator').classList.add('visible');
        }

        function hidePlanModeIndicator() {
            planModeActive = false;
            document.getElementById('plan-mode-indicator').classList.remove('visible');
        }

        function showPlanApprovalDialog(plan) {
            pendingPlanData = plan;
            const modal = document.getElementById('plan-approval-modal');
            const summaryEl = document.getElementById('plan-summary');
            const stepsEl = document.getElementById('plan-steps');
            const filesEl = document.getElementById('plan-files');

            summaryEl.textContent = plan.summary;

            if (plan.steps && plan.steps.length > 0) {
                stepsEl.innerHTML = '<h4>Steps</h4>' + plan.steps.map((step, i) => `
                    <div class="plan-step">
                        <span class="step-num">${i + 1}</span>
                        <span class="step-text">${step}</span>
                    </div>
                `).join('');
                stepsEl.style.display = 'block';
            } else {
                stepsEl.style.display = 'none';
            }

            if (plan.files_to_modify && plan.files_to_modify.length > 0) {
                filesEl.innerHTML = '<h4>Files to modify</h4><ul>' +
                    plan.files_to_modify.map(f => `<li>📄 ${f}</li>`).join('') +
                    '</ul>';
                filesEl.style.display = 'block';
            } else {
                filesEl.style.display = 'none';
            }

            modal.classList.add('active');
        }

        function hidePlanApprovalDialog() {
            document.getElementById('plan-approval-modal').classList.remove('active');
            pendingPlanData = null;
        }

        async function approvePlan() {
            hidePlanApprovalDialog();
            hidePlanModeIndicator();

            // Send approval message
            const input = document.getElementById('message-input');
            input.value = "Approved. Please proceed with the implementation.";
            sendMessage();
        }

        function rejectPlan() {
            hidePlanApprovalDialog();
            hidePlanModeIndicator();

            // Send rejection message
            const input = document.getElementById('message-input');
            input.value = "I'd like to modify the plan. Let's discuss alternatives.";
            sendMessage();
        }

        // ==================== Claude Code Pattern: Context Summary ====================

        function showContextIndicator(text = 'Context summarized') {
            const indicator = document.getElementById('context-indicator');
            document.getElementById('context-indicator-text').textContent = text;
            indicator.classList.add('visible');

            // Auto-hide after 5 seconds
            setTimeout(() => {
                indicator.classList.remove('visible');
            }, 5000);
        }

        function hideContextIndicator() {
            document.getElementById('context-indicator').classList.remove('visible');
        }

        // ==================== Cross-Session Task Delegation ====================

        // Find conversation by session number
        function findConversationBySessionNumber(sessionNumber) {
            const totalCount = conversations.length;
            for (let i = 0; i < conversations.length; i++) {
                const convSessionNum = totalCount - i;
                if (convSessionNum === sessionNumber) {
                    return conversations[i];
                }
            }
            return null;
        }

        // Get session number for a conversation
        function getSessionNumberForConv(convId) {
            const totalCount = conversations.length;
            const index = conversations.findIndex(c => c.id === convId);
            if (index === -1) return -1;
            return totalCount - index;
        }

        // Create a new session for delegation (without switching to it)
        function createDelegationSession(workingDir, sessionName) {
            const newConvId = Date.now().toString();

            // Initialize runtime state
            convRuntime[newConvId] = {
                isStreaming: false,
                attachments: [],
                messages: [],
                workingDir: workingDir || '',
                delegatedTasks: {},
                incomingTasks: {},
                delegationQueue: []
            };

            // Add to conversations list
            conversations.unshift({
                id: newConvId,
                title: sessionName || 'Delegated Task',
                messages: [],
                workingDir: workingDir || '',
                createdAt: Date.now()
            });

            // Don't switch to it, just update the list
            renderConversations();
            saveConversation(newConvId);

            return newConvId;
        }

        // Handle subagent task from task tool (synchronous - waits for completion like Claude Code)
        async function handleBackgroundTask(sourceConvId, taskResult) {
            const { task_id, description, prompt, session_name } = taskResult;

            try {
                // Get source session info
                const sourceRuntime = getConvRuntime(sourceConvId);

                // Inherit working directory from source session
                const workDir = sourceRuntime.workingDir || '';
                const convName = session_name || `Subagent: ${description.substring(0, 25)}...`;

                // Create new session for the subagent
                const targetConvId = createDelegationSession(workDir, convName);
                const targetSessionNumber = conversations.length;

                console.log(`[Subagent] Starting task ${task_id} in Session #${targetSessionNumber}`);

                // Execute subagent and WAIT for completion (synchronous like Claude Code)
                const result = await executeSubagentTask(targetConvId, prompt, task_id, description);

                // Return result directly as tool_result (Claude Code subagent format)
                return result;

            } catch (error) {
                console.error(`[Subagent] Error:`, error);
                return formatSubagentError(task_id, description, error.message);
            }
        }

        // Execute subagent task synchronously and return result
        async function executeSubagentTask(targetConvId, prompt, taskId, description) {
            const targetRuntime = getConvRuntime(targetConvId);
            const targetSessionNum = getSessionNumberForConv(targetConvId);

            try {
                // Add the task as a user message in subagent session
                targetRuntime.messages.push({
                    role: 'user',
                    content: prompt
                });

                // Set streaming flag
                targetRuntime.isStreaming = true;
                updateConversationStatus(targetConvId, 'active');
                renderConversations();

                // Execute the conversation and WAIT for completion
                await continueConversation(targetConvId);

                // Collect subagent response
                const assistantMessages = targetRuntime.messages
                    .filter(m => m.role === 'assistant' && !m.isThinking);

                // Get the final response content
                let responseContent = '';
                if (assistantMessages.length > 0) {
                    const lastMsg = assistantMessages[assistantMessages.length - 1];
                    responseContent = typeof lastMsg.content === 'string'
                        ? lastMsg.content
                        : (lastMsg.displayContent || JSON.stringify(lastMsg.content));
                }

                console.log(`[Subagent] Task ${taskId} completed in Session #${targetSessionNum}`);

                // Return in Claude Code subagent format
                return formatSubagentResult(taskId, description, targetSessionNum, responseContent);

            } catch (error) {
                console.error(`[Subagent] Error executing task ${taskId}:`, error);
                return formatSubagentError(taskId, description, error.message);

            } finally {
                targetRuntime.isStreaming = false;
                updateConversationStatus(targetConvId, 'idle');
                renderConversations();
            }
        }

        // Format subagent result like Claude Code
        function formatSubagentResult(taskId, description, sessionNum, content) {
            return {
                type: "subagent_result",
                task_id: taskId,
                status: "completed",
                result: `<subagent_result>
<task_description>${description}</task_description>
<session>#${sessionNum}</session>
<status>completed</status>
<output>
${content || 'Task completed successfully.'}
</output>
</subagent_result>`
            };
        }

        // Format subagent error like Claude Code
        function formatSubagentError(taskId, description, errorMsg) {
            return {
                type: "subagent_result",
                task_id: taskId,
                status: "error",
                result: `<subagent_result>
<task_description>${description}</task_description>
<status>error</status>
<error>${errorMsg}</error>
</subagent_result>`
            };
        }

        // Handle delegation request from delegate_task tool
        async function handleDelegation(sourceConvId, delegationResult) {
            const { task_id, task, wait_for_result, create_new_session, working_directory, session_name, session_number } = delegationResult;

            let targetConvId;
            let targetSessionNumber;
            let targetTitle;

            if (create_new_session) {
                // Create a new session for this task
                const sourceRuntime = getConvRuntime(sourceConvId);
                // Inherit working directory from source if not specified
                const workDir = working_directory || sourceRuntime.workingDir || '';
                const convName = session_name || `Delegated: ${task.substring(0, 30)}...`;

                targetConvId = createDelegationSession(workDir, convName);
                targetSessionNumber = conversations.length; // New session is at the top
                targetTitle = convName;

                console.log(`[Delegation] Created new session #${targetSessionNumber} with workingDir: ${workDir}`);
            } else {
                // Find existing target conversation
                const targetConv = findConversationBySessionNumber(session_number);
                if (!targetConv) {
                    return {
                        success: false,
                        error: `Session #${session_number} not found`,
                        task_id
                    };
                }

                // Prevent self-delegation
                if (targetConv.id === sourceConvId) {
                    return {
                        success: false,
                        error: `Cannot delegate to the same session`,
                        task_id
                    };
                }

                targetConvId = targetConv.id;
                targetSessionNumber = session_number;
                targetTitle = targetConv.title || `Session #${session_number}`;
            }

            // Get/init target runtime
            const targetRuntime = getConvRuntime(targetConvId);
            if (!targetRuntime.delegatedTasks) targetRuntime.delegatedTasks = {};
            if (!targetRuntime.incomingTasks) targetRuntime.incomingTasks = {};
            if (!targetRuntime.delegationQueue) targetRuntime.delegationQueue = [];

            // Check for circular delegation
            if (targetRuntime.incomingTasks[task_id]) {
                return {
                    success: false,
                    error: `Circular delegation detected`,
                    task_id
                };
            }

            // Record delegation in source conversation
            const sourceRuntime = getConvRuntime(sourceConvId);
            if (!sourceRuntime.delegatedTasks) sourceRuntime.delegatedTasks = {};
            if (!sourceRuntime.incomingTasks) sourceRuntime.incomingTasks = {};
            if (!sourceRuntime.delegationQueue) sourceRuntime.delegationQueue = [];

            const sourceSessionNumber = getSessionNumberForConv(sourceConvId);
            sourceRuntime.delegatedTasks[task_id] = {
                taskId: task_id,
                targetConvId: targetConvId,
                targetSessionNumber: targetSessionNumber,
                prompt: task,
                status: 'pending',
                result: null,
                createdAt: Date.now(),
                isNewSession: create_new_session || false
            };

            // Record incoming task in target conversation
            targetRuntime.incomingTasks[task_id] = {
                taskId: task_id,
                sourceConvId: sourceConvId,
                sourceSessionNumber: sourceSessionNumber,
                prompt: task,
                status: 'pending'
            };

            // Update UI to show delegation indicators
            renderConversations();

            // Execute in target session (async)
            executeInSession(targetConvId, task, task_id, sourceConvId);

            // Return result
            const message = create_new_session
                ? `Created new Session #${targetSessionNumber} and delegating task. You will be notified when it completes.`
                : `Task delegated to Session #${targetSessionNumber}. You will be notified when it completes.`;

            return {
                success: true,
                task_id,
                status: 'delegating',
                target_session: targetSessionNumber,
                target_title: targetTitle,
                is_new_session: create_new_session || false,
                message
            };
        }

        // Execute a delegated task in target session
        async function executeInSession(targetConvId, task, taskId, sourceConvId) {
            const targetRuntime = getConvRuntime(targetConvId);
            const sourceRuntime = getConvRuntime(sourceConvId);

            // Update status
            if (targetRuntime.incomingTasks[taskId]) {
                targetRuntime.incomingTasks[taskId].status = 'executing';
            }
            if (sourceRuntime.delegatedTasks[taskId]) {
                sourceRuntime.delegatedTasks[taskId].status = 'executing';
            }
            renderConversations();

            // If target is busy, queue the task
            if (targetRuntime.isStreaming) {
                console.log(`[Delegation] Session ${targetConvId} is busy, queueing task ${taskId}`);
                targetRuntime.delegationQueue.push({ taskId, task, sourceConvId });

                // Listen for when streaming completes
                const checkAndExecute = () => {
                    if (!targetRuntime.isStreaming && targetRuntime.delegationQueue.length > 0) {
                        const nextTask = targetRuntime.delegationQueue.shift();
                        executeInSession(targetConvId, nextTask.task, nextTask.taskId, nextTask.sourceConvId);
                    }
                };
                // Check periodically
                const intervalId = setInterval(() => {
                    if (!targetRuntime.isStreaming) {
                        clearInterval(intervalId);
                        checkAndExecute();
                    }
                }, 500);
                return;
            }

            try {
                // Add the delegated task as a user message in target conversation
                const sourceSessionNum = getSessionNumberForConv(sourceConvId);
                const delegatedPrompt = `[Delegated from Session #${sourceSessionNum}]\n\n${task}`;

                targetRuntime.messages.push({
                    role: 'user',
                    content: delegatedPrompt,
                    isDelegated: true,
                    delegationTaskId: taskId,
                    delegationSourceConvId: sourceConvId
                });

                // If we're viewing the target conversation, render the new message
                if (currentConversationId === targetConvId) {
                    renderMessages();
                }

                // Set streaming flag
                targetRuntime.isStreaming = true;
                updateConversationStatus(targetConvId, 'active');

                // Execute the conversation
                await continueConversation(targetConvId);

                // Task completed successfully
                console.log(`[Delegation] Task ${taskId} execution completed in session ${targetConvId}`);

                if (targetRuntime.incomingTasks[taskId]) {
                    targetRuntime.incomingTasks[taskId].status = 'completed';
                }
                if (sourceRuntime.delegatedTasks[taskId]) {
                    sourceRuntime.delegatedTasks[taskId].status = 'completed';

                    // Get result summary (last assistant message)
                    const assistantMsgs = targetRuntime.messages.filter(m => m.role === 'assistant' && !m.isThinking);
                    console.log(`[Delegation] Task ${taskId}: found ${assistantMsgs.length} assistant messages in target`);

                    const lastAssistantMsg = assistantMsgs.pop();
                    if (lastAssistantMsg) {
                        const content = typeof lastAssistantMsg.content === 'string'
                            ? lastAssistantMsg.content
                            : JSON.stringify(lastAssistantMsg.content);
                        sourceRuntime.delegatedTasks[taskId].result = content.substring(0, 500);
                        console.log(`[Delegation] Task ${taskId}: captured result (${content.length} chars)`);
                    } else {
                        console.warn(`[Delegation] Task ${taskId}: no assistant message found`);
                    }
                } else {
                    console.warn(`[Delegation] Task ${taskId}: not found in sourceRuntime.delegatedTasks`);
                }

                // Notify source session
                console.log(`[Delegation] Emitting delegation_complete for task ${taskId}`);
                crossSessionEvents.emit('delegation_complete', {
                    taskId,
                    sourceConvId,
                    targetConvId,
                    status: 'completed'
                });

            } catch (error) {
                console.error(`[Delegation] Error executing task ${taskId}:`, error);

                // Update status to failed
                if (targetRuntime.incomingTasks[taskId]) {
                    targetRuntime.incomingTasks[taskId].status = 'failed';
                }
                if (sourceRuntime.delegatedTasks[taskId]) {
                    sourceRuntime.delegatedTasks[taskId].status = 'failed';
                    sourceRuntime.delegatedTasks[taskId].result = error.message;
                }

                crossSessionEvents.emit('delegation_complete', {
                    taskId,
                    sourceConvId,
                    targetConvId,
                    status: 'failed',
                    error: error.message
                });
            } finally {
                targetRuntime.isStreaming = false;
                updateConversationStatus(targetConvId, 'idle');
                renderConversations();
            }
        }

        // Listen for delegation completion to notify source session
        crossSessionEvents.on('delegation_complete', (data) => {
            const { taskId, sourceConvId, targetConvId, status, error } = data;
            const targetSessionNum = getSessionNumberForConv(targetConvId);
            const sourceRuntime = getConvRuntime(sourceConvId);

            console.log(`[Delegation] Complete event received: taskId=${taskId}, targetSession=#${targetSessionNum}, status=${status}`);

            const task = sourceRuntime.delegatedTasks?.[taskId];
            if (!task) {
                console.warn(`[Delegation] Task ${taskId} not found in delegatedTasks`);
                return;
            }

            // Check if result message already exists (avoid duplicates)
            const alreadyExists = sourceRuntime.messages.some(m =>
                m.isDelegationResult && m.delegationTaskId === taskId
            );
            if (alreadyExists) {
                console.log(`[Delegation] Result for task ${taskId} already exists, skipping`);
                return;
            }

            // Add delegation result as a message in source conversation
            const taskPromptPreview = task.prompt ? task.prompt.substring(0, 50) + (task.prompt.length > 50 ? '...' : '') : 'Task';
            const resultContent = status === 'completed'
                ? `📥 **Session #${targetSessionNum}** 返回结果\n\n> 任务: ${taskPromptPreview}\n\n---\n\n${task.result || 'Task completed successfully.'}`
                : `❌ **Session #${targetSessionNum}** 执行失败\n\n> 任务: ${taskPromptPreview}\n\n---\n\n${error || 'Unknown error'}`;

            console.log(`[Delegation] Adding result message for task ${taskId}, result length: ${task.result?.length || 0}`);

            sourceRuntime.messages.push({
                role: 'assistant',
                content: resultContent,
                isDelegationResult: true,
                delegationTaskId: taskId,
                delegationStatus: status
            });

            // Save the conversation immediately
            saveConversation(sourceConvId);
            console.log(`[Delegation] Saved conversation ${sourceConvId}, total messages: ${sourceRuntime.messages.length}`);

            // If source conversation is currently viewed, refresh messages and show notification
            if (currentConversationId === sourceConvId) {
                renderMessages();
                showDelegationResultNotification(taskId, targetSessionNum, status, task.result || error);
            }
        });

        // Show notification banner for delegation result
        function showDelegationResultNotification(taskId, targetSessionNum, status, result) {
            // Remove existing notification for this task
            const existing = document.querySelector(`[data-delegation-task="${taskId}"]`);
            if (existing) existing.remove();

            const banner = document.createElement('div');
            banner.className = `delegation-result-banner ${status}`;
            banner.dataset.delegationTask = taskId;
            banner.innerHTML = `
                <div class="delegation-result-header">
                    <span class="delegation-result-icon">${status === 'completed' ? '✓' : '✗'}</span>
                    <span>Task ${status} in Session #${targetSessionNum}</span>
                    <button class="delegation-result-close" onclick="this.parentElement.parentElement.remove()">×</button>
                </div>
                ${result ? `<div class="delegation-result-summary">${escapeHtml(result.substring(0, 200))}${result.length > 200 ? '...' : ''}</div>` : ''}
            `;

            const chatContent = document.getElementById('chat-content');
            chatContent.insertBefore(banner, chatContent.firstChild);

            // Auto-remove after 10 seconds
            setTimeout(() => banner.remove(), 10000);
        }

        // ==================== Tool Result UI Handler ====================

        function handleToolResultUI(toolName, result, convId = null) {
            // Handle special UI actions from tool results
            if (!result) return;

            // Todo updates
            if (result.ui_update === 'todo_panel' && result.todos) {
                updateTodoPanel(result.todos);
            }

            // Ask user dialog
            if (result.ui_action === 'show_question_dialog') {
                showAskUserDialog(result.question, result.options, result.allow_custom);
            }

            // Plan mode
            if (result.ui_update === 'plan_mode_indicator') {
                if (result.mode === 'plan') {
                    showPlanModeIndicator();
                } else {
                    hidePlanModeIndicator();
                }
            }

            // Plan approval
            if (result.ui_action === 'show_plan_approval' && result.plan) {
                showPlanApprovalDialog(result.plan);
            }

            // Context summary
            if (result.ui_update === 'context_indicator') {
                showContextIndicator();
            }

            // Delegation result - update conversation list to show badges
            if (result.type === 'delegate_task') {
                renderConversations();
            }
        }

        // ==================== Project Functions ====================

        function renderProjects() {
            const list = document.getElementById('projects-list');
            if (projects.length === 0) {
                list.innerHTML = '';
                return;
            }

            list.innerHTML = projects.map(p => `
                <div class="project-item ${p.id === currentProjectId ? 'active' : ''}" onclick="selectProject('${p.id}')">
                    <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M2 4h10M2 7h10M2 10h6"/>
                    </svg>
                    <span class="project-name">${p.name}</span>
                    <button class="delete-project" onclick="deleteProject('${p.id}', event)">
                        <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M2 2l8 8M10 2l-8 8"/>
                        </svg>
                    </button>
                </div>
            `).join('');
        }

        function toggleProjectsSection() {
            document.getElementById('projects-section').classList.toggle('collapsed');
        }

        function showProjectModal() {
            document.getElementById('project-modal').classList.add('active');
            document.getElementById('project-name-input').focus();
        }

        function hideProjectModal() {
            document.getElementById('project-modal').classList.remove('active');
            document.getElementById('project-name-input').value = '';
        }

        // ==================== Working Directory Selector Functions ====================
        let workdirSelectorResolve = null;

        function showWorkdirSelector() {
            return new Promise((resolve) => {
                workdirSelectorResolve = resolve;
                const modal = document.getElementById('workdir-selector-modal');
                const listEl = document.getElementById('workdir-selector-list');

                // 填充现有工作目录列表
                listEl.innerHTML = workingFolders.map(folder => `
                    <div class="workdir-selector-item" onclick="selectExistingFolderForChat('${folder.replace(/'/g, "\\'")}')">
                        <svg class="folder-icon" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                            <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2v11z"/>
                        </svg>
                        <span class="folder-path" title="${folder}">${folder}</span>
                        <button class="set-default-btn" onclick="event.stopPropagation(); setAsDefaultAndCreateChat('${folder.replace(/'/g, "\\'")}')">
                            设为默认
                        </button>
                    </div>
                `).join('');

                modal.classList.add('active');
            });
        }

        function hideWorkdirSelector(result = null) {
            document.getElementById('workdir-selector-modal').classList.remove('active');
            if (workdirSelectorResolve) {
                workdirSelectorResolve(result);
                workdirSelectorResolve = null;
            }
        }

        function selectExistingFolderForChat(folder) {
            hideWorkdirSelector({ folder: folder, setDefault: false });
        }

        function setAsDefaultAndCreateChat(folder) {
            // 设置为默认工作目录（全局生效）
            defaultWorkingFolder = folder;
            localStorage.setItem('defaultWorkingFolder', folder);
            console.log('Set default working folder:', folder);
            // 更新 workspace 列表显示星标
            renderWorkingFolders();
            hideWorkdirSelector({ folder: folder, setDefault: true });
        }

        async function selectNewFolderForChat() {
            hideWorkdirSelector(null); // 先关闭选择器
            const folders = await window.electronAPI.selectFolder();
            if (folders && folders.length > 0) {
                const newFolder = folders[0];
                // 添加到 workspace
                if (!workingFolders.includes(newFolder)) {
                    workingFolders.push(newFolder);
                    localStorage.setItem('workingFolders', JSON.stringify(workingFolders));
                    renderWorkingFolders();
                    console.log('Added folder to workspace:', newFolder);
                }
                // 直接创建会话
                await createConversationWithFolder(newFolder);
            }
        }

        async function createConversationWithFolder(workingDir) {
            // 直接创建带有工作目录的会话（跳过选择流程）
            if (isCreatingConversation) {
                console.log('Conversation creation already in progress, skipping');
                return null;
            }
            isCreatingConversation = true;

            try {
                const newId = Date.now().toString() + '-' + Math.random().toString(36).substr(2, 9);
                currentConversationId = newId;

                convRuntime[newId] = {
                    isStreaming: false,
                    attachments: [],
                    messages: [],
                    workingDir: workingDir || ''
                };

                const newConv = {
                    id: newId,
                    title: 'New Chat',
                    messages: [],
                    workingDir: workingDir || '',
                    createdAt: Date.now()
                };
                conversations.unshift(newConv);
                // Session saved to backend via SessionAPI

                document.getElementById('chat-content').innerHTML = welcomeTemplate;
                document.getElementById('header-title').textContent = 'New Chat';
                const tokenCountEl = document.getElementById('token-count');
                if (tokenCountEl) tokenCountEl.textContent = '';
                updateSendButtonState();
                syncStatusBarWithConversation(newId);
                renderConversations();
                hideContextIndicator();
                updateWorkingDirDisplay(workingDir);

                return newId;
            } finally {
                isCreatingConversation = false;
            }
        }
        // ==================== End Working Directory Selector ====================

        function createProject() {
            const name = document.getElementById('project-name-input').value.trim();
            if (!name) return;

            const project = {
                id: Date.now().toString(),
                name: name,
                createdAt: Date.now(),
                conversationIds: []
            };

            projects.unshift(project);
            localStorage.setItem('projects', JSON.stringify(projects));
            hideProjectModal();
            selectProject(project.id);
            renderProjects();
        }

        function selectProject(id) {
            currentProjectId = id;
            const project = projects.find(p => p.id === id);
            if (project) {
                document.getElementById('header-title').textContent = project.name;
            }
            renderProjects();
            // Filter conversations for this project
            renderConversations();
        }

        function deleteProject(id, e) {
            e.stopPropagation();
            projects = projects.filter(p => p.id !== id);
            localStorage.setItem('projects', JSON.stringify(projects));
            if (currentProjectId === id) {
                currentProjectId = null;
                document.getElementById('header-title').textContent = 'New Chat';
            }
            renderProjects();
        }

