        // NOTE: BASE_URL and CONFIG are defined in config.js (loaded before this file)

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
        function showToast(message, type = 'info', duration = CONFIG.TIMEOUTS.TOAST_DURATION) {
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

        // Open image preview modal
        window.openImagePreview = function(imageSrc) {
            // Create modal
            const modal = document.createElement('div');
            modal.className = 'image-preview-modal';
            modal.innerHTML = '';
            const img = document.createElement('img');
            img.src = imageSrc;
            img.alt = 'Image preview';
            modal.appendChild(img);

            // Close on click
            modal.addEventListener('click', () => modal.remove());

            // Close on Escape key
            const handleEscape = (e) => {
                if (e.key === 'Escape') {
                    modal.remove();
                    document.removeEventListener('keydown', handleEscape);
                }
            };
            document.addEventListener('keydown', handleEscape);

            document.body.appendChild(modal);
        };

        // Reset stuck conversation state - call when network recovers or user wants to force reset
        // Set showToast=false when calling manually via /reset command
        function resetStuckConversations(showToastMsg = true) {
            let resetCount = 0;
            for (const convId in convRuntime) {
                const runtime = convRuntime[convId];
                if (runtime.isStreaming) {
                    console.log(`[Recovery] Resetting stuck conversation: ${convId}`);
                    runtime.isStreaming = false;

                    // Abort any pending requests to release resources
                    if (typeof abortControllers !== 'undefined' && abortControllers[convId]) {
                        try {
                            abortControllers[convId].abort();
                            console.log(`[Recovery] Aborted pending request for: ${convId}`);
                        } catch (e) {
                            // Ignore abort errors
                        }
                    }

                    // Remove any thinking indicators
                    const thinkingIdx = runtime.messages.findIndex(m => m.isThinking);
                    if (thinkingIdx >= 0) {
                        runtime.messages.splice(thinkingIdx, 1);
                    }

                    updateConversationStatus(convId, 'idle');
                    resetCount++;
                }
            }

            if (resetCount > 0) {
                updateSendButtonState();
                updateStatus('idle');
                renderMessages();
                if (showToastMsg) {
                    showToast(`Connection recovered. ${resetCount} stuck task(s) reset.`, 'warning', 8000);
                }
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

            // Update metadata only (no message overwrite) - safe for rename
            async updateMetadata(sessionId, metadata) {
                try {
                    const response = await fetch(`${BASE_URL}/v1/sessions/${sessionId}`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ metadata })
                    });
                    return response.ok;
                } catch (e) {
                    console.error('SessionAPI.updateMetadata error:', e);
                    return false;
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

        // Memory management configuration
        const MEMORY_CONFIG = {
            MAX_CACHED_SESSIONS: 10,      // Keep runtime for at most N recently accessed sessions
            GC_INTERVAL_MS: 5 * 60 * 1000, // Run garbage collection every 5 minutes
            MIN_IDLE_TIME_MS: 3 * 60 * 1000 // Session must be idle for 3 minutes before cleanup
        };

        // Track recently accessed sessions (most recent first)
        let recentlyAccessedSessions = [];

        // Update recently accessed sessions list
        function markSessionAccessed(convId) {
            if (!convId) return;
            // Remove if already in list
            recentlyAccessedSessions = recentlyAccessedSessions.filter(id => id !== convId);
            // Add to front
            recentlyAccessedSessions.unshift(convId);
            // Trim to max size
            if (recentlyAccessedSessions.length > MEMORY_CONFIG.MAX_CACHED_SESSIONS * 2) {
                recentlyAccessedSessions = recentlyAccessedSessions.slice(0, MEMORY_CONFIG.MAX_CACHED_SESSIONS * 2);
            }
        }

        // Cleanup inactive session runtimes to free memory
        // Preserves: current session, streaming sessions, and recently accessed sessions
        function cleanupInactiveRuntimes() {
            const now = Date.now();
            const keepIds = new Set([
                currentConversationId,
                ...getStreamingConvIds(),
                ...recentlyAccessedSessions.slice(0, MEMORY_CONFIG.MAX_CACHED_SESSIONS)
            ].filter(Boolean));

            let cleanedCount = 0;
            for (const convId of Object.keys(convRuntime)) {
                if (keepIds.has(convId)) continue;

                const runtime = convRuntime[convId];
                // Don't clean up if streaming
                if (runtime.isStreaming) continue;

                // Clean up runtime
                delete convRuntime[convId];
                cleanupAbortController(convId);
                cleanedCount++;
            }

            if (cleanedCount > 0) {
                console.log(`[Memory GC] Cleaned up ${cleanedCount} inactive session runtimes`);
            }
            return cleanedCount;
        }

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

        // Cleanup abort controller for a conversation (call when deleting session)
        // Part of memory leak fix - abortControllers were never cleaned up
        function cleanupAbortController(convId) {
            if (abortControllers[convId]) {
                try {
                    abortControllers[convId].abort(); // Abort any pending requests
                } catch (e) {
                    // Ignore abort errors
                }
                delete abortControllers[convId];
            }
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

        // Force reset all stuck streaming states
        // Use this when sessions get stuck in "Running" state
        // Alias for resetStuckConversations with showToast=false
        function forceResetAllStreaming() {
            console.log('Force resetting all streaming states via /reset command');
            return resetStuckConversations(false);
        }

        // Legacy compatibility - will be removed after refactor
        let attachments = [];

        // Projects state
        let projects = JSON.parse(localStorage.getItem('projects') || '[]');
        let currentProjectId = null;

        // Working folders state (persisted to disk cache via electronAPI.cache)
        let workingFolders = [];
        let currentWorkingDir = '';
        let defaultWorkingFolder = '~/Downloads';

        // Save workspace state to disk cache
        async function saveWorkspaceCache() {
            if (window.electronAPI?.cache) {
                await window.electronAPI.cache.set('workspace', {
                    workingFolders,
                    currentWorkingDir,
                    defaultWorkingFolder
                });
            }
        }

        // Load workspace state from disk cache
        async function loadWorkspaceCache() {
            if (window.electronAPI?.cache) {
                const cached = await window.electronAPI.cache.get('workspace');
                if (cached) {
                    workingFolders = cached.workingFolders || [];
                    currentWorkingDir = cached.currentWorkingDir || '';
                    defaultWorkingFolder = cached.defaultWorkingFolder || '~/Downloads';
                    return true;
                }
            }
            return false;
        }


        // Skills state
        let availableSkills = [];
        let activeSkill = null;  // Currently active skill for the conversation
        let showSkillPicker = false;

        let teamModeEnabled = false;
        let teamCollaborativeMode = false; // false = classic, true = collaborative

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
            await loadModelsFromAPI();

            // Initialize context indicator (will be updated when conversation loads)
            updateContextIndicator(null);

            // Start Memory sync status updates
            startMemorySyncStatusUpdates();

            // Start periodic memory garbage collection
            // Cleans up inactive session runtimes to prevent memory leaks
            setInterval(() => {
                cleanupInactiveRuntimes();
            }, MEMORY_CONFIG.GC_INTERVAL_MS);
            console.log(`[Memory GC] Started periodic cleanup every ${MEMORY_CONFIG.GC_INTERVAL_MS / 1000}s`);

            // Load workspace cache from disk (persists across macOS restarts)
            await loadWorkspaceCache();
            console.log('[Cache] Loaded workspace:', { workingFolders, currentWorkingDir, defaultWorkingFolder });

            // Ensure default working folder is in workspace list
            ensureDefaultFolderInWorkspace();

            // Prune workspace folders that no longer exist on disk
            await pruneDeletedWorkingFolders();

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
            // Double-Escape (within 500ms) forces reset of all stuck sessions
            let lastEscapeTime = 0;
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    const now = Date.now();
                    const timeSinceLastEscape = now - lastEscapeTime;
                    lastEscapeTime = now;

                    // Double-Escape: force reset all stuck sessions
                    if (timeSinceLastEscape < 500) {
                        e.preventDefault();
                        const resetCount = forceResetAllStreaming();
                        if (resetCount > 0) {
                            showToast(`Force reset ${resetCount} stuck session(s)`, 'warning', 3000);
                        }
                        return;
                    }

                    // Single Escape: stop current task if streaming
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
            const { ok, data, error } = await apiCall('/v1/skills', {}, { retry: false });
            if (ok) {
                availableSkills = data.skills || [];
                console.log('Loaded skills:', availableSkills.map(s => s.name));
            } else {
                console.error('Failed to load skills:', error);
                availableSkills = [];
            }
        }

        // Built-in commands for the picker (defined here for scope access)
        const pickerBuiltInCommands = [
            { name: 'name', description: 'Rename current session (usage: /name New Title)', isBuiltIn: true },
            { name: 'rename', description: 'Alias for /name', isBuiltIn: true },
            { name: 'clear', description: 'Clear current session messages', isBuiltIn: true },
            { name: 'terminal', description: 'Execute a command inline (usage: /terminal ls -la)', isBuiltIn: true },
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
            const { ok, data, error } = await apiCall(`/v1/skills/${skillName}/instructions`, {}, { retry: false });
            if (ok) {
                return data.instructions || '';
            }
            console.error('Failed to get skill instructions:', error);
            return '';
        }

        // Auto-detect skill from message content (SKILL_KEYWORDS defined in config.js)
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
                case 'compacting':
                    status.textContent = '◐ Compacting...';
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
                        memory_files: [],
                        model: settings.model || getDefaultModel()
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
                        system: '',
                        tools: tools,
                        skills: skills,
                        memory_files: memory_files,
                        model: settings.model || getDefaultModel()
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

            // Map type to background color
            let bgColor;
            switch (type) {
                case 'success': bgColor = 'var(--success, #28a745)'; break;
                case 'warning': bgColor = '#f0ad4e'; break;
                case 'error': bgColor = '#d9534f'; break;
                default: bgColor = 'var(--accent, #007bff)';
            }

            notification.style.cssText = `
                position: fixed;
                bottom: 80px;
                right: 20px;
                background: ${bgColor};
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

        // Enable/disable input during context compaction
        function setInputEnabled(enabled) {
            const input = document.getElementById('message-input');
            const sendBtn = document.querySelector('.send-button');

            if (input) {
                input.disabled = !enabled;
                input.style.opacity = enabled ? '1' : '0.6';
            }
            if (sendBtn) {
                sendBtn.disabled = !enabled;
                sendBtn.style.opacity = enabled ? '1' : '0.6';
            }

            // Also show/hide a blocking overlay if needed
            let overlay = document.getElementById('compact-overlay');
            if (!enabled) {
                if (!overlay) {
                    overlay = document.createElement('div');
                    overlay.id = 'compact-overlay';
                    overlay.style.cssText = `
                        position: fixed;
                        bottom: 0;
                        left: 0;
                        right: 0;
                        height: 60px;
                        background: rgba(0,0,0,0.3);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        color: white;
                        font-size: 14px;
                        z-index: 999;
                    `;
                    overlay.textContent = '正在压缩上下文，请稍候...';
                    document.body.appendChild(overlay);
                }
            } else {
                if (overlay) {
                    overlay.remove();
                }
            }
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
                    body: JSON.stringify({ messages: apiMessages, model: settings.model || getDefaultModel() })
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
                        saveWorkspaceCache();
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
                                saveWorkspaceCache();
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
                // Mark this session as accessed (memory management)
                markSessionAccessed(id);

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
                // Clean up abort controller (memory leak fix)
                cleanupAbortController(c.id);
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

            // Clean up abort controller (memory leak fix)
            cleanupAbortController(id);

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

            // Save renamed title to backend (metadata-only, no message overwrite)
            SessionAPI.updateMetadata(convId, {
                title: conv.title,
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
                // SVG icons for avatars (matching welcome icon style)
                const dogIcon = '<svg viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="50" cy="38" rx="22" ry="20"/><path d="M28 35 C15 38, 8 55, 12 72 C14 78, 18 80, 22 78 C28 75, 30 65, 30 55"/><path d="M72 35 C85 38, 92 55, 88 72 C86 78, 82 80, 78 78 C72 75, 70 65, 70 55"/><circle cx="40" cy="35" r="3" fill="currentColor"/><circle cx="60" cy="35" r="3" fill="currentColor"/><ellipse cx="50" cy="48" rx="5" ry="4" fill="currentColor"/><path d="M45 52 Q50 58, 55 52"/></svg>';
                const userIcon = '<svg viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><circle cx="50" cy="35" r="18"/><path d="M20 90 C20 65 35 55 50 55 C65 55 80 65 80 90"/></svg>';
                const delegationIcon = '<svg viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M70 30 L30 50 L70 70"/><path d="M30 50 L80 50"/></svg>';
                const taskIcon = '<svg viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><rect x="20" y="15" width="60" height="70" rx="5"/><line x1="35" y1="35" x2="65" y2="35"/><line x1="35" y1="50" x2="65" y2="50"/><line x1="35" y1="65" x2="55" y2="65"/></svg>';

                let avatar = dogIcon;
                let label = 'Springo';

                if (isDelegationResult) {
                    extraClass = ' delegation-result';
                    avatar = delegationIcon;
                    label = 'Delegation Result';
                } else if (isTaskResult) {
                    extraClass = ' task-result';
                    avatar = taskIcon;
                    label = 'Task Result';
                } else if (m.role === 'user') {
                    avatar = userIcon;
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

            // Strip chat-tool-container HTML (tools shown in inline panel instead)
            if (typeof content === 'string' && content.includes('<div class="chat-tool-container"')) {
                // Remove tool container, keep only the text content
                content = content.replace(/<div class="chat-tool-container">[\s\S]*?<!-- END_TOOL_CONTAINER -->/g, '').trim();
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
                    if (c.type === 'image') {
                        // Render actual image if base64 data is available
                        if (c.source?.data) {
                            const mediaType = c.source.media_type || 'image/png';
                            return `<div class="chat-image-container">
                                <img src="data:${mediaType};base64,${c.source.data}"
                                     class="chat-image"
                                     alt="Uploaded image"
                                     onclick="window.openImagePreview(this.src)">
                            </div>`;
                        }
                        // Image reference without data (not yet restored)
                        return '<div class="chat-image-placeholder">[Image loading...]</div>';
                    }
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
        async function fetchWithRetry(url, options, maxRetries = CONFIG.RETRY.MAX_ATTEMPTS, timeout = CONFIG.TIMEOUTS.FETCH_RETRY, externalSignal = null) {
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

        /**
         * Unified API call wrapper with consistent error handling
         * @param {string} endpoint - API endpoint (without BASE_URL)
         * @param {object} options - fetch options (method, body, headers)
         * @param {object} config - additional config { parseJson: true, retry: true, timeout: 30000 }
         * @returns {Promise<{ok: boolean, data: any, error: string|null, status: number}>}
         */
        async function apiCall(endpoint, options = {}, config = {}) {
            const { parseJson = true, retry = true, timeout = 30000, maxRetries = 2 } = config;
            const url = endpoint.startsWith('http') ? endpoint : `${BASE_URL}${endpoint}`;

            const fetchOptions = {
                headers: { 'Content-Type': 'application/json', ...options.headers },
                ...options
            };

            try {
                const response = retry
                    ? await fetchWithRetry(url, fetchOptions, maxRetries, timeout)
                    : await fetch(url, fetchOptions);

                // Handle non-OK responses consistently
                if (!response.ok) {
                    let errorMessage = `HTTP ${response.status}`;
                    try {
                        const errorData = await response.json();
                        errorMessage = errorData.error || errorData.detail || errorData.message || errorMessage;
                    } catch {
                        // If response isn't JSON, use status text
                        errorMessage = response.statusText || errorMessage;
                    }
                    return { ok: false, data: null, error: errorMessage, status: response.status };
                }

                // Parse response
                if (parseJson) {
                    const data = await response.json();
                    return { ok: true, data, error: null, status: response.status };
                }

                return { ok: true, data: response, error: null, status: response.status };
            } catch (e) {
                // Network errors, timeouts, etc.
                const isAbort = e.name === 'AbortError';
                const errorMessage = isAbort ? 'Request timed out' : (e.message || 'Network error');
                return { ok: false, data: null, error: errorMessage, status: 0 };
            }
        }

        // SSE Stream Parser for handling streaming responses
        // With timeout protection to prevent hanging on large responses
        async function* parseSSEStream(reader, timeoutMs = CONFIG.TIMEOUTS.SSE_HEARTBEAT) {
            const decoder = new TextDecoder();
            let buffer = '';
            let lastActivityTime = Date.now();

            // Helper to read with timeout
            async function readWithTimeout() {
                return new Promise((resolve, reject) => {
                    const timeoutId = setTimeout(() => {
                        reject(new Error(`SSE stream timeout: no data received for ${timeoutMs/1000}s`));
                    }, timeoutMs);

                    reader.read().then(result => {
                        clearTimeout(timeoutId);
                        lastActivityTime = Date.now();
                        resolve(result);
                    }).catch(err => {
                        clearTimeout(timeoutId);
                        reject(err);
                    });
                });
            }

            while (true) {
                const { done, value } = await readWithTimeout();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Split on double newlines (SSE event separator)
                const events = buffer.split('\n\n');
                buffer = events.pop() || ''; // Keep incomplete event in buffer

                // Safety: if buffer grows too large, something is wrong
                if (buffer.length > 10 * 1024 * 1024) { // 10MB limit
                    console.error('SSE buffer overflow, clearing');
                    buffer = '';
                }

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
                            console.warn('SSE parse error:', e, eventData?.substring(0, 200));
                        }
                    }
                }
            }
        }

        // Process streaming response and update UI progressively
        // With watchdog timer to prevent hanging on large responses
        async function processStreamingResponse(response, convId, onTextUpdate, onComplete) {
            const reader = response.body.getReader();
            let textContent = '';
            let toolUses = [];
            let currentToolUse = null;
            let currentToolInput = '';
            let streamToolInterval = null;  // Local interval for real-time tool updates
            let streamCompleted = false;

            // Watchdog: SSE heartbeat timeout (backend sends heartbeats to keep alive)
            const STREAM_TIMEOUT_MS = CONFIG.TIMEOUTS.SSE_HEARTBEAT;

            try {
                for await (const { event, data } of parseSSEStream(reader, STREAM_TIMEOUT_MS)) {
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
                                // Skip logging for scheduler (silent operation)
                                if (block.name !== 'scheduler') {
                                    console.log(`[${convId}] Stream: tool_use started - ${block.name}`);
                                }
                            }
                            break;

                        case 'content_block_delta':
                            const delta = data.delta;
                            if (delta.type === 'text_delta') {
                                textContent += delta.text;
                                onTextUpdate(textContent, toolUses, false);
                            } else if (delta.type === 'input_json_delta' && currentToolUse) {
                                currentToolInput += delta.partial_json;
                                // Skip logging for scheduler (silent operation)
                                if (currentToolUse.name !== 'scheduler') {
                                    console.log(`[${convId}] input_json_delta for ${currentToolUse.name}: +${delta.partial_json.length} chars`);
                                }
                            }
                            break;

                        case 'content_block_stop':
                            if (currentToolUse) {
                                try {
                                    currentToolUse.input = JSON.parse(currentToolInput || '{}');
                                    // Skip logging for scheduler (silent operation)
                                    if (currentToolUse.name !== 'scheduler') {
                                        console.log(`[${convId}] Parsed input for ${currentToolUse.name}:`, JSON.stringify(currentToolUse.input).substring(0, 100));
                                    }
                                } catch (e) {
                                    console.error(`[${convId}] Failed to parse tool input: ${e.message}, raw: ${currentToolInput.substring(0, 100)}`);
                                    currentToolUse.input = {};
                                }
                                toolUses.push(currentToolUse);
                                // Skip logging for scheduler (silent operation)
                                if (currentToolUse.name !== 'scheduler') {
                                    console.log(`[${convId}] Stream: tool_use complete - ${currentToolUse.name}`);
                                }
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
                            // Skip logging if only scheduler tool
                            if (!data.tools?.every(t => t.name === 'scheduler')) {
                                console.log(`[${convId}] Server executing tools:`, data.tools?.map(t => t.name));
                            }
                            // Add tools to inline panel in running state
                            if (currentConversationId === convId && data.tools) {
                                for (const tool of data.tools) {
                                    // Add to toolUses if not already present
                                    if (!toolUses.find(tu => tu.id === tool.id)) {
                                        toolUses.push({ id: tool.id, name: tool.name, input: tool.input || {}, status: 'running' });
                                    }
                                }
                                // Update inline panel immediately
                                updateInlineChatToolPanel(toolUses);
                                // Start interval to update elapsed time (AUTO mode)
                                if (streamToolInterval) clearInterval(streamToolInterval);
                                streamToolInterval = setInterval(() => {
                                    if (currentConversationId === convId) {
                                        updateInlineChatToolPanel(toolUses);
                                    }
                                }, 1000);
                            }
                            break;

                        case 'tool_executing':
                            // Skip logging for scheduler (silent operation)
                            if (data.name !== 'scheduler') {
                                console.log(`[${convId}] Executing: ${data.name}`);
                            }
                            // Update tool status to running and refresh panel
                            if (currentConversationId === convId) {
                                const executingTool = toolUses.find(tu => tu.id === data.id);
                                if (executingTool) {
                                    executingTool.status = 'running';
                                    updateInlineChatToolPanel(toolUses);
                                }
                            }
                            break;

                        case 'tool_result':
                            // Backend sends: tool_use_id, tool_name, result
                            // Skip logging for scheduler (silent operation)
                            if (data.tool_name !== 'scheduler') {
                                console.log(`[${convId}] Tool result: ${data.tool_name}`);
                            }

                            // Inject actual task list for scheduler list action
                            let resultData = data.result;
                            if (data.tool_name === 'scheduler' && resultData?.ui_update === 'schedules_panel' && !resultData?.task && !resultData?.action) {
                                // This is a list action - inject actual tasks
                                const taskList = Object.values(scheduledTasks)
                                    .sort((a, b) => (a.num || 0) - (b.num || 0))
                                    .map(t => ({
                                        num: t.num || '?',
                                        id: t.id,
                                        name: t.name,
                                        type: t.scheduleType,
                                        schedule: t.scheduleValue,
                                        enabled: t.enabled,
                                        status: t.status || 'pending',
                                        nextRun: t.nextRun ? new Date(t.nextRun).toLocaleString() : null
                                    }));
                                resultData = {
                                    ...resultData,
                                    tasks: taskList,
                                    task_count: taskList.length,
                                    message: taskList.length > 0
                                        ? `Found ${taskList.length} scheduled task(s). Use num to reference tasks.`
                                        : 'No scheduled tasks'
                                };
                            }

                            // Store result in toolUses array for chat display
                            const matchingTool = toolUses.find(tu => tu.id === data.tool_use_id);
                            if (matchingTool) {
                                matchingTool.result = resultData;
                                matchingTool.status = 'complete';
                            }
                            // Update inline panel immediately to show completion
                            if (currentConversationId === convId) {
                                updateInlineChatToolPanel(toolUses);
                            }
                            break;

                        case 'heartbeat':
                            // SSE heartbeat to keep connection alive during long tool execution
                            console.log(`[${convId}] Heartbeat: ${data.tool_name} running for ${data.elapsed_seconds}s`);
                            // Update tool elapsed time in panel
                            if (currentConversationId === convId) {
                                const heartbeatTool = toolUses.find(tu => tu.id === data.tool_id);
                                if (heartbeatTool) {
                                    heartbeatTool.elapsed = data.elapsed_seconds;
                                    updateInlineChatToolPanel(toolUses);
                                }
                            }
                            break;

                        case 'tool_execution_complete':
                            console.log(`[${convId}] All ${data.count} tools executed on server`);
                            // Stop elapsed time update interval
                            if (streamToolInterval) {
                                clearInterval(streamToolInterval);
                                streamToolInterval = null;
                            }
                            // Final update to inline panel
                            if (currentConversationId === convId) {
                                updateInlineChatToolPanel(toolUses);
                            }
                            break;

                        case 'skill_injected':
                            // Skill was activated and injected into system prompt
                            console.log(`[${convId}] Skill injected: ${data.skill_name}`);
                            // Note: skill execution shown via subsequent tool calls (use_skill, read_file, etc.)
                            break;

                        case 'context_compact':
                            // Claude Code 风格：context 接近限制时自动 compact
                            console.log(`[${convId}] Context compacting: ${data.reason}, tokens_before: ${data.tokens_before}`);
                            if (currentConversationId === convId) {
                                // Show compacting state in status bar only
                                updateStatus('compacting');
                            }
                            break;

                        case 'context_compact_done':
                            // Compact completed successfully
                            console.log(`[${convId}] Context compact done: ${data.messages_before} -> ${data.messages_after} messages, ${data.tokens_after} tokens`);
                            if (currentConversationId === convId) {
                                updateStatus('running');  // Resume running state
                                updateContextIndicator({
                                    total_tokens: data.tokens_after,
                                    max_tokens: CONFIG.TOKENS.MAX_CONTEXT,
                                    usage_percent: (data.tokens_after / CONFIG.TOKENS.MAX_CONTEXT) * 100,
                                    status: 'normal'
                                }, convId);
                            }
                            break;

                        case 'context_compact_failed':
                            // Compact failed - resume running
                            console.error(`[${convId}] Context compact failed: ${data.error}`);
                            if (currentConversationId === convId) {
                                updateStatus('running');
                            }
                            break;

                        case 'messages_updated':
                            // Backend has modified messages (truncated/compacted) - sync to frontend
                            // This is CRITICAL for Claude Code style context management
                            console.log(`[${convId}] Messages updated from backend: ${data.messages?.length} messages, ${data.token_count} tokens`);
                            if (data.messages && convRuntime[convId]) {
                                // Update frontend messages with compacted version
                                convRuntime[convId].messages = data.messages;
                                console.log(`[${convId}] Frontend messages synced with backend`);

                                // Update context indicator
                                if (currentConversationId === convId) {
                                    updateContextIndicator({
                                        total_tokens: data.token_count,
                                        max_tokens: CONFIG.TOKENS.MAX_CONTEXT,
                                        usage_percent: (data.token_count / CONFIG.TOKENS.MAX_CONTEXT) * 100,
                                        status: data.token_count > CONFIG.TOKENS.WARNING_THRESHOLD ? 'critical' :
                                                data.token_count > CONFIG.TOKENS.COMPACT_THRESHOLD ? 'warning' : 'normal'
                                    }, convId);
                                }
                            }
                            break;

                        // === Agent Team SSE Events (rendered in Team tab only) ===
                        case 'team_spawned':
                            console.log(`[${convId}] Team spawned: ${data.team_id} with ${data.agents?.length} agents`);
                            if (currentConversationId === convId) {
                                initTeamSplitPanel(data.team_id, data.agents, data.user_request);
                            }
                            break;

                        case 'team_planning':
                            if (currentConversationId === convId) {
                                updateTeamSplitStatus(data.team_id, 'planning', 'Planning...');
                            }
                            break;

                        case 'team_task_board':
                            if (currentConversationId === convId) {
                                addTeamSplitAgents(data.team_id, data.tasks);
                                updateTeamSplitStatus(data.team_id, 'executing', 'Agents working...');
                            }
                            break;

                        case 'team_agent_start':
                            if (currentConversationId === convId) {
                                updateTeamSplitAgent(data.team_id, data.agent_id, data.role, 'thinking', data.task_title);
                            }
                            break;

                        case 'team_agent_progress':
                            if (currentConversationId === convId) {
                                updateTeamSplitAgent(data.team_id, data.agent_id, data.role, data.status, '', data.preview);
                            }
                            break;

                        case 'team_agent_complete':
                            if (currentConversationId === convId) {
                                updateTeamSplitAgent(data.team_id, data.agent_id, data.role, 'complete', data.task_title, data.findings);
                            }
                            break;

                        case 'team_agent_error':
                            if (currentConversationId === convId) {
                                updateTeamSplitAgent(data.team_id, data.agent_id, data.role, 'error', '', data.error);
                            }
                            break;

                        case 'team_agent_delta':
                            if (currentConversationId === convId) {
                                appendTeamAgentDelta(data.team_id, data.agent_id, data.role, data.delta);
                            }
                            break;

                        case 'team_agent_tool':
                            if (currentConversationId === convId) {
                                appendTeamAgentToolEvent(data.team_id, data.agent_id, data.role, data.tool_name, data.status, data.result_preview);
                            }
                            break;

                        case 'team_synthesis_delta':
                            // Stream synthesis to chat window (not team panel)
                            textContent += data.delta;
                            onTextUpdate(textContent, toolUses, false);
                            break;

                        case 'team_synthesizing':
                            if (currentConversationId === convId) {
                                updateTeamSplitStatus(data.team_id, 'synthesizing', 'Synthesizing...');
                            }
                            break;

                        case 'team_complete':
                            if (currentConversationId === convId) {
                                updateTeamSplitStatus(data.team_id, 'complete', 'Complete');
                            }
                            // Result already streamed via team_synthesis_delta
                            break;

                        case 'team_error':
                            if (currentConversationId === convId) {
                                updateTeamSplitStatus(data.team_id, 'error', `Error: ${data.error}`);
                            }
                            break;

                        // === Collaborative Team Events ===
                        case 'team_agent_message':
                            if (currentConversationId === convId) {
                                appendTeamMessage(data.team_id, data.sender, data.recipient, data.content, data.summary);
                            }
                            break;

                        case 'team_agent_broadcast':
                            if (currentConversationId === convId) {
                                appendTeamMessage(data.team_id, data.sender, 'all', data.content, data.summary, true);
                            }
                            break;

                        case 'team_agent_idle':
                            if (currentConversationId === convId) {
                                updateTeamSplitAgent(data.team_id, null, null, 'idle', '', '', data.agent_name);
                            }
                            break;

                        case 'team_agent_shutdown':
                            if (currentConversationId === convId) {
                                updateTeamSplitAgent(data.team_id, null, null, 'shutdown', '', '', data.agent_name);
                            }
                            break;

                        case 'team_task_created':
                            if (currentConversationId === convId) {
                                addTeamTaskBoardItem(data.team_id, data.task_id, data.title, data.owner, 'pending');
                            }
                            break;

                        case 'team_task_updated':
                            if (currentConversationId === convId) {
                                updateTeamTaskBoardItem(data.team_id, data.task_id, data.status, data.owner, data.title);
                            }
                            break;

                        case 'team_task_unblocked':
                            if (currentConversationId === convId) {
                                updateTeamTaskBoardItem(data.team_id, data.task_id, 'unblocked', data.owner, data.title);
                            }
                            break;

                        case 'error':
                            throw new Error(data.error?.message || 'Stream error');
                    }
                }

                streamCompleted = true;
                onComplete(textContent, toolUses);
                return { textContent, toolUses };

            } catch (e) {
                console.error(`[${convId}] Stream error:`, e);
                // Still call onComplete with whatever we have so UI state is updated
                if (!streamCompleted) {
                    console.log(`[${convId}] Calling onComplete after error with partial data`);
                    onComplete(textContent, toolUses);
                }
                throw e;
            } finally {
                // Always cleanup interval
                if (streamToolInterval) {
                    clearInterval(streamToolInterval);
                    streamToolInterval = null;
                }
                // Always try to cancel the reader to release resources
                try {
                    await reader.cancel();
                    console.log(`[${convId}] Stream reader cancelled`);
                } catch (cancelError) {
                    // Ignore cancel errors - reader may already be closed
                }
            }
        }

        // Execute a tool via the API with timeout and retry
        // OPTIMIZATION: Reduced timeout and retries to avoid long waits
        // - 45 second timeout (MCP server has 30s internal timeout)
        // - 1 retry only (max 90s total instead of 8 minutes)
        async function executeTool(toolName, toolInput) {
            try {
                console.log(`[executeTool] Starting: ${toolName}`);

                // Handle frontend-side background task tools directly
                if (toolName === 'get_background_task_status') {
                    const taskId = toolInput.task_id;
                    return window.getBackgroundTaskStatus ? window.getBackgroundTaskStatus(taskId) : { error: 'Background task system not initialized' };
                }
                if (toolName === 'list_background_tasks') {
                    return window.listBackgroundTasks ? { tasks: window.listBackgroundTasks() } : { tasks: [] };
                }

                const response = await fetchWithRetry(`${BASE_URL}/v1/tools/execute`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: toolName, input: toolInput })
                }, 1, CONFIG.TIMEOUTS.TOOL_EXECUTION); // 1 retry, 3 min timeout for complex tools

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

        // === Agent Team UI Functions ===

        // Role display config: label, color, icon
        const TEAM_ROLE_CONFIG = {
            orchestrator: { label: 'Orchestrator', color: '#7c3aed', icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z' },
            explorer:     { label: 'Explorer',     color: '#2563eb', icon: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z' },
            researcher:   { label: 'Researcher',   color: '#059669', icon: 'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253' },
            implementer:  { label: 'Implementer',  color: '#d97706', icon: 'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4' },
            reviewer:     { label: 'Reviewer',     color: '#dc2626', icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z' },
            custom:       { label: 'Agent',        color: '#6366f1', icon: 'M13 10V3L4 14h7v7l9-11h-7z' },
        };

        // Get role config with fallback for custom roles - use actual role name as label
        function getTeamRoleConfig(roleName) {
            if (TEAM_ROLE_CONFIG[roleName]) return TEAM_ROLE_CONFIG[roleName];
            const base = TEAM_ROLE_CONFIG.custom;
            const label = roleName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            return { ...base, label };
        }

        // Append streaming delta text to an agent's output in the split panel
        function appendTeamAgentDelta(teamId, agentId, role, delta) {
            if (teamId !== activeTeamSplitId) return;
            const agentsContainer = document.getElementById('team-split-agents');
            if (!agentsContainer) return;
            const card = agentsContainer.querySelector(`[data-agent-id="${agentId}"]`);
            if (!card) return;

            // Set badge to executing with pulse
            const badge = card.querySelector('.team-split-agent-badge');
            if (badge && badge.textContent !== 'executing') {
                badge.textContent = 'executing';
                badge.className = 'team-split-agent-badge executing';
            }
            if (!card.classList.contains('active')) {
                card.classList.add('active');
            }

            // Append delta text to output
            const outputEl = card.querySelector('.team-split-agent-output');
            if (outputEl) {
                if (outputEl.style.display === 'none' || !outputEl.style.display) {
                    outputEl.style.display = 'block';
                    outputEl.setAttribute('data-streaming', 'true');
                    // Set a default expanded height if not already user-resized
                    if (!card.style.height) {
                        card.style.height = '180px';
                    }
                }
                outputEl.textContent += delta;
                outputEl.scrollTop = outputEl.scrollHeight;
            }

        }

        function appendTeamAgentToolEvent(teamId, agentId, role, toolName, status, resultPreview) {
            if (teamId !== activeTeamSplitId) return;
            const agentsContainer = document.getElementById('team-split-agents');
            if (!agentsContainer) return;
            const card = agentsContainer.querySelector(`[data-agent-id="${agentId}"]`);
            if (!card) return;

            const outputEl = card.querySelector('.team-split-agent-output');
            if (!outputEl) return;

            if (outputEl.style.display === 'none' || !outputEl.style.display) {
                outputEl.style.display = 'block';
                outputEl.setAttribute('data-streaming', 'true');
                if (!card.style.height) {
                    card.style.height = '180px';
                }
            }

            if (status === 'start') {
                outputEl.textContent += `\n[tool] ${toolName} ...`;
            } else if (status === 'complete') {
                // Replace trailing "..." with done marker
                const text = outputEl.textContent;
                const pending = `\n[tool] ${toolName} ...`;
                if (text.endsWith(pending)) {
                    outputEl.textContent = text.slice(0, -3) + 'done';
                } else {
                    outputEl.textContent += ` done`;
                }
                outputEl.textContent += '\n';
            } else if (status === 'error') {
                const text = outputEl.textContent;
                const pending = `\n[tool] ${toolName} ...`;
                if (text.endsWith(pending)) {
                    outputEl.textContent = text.slice(0, -3) + 'error';
                } else {
                    outputEl.textContent += ` error`;
                }
                outputEl.textContent += '\n';
            }
            outputEl.scrollTop = outputEl.scrollHeight;
        }

        // Append streaming synthesis delta to the Team tab split panel
        function appendTeamSynthesisDelta(teamId, delta) {
            if (teamId !== activeTeamSplitId) return;
            const splitContent = document.getElementById('team-split-content');
            if (!splitContent) return;

            let synthesisEl = splitContent.querySelector('.team-synthesis-stream');
            if (!synthesisEl) {
                synthesisEl = document.createElement('div');
                synthesisEl.className = 'team-synthesis-stream team-split-agent-output';
                synthesisEl.style.display = 'block';
                const agentsContainer = document.getElementById('team-split-agents');
                if (agentsContainer) {
                    agentsContainer.parentNode.insertBefore(synthesisEl, agentsContainer.nextSibling);
                } else {
                    splitContent.appendChild(synthesisEl);
                }
            }

            synthesisEl.textContent += delta;
            synthesisEl.scrollTop = synthesisEl.scrollHeight;
        }

        // Render the main team panel in chat
        function renderTeamPanel(teamId, agents, userRequest) {
            const chatContent = document.getElementById('chat-content');
            if (!chatContent) return;

            // Remove existing team panel if any
            const existing = document.getElementById(`team-panel-${teamId}`);
            if (existing) existing.remove();

            const agentCards = agents.map(a => {
                const cfg = getTeamRoleConfig(a.role);
                return `
                    <div class="team-agent-card" data-agent-id="${a.agent_id}" data-team-id="${teamId}" style="--agent-color: ${cfg.color}; cursor:pointer" onclick="toggleAgentDetail(this, '${teamId}', '${a.agent_id}')">
                        <div class="team-agent-header">
                            <svg class="team-agent-icon" fill="none" stroke="${cfg.color}" viewBox="0 0 24 24" width="16" height="16">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${cfg.icon}"/>
                            </svg>
                            <span class="team-agent-role">${cfg.label}</span>
                            <span class="team-agent-status-badge idle">idle</span>
                        </div>
                        <div class="team-agent-purpose">${a.purpose || ''}</div>
                        <div class="team-agent-findings" style="display:none;"></div>
                    </div>
                `;
            }).join('');

            const panel = document.createElement('div');
            panel.id = `team-panel-${teamId}`;
            panel.className = 'team-panel';
            panel.innerHTML = `
                <div class="team-panel-header" onclick="toggleTeamPanel('${teamId}')">
                    <div class="team-panel-title">
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="18" height="18">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/>
                        </svg>
                        <span>Agent Team</span>
                        <span class="team-status-text">Spawned</span>
                    </div>
                    <svg class="team-panel-toggle" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="16" height="16">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                    </svg>
                </div>
                <div class="team-panel-body">
                    <div class="team-agents-grid">${agentCards}</div>
                    <div class="team-task-board" style="display:none;">
                        <div class="team-task-board-title">Task Board</div>
                        <div class="team-task-board-list"></div>
                    </div>
                    <div class="team-result" style="display:none;"></div>
                </div>
            `;
            chatContent.appendChild(panel);
            scrollToBottom();
        }

        // Update overall team status text
        function updateTeamStatus(teamId, status, text) {
            const panel = document.getElementById(`team-panel-${teamId}`);
            if (!panel) return;
            const statusEl = panel.querySelector('.team-status-text');
            if (statusEl) {
                statusEl.textContent = text;
                statusEl.className = `team-status-text ${status}`;
            }
        }

        // Render the task board within the team panel
        function renderTeamTaskBoard(teamId, tasks) {
            const panel = document.getElementById(`team-panel-${teamId}`);
            if (!panel) return;

            const boardEl = panel.querySelector('.team-task-board');
            const listEl = panel.querySelector('.team-task-board-list');
            if (!boardEl || !listEl) return;

            boardEl.style.display = 'block';
            listEl.innerHTML = tasks.map(t => {
                const cfg = getTeamRoleConfig(t.role);
                return `
                    <div class="team-task-item" data-task-agent="${t.assigned_to}" data-task-id="${t.task_id}">
                        <span class="team-task-status-dot pending"></span>
                        <span class="team-task-title">${t.title}</span>
                        <span class="team-task-role" style="color: ${cfg.color}">${cfg.label}</span>
                    </div>
                `;
            }).join('');

            // Also add any new agents that were spawned for tasks
            const agentsGrid = panel.querySelector('.team-agents-grid');
            if (agentsGrid) {
                for (const task of tasks) {
                    const existingCard = agentsGrid.querySelector(`[data-agent-id="${task.assigned_to}"]`);
                    if (!existingCard) {
                        const cfg = getTeamRoleConfig(task.role);
                        const card = document.createElement('div');
                        card.className = 'team-agent-card';
                        card.setAttribute('data-agent-id', task.assigned_to);
                        card.setAttribute('data-team-id', teamId);
                        card.style.setProperty('--agent-color', cfg.color);
                        card.innerHTML = `
                            <div class="team-agent-header">
                                <svg class="team-agent-icon" fill="none" stroke="${cfg.color}" viewBox="0 0 24 24" width="16" height="16">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${cfg.icon}"/>
                                </svg>
                                <span class="team-agent-role">${cfg.label}</span>
                                <span class="team-agent-status-badge idle">idle</span>
                            </div>
                            <div class="team-agent-purpose">${task.title}</div>
                            <div class="team-agent-findings" style="display:none;"></div>
                        `;
                        agentsGrid.appendChild(card);
                    }
                }
            }
            scrollToBottom();
        }

        // Update an agent card status
        function updateTeamAgent(teamId, agentId, role, status, taskTitle, content) {
            const panel = document.getElementById(`team-panel-${teamId}`);
            if (!panel) return;
            const card = panel.querySelector(`[data-agent-id="${agentId}"]`);
            if (!card) return;

            const badge = card.querySelector('.team-agent-status-badge');
            if (badge) {
                badge.textContent = status;
                badge.className = `team-agent-status-badge ${status}`;
            }

            // Add pulsing animation for active states
            if (status === 'thinking' || status === 'executing') {
                card.classList.add('active');
            } else {
                card.classList.remove('active');
            }

            // Show findings for complete/error
            if ((status === 'complete' || status === 'error') && content) {
                const findingsEl = card.querySelector('.team-agent-findings');
                if (findingsEl) {
                    const truncated = content.length > 300 ? content.substring(0, 300) + '...' : content;
                    findingsEl.textContent = truncated;
                    findingsEl.style.display = 'block';
                    findingsEl.classList.add(status === 'error' ? 'error' : 'success');
                }
            }

            // Update detail view if expanded
            const detailEl = card.querySelector('.agent-detail-content');
            if (detailEl && content) {
                detailEl.innerHTML = formatTeamAgentContent(content);
            }
            scrollToBottom();
        }

        // Update task board item status when agent completes
        function updateTeamTaskStatus(teamId, agentId, status) {
            const panel = document.getElementById(`team-panel-${teamId}`);
            if (!panel) return;
            const taskItem = panel.querySelector(`[data-task-agent="${agentId}"]`);
            if (!taskItem) return;
            const dot = taskItem.querySelector('.team-task-status-dot');
            if (dot) {
                dot.className = `team-task-status-dot ${status}`;
            }
        }

        // Render the final synthesized result
        function renderTeamResult(teamId, result, totalTokens) {
            const panel = document.getElementById(`team-panel-${teamId}`);
            if (!panel) return;
            const resultEl = panel.querySelector('.team-result');
            if (!resultEl) return;

            const tokenInfo = totalTokens ?
                `${totalTokens.input_tokens + totalTokens.output_tokens} tokens` : '';

            resultEl.style.display = 'block';
            resultEl.innerHTML = `
                <div class="team-result-header">
                    <span>Synthesized Result</span>
                    ${tokenInfo ? `<span class="team-result-tokens">${tokenInfo}</span>` : ''}
                </div>
                <div class="team-result-content">${escapeHtml(result).replace(/\n/g, '<br>')}</div>
            `;
            scrollToBottom();
        }

        // Toggle team panel collapsed state
        window.toggleTeamPanel = function(teamId) {
            const panel = document.getElementById(`team-panel-${teamId}`);
            if (panel) {
                panel.classList.toggle('collapsed');
            }
        };

        // Toggle agent card detail view
        window.toggleAgentDetail = function(cardEl, teamId, agentId) {
            // Toggle expanded class
            const isExpanded = cardEl.classList.toggle('expanded');

            // Find or create detail section
            let detail = cardEl.querySelector('.team-agent-detail');
            if (!detail) {
                detail = document.createElement('div');
                detail.className = 'team-agent-detail';
                detail.innerHTML = '<div class="agent-detail-content">Waiting for output...</div>';
                cardEl.appendChild(detail);
            }

            detail.style.display = isExpanded ? '' : 'none';
        };

        // Format agent detail content with basic markdown
        function formatTeamAgentContent(content) {
            if (!content) return '<span class="ansi-dim">No output yet...</span>';
            // Convert markdown-like content to HTML
            let html = escapeHtml(content);
            // Basic markdown: bold, code blocks, line breaks
            html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
            html = html.replace(/\n/g, '<br>');
            return html;
        }

        // Helper: escape HTML to prevent XSS
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
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
                        ${tu.result ? (tu.name === 'execute_command' && !tu.result.error ? `
                        <div class="tool-detail-section">
                            <div class="tool-detail-section-label">Output</div>
                            ${formatTerminalOutput(tu)}
                        </div>
                        ` : `
                        <div class="tool-detail-section">
                            <div class="tool-detail-section-label">Output</div>
                            <pre>${JSON.stringify(tu.result, null, 2)}</pre>
                        </div>
                        `) : `
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
                let isTerminalOutput = false;
                if (hasResult) {
                    // Detect execute_command tool for terminal-styled rendering
                    if (tu.name === 'execute_command' && tu.result && !hasError) {
                        isTerminalOutput = true;
                    }
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

                // Terminal-styled output for execute_command
                let outputHtml = '';
                if (hasResult && isTerminalOutput) {
                    outputHtml = formatTerminalOutput(tu);
                } else if (hasResult) {
                    outputHtml = `
                        <div class="chat-tool-section">
                            <div class="chat-tool-label">${hasError ? 'Error' : 'Output'}</div>
                            <pre class="chat-tool-code ${hasError ? 'error' : ''}">${escapeHtml(outputStr)}</pre>
                        </div>`;
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
                            ${outputHtml}
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

        // Convert ANSI escape codes to HTML spans
        function ansiToHtml(text) {
            if (!text) return '';
            // Escape HTML first
            let html = text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');

            // Map ANSI codes to CSS classes
            const ansiMap = {
                '0': '</span>',  // reset
                '1': '<span class="ansi-bold">',
                '2': '<span class="ansi-dim">',
                '30': '<span style="color:#414868">',  // black
                '31': '<span class="ansi-red">',
                '32': '<span class="ansi-green">',
                '33': '<span class="ansi-yellow">',
                '34': '<span class="ansi-blue">',
                '35': '<span class="ansi-magenta">',
                '36': '<span class="ansi-cyan">',
                '37': '<span class="ansi-white">',
                '90': '<span class="ansi-dim">',  // bright black (gray)
                '91': '<span class="ansi-red">',
                '92': '<span class="ansi-green">',
                '93': '<span class="ansi-yellow">',
                '94': '<span class="ansi-blue">',
                '95': '<span class="ansi-magenta">',
                '96': '<span class="ansi-cyan">',
                '97': '<span class="ansi-white">',
            };

            // Replace ANSI escape sequences
            html = html.replace(/\x1b\[([0-9;]+)m/g, (match, codes) => {
                const parts = codes.split(';');
                let result = '';
                for (const code of parts) {
                    if (ansiMap[code]) {
                        result += ansiMap[code];
                    }
                }
                return result || '';
            });

            // Remove any remaining escape sequences
            html = html.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '');

            return html;
        }

        // Format execute_command result as terminal output
        function formatTerminalOutput(tu) {
            const result = tu.result || {};
            const command = tu.input?.command || result.command || '';
            const exitCode = result.return_code;
            const stdout = result.stdout || '';
            const stderr = result.stderr || '';

            const exitCodeClass = (exitCode === 0) ? 'success' : 'error';
            const exitCodeText = exitCode !== undefined ? `exit ${exitCode}` : '';

            // Combine stdout and stderr with ANSI color conversion
            let outputContent = '';
            if (stdout) {
                outputContent += ansiToHtml(stdout);
            }
            if (stderr) {
                outputContent += `<span class="ansi-stderr">${ansiToHtml(stderr)}</span>`;
            }
            if (!outputContent) {
                outputContent = '<span class="ansi-dim">(no output)</span>';
            }

            return `
                <div class="chat-tool-section">
                    <div class="terminal-output">
                        <div class="terminal-header">
                            <span class="terminal-cmd">$ ${escapeHtml(command)}</span>
                            ${exitCodeText ? `<span class="terminal-exit-code ${exitCodeClass}">${exitCodeText}</span>` : ''}
                        </div>
                        ${outputContent}
                    </div>
                </div>`;
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
            'reset': { description: 'Force reset stuck sessions', handler: handleResetCommand },
            'terminal': { description: 'Execute a terminal command inline', handler: handleTerminalCommand },
        };

        // Handle /reset command - force reset stuck streaming states
        function handleResetCommand(args) {
            const resetCount = forceResetAllStreaming();
            if (resetCount > 0) {
                alert(`Reset ${resetCount} stuck session(s). You can now send messages.`);
            } else {
                alert('No stuck sessions found.');
            }
            return true;
        }

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

        // Handle /terminal command - execute command inline in chat
        // Supports natural language: /terminal 重复执行whoami -> parses to "whoami"
        async function handleTerminalCommand(args) {
            const input = args.trim();
            if (!input) {
                alert('Usage: /terminal <command>\nExample: /terminal ls -la\nAlso supports: /terminal 查看当前目录');
                return true;
            }
            
            // Try to parse the input (handles both commands and natural language)
            try {
                const res = await fetch(BASE_URL + '/v1/terminal/parse', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ input: input })
                });
                
                if (res.ok) {
                    const data = await res.json();
                    if (data.success && data.command) {
                        // If natural language was parsed, show what command will run
                        if (data.is_natural_language) {
                            console.log(`[NL Parse] "${input}" -> "${data.command}"`);
                        }
                        executeTerminalFromChat(data.command);
                    } else {
                        // Parse failed, try to execute as-is
                        console.warn('NL parse failed, executing as-is:', data.error);
                        executeTerminalFromChat(input);
                    }
                } else {
                    // API error, execute as-is
                    console.warn('NL parse API error, executing as-is');
                    executeTerminalFromChat(input);
                }
            } catch (e) {
                // Network error, execute as-is
                console.warn('NL parse network error, executing as-is:', e);
                executeTerminalFromChat(input);
            }
            
            return true;
        }

        async function sendMessage() {
            const input = document.getElementById('message-input');
            let content = input.value.trim();

            // Check if CURRENT conversation is streaming (allow other conversations to stream)
            if ((!content && attachments.length === 0) || isCurrentStreaming()) return;

            // Team mode check - route through teams API
            if (teamModeEnabled) {
                return sendTeamMessage(content);
            }

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

            // Handle #terminal — inject terminal panel output into chat as context
            if (content.trim() === '#terminal' || content.startsWith('#terminal ')) {
                input.value = '';
                input.style.height = 'auto';
                injectTerminalOutputToChat(content);
                return;
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

            // Detect and save interests from user message
            detectAndSaveInterests(content || textContent);

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
                // Note: timeout errors should NOT be treated as abort errors
                const isAbortError = e.name === 'AbortError' && !e.message?.includes('timeout');
                const isTimeoutError = e.message?.includes('timeout') || e.message?.includes('Timeout');

                if (isAbortError) {
                    // User switched away from this conversation - not a real error
                    console.log(`[${thisConvId}] Stream aborted (user switched away)`);
                    // Set to 'completed' instead of 'running' to allow sending new messages
                    updateConversationStatus(thisConvId, 'completed');
                } else if (isTimeoutError) {
                    // Timeout error - mark as error but allow retry
                    console.error(`[${thisConvId}] Stream timeout: ${e.message}`);
                    updateConversationStatus(thisConvId, 'error');
                    if (currentConversationId === thisConvId) {
                        updateStatus('error', 'Request timed out. Please try again.');
                        hideToolPanel();
                    }
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

            const model = settings.model || getDefaultModel();
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
            // Also strip internal fields like _imageRef that API doesn't recognize
            const filteredMessages = messages
                .filter(m => !m.isThinking)
                .filter(m => {
                    if (!m.content) return false;
                    if (typeof m.content === 'string' && m.content.trim() === '') return false;
                    if (Array.isArray(m.content) && m.content.length === 0) return false;
                    return true;
                })
                .map(m => {
                    // Clean content - remove internal fields like _imageRef
                    let cleanContent = m.content;
                    if (Array.isArray(m.content)) {
                        cleanContent = m.content.map(block => {
                            if (block.type === 'image' && block._imageRef) {
                                // Strip _imageRef, keep only API-compatible fields
                                return {
                                    type: 'image',
                                    source: block.source
                                };
                            }
                            return block;
                        });
                    }
                    return {
                        role: m.role,
                        content: cleanContent
                    };
                });

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

## CRITICAL RULE - NO EMOJIS (STRICTLY ENFORCED)

**ABSOLUTELY DO NOT use any emojis, emoticons, or unicode symbols in your responses.** This is a strict requirement:
- NO emoji characters (😀, 📁, ✅, ❌, 🎉, ✨, 📝, etc.)
- NO unicode symbols (✓, ✗, •, →, ★, etc.)
- Use plain text only: "Done", "Error", "Success", "-", "->", "*"
- This applies to ALL responses and ALL generated files

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
                    compact_model: settings.compactModel || getDefaultCompactModel(),  // Model for context compaction
                    session_id: convId  // Session ID for tool-results storage (matches session directory)
                };
                console.log(`[${convId}] Request body (streaming):`, JSON.stringify(requestBody).substring(0, 200));

                // Use native fetch for streaming (no retry wrapper)
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 900000); // 15 minute timeout for streaming (matches bedrock_read_timeout)

                // Link external abort signal
                if (abortSignal) {
                    abortSignal.addEventListener('abort', () => controller.abort());
                }

                // Use auto mode for server-side tool execution (faster)
                const apiEndpoint = AUTO_TOOL_EXECUTION ? '/v1/messages-auto' : '/v1/messages';
                // Only send anthropic-version header for Anthropic (Claude) models
                const reqHeaders = { 'Content-Type': 'application/json' };
                if (model.startsWith('claude-')) {
                    reqHeaders['anthropic-version'] = '2023-06-01';
                }
                const response = await fetch(`${BASE_URL}${apiEndpoint}`, {
                    method: 'POST',
                    headers: reqHeaders,
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

                        // Handle execute_command with run_in_background - show in Tasks panel
                        if (tu.name === 'execute_command' && result.task_id && result.status === 'running') {
                            if (tu.input && tu.input.command) result.command = tu.input.command;
                            if (tu.input && tu.input.description) result.description = tu.input.description;
                            await handleBackgroundCommand(convId, result);
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

                    // Update chat display (non-AUTO mode)
                    // Tool calls are shown in inline panel, not in chat message
                    if (textContent && currentConversationId === convId) {
                        const lastMsg = messages[messages.length - 1];
                        if (lastMsg && lastMsg.role === 'assistant') {
                            lastMsg.displayContent = textContent;
                            updateLastMessageContent(textContent);
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

                    // Handle special tools that need frontend processing (task, delegate_task, background commands)
                    for (const tu of toolUses) {
                        if (tu.result && typeof tu.result === 'object') {
                            // Handle task tool - launch background task in new session
                            if (tu.name === 'task' && tu.result.ui_action === 'launch_background_task') {
                                console.log(`[${convId}] AUTO mode: Launching background task for ${tu.name}`);
                                tu.result = await handleBackgroundTask(convId, tu.result);
                            }
                            // Handle execute_command with run_in_background - show in Tasks panel
                            if (tu.name === 'execute_command' && tu.result.task_id && tu.result.status === 'running') {
                                console.log(`[${convId}] AUTO mode: Background command detected: ${tu.result.task_id}`);
                                // Enrich result with command from tool input
                                if (tu.input && tu.input.command) {
                                    tu.result.command = tu.input.command;
                                }
                                if (tu.input && tu.input.description) {
                                    tu.result.description = tu.input.description;
                                }
                                await handleBackgroundCommand(convId, tu.result);
                            }
                            // Handle delegation tool
                            if (tu.name === 'delegate_task' && tu.result.ui_action === 'delegate_to_session') {
                                console.log(`[${convId}] AUTO mode: Handling delegation for ${tu.name}`);
                                tu.result = await handleDelegation(convId, tu.result);
                            }
                            // Handle other special UI actions
                            handleToolResultUI(tu.name, tu.result, convId);
                        }
                    }

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

                        // Update chat display - tool calls shown in inline panel, not in message
                        if (textContent && currentConversationId === convId) {
                            const lastMsg = messages[messages.length - 2]; // Assistant message before tool_result
                            if (lastMsg && lastMsg.role === 'assistant') {
                                lastMsg.displayContent = textContent;
                                updateLastMessageContent(textContent);
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

                    // Memory leak fix: Release canvas and image resources
                    // Setting dimensions to 0 releases GPU memory used by canvas
                    canvas.width = 0;
                    canvas.height = 0;
                    // Clear image source to release memory
                    img.src = '';
                    img.onload = null;
                    img.onerror = null;

                    resolve({
                        base64,
                        mediaType,
                        width,
                        height
                    });
                };
                img.onerror = () => {
                    // Clean up on error too
                    img.src = '';
                    img.onload = null;
                    img.onerror = null;
                    reject(new Error('Failed to load image'));
                };

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
                } else if (a.isTaskResult) {
                    // Show task result attachment with special style
                    return `
                        <div class="attachment task-result-attachment" title="Task: ${escapeHTML(a.name.replace('🔄 ', ''))}">
                            <svg class="file-icon" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                            </svg>
                            ${a.name}
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
            const modal = document.getElementById('settings-modal');
            modal.style.removeProperty('display');  // Clear any inline display override
            modal.classList.add('active');
            // Load default working directory
            document.getElementById('settings-default-workdir').value = defaultWorkingFolder || '~/Downloads';
            populateModelDropdowns();
            document.getElementById('settings-model').value = settings.model || getDefaultModel();
            document.getElementById('settings-max-tokens').value = settings.maxTokens || 16384;
            document.getElementById('settings-temperature').value = settings.temperature || 0.7;
            document.getElementById('temp-value').textContent = settings.temperature || 0.7;
            // Compact model setting (default to Haiku 4.5)
            document.getElementById('settings-compact-model').value = settings.compactModel || getDefaultCompactModel();
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
                saveWorkspaceCache();
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
            // Update token limits for the selected model
            updateTokenLimits(settings.model);
            // Save AWS credentials
            saveAwsSettings();
            // Save Memory settings
            saveMemorySettings();
        }

        function loadSettings() {
            migrateSettings();
            setTheme('light');
        }

        function migrateSettings() {
            let needsSave = false;

            // [Legacy migration] Migrate models removed from registry to latest equivalents
            const removedModelMigration = {
                'claude-3-haiku-20240307': 'claude-haiku-4-5-20251001',
                'claude-3-sonnet-20240229': 'claude-sonnet-4-5-20250929',
                'claude-3-opus-20240229': 'claude-opus-4-6',
                'claude-3-5-haiku-20241022': 'claude-haiku-4-5-20251001',
                'claude-3-5-sonnet-20241022': 'claude-sonnet-4-5-20250929',
                'claude-3-7-sonnet-20250219': 'claude-sonnet-4-5-20250929',
                'claude-sonnet-4-20250514': 'claude-sonnet-4-5-20250929',
                'claude-opus-4-20250514': 'claude-opus-4-6',
                'claude-opus-4-5-20251101': 'claude-opus-4-6',
                'deepseek-r1': 'deepseek-v3.2',
                'deepseek-v3.1': 'deepseek-v3.2',
                'minimax-m2': 'minimax-m2.1',
                'kimi-k2-thinking': 'kimi-k2.5',
                'qwen3-235b': 'qwen3-coder-480b',
                'qwen3-32b': 'qwen3-coder-480b',
                'qwen3-vl-235b': 'qwen3-coder-480b',
                'qwen3-coder-30b': 'qwen3-coder-480b',
                'glm-4.7-flash': 'glm-4.7',
            };
            if (removedModelMigration[settings.model]) {
                settings.model = removedModelMigration[settings.model];
                needsSave = true;
                console.log('[Settings Migration] model upgraded to', settings.model);
            }
            if (removedModelMigration[settings.compactModel]) {
                settings.compactModel = removedModelMigration[settings.compactModel];
                needsSave = true;
                console.log('[Settings Migration] compactModel upgraded to', settings.compactModel);
            }

            if (needsSave) {
                localStorage.setItem('settings', JSON.stringify(settings));
                console.log('[Settings Migration] Settings saved');
            }
        }

        function saveSettings() {
            localStorage.setItem('settings', JSON.stringify(settings));
        }

        // Cached model list from API
        let _availableModels = [];
        // Provider-grouped models from API (provider -> model[])
        let _modelsByProvider = {};
        // Default model IDs from API (avoids hardcoding)
        let _defaultModel = 'claude-opus-4-6';
        let _defaultCompactModel = 'claude-haiku-4-5-20251001';

        // Provider display names for optgroup headers
        const _providerLabels = {
            anthropic: 'Anthropic',
            deepseek: 'DeepSeek',
            minimax: 'MiniMax',
            moonshot: 'Moonshot (Kimi)',
            qwen: 'Qwen',
            zai: 'Z.AI (GLM)',
        };

        async function loadModelsFromAPI() {
            try {
                const res = await fetch(`${BASE_URL}/v1/models`);
                const data = await res.json();
                _availableModels = data.data || [];
                _modelsByProvider = data.models || {};
                if (data.default_model) _defaultModel = data.default_model;
                if (data.default_compact_model) _defaultCompactModel = data.default_compact_model;
                populateModelDropdowns();
                // Apply limits for current model
                updateTokenLimits(settings.model || _defaultModel);
            } catch (e) {
                console.warn('[Models] Failed to load from API, using defaults:', e.message);
            }
        }

        function getDefaultModel() {
            return _defaultModel;
        }

        function getDefaultCompactModel() {
            return _defaultCompactModel;
        }

        function populateModelDropdowns() {
            const modelSelect = document.getElementById('settings-model');
            const compactSelect = document.getElementById('settings-compact-model');
            if (!modelSelect || !compactSelect) return;
            if (!Object.keys(_modelsByProvider).length && !_availableModels.length) return;

            // Helper: populate a <select> with optgroup sections per provider
            function fillSelect(selectEl) {
                selectEl.innerHTML = '';
                const providers = Object.keys(_modelsByProvider);
                if (providers.length) {
                    for (const provider of providers) {
                        const group = document.createElement('optgroup');
                        group.label = _providerLabels[provider] || provider;
                        for (const m of _modelsByProvider[provider]) {
                            const opt = document.createElement('option');
                            opt.value = m.id;
                            opt.textContent = m.display_name;
                            group.appendChild(opt);
                        }
                        selectEl.appendChild(group);
                    }
                } else {
                    // Fallback: flat list (backward compat)
                    for (const m of _availableModels) {
                        const opt = document.createElement('option');
                        opt.value = m.id;
                        opt.textContent = m.display_name;
                        selectEl.appendChild(opt);
                    }
                }
            }

            fillSelect(modelSelect);
            fillSelect(compactSelect);

            // Set current values (fall back to default if stored model no longer exists)
            modelSelect.value = settings.model || _defaultModel;
            if (!modelSelect.value) {
                modelSelect.value = _defaultModel;
                settings.model = _defaultModel;
                saveSettings();
            }
            compactSelect.value = settings.compactModel || _defaultCompactModel;
            if (!compactSelect.value) {
                compactSelect.value = _defaultCompactModel;
                settings.compactModel = _defaultCompactModel;
                saveSettings();
            }

            // Listen for model change to update token limits
            modelSelect.addEventListener('change', () => {
                updateTokenLimits(modelSelect.value);
            });
        }

        function updateTokenLimits(modelId) {
            const model = _availableModels.find(m => m.id === modelId);
            if (model && model.context) {
                CONFIG.TOKENS.MAX_CONTEXT = model.context.max_context_tokens;
                CONFIG.TOKENS.WARNING_THRESHOLD = model.context.warning_threshold;
                CONFIG.TOKENS.COMPACT_THRESHOLD = model.context.compact_threshold;
                CONFIG.TOKENS.MAX_OUTPUT = model.context.max_output_tokens;
                // Update the max tokens input constraint to match the model's max output
                const maxTokensInput = document.getElementById('settings-max-tokens');
                if (maxTokensInput) {
                    maxTokensInput.max = model.context.max_output_tokens;
                }
                console.log(`[Models] Token limits updated for ${modelId}: ${CONFIG.TOKENS.MAX_CONTEXT.toLocaleString()} context, ${model.context.max_output_tokens.toLocaleString()} max output`);
            }
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
                // Load Memory config
                const memRes = await fetch(`${BASE_URL}/v1/config/memory`);
                const memData = await memRes.json();

                document.getElementById('settings-memory-enabled').checked = memData.memory_enabled !== false;
                document.getElementById('settings-memory-region').value = memData.memory_region || 'us-west-2';
                document.getElementById('settings-memory-id').value = memData.memory_id || '';

                // Load S3 config
                try {
                    const s3Res = await fetch(`${BASE_URL}/v1/config/s3`);
                    const s3Data = await s3Res.json();
                    document.getElementById('settings-s3-bucket').value = s3Data.s3_bucket || '';
                } catch (e) {
                    console.log('S3 config not available');
                }

                // LTM strategies only shown after user clicks Refresh
            } catch (e) {
                console.log('Failed to load Memory settings:', e);
            }
        }

        function displayLtmStrategies(ltmConfig) {
            const display = document.getElementById('ltm-strategies-display');

            if (!ltmConfig || !ltmConfig.strategies || ltmConfig.strategies.length === 0) {
                display.style.display = 'none';
                return;
            }

            display.style.display = 'block';

            const html = ltmConfig.strategies.map(strategy => {
                const unverifiedBadge = strategy.unverified
                    ? '<span class="ltm-strategy-unverified">Unverified</span>'
                    : '<span class="ltm-strategy-verified">✓</span>';
                return `
                    <div class="ltm-strategy-row ${strategy.unverified ? 'unverified' : ''}">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div class="ltm-strategy-name">${escapeHTML(strategy.name)}</div>
                            ${unverifiedBadge}
                        </div>
                        <span class="ltm-strategy-type">${escapeHTML(strategy.type)}</span>
                        <div class="ltm-strategy-namespace">${escapeHTML(strategy.namespace)}</div>
                    </div>
                `;
            }).join('');

            display.innerHTML = html;
        }

        async function refreshLtmStrategies() {
            const btn = document.getElementById('refresh-strategies-btn');
            const icon = document.getElementById('refresh-strategies-icon');

            // Show loading state
            btn.disabled = true;
            icon.classList.add('spinning');
            icon.textContent = '↻';

            try {
                // Save memory settings first so memory_id is persisted
                await saveMemorySettings();

                const response = await fetch(`${BASE_URL}/v1/config/memory/strategies/refresh`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });

                const result = await response.json();

                if (result.success && result.strategies) {
                    // Update display with new strategies
                    displayLtmStrategies({ strategies: result.strategies });
                    showNotification(`✓ Connected — ${result.strategies.length} strategies`, 'success');
                } else {
                    displayLtmStrategies(null);
                    showNotification(result.error || 'No strategies found', 'error');
                }
            } catch (e) {
                console.error('Failed to refresh strategies:', e);
                showNotification('Failed to connect to Memory', 'error');
            } finally {
                btn.disabled = false;
                icon.classList.remove('spinning');
            }
        }

        let _memorySaveTimer = null;
        async function saveMemorySettings() {
            const enabled = document.getElementById('settings-memory-enabled')?.checked;
            const memoryId = document.getElementById('settings-memory-id')?.value?.trim();
            const region = document.getElementById('settings-memory-region')?.value;
            const s3Bucket = document.getElementById('settings-s3-bucket')?.value?.trim();

            if (enabled === undefined) return; // settings modal not open

            try {
                // Save Memory config
                await fetch(`${BASE_URL}/v1/config/memory`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        memory_enabled: enabled,
                        memory_id: memoryId,
                        memory_region: region
                    })
                });

                // Save S3 config (same region as Memory)
                await fetch(`${BASE_URL}/v1/config/s3`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        s3_bucket: s3Bucket,
                        s3_region: region,
                        s3_enabled: enabled && s3Bucket ? true : false
                    })
                });

                console.log('Memory and S3 settings saved');
            } catch (e) {
                console.error('Failed to save settings:', e);
            }
        }

        // Auto-save memory/S3 settings on input change (debounced)
        function debouncedSaveMemorySettings() {
            if (_memorySaveTimer) clearTimeout(_memorySaveTimer);
            _memorySaveTimer = setTimeout(() => saveMemorySettings(), 800);
        }

        document.addEventListener('DOMContentLoaded', () => {
            const memoryFields = ['settings-memory-id', 'settings-memory-enabled', 'settings-memory-region', 'settings-s3-bucket'];
            for (const id of memoryFields) {
                const el = document.getElementById(id);
                if (el) {
                    el.addEventListener('change', debouncedSaveMemorySettings);
                    if (el.type === 'text' || el.tagName === 'INPUT') {
                        el.addEventListener('input', debouncedSaveMemorySettings);
                    }
                }
            }
        });

        // ==================== Memory Sync Status ====================
        let memorySyncStatusInterval = null;

        // Track last known good sync count
        let lastKnownSyncCount = 0;

        async function updateMemorySyncStatus() {
            const iconEl = document.getElementById('sync-icon');
            const textEl = document.getElementById('sync-text');

            if (!iconEl || !textEl) {
                return;
            }

            try {
                const res = await fetch(`${BASE_URL}/v1/memory/status`);
                const data = await res.json();

                // Update icon class
                iconEl.className = 'sync-icon';

                // Track last known good count
                if (data.sessions_synced > 0) {
                    lastKnownSyncCount = data.sessions_synced;
                }

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
                    case 'not_running':
                        iconEl.classList.add('disabled');
                        // Show last known count instead of alarming message
                        textEl.textContent = lastKnownSyncCount > 0
                            ? `Synced: ${lastKnownSyncCount} sessions`
                            : 'Memory: off';
                        break;
                    case 'error':
                        // Show warning state (yellow) instead of error (red)
                        iconEl.classList.add('syncing');
                        textEl.textContent = lastKnownSyncCount > 0
                            ? `Synced: ${lastKnownSyncCount} sessions`
                            : 'Sync paused';
                        break;
                    default:
                        iconEl.classList.add('disabled');
                        textEl.textContent = lastKnownSyncCount > 0
                            ? `Synced: ${lastKnownSyncCount} sessions`
                            : 'Memory: --';
                }

                // Add tooltip with details (only place to show technical details)
                document.getElementById('memory-sync-status').title =
                    `AgentCore Memory Sync\n` +
                    `Status: ${data.status || 'unknown'}\n` +
                    `Memory ID: ${data.memory_id || 'N/A'}\n` +
                    `Region: ${data.region || 'N/A'}\n` +
                    `Sessions: ${data.sessions_synced || 0}\n` +
                    `Total Events: ${data.total_events || 0}`;

            } catch (e) {
                // Network error - show last known count, don't alarm user
                console.error('[Memory] Error fetching status:', e);
                iconEl.className = 'sync-icon disabled';
                textEl.textContent = lastKnownSyncCount > 0
                    ? `Synced: ${lastKnownSyncCount} sessions`
                    : 'Memory: --';
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
                saveWorkspaceCache();
                console.log('Added default working folder to workspace:', defaultWorkingFolder);
            }
        }

        // Remove workspace folders whose paths no longer exist on disk
        async function pruneDeletedWorkingFolders() {
            if (workingFolders.length === 0) return;
            try {
                const response = await fetch(`${BASE_URL}/v1/config/check-paths`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(workingFolders)
                });
                if (!response.ok) return;
                const result = await response.json();
                const before = workingFolders.length;
                workingFolders = workingFolders.filter(f => result[f] !== false);
                if (workingFolders.length < before) {
                    console.log(`[Workspace] Pruned ${before - workingFolders.length} deleted folder(s)`);
                    // If default folder was deleted, clear it
                    if (defaultWorkingFolder && result[defaultWorkingFolder] === false) {
                        console.log(`[Workspace] Default folder deleted: ${defaultWorkingFolder}`);
                        defaultWorkingFolder = workingFolders[0] || '';
                    }
                    // If current working dir was deleted, switch to default
                    if (currentWorkingDir && result[currentWorkingDir] === false) {
                        console.log(`[Workspace] Current working dir deleted: ${currentWorkingDir}`);
                        currentWorkingDir = defaultWorkingFolder || workingFolders[0] || '';
                    }
                    saveWorkspaceCache();
                }
            } catch (e) {
                console.warn('[Workspace] Failed to check folder paths:', e.message);
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
            saveWorkspaceCache();

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
                console.log('Default folder cleared');
            } else {
                defaultWorkingFolder = folder;
                console.log('Default folder set to:', folder);
            }
            saveWorkspaceCache();
            renderWorkingFolders();
        }

        // Browse for default working directory (Settings dialog)
        async function browseDefaultWorkdir() {
            if (window.electronAPI?.selectFolder) {
                const folders = await window.electronAPI.selectFolder();
                if (folders && folders.length > 0) {
                    const folder = folders[0];
                    document.getElementById('settings-default-workdir').value = folder;
                    // Also update the variable and save to disk cache
                    defaultWorkingFolder = folder;
                    saveWorkspaceCache();
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
                        // If the requested folder doesn't exist on disk, fall back
                        if (data.exists === false) {
                            console.warn(`Working directory not found on disk: ${folder}`);
                            const fallback = defaultWorkingFolder || workingFolders[0] || '';
                            if (fallback && fallback !== folder) {
                                console.log(`Falling back to: ${fallback}`);
                                currentWorkingDir = fallback;
                                // Update the current conversation to use the fallback
                                if (currentConversationId) {
                                    const conv = conversations.find(c => c.id === currentConversationId);
                                    if (conv) conv.workingDir = fallback;
                                    const runtime = convRuntime[currentConversationId];
                                    if (runtime) runtime.workingDir = fallback;
                                }
                                updateWorkingDirDisplay(fallback);
                                renderWorkingFolders();
                                // Sync the fallback folder to the server
                                return updateServerWorkingDir(fallback, 1);
                            }
                        }
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
                    saveWorkspaceCache();
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
                        saveWorkspaceCache();
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
            saveWorkspaceCache();
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

        // ==================== Right Panel ====================
        let rightPanelOpen = false;
        let rightPanelWidth = 280;

        function initRightPanel() {
            const toggle = document.getElementById('right-panel-toggle');
            const panel = document.getElementById('right-panel');
            const resizeHandle = document.getElementById('right-panel-resize');

            if (!toggle || !panel) return;

            // Toggle panel
            toggle.addEventListener('click', () => {
                toggleRightPanel();
            });

            // Keyboard shortcut: Cmd/Ctrl + /
            document.addEventListener('keydown', (e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === '/') {
                    e.preventDefault();
                    toggleRightPanel();
                }
            });

            // Tab switching
            panel.querySelectorAll('.right-panel-tab').forEach(tab => {
                tab.addEventListener('click', () => {
                    const tabName = tab.dataset.tab;
                    switchRightPanelTab(tabName);
                });
            });

            // Resize handle
            if (resizeHandle) {
                let isResizing = false;
                let startX = 0;
                let startWidth = 0;

                resizeHandle.addEventListener('mousedown', (e) => {
                    isResizing = true;
                    startX = e.clientX;
                    startWidth = panel.offsetWidth;
                    resizeHandle.classList.add('dragging');
                    document.body.style.cursor = 'ew-resize';
                    document.body.style.userSelect = 'none';
                    e.preventDefault();
                });

                document.addEventListener('mousemove', (e) => {
                    if (!isResizing) return;
                    const diff = startX - e.clientX;
                    const maxW = Math.floor(window.innerWidth * 0.7);
                    const newWidth = Math.min(maxW, Math.max(200, startWidth + diff));
                    panel.style.width = newWidth + 'px';
                    rightPanelWidth = newWidth;
                });

                document.addEventListener('mouseup', () => {
                    if (isResizing) {
                        isResizing = false;
                        resizeHandle.classList.remove('dragging');
                        document.body.style.cursor = '';
                        document.body.style.userSelect = '';
                    }
                });
            }
        }

        function toggleRightPanel() {
            const toggle = document.getElementById('right-panel-toggle');
            const panel = document.getElementById('right-panel');
            if (!panel) return;

            rightPanelOpen = !rightPanelOpen;
            panel.classList.toggle('hidden', !rightPanelOpen);
            if (toggle) toggle.classList.toggle('active', rightPanelOpen);

            if (rightPanelOpen) {
                panel.style.width = rightPanelWidth + 'px';
                // Update tasks when opening
                updateRightPanelTasks();
            }

            // Update overdue notification positions
            updateOverdueNotificationPositions();
        }

        function switchRightPanelTab(tabName) {
            const panel = document.getElementById('right-panel');
            if (!panel) return;

            // Update tab buttons
            panel.querySelectorAll('.right-panel-tab').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.tab === tabName);
            });

            // Update sections
            panel.querySelectorAll('.right-panel-section').forEach(section => {
                const sectionId = section.id.replace('panel-', '');
                section.classList.toggle('active', sectionId === tabName);
            });

            // Load SSH config when switching to terminal tab
            if (tabName === 'terminal') {
                loadSSHConfig();
            }
        }

        // Update tasks in right panel
        function updateRightPanelTasks() {
            const tasksList = document.getElementById('panel-tasks-list');
            if (!tasksList) return;

            const taskIds = Object.keys(backgroundTasks);
            const runningTasks = taskIds.filter(id => backgroundTasks[id].status === 'running');

            if (taskIds.length === 0) {
                tasksList.innerHTML = `
                    <div class="panel-placeholder">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.5">
                            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                        </svg>
                        <span>No background tasks</span>
                    </div>
                `;
                return;
            }

            // Sort: running first, then by start time
            const sortedIds = taskIds.sort((a, b) => {
                const taskA = backgroundTasks[a];
                const taskB = backgroundTasks[b];
                if (taskA.status === 'running' && taskB.status !== 'running') return -1;
                if (taskB.status === 'running' && taskA.status !== 'running') return 1;
                return taskB.startedAt - taskA.startedAt;
            });

            tasksList.innerHTML = sortedIds.map(taskId => {
                const task = backgroundTasks[taskId];
                const elapsed = Math.floor((Date.now() - task.startedAt) / 1000);
                const statusClass = task.status;

                let statusHtml = '';
                if (task.status === 'running') {
                    statusHtml = `<div class="spinner"></div><span>${formatDuration(elapsed)}</span>`;
                } else if (task.status === 'completed') {
                    const duration = task.completedAt ? Math.floor((task.completedAt - task.startedAt) / 1000) : elapsed;
                    statusHtml = `<span>✓ Done (${formatDuration(duration)})</span>`;
                } else if (task.status === 'cancelled') {
                    const duration = task.completedAt ? Math.floor((task.completedAt - task.startedAt) / 1000) : elapsed;
                    statusHtml = `<span>⊘ Cancelled (${formatDuration(duration)})</span>`;
                } else if (task.status === 'error') {
                    statusHtml = `<span>✗ Failed</span>`;
                }

                // All tasks can be dragged
                const isDraggable = true;

                return `
                    <div class="panel-task-item ${statusClass}" data-task-id="${taskId}" ${isDraggable ? 'draggable="true"' : ''}>
                        <div class="panel-task-row">
                            <div class="panel-task-info">
                                <div class="panel-task-name" title="${escapeHTML(task.description)}">${escapeHTML(task.description)}</div>
                                <div class="panel-task-status ${statusClass}">${statusHtml}</div>
                            </div>
                            <div class="panel-task-actions">
                                ${task.targetConvId ? `<button class="panel-task-btn goto" data-task-id="${taskId}" title="View session">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                                        <polyline points="15 3 21 3 21 9"/>
                                        <line x1="10" y1="14" x2="21" y2="3"/>
                                    </svg>
                                </button>` : ''}
                                ${task.status === 'running' ? `
                                    <button class="panel-task-btn cancel" data-task-id="${taskId}" title="Cancel">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <line x1="18" y1="6" x2="6" y2="18"/>
                                            <line x1="6" y1="6" x2="18" y2="18"/>
                                        </svg>
                                    </button>
                                ` : `
                                    <button class="panel-task-btn cancel" data-task-id="${taskId}" title="Remove">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <line x1="18" y1="6" x2="6" y2="18"/>
                                            <line x1="6" y1="6" x2="18" y2="18"/>
                                        </svg>
                                    </button>
                                `}
                            </div>
                        </div>
                        ${task.status === 'running' ? '<div class="panel-task-progress"><div class="panel-task-progress-bar" style="width: 100%"></div></div>' : ''}
                    </div>
                `;
            }).join('');

            // Add event delegation for buttons
            tasksList.querySelectorAll('.panel-task-btn.goto').forEach(btn => {
                btn.onclick = (e) => {
                    e.stopPropagation();
                    const taskId = btn.dataset.taskId;
                    const task = backgroundTasks[taskId];
                    if (task && task.targetConvId) {
                        loadConversation(task.targetConvId);
                    }
                };
            });

            tasksList.querySelectorAll('.panel-task-btn.cancel').forEach(btn => {
                btn.onclick = (e) => {
                    e.stopPropagation();
                    const taskId = btn.dataset.taskId;
                    const task = backgroundTasks[taskId];
                    if (task) {
                        if (task.status === 'running') {
                            cancelBgTask(taskId);
                        } else {
                            removeBgTask(taskId);
                        }
                    }
                };
            });

            // Add drag event handlers for completed tasks
            tasksList.querySelectorAll('.panel-task-item[draggable="true"]').forEach(item => {
                item.addEventListener('dragstart', (e) => {
                    const taskId = item.dataset.taskId;
                    const task = backgroundTasks[taskId];
                    if (task) {
                        item.classList.add('dragging');
                        e.dataTransfer.effectAllowed = 'copy';
                        // Use same format as files - JSON array with special task marker
                        const taskData = [{
                            isTask: true,
                            taskId: taskId,
                            name: task.description,
                            sessionNumber: task.targetSessionNumber,
                            targetConvId: task.targetConvId
                        }];
                        e.dataTransfer.setData('text/plain', JSON.stringify(taskData));
                    }
                });

                item.addEventListener('dragend', () => {
                    item.classList.remove('dragging');
                });
            });
        }

        // Add task result as attachment (similar to file attachment)
        function addTaskToAttachments(taskData) {
            // Check if already attached
            const alreadyAttached = attachments.some(a => a.taskId === taskData.taskId);
            if (alreadyAttached) return;

            attachments.push({
                name: `${taskData.name}`,
                type: 'application/x-task-result',
                taskId: taskData.taskId,
                sessionNumber: taskData.sessionNumber,
                targetConvId: taskData.targetConvId,
                isTaskResult: true
            });

            renderAttachments();
            document.getElementById('send-btn').disabled = false;
        }

        // Add news to input field for asking about
        function addNewsToInput(newsData) {
            const input = document.getElementById('message-input');
            if (!input) return;

            // Format news as a reference in the input
            const newsRef = `[${newsData.title}](${newsData.url})`;

            // Insert at cursor position or append
            if (input.value) {
                input.value = input.value + '\n\n' + newsRef;
            } else {
                input.value = newsRef;
            }

            // Trigger input event to resize textarea
            input.dispatchEvent(new Event('input', { bubbles: true }));

            // Enable send button
            document.getElementById('send-btn').disabled = false;
        }

        // Initialize right panel on page load
        document.addEventListener('DOMContentLoaded', initRightPanel);

        // ==================== News Panel ====================
        let newsItems = [];
        let newsLastUpdated = null;
        let newsRefreshInterval = null;
        const NEWS_REFRESH_INTERVAL = 60 * 60 * 1000; // 1 hour

        function initNewsPanel() {
            // Load user interests
            loadUserInterests();

            // Load news on startup
            refreshNews();

            // Set up hourly auto-refresh
            newsRefreshInterval = setInterval(refreshNews, NEWS_REFRESH_INTERVAL);
        }

        async function loadUserInterests() {
            try {
                const res = await fetch(BASE_URL + '/v1/news/interests');
                const data = await res.json();
                if (data.success) {
                    renderInterestTags(data.interests);
                }
            } catch (e) {
                console.error('Failed to load interests:', e);
            }
        }

        function renderInterestTags(interests) {
            const container = document.getElementById('news-interests-tags');
            if (!container) return;

            if (!interests || interests.length === 0) {
                container.innerHTML = '<span class="news-interest-hint">Say "\u6211\u5173\u6CE8..." in chat to add</span>';
                return;
            }

            container.innerHTML = interests.map(interest =>
                `<span class="news-interest-tag">
                    ${escapeHTML(interest)}
                    <button class="news-interest-remove" onclick="removeInterest('${escapeHTML(interest).replace(/'/g, "\\'")}')" title="Remove">\u00d7</button>
                </span>`
            ).join('');
        }

        async function removeInterest(interest) {
            try {
                await fetch(BASE_URL + '/v1/news/interests/' + encodeURIComponent(interest), { method: 'DELETE' });
                loadUserInterests();
                // Refresh news with updated interests
                refreshNews(true);
            } catch (e) {
                console.error('Failed to remove interest:', e);
            }
        }

        async function addUserInterests(interests) {
            try {
                const res = await fetch(BASE_URL + '/v1/news/interests', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ interests })
                });
                const data = await res.json();
                if (data.success) {
                    renderInterestTags(data.interests);
                    // Refresh news with new interests
                    refreshNews(true);
                }
            } catch (e) {
                console.error('Failed to add interests:', e);
            }
        }

        function detectAndSaveInterests(message) {
            if (!message) return;

            const patterns = [
                /\u6211\u5173\u6CE8(.+)/,
                /\u6211\u60F3\u5173\u6CE8(.+)/,
                /\u5173\u6CE8\u4E00\u4E0B(.+)/,
                /\u6211\u5BF9(.+?)(?:\u611F\u5174\u8DA3|\u5F88\u611F\u5174\u8DA3)/,
                /\u5E2E\u6211\u5173\u6CE8(.+)/,
                /\u6211\u60F3\u4E86\u89E3(.+)/,
                /i'?m interested in (.+)/i,
                /i want to follow (.+)/i,
                /keep me updated on (.+)/i,
                /track news about (.+)/i,
            ];

            for (const pattern of patterns) {
                const match = message.match(pattern);
                if (match) {
                    let topicStr = match[1].trim();
                    // Remove trailing punctuation and connectors
                    topicStr = topicStr.replace(/[\u3002.!\uFF01?\uFF1F\u7684\u76F8\u5173\u65B0\u95FB\u52A8\u6001\u65B9\u9762\u5185\u5BB9]+$/g, '');
                    // Split by delimiters
                    const topics = topicStr.split(/[,\uFF0C\u3001;\uFF1B\u548C\u4E0E\u53CA&\s]+/).filter(t => t.trim().length > 1).map(t => t.trim());
                    if (topics.length > 0) {
                        addUserInterests(topics);
                        console.log('Detected interests:', topics);
                    }
                    break;
                }
            }
        }

        let newsPollingTimer = null;

        async function refreshNews(force = false) {
            const list = document.getElementById('panel-news-list');
            const updatedEl = document.getElementById('news-updated');
            const refreshBtn = document.querySelector('.news-refresh-btn');

            if (!list) return;

            // Show loading state
            if (refreshBtn) refreshBtn.classList.add('spinning');

            // Only show loading placeholder if we have no cached news
            if (newsItems.length === 0) {
                list.innerHTML = `
                    <div class="panel-placeholder">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.5">
                            <path d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 12h10"/>
                        </svg>
                        <span>Loading personalized news...</span>
                        <span class="news-hint">Reading your interests from memory...</span>
                    </div>
                `;
            }

            try {
                const m = encodeURIComponent(settings.model || getDefaultModel());
                const customTopics = '';  // Now handled server-side via interests
                let url = force ? `${BASE_URL}/v1/news/fetch?force=true&model=${m}` : `${BASE_URL}/v1/news/fetch?model=${m}`;
                if (customTopics) url += `&topics=${encodeURIComponent(customTopics)}`;
                const response = await fetch(url);
                const data = await response.json();

                // Handle async loading status
                if (data.status === 'loading') {
                    // Task is running, poll for results
                    if (updatedEl) {
                        updatedEl.textContent = 'Fetching personalized news...';
                    }
                    // Start polling if not already
                    if (!newsPollingTimer) {
                        newsPollingTimer = setTimeout(() => {
                            newsPollingTimer = null;
                            refreshNews();
                        }, 3000); // Poll every 3 seconds
                    }
                    // Show cached news if available
                    if (data.news && data.news.length > 0) {
                        newsItems = data.news;
                        updateNewsPanel();
                    }
                    return; // Keep spinner spinning
                }

                // Clear polling timer
                if (newsPollingTimer) {
                    clearTimeout(newsPollingTimer);
                    newsPollingTimer = null;
                }

                if (refreshBtn) refreshBtn.classList.remove('spinning');

                if (data.success && data.news && data.news.length > 0) {
                    newsItems = data.news;
                    newsLastUpdated = new Date(data.timestamp) || new Date();
                    updateNewsPanel();
                    if (updatedEl) {
                        const cached = data.cached ? ' (cached)' : '';
                        updatedEl.textContent = `Updated: ${newsLastUpdated.toLocaleTimeString()}${cached}`;
                    }
                    // Show topics
                    if (data.topics && data.topics.length > 0) {
                        console.log('News topics from LTM:', data.topics);
                    }
                } else if (data.success && (!data.news || data.news.length === 0)) {
                    list.innerHTML = `
                        <div class="panel-placeholder">
                            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.5">
                                <path d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 12h10"/>
                            </svg>
                            <span>No news available</span>
                            <span class="news-hint">Configure LTM in Settings to personalize</span>
                        </div>
                    `;
                    if (updatedEl) {
                        updatedEl.textContent = `Checked: ${new Date().toLocaleTimeString()}`;
                    }
                } else {
                    list.innerHTML = `
                        <div class="news-error">
                            <span>Failed to load news</span>
                            <span class="news-hint">${data.error || 'Unknown error'}</span>
                        </div>
                    `;
                }
            } catch (err) {
                if (refreshBtn) refreshBtn.classList.remove('spinning');
                if (newsPollingTimer) {
                    clearTimeout(newsPollingTimer);
                    newsPollingTimer = null;
                }
                console.error('News fetch error:', err);
                list.innerHTML = `
                    <div class="news-error">
                        <span>Network error</span>
                        <span class="news-hint">Check if the server is running</span>
                    </div>
                `;
            }
        }

        function updateNewsPanel() {
            const list = document.getElementById('panel-news-list');
            if (!list || newsItems.length === 0) return;

            list.innerHTML = newsItems.map((item, index) => `
                <div class="news-item" draggable="true" data-news-index="${index}">
                    <div class="news-item-header">
                        <div class="news-item-topic">${escapeHTML(item.topic || 'News')}</div>
                        <div class="news-drag-hint" title="Drag to chat">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" opacity="0.4">
                                <circle cx="9" cy="5" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="9" cy="19" r="1"/>
                                <circle cx="15" cy="5" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="19" r="1"/>
                            </svg>
                        </div>
                    </div>
                    <a href="${escapeHTML(item.url)}" class="news-item-title" target="_blank"
                       onclick="openExternalLink('${escapeHTML(item.url)}'); return false;">
                        ${escapeHTML(item.title)}
                    </a>
                    <div class="news-item-desc">${escapeHTML(item.description || '')}</div>
                    <div class="news-item-meta">
                        <span class="news-item-source">${escapeHTML(item.source || 'Unknown')}</span>
                        <span class="news-item-time">${formatNewsTime(item.publishedAt)}</span>
                    </div>
                </div>
            `).join('');

            // Add drag event handlers for news items
            list.querySelectorAll('.news-item[draggable="true"]').forEach(item => {
                item.addEventListener('dragstart', (e) => {
                    const newsIndex = parseInt(item.dataset.newsIndex);
                    const news = newsItems[newsIndex];
                    if (news) {
                        item.classList.add('dragging');
                        e.dataTransfer.effectAllowed = 'copy';
                        // Set drag data - news info as JSON
                        const newsData = [{
                            isNews: true,
                            title: news.title,
                            description: news.description,
                            url: news.url,
                            source: news.source,
                            topic: news.topic
                        }];
                        e.dataTransfer.setData('text/plain', JSON.stringify(newsData));
                    }
                });

                item.addEventListener('dragend', () => {
                    item.classList.remove('dragging');
                });
            });
        }

        function formatNewsTime(timeStr) {
            if (!timeStr) return '';

            // If it's already a relative time string (e.g., "2 hours ago")
            if (timeStr.includes('ago') || timeStr.includes('hour') || timeStr.includes('day') || timeStr.includes('minute')) {
                return timeStr;
            }

            // Try to parse as date
            try {
                const date = new Date(timeStr);
                if (isNaN(date.getTime())) return timeStr;

                const now = new Date();
                const diff = now - date;
                const hours = Math.floor(diff / (1000 * 60 * 60));
                const days = Math.floor(hours / 24);

                if (hours < 1) return 'Just now';
                if (hours < 24) return `${hours}h ago`;
                if (days < 7) return `${days}d ago`;
                return date.toLocaleDateString();
            } catch {
                return timeStr;
            }
        }

        function openExternalLink(url) {
            if (window.electronAPI?.openExternal) {
                window.electronAPI.openExternal(url);
            } else {
                window.open(url, '_blank');
            }
        }

        // Initialize news panel on page load
        document.addEventListener('DOMContentLoaded', initNewsPanel);

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

            // Get dragged data
            const data = event.dataTransfer.getData('text/plain');
            if (!data) return;

            try {
                const items = JSON.parse(data);
                if (items.length === 0) return;

                // Check if this is a task drop
                if (items[0].isTask) {
                    for (const task of items) {
                        addTaskToAttachments(task);
                    }
                    document.getElementById('message-input')?.focus();
                    return;
                }

                // Check if this is a news drop
                if (items[0].isNews) {
                    for (const news of items) {
                        addNewsToInput(news);
                    }
                    document.getElementById('message-input')?.focus();
                    return;
                }

                // Otherwise it's a file drop
                selectedFiles = items;
                addSelectedFilesToAttachments();

                // Focus input
                document.getElementById('message-input')?.focus();
            } catch (e) {
                console.error('Failed to parse dragged data:', e);
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
            const allDone = completed === todos.length && todos.length > 0;
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
                <div class="inline-tasks-header" onclick="toggleInlineTasks(this.parentElement)" style="cursor:pointer">
                    <div style="display:flex;align-items:center;gap:6px">
                        <span class="inline-tasks-chevron ${allDone ? 'collapsed' : ''}">▾</span>
                        <h4>📋 Tasks</h4>
                    </div>
                    <span class="inline-tasks-progress ${allDone ? 'all-done' : ''}">${completed}/${todos.length}${allDone ? ' ✓' : ''}</span>
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

            // Auto-collapse after all tasks complete
            if (allDone) {
                setTimeout(() => {
                    const container = document.querySelector('.inline-tasks');
                    if (container && !container.classList.contains('manually-expanded')) {
                        container.classList.add('collapsed');
                        const chevron = container.querySelector('.inline-tasks-chevron');
                        if (chevron) chevron.classList.add('collapsed');
                    }
                }, 1500);
            }
        }

        function toggleInlineTasks(container) {
            if (!container) return;
            const isCollapsed = container.classList.toggle('collapsed');
            container.classList.toggle('manually-expanded', !isCollapsed);
            const chevron = container.querySelector('.inline-tasks-chevron');
            if (chevron) {
                chevron.classList.toggle('collapsed', isCollapsed);
            }
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

        // Background task registry for tracking async tasks
        const backgroundTasks = {};

        // Handle subagent task from task tool (TRUE ASYNC - doesn't block SSE connection)
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

                console.log(`[BackgroundTask] Starting task ${task_id} in Session #${targetSessionNumber} (async)`);

                // Register the task
                backgroundTasks[task_id] = {
                    status: 'running',
                    sourceConvId,
                    targetConvId,
                    targetSessionNumber,
                    description,
                    startedAt: Date.now(),
                    result: null
                };

                // Update panel and start progress tracking
                updateBgTasksPanel();
                startBgTasksProgressUpdate();

                // Execute in background - DON'T await!
                executeSubagentTaskAsync(targetConvId, prompt, task_id, description, sourceConvId)
                    .then(result => {
                        // Don't overwrite if already cancelled
                        if (backgroundTasks[task_id].status !== 'cancelled') {
                            backgroundTasks[task_id].status = 'completed';
                            backgroundTasks[task_id].result = result;
                            backgroundTasks[task_id].completedAt = Date.now();
                            console.log(`[BackgroundTask] Task ${task_id} completed`);

                            // Auto-inject result into source session if it's idle
                            injectBackgroundTaskResult(sourceConvId, task_id, result);
                        } else {
                            console.log(`[BackgroundTask] Task ${task_id} was cancelled, not injecting result`);
                        }

                        // Update panel
                        updateBgTasksPanel();
                    })
                    .catch(error => {
                        // Don't overwrite if already cancelled
                        if (backgroundTasks[task_id].status !== 'cancelled') {
                            backgroundTasks[task_id].status = 'error';
                            backgroundTasks[task_id].error = error.message;
                        }
                        backgroundTasks[task_id].completedAt = Date.now();
                        console.error(`[BackgroundTask] Task ${task_id} failed:`, error);

                        // Update panel
                        updateBgTasksPanel();
                    });

                // Return immediately - don't wait!
                return {
                    type: "background_task_started",
                    task_id,
                    status: "running",
                    target_session: targetSessionNumber,
                    description,
                    message: `Task started in Session #${targetSessionNumber}. Running in background - you can continue working. Use get_background_task_status("${task_id}") to check progress.`
                };

            } catch (error) {
                console.error(`[BackgroundTask] Error starting task:`, error);
                return {
                    type: "background_task_error",
                    task_id,
                    status: "error",
                    error: error.message
                };
            }
        }

        // Handle background command from execute_command with run_in_background=true
        // Shows the command in the Tasks panel and polls for completion
        async function handleBackgroundCommand(sourceConvId, commandResult) {
            const { task_id, output_file } = commandResult;
            // Use a short description: prefer the tool's description, then command, then message
            const description = commandResult.description || commandResult.command || 'Background command';

            // Get working directory from source session for resolving relative paths
            const sourceRuntime = getConvRuntime(sourceConvId);
            const workingDir = (sourceRuntime && sourceRuntime.workingDir) || '';

            console.log(`[BackgroundCommand] Registering command task ${task_id}: ${description} (cwd: ${workingDir})`);

            // Register in backgroundTasks
            backgroundTasks[task_id] = {
                status: 'running',
                sourceConvId,
                targetConvId: null,
                targetSessionNumber: null,
                description,
                startedAt: Date.now(),
                result: null,
                type: 'command',
                outputFile: output_file,
                workingDir: workingDir
            };

            // Update panel and start progress tracking
            updateBgTasksPanel();
            startBgTasksProgressUpdate();

            // Poll for completion in background (don't await)
            pollBackgroundCommand(task_id, sourceConvId);

            // Return original result so the model sees it
            return commandResult;
        }

        // Poll background command status via get_task_status tool
        function pollBackgroundCommand(taskId, sourceConvId) {
            const pollId = setInterval(async () => {
                try {
                    const status = await executeTool('get_task_status', { task_id: taskId });

                    if (status.status === 'completed') {
                        clearInterval(pollId);

                        backgroundTasks[taskId].status = 'completed';
                        backgroundTasks[taskId].completedAt = Date.now();
                        backgroundTasks[taskId].result = status.output || '';
                        backgroundTasks[taskId].returnCode = status.return_code;

                        console.log(`[BackgroundCommand] Task ${taskId} completed (rc=${status.return_code})`);

                        // Inject result into source session
                        injectCommandTaskResult(sourceConvId, taskId, status);
                        updateBgTasksPanel();
                    } else if (status.error && !status.output_file) {
                        // Real error (not just "still running")
                        clearInterval(pollId);

                        backgroundTasks[taskId].status = 'error';
                        backgroundTasks[taskId].completedAt = Date.now();
                        backgroundTasks[taskId].error = status.error;

                        updateBgTasksPanel();
                    }
                } catch (e) {
                    console.error(`[BackgroundCommand] Poll error for ${taskId}:`, e);
                }
            }, 2000);
        }

        // Resolve relative paths in text to absolute paths using working directory
        function resolveRelativePaths(text, workingDir) {
            if (!text || !workingDir) return text;
            // Resolve ./path and ../path patterns to absolute paths
            return text.replace(/(^|\s)(\.\.?\/[^\s"'`)<>\n]+)/gm, (match, prefix, relPath) => {
                let absPath;
                if (relPath.startsWith('./')) {
                    absPath = workingDir + '/' + relPath.slice(2);
                } else if (relPath.startsWith('../')) {
                    // Simple parent resolution
                    const parentDir = workingDir.replace(/\/[^/]+$/, '');
                    absPath = parentDir + '/' + relPath.slice(3);
                } else {
                    return match;
                }
                // Normalize double slashes
                absPath = absPath.replace(/\/+/g, '/');
                return prefix + absPath;
            });
        }

        // Inject command task result into chat
        function injectCommandTaskResult(sourceConvId, taskId, status) {
            try {
                const sourceRuntime = getConvRuntime(sourceConvId);
                if (!sourceRuntime) return;

                const task = backgroundTasks[taskId];
                const duration = task.completedAt ? ((task.completedAt - task.startedAt) / 1000).toFixed(1) : '?';
                let output = status.output || '(no output)';
                const rc = status.return_code;

                // Resolve relative paths in output to absolute paths
                if (task.workingDir) {
                    output = resolveRelativePaths(output, task.workingDir);
                }

                const resultMessage = {
                    role: 'assistant',
                    content: `## ${rc === 0 ? '后台任务完成 ✓' : '后台任务失败 ✗'}\n\n**任务**: ${task.description}\n**耗时**: ${duration}s\n\n---\n\n${output}`,
                    isBackgroundTaskResult: true,
                    taskId: taskId
                };

                // Only inject if not currently streaming
                if (!sourceRuntime.isStreaming) {
                    sourceRuntime.messages.push(resultMessage);
                    saveConversation(sourceConvId);
                    if (currentConversationId === sourceConvId) {
                        renderMessages();
                    }
                }
            } catch (e) {
                console.error(`[BackgroundCommand] Error injecting result for ${taskId}:`, e);
            }
        }

        // Execute subagent task asynchronously
        async function executeSubagentTaskAsync(targetConvId, prompt, taskId, description, sourceConvId) {
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

                // Execute the conversation
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

                console.log(`[BackgroundTask] Task ${taskId} completed in Session #${targetSessionNum}`);

                return formatSubagentResult(taskId, description, targetSessionNum, responseContent);

            } catch (error) {
                console.error(`[BackgroundTask] Error executing task ${taskId}:`, error);
                return formatSubagentError(taskId, description, error.message);

            } finally {
                targetRuntime.isStreaming = false;
                updateConversationStatus(targetConvId, 'idle');
                renderConversations();
            }
        }

        // Inject background task result into source session
        function injectBackgroundTaskResult(sourceConvId, taskId, result) {
            const sourceRuntime = getConvRuntime(sourceConvId);
            if (!sourceRuntime) return;

            const task = backgroundTasks[taskId];
            const duration = task.completedAt ? ((task.completedAt - task.startedAt) / 1000).toFixed(1) : '?';

            // Extract the actual output from the result
            let outputContent = '';
            if (result && result.result) {
                // Parse the subagent result XML-like structure
                const resultStr = typeof result.result === 'string' ? result.result : JSON.stringify(result.result);
                // Extract content between <output> tags if present
                const outputMatch = resultStr.match(/<output>([\s\S]*?)<\/output>/);
                if (outputMatch) {
                    outputContent = outputMatch[1].trim();
                } else {
                    outputContent = resultStr;
                }
            }

            // Create a result message to inject
            const resultMessage = {
                role: 'assistant',
                content: `## 后台任务完成 ✓\n\n**任务**: ${task.description}\n**耗时**: ${duration}s\n**会话**: #${task.targetSessionNumber}\n\n---\n\n${outputContent}`,
                isBackgroundTaskResult: true,
                taskId: taskId
            };

            // Only inject if source session is idle (not currently streaming)
            if (sourceRuntime.isStreaming) {
                console.log(`[BackgroundTask] Source session busy, will inject when idle`);
                // Store pending injection
                if (!sourceRuntime.pendingTaskResults) {
                    sourceRuntime.pendingTaskResults = [];
                }
                sourceRuntime.pendingTaskResults.push(resultMessage);
                return;
            }

            // Inject the result message
            sourceRuntime.messages.push(resultMessage);
            console.log(`[BackgroundTask] Injected result for task ${taskId} (took ${duration}s)`);

            // Save and re-render if viewing this conversation
            saveConversation(sourceConvId);
            if (currentConversationId === sourceConvId) {
                renderMessages();
            }
        }

        // Get background task status (can be called by Claude)
        function getBackgroundTaskStatus(taskId) {
            const task = backgroundTasks[taskId];
            if (!task) {
                return { error: `Unknown task: ${taskId}` };
            }

            const result = {
                task_id: taskId,
                status: task.status,
                target_session: task.targetSessionNumber,
                description: task.description,
                started_at: new Date(task.startedAt).toISOString(),
                duration_ms: Date.now() - task.startedAt
            };

            if (task.status === 'completed') {
                result.completed_at = new Date(task.completedAt).toISOString();
                result.result = task.result;
            } else if (task.status === 'error') {
                result.error = task.error;
            }

            return result;
        }

        // List all background tasks
        function listBackgroundTasks() {
            return Object.entries(backgroundTasks).map(([taskId, task]) => ({
                task_id: taskId,
                status: task.status,
                target_session: task.targetSessionNumber,
                description: task.description,
                duration_ms: Date.now() - task.startedAt
            }));
        }

        // Expose to window for tool access
        window.getBackgroundTaskStatus = getBackgroundTaskStatus;
        window.listBackgroundTasks = listBackgroundTasks;

        // ==================== Background Tasks Panel UI ====================

        let bgTasksProgressInterval = null;

        // Update background tasks panel (uses right panel)
        function updateBgTasksPanel() {
            // Update the right panel tasks section
            updateRightPanelTasks();
        }

        // Format duration in human readable format
        function formatDuration(seconds) {
            if (seconds < 60) return `${seconds}s`;
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            return `${mins}m ${secs}s`;
        }

        // Go to task's target session
        window.gotoTaskSession = function(taskId) {
            const task = backgroundTasks[taskId];
            if (task && task.targetConvId) {
                loadConversation(task.targetConvId);
            }
        };

        // Cancel a running background task
        window.cancelBgTask = function(taskId) {
            const task = backgroundTasks[taskId];
            if (!task || task.status !== 'running') return;

            // Stop the target session if streaming
            const targetRuntime = getConvRuntime(task.targetConvId);
            if (targetRuntime && targetRuntime.isStreaming) {
                targetRuntime.isStreaming = false;
                // Abort the request if possible
                if (typeof abortControllers !== 'undefined' && abortControllers[task.targetConvId]) {
                    try {
                        abortControllers[task.targetConvId].abort();
                    } catch (e) {}
                }
            }

            // Update task status
            task.status = 'cancelled';
            task.completedAt = Date.now();
            task.error = 'User cancelled';

            console.log(`[BackgroundTask] Task ${taskId} cancelled by user`);
            updateBgTasksPanel();
        };

        // Remove a completed/failed task from the panel
        window.removeBgTask = function(taskId) {
            delete backgroundTasks[taskId];
            updateBgTasksPanel();
        };

        // Start progress update interval
        function startBgTasksProgressUpdate() {
            if (bgTasksProgressInterval) return;
            bgTasksProgressInterval = setInterval(() => {
                const hasRunning = Object.values(backgroundTasks).some(t => t.status === 'running');
                if (hasRunning) {
                    updateBgTasksPanel();
                } else {
                    // Stop interval if no running tasks
                    clearInterval(bgTasksProgressInterval);
                    bgTasksProgressInterval = null;
                }
            }, 1000);
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

        // ==================== Scheduler Engine ====================
        // Manages scheduled/delayed tasks with cron support

        // Scheduler state (persisted via electronAPI.schedules - separate file, survives cache clear)
        let scheduledTasks = {};
        let schedulerJobs = {};  // Active cron/timer jobs
        let nextTaskNum = 1;     // Auto-increment task number for easy reference

        // Load Croner library for cron parsing (lightweight, browser-compatible)
        // Using Croner: https://github.com/Hexagon/croner
        // Note: Library exports global as 'Cron'
        const cronerScript = document.createElement('script');
        cronerScript.src = 'js/croner.min.js';  // Local copy for reliability
        cronerScript.onload = () => initScheduler();
        cronerScript.onerror = () => {
            // Fallback to CDN
            const cdnScript = document.createElement('script');
            cdnScript.src = 'https://cdn.jsdelivr.net/npm/croner@8/dist/croner.umd.min.js';
            cdnScript.onload = () => initScheduler();
            cdnScript.onerror = () => initScheduler();  // Still init for delay/once tasks
            document.head.appendChild(cdnScript);
        };
        document.head.appendChild(cronerScript);

        // Initialize scheduler - load saved tasks and start jobs
        async function initScheduler() {
            // Load saved tasks from dedicated file (survives cache clear)
            if (window.electronAPI?.schedules) {
                const saved = await window.electronAPI.schedules.get();
                if (saved && typeof saved === 'object') {
                    scheduledTasks = saved;
                }
            }

            // Assign numbers to tasks that don't have them, then calculate next
            let maxNum = 0;
            const tasksNeedingNum = [];
            for (const task of Object.values(scheduledTasks)) {
                if (task.num) {
                    maxNum = Math.max(maxNum, task.num);
                } else {
                    tasksNeedingNum.push(task);
                }
            }
            // Assign numbers to tasks without them (sorted by creation time)
            tasksNeedingNum.sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
            for (const task of tasksNeedingNum) {
                maxNum++;
                task.num = maxNum;
            }
            nextTaskNum = maxNum + 1;
            if (tasksNeedingNum.length > 0) {
                saveScheduledTasks();  // Save the assigned numbers
            }

            const now = Date.now();
            const overdueTasks = [];

            // Check for overdue tasks and start non-overdue ones
            for (const taskId of Object.keys(scheduledTasks)) {
                const task = scheduledTasks[taskId];
                if (!task.enabled) continue;
                // Skip already completed/failed/skipped tasks
                if (task.status === 'completed' || task.status === 'failed' || task.status === 'skipped') continue;

                // Check if task is overdue (for delay and once types)
                if ((task.scheduleType === 'delay' || task.scheduleType === 'once') && task.nextRun && task.nextRun < now) {
                    overdueTasks.push(taskId);
                } else {
                    startScheduledJob(taskId);
                }
            }

            // Show overdue task notifications
            for (const taskId of overdueTasks) {
                showOverdueTaskNotification(taskId);
            }

            // Update UI
            updateSchedulesPanel();
        }

        // Show notification for overdue task
        function showOverdueTaskNotification(taskId) {
            const task = scheduledTasks[taskId];
            if (!task) return;

            const notification = document.createElement('div');
            notification.className = 'overdue-task-notification';
            notification.dataset.taskId = taskId;

            // Calculate how long overdue
            const now = Date.now();
            const overdueMs = now - task.nextRun;
            const overdueText = formatOverdueTime(overdueMs);

            notification.innerHTML = `
                <div class="overdue-task-header">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="12" y1="8" x2="12" y2="12"/>
                        <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                    <span>Task Overdue</span>
                </div>
                <div class="overdue-task-content">
                    <div class="overdue-task-name">${escapeHtml(task.name)}</div>
                    <div class="overdue-task-time">Overdue by ${overdueText}</div>
                </div>
                <div class="overdue-task-actions">
                    <button class="overdue-btn execute" data-action="execute">Execute</button>
                    <button class="overdue-btn reschedule" data-action="reschedule">Reschedule</button>
                    <button class="overdue-btn skip" data-action="skip">Skip</button>
                </div>
            `;

            // Add click handlers
            notification.querySelectorAll('.overdue-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    handleOverdueTask(taskId, btn.dataset.action);
                });
            });

            document.body.appendChild(notification);
            updateOverdueNotificationPositions();
        }

        // Update overdue notification positions based on panel state
        function updateOverdueNotificationPositions() {
            const notifications = document.querySelectorAll('.overdue-task-notification');
            if (notifications.length === 0) return;

            const panel = document.getElementById('right-panel');
            const panelOpen = panel && !panel.classList.contains('hidden');
            const panelWidth = panelOpen ? (panel.offsetWidth || 280) : 0;

            // Position: 10px from panel edge (or window edge if panel closed)
            const rightPos = panelWidth + 10;

            notifications.forEach(n => {
                n.style.right = rightPos + 'px';
            });
        }

        // Format overdue time
        function formatOverdueTime(ms) {
            const minutes = Math.floor(ms / 60000);
            const hours = Math.floor(minutes / 60);
            const days = Math.floor(hours / 24);

            if (days > 0) return `${days}d ${hours % 24}h`;
            if (hours > 0) return `${hours}h ${minutes % 60}m`;
            return `${minutes}m`;
        }

        // Handle overdue task action
        window.handleOverdueTask = async function(taskId, action) {
            const task = scheduledTasks[taskId];
            if (!task) return;

            // Remove notification
            const notification = document.querySelector(`.overdue-task-notification[data-task-id="${taskId}"]`);
            if (notification) notification.remove();

            if (action === 'execute') {
                // Execute immediately (task will be marked as completed in executeScheduledTask)
                await executeScheduledTask(taskId);
            } else if (action === 'reschedule') {
                // Show reschedule dialog
                showRescheduleDialog(taskId);
            } else if (action === 'skip') {
                // Mark as skipped
                task.status = 'skipped';
                task.completedAt = Date.now();
                saveScheduledTasks();
            }

            updateSchedulesPanel();
        };

        // Show reschedule dialog
        function showRescheduleDialog(taskId) {
            const task = scheduledTasks[taskId];
            if (!task) return;

            const dialog = document.createElement('div');
            dialog.className = 'reschedule-dialog-overlay';
            dialog.innerHTML = `
                <div class="reschedule-dialog">
                    <div class="reschedule-dialog-header">Reschedule: ${escapeHtml(task.name)}</div>
                    <div class="reschedule-dialog-options">
                        <button data-minutes="5">5 min</button>
                        <button data-minutes="15">15 min</button>
                        <button data-minutes="30">30 min</button>
                        <button data-minutes="60">1 hour</button>
                    </div>
                    <button class="reschedule-dialog-cancel">Cancel</button>
                </div>
            `;

            // Add click handlers
            dialog.querySelectorAll('.reschedule-dialog-options button').forEach(btn => {
                btn.addEventListener('click', () => {
                    rescheduleTask(taskId, parseInt(btn.dataset.minutes));
                });
            });

            dialog.querySelector('.reschedule-dialog-cancel').addEventListener('click', () => {
                dialog.remove();
            });

            document.body.appendChild(dialog);
        }

        // Reschedule task
        window.rescheduleTask = function(taskId, minutes) {
            const task = scheduledTasks[taskId];
            if (!task) return;

            // Update next run time
            task.nextRun = Date.now() + minutes * 60 * 1000;
            task.scheduleType = 'delay';
            task.scheduleValue = String(minutes);
            saveScheduledTasks();

            // Start the job
            startScheduledJob(taskId);

            // Close dialog
            document.querySelector('.reschedule-dialog-overlay')?.remove();

            // Show confirmation
            showScheduleToast(task.name, `in ${minutes} min`);

            updateSchedulesPanel();
        };

        // Save scheduled tasks to disk (separate file, survives cache clear)
        async function saveScheduledTasks() {
            if (window.electronAPI?.schedules) {
                await window.electronAPI.schedules.set(scheduledTasks);
            }
        }

        // Create a new scheduled task from tool result
        // Find task by ID or numeric index
        function findTaskId(idOrNum) {
            if (!idOrNum) return null;
            // If it's already a full ID, return it
            if (scheduledTasks[idOrNum]) return idOrNum;
            // Try to find by numeric index
            const num = parseInt(idOrNum);
            if (!isNaN(num)) {
                const task = Object.values(scheduledTasks).find(t => t.num === num);
                if (task) return task.id;
            }
            return idOrNum;  // Return as-is, let caller handle not found
        }

        function handleSchedulerToolResult(result) {
            if (!result.success) return;

            if (result.action === 'cancel' && result.task_id) {
                // Cancel task (support numeric ID)
                const taskId = findTaskId(result.task_id);
                cancelScheduledTask(taskId);
            } else if (result.action === 'update' && result.task_id && result.updates) {
                // Update task (support numeric ID)
                const taskId = findTaskId(result.task_id);
                updateScheduledTask(taskId, result.updates);
            } else if (result.task) {
                // Create new task with numeric index
                const task = result.task;
                task.num = nextTaskNum++;

                // Inject current session's working directory if not already set
                if (!task.workingDirectory && currentConversationId) {
                    const runtime = getConvRuntime(currentConversationId);
                    if (runtime?.workingDir) {
                        task.workingDirectory = runtime.workingDir;
                    }
                }

                scheduledTasks[task.id] = task;
                saveScheduledTasks();
                startScheduledJob(task.id);
                updateSchedulesPanel();

                // Auto-open panel and switch to Schedules tab
                const panel = document.getElementById('right-panel');
                if (panel?.classList.contains('hidden')) {
                    toggleRightPanel();
                }
                switchRightPanelTab('schedules');
                // No toast on success - silent creation
            }
        }

        // Start a scheduled job (cron, delay, or once)
        function startScheduledJob(taskId) {
            const task = scheduledTasks[taskId];
            if (!task || !task.enabled) return;

            // Stop existing job if any
            stopScheduledJob(taskId);

            const { scheduleType, scheduleValue } = task;

            if (scheduleType === 'cron') {
                // Use Cron (croner library) for cron expressions
                if (typeof Cron !== 'undefined') {
                    try {
                        const job = new Cron(scheduleValue, () => {
                            executeScheduledTask(taskId);
                        });
                        schedulerJobs[taskId] = { type: 'cron', job };

                        // Update next run time
                        const nextRun = job.nextRun();
                        if (nextRun) {
                            task.nextRun = nextRun.getTime();
                            saveScheduledTasks();
                        }
                    } catch (e) {
                        // Invalid cron expression - silently fail
                    }
                }

            } else if (scheduleType === 'delay') {
                // Delay in minutes
                const minutes = parseInt(scheduleValue);
                if (isNaN(minutes) || minutes <= 0) return;

                const now = Date.now();
                const triggerAt = task.nextRun || (now + minutes * 60 * 1000);
                const delay = Math.max(0, triggerAt - now);

                // If delay is 0 and triggerAt is in the past, show overdue notification
                if (delay === 0 && triggerAt < now) {
                    showOverdueTaskNotification(taskId);
                    return;
                }

                const timerId = setTimeout(async () => {
                    await executeScheduledTask(taskId);
                    delete schedulerJobs[taskId];
                    updateSchedulesPanel();
                }, delay);

                schedulerJobs[taskId] = { type: 'delay', timerId };
                task.nextRun = triggerAt;
                saveScheduledTasks();

            } else if (scheduleType === 'once') {
                // Specific datetime (ISO format)
                const targetTime = new Date(scheduleValue).getTime();
                if (isNaN(targetTime)) return;

                const now = Date.now();
                const delay = Math.max(0, targetTime - now);

                if (delay === 0 && targetTime < now) {
                    // Already passed - show overdue notification instead of auto-completing
                    showOverdueTaskNotification(taskId);
                    return;
                }

                const timerId = setTimeout(async () => {
                    await executeScheduledTask(taskId);
                    delete schedulerJobs[taskId];
                    updateSchedulesPanel();
                }, delay);

                schedulerJobs[taskId] = { type: 'once', timerId };
                task.nextRun = targetTime;
                saveScheduledTasks();
            }

            updateSchedulesPanel();
        }

        // Stop a scheduled job
        function stopScheduledJob(taskId) {
            const job = schedulerJobs[taskId];
            if (!job) return;

            if (job.type === 'cron' && job.job) {
                job.job.stop();
            } else if ((job.type === 'delay' || job.type === 'once') && job.timerId) {
                clearTimeout(job.timerId);
            }

            delete schedulerJobs[taskId];
        }

        // Execute a scheduled task
        async function executeScheduledTask(taskId) {
            const task = scheduledTasks[taskId];
            if (!task) return;

            // Update last run time and set status to running
            task.lastRun = Date.now();
            task.status = 'running';

            // Update next run for cron tasks
            if (task.scheduleType === 'cron' && schedulerJobs[taskId]?.job) {
                const nextRun = schedulerJobs[taskId].job.nextRun();
                task.nextRun = nextRun ? nextRun.getTime() : null;
            }

            saveScheduledTasks();
            updateSchedulesPanel();

            // Execute the prompt and track result
            let targetConvId = null;
            let success = false;
            let errorMsg = null;

            try {
                if (task.createSession) {
                    // Create a new session for execution with task's working directory
                    const workDir = task.workingDirectory || '';
                    targetConvId = createDelegationSession(workDir, `Scheduled: ${task.name}`);
                    await sendMessageToSession(targetConvId, task.prompt);
                } else {
                    // Send to current session
                    targetConvId = currentConversationId;
                    if (targetConvId) {
                        await sendMessageToSession(targetConvId, task.prompt);
                    }
                }
                success = true;
                task.outputConvId = targetConvId;  // Store output session for viewing

                // Track execution count
                task.executionCount = (task.executionCount || 0) + 1;

                // Determine final status based on task type and termination conditions
                if (task.scheduleType === 'cron') {
                    // Check termination conditions for cron tasks
                    let shouldTerminate = false;

                    // Check max executions
                    if (task.maxExecutions && task.executionCount >= task.maxExecutions) {
                        shouldTerminate = true;
                    }

                    // Check end date
                    if (task.endDate && Date.now() >= new Date(task.endDate).getTime()) {
                        shouldTerminate = true;
                    }

                    if (shouldTerminate) {
                        task.status = 'completed';
                        task.completedAt = Date.now();
                        stopScheduledJob(taskId);
                    } else {
                        // Cron task continues - reset to enabled status
                        task.status = 'enabled';
                    }
                } else {
                    // One-time tasks (delay/once) are completed
                    task.status = 'completed';
                    task.completedAt = Date.now();
                }
            } catch (e) {
                errorMsg = e.message || 'Unknown error';
                success = false;
                // For cron tasks, a single failure doesn't stop the task
                if (task.scheduleType === 'cron') {
                    task.status = 'enabled';
                    task.lastError = errorMsg;
                    task.executionCount = (task.executionCount || 0) + 1;
                } else {
                    task.status = 'failed';
                    task.completedAt = Date.now();
                    task.errorMsg = errorMsg;
                }
            }

            saveScheduledTasks();
            updateSchedulesPanel();

            // Only show reminder notification on failure
            if (!success && task.notifyOnTrigger) {
                showScheduleReminder(task.name, task.prompt, success, errorMsg, targetConvId);
            }
        }

        // Show persistent schedule reminder notification
        function showScheduleReminder(taskName, taskPrompt, success = true, errorMsg = null, convId = null) {
            // Remove existing reminder if any
            const existing = document.querySelector('.schedule-reminder');
            if (existing) existing.remove();

            const reminder = document.createElement('div');
            reminder.className = `schedule-reminder ${success ? '' : 'error'}`;

            // Icon based on success/error
            const icon = success
                ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>'
                : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';

            // Build content
            const statusText = success ? '' : `<span class="schedule-reminder-error">${escapeHtml(errorMsg)}</span>`;
            const viewBtnHtml = success && convId
                ? `<button class="schedule-reminder-view">View</button>`
                : '';

            reminder.innerHTML = `
                <div class="schedule-reminder-icon">${icon}</div>
                <div class="schedule-reminder-content">
                    <div class="schedule-reminder-title">${escapeHtml(taskName)}</div>
                    <div class="schedule-reminder-prompt">${escapeHtml(taskPrompt)}</div>
                    ${statusText}
                </div>
                ${viewBtnHtml}
                <button class="schedule-reminder-confirm">OK</button>
            `;

            // Add click handlers
            const viewBtn = reminder.querySelector('.schedule-reminder-view');
            if (viewBtn && convId) {
                viewBtn.addEventListener('click', () => {
                    loadConversation(convId);
                    reminder.remove();
                });
            }

            const confirmBtn = reminder.querySelector('.schedule-reminder-confirm');
            if (confirmBtn) {
                confirmBtn.addEventListener('click', () => {
                    reminder.remove();
                });
            }

            document.body.appendChild(reminder);

            // Auto-remove after 5 minutes
            setTimeout(() => {
                if (reminder.parentElement) {
                    reminder.remove();
                }
            }, 5 * 60 * 1000);
        }

        // Show schedule creation toast (matches app accent color)
        function showScheduleToast(taskName, scheduleDesc) {
            // Remove existing schedule toast if any
            const existing = document.querySelector('.schedule-toast');
            if (existing) existing.remove();

            const toast = document.createElement('div');
            toast.className = 'schedule-toast';
            toast.innerHTML = `
                <svg class="schedule-toast-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <polyline points="12 6 12 12 16 14"/>
                </svg>
                <div class="schedule-toast-content">
                    <span class="schedule-toast-title">${escapeHtml(taskName)}</span>
                    <span class="schedule-toast-desc">${escapeHtml(scheduleDesc)}</span>
                </div>
                <button class="schedule-toast-close" onclick="this.parentElement.remove()">&times;</button>
            `;

            document.body.appendChild(toast);

            // Auto-remove after 4 seconds
            setTimeout(() => {
                if (toast.parentElement) {
                    toast.classList.add('schedule-toast-fade-out');
                    setTimeout(() => toast.remove(), 300);
                }
            }, 4000);
        }

        // Send a message to a specific session
        async function sendMessageToSession(convId, message) {
            const runtime = getConvRuntime(convId);
            if (!runtime) return;

            // Add user message
            runtime.messages.push({
                role: 'user',
                content: message,
                isScheduled: true
            });

            // If viewing this conversation, render
            if (currentConversationId === convId) {
                renderMessages();
            }

            // Execute
            runtime.isStreaming = true;
            updateConversationStatus(convId, 'active');

            try {
                await continueConversation(convId);
            } finally {
                runtime.isStreaming = false;
                updateConversationStatus(convId, 'idle');
            }
        }

        // Cancel a scheduled task
        function cancelScheduledTask(taskId) {
            stopScheduledJob(taskId);
            delete scheduledTasks[taskId];
            saveScheduledTasks();
            updateSchedulesPanel();
        }

        // Update a scheduled task
        function updateScheduledTask(taskId, updates) {
            const task = scheduledTasks[taskId];
            if (!task) return;

            // Apply updates
            Object.assign(task, updates);

            // Restart job if schedule changed
            if (updates.scheduleType || updates.scheduleValue) {
                stopScheduledJob(taskId);
                if (task.enabled) {
                    startScheduledJob(taskId);
                }
            } else if ('enabled' in updates) {
                if (updates.enabled) {
                    startScheduledJob(taskId);
                } else {
                    stopScheduledJob(taskId);
                }
            }

            saveScheduledTasks();
            updateSchedulesPanel();
        }

        // Toggle task enabled state
        window.toggleScheduledTask = function(taskId) {
            const task = scheduledTasks[taskId];
            if (!task) return;

            task.enabled = !task.enabled;

            if (task.enabled) {
                startScheduledJob(taskId);
            } else {
                stopScheduledJob(taskId);
            }

            saveScheduledTasks();
            updateSchedulesPanel();
        };

        // Delete a scheduled task
        window.deleteScheduledTask = function(taskId) {
            const task = scheduledTasks[taskId];
            if (!task) return;

            stopScheduledJob(taskId);
            delete scheduledTasks[taskId];
            saveScheduledTasks();
            updateSchedulesPanel();
        };

        // Pulse the right panel toggle icon (heartbeat effect)
        function pulseRightPanelIcon() {
            const toggle = document.getElementById('right-panel-toggle');
            if (!toggle) return;

            // Add pulse class
            toggle.classList.add('panel-pulse');

            // Remove after animation completes
            setTimeout(() => {
                toggle.classList.remove('panel-pulse');
            }, 600);
        }

        // Update the Schedules panel UI
        function updateSchedulesPanel() {
            const list = document.getElementById('panel-schedules-list');
            if (!list) return;

            const taskIds = Object.keys(scheduledTasks);

            // Pulse the right panel icon to indicate change
            pulseRightPanelIcon();

            if (taskIds.length === 0) {
                list.innerHTML = `
                    <div class="panel-placeholder">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.5">
                            <circle cx="12" cy="12" r="10"/>
                            <polyline points="12 6 12 12 16 14"/>
                        </svg>
                        <span>No scheduled tasks</span>
                        <span class="panel-placeholder-hint">Ask Claude to create reminders or scheduled tasks</span>
                    </div>
                `;
                return;
            }

            // Separate active tasks from older (expired/completed) tasks
            const now = Date.now();
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const todayStart = today.getTime();

            const todayTasks = [];
            const olderTasks = [];

            taskIds.forEach(taskId => {
                const task = scheduledTasks[taskId];
                const isCompleted = task.status === 'completed' || task.status === 'failed' || task.status === 'skipped';

                // Determine if task should be in "Older" section
                let isOlder = false;

                if (task.type === 'cron') {
                    // Cron tasks: older only if disabled AND no future runs
                    // Active cron tasks with future nextRun are never "older"
                    if (task.nextRun && task.nextRun > now) {
                        isOlder = false; // Has future run, keep in active
                    } else if (isCompleted && task.completedAt && task.completedAt < todayStart) {
                        isOlder = true; // Completed before today
                    }
                } else if (task.type === 'once') {
                    // Once tasks: older if scheduled time has passed and completed
                    if (isCompleted) {
                        // Use completedAt time to determine if older
                        isOlder = task.completedAt && task.completedAt < todayStart;
                    } else if (task.scheduledAt && task.scheduledAt < todayStart) {
                        // Pending but scheduled time was before today
                        isOlder = true;
                    }
                } else if (task.type === 'delay') {
                    // Delay tasks: older if completed before today
                    if (isCompleted) {
                        isOlder = task.completedAt && task.completedAt < todayStart;
                    }
                }

                if (isOlder) {
                    olderTasks.push(taskId);
                } else {
                    todayTasks.push(taskId);
                }
            });

            // Sort today's tasks: running first, then pending, then by trigger time (newest first)
            const sortTasks = (ids) => ids.sort((a, b) => {
                const taskA = scheduledTasks[a];
                const taskB = scheduledTasks[b];

                // Running tasks first
                if (taskA.status === 'running' && taskB.status !== 'running') return -1;
                if (taskB.status === 'running' && taskA.status !== 'running') return 1;

                // Then pending tasks
                const aFinished = taskA.status === 'completed' || taskA.status === 'failed' || taskA.status === 'skipped';
                const bFinished = taskB.status === 'completed' || taskB.status === 'failed' || taskB.status === 'skipped';
                if (aFinished !== bFinished) return aFinished ? 1 : -1;

                // For finished tasks: sort by trigger time (lastRun), newest first
                if (aFinished && bFinished) {
                    const timeA = taskA.lastRun || taskA.completedAt || 0;
                    const timeB = taskB.lastRun || taskB.completedAt || 0;
                    return timeB - timeA;  // Descending (newest first)
                }

                // For pending tasks: sort by next run time (soonest first)
                const timeA = taskA.nextRun || Infinity;
                const timeB = taskB.nextRun || Infinity;
                return timeA - timeB;
            });

            sortTasks(todayTasks);
            sortTasks(olderTasks);

            let html = '';

            // Render today's tasks
            if (todayTasks.length > 0) {
                html += todayTasks.map(taskId => renderScheduleItem(taskId)).join('');
            }

            // Render older tasks (collapsed)
            if (olderTasks.length > 0) {
                html += `
                    <div class="schedule-older-section">
                        <div class="schedule-older-header" onclick="toggleOlderTasks()">
                            <svg class="schedule-older-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="6 9 12 15 18 9"/>
                            </svg>
                            <span>Older (${olderTasks.length})</span>
                        </div>
                        <div class="schedule-older-list collapsed">
                            ${olderTasks.map(taskId => renderScheduleItem(taskId)).join('')}
                        </div>
                    </div>
                `;
            }

            list.innerHTML = html;
        }

        // Toggle older tasks visibility
        window.toggleOlderTasks = function() {
            const olderList = document.querySelector('.schedule-older-list');
            const arrow = document.querySelector('.schedule-older-arrow');
            if (olderList) {
                olderList.classList.toggle('collapsed');
                arrow?.classList.toggle('expanded');
            }
        };

        // Render a single schedule item
        function renderScheduleItem(taskId) {
            const task = scheduledTasks[taskId];
            const clockIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>';
            const calendarIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>';
            const checkIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="9 12 11 14 15 10"/></svg>';
            const errorIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
            const skipIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>';

            // Determine icon and status
            const runningIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spinning"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>';

            let icon, statusClass, statusText;
            if (task.status === 'running') {
                icon = runningIcon;
                statusClass = 'running';
                statusText = 'Running';
            } else if (task.status === 'completed') {
                icon = checkIcon;
                statusClass = 'completed';
                statusText = 'Completed';
            } else if (task.status === 'failed') {
                icon = errorIcon;
                statusClass = 'failed';
                statusText = 'Failed';
            } else if (task.status === 'skipped') {
                icon = skipIcon;
                statusClass = 'skipped';
                statusText = 'Skipped';
            } else {
                icon = task.scheduleType === 'cron' ? calendarIcon : clockIcon;
                statusClass = task.enabled ? 'enabled' : 'disabled';
                statusText = '';
            }

            const scheduleDesc = formatScheduleDescription(task);
            const isFinished = task.status === 'completed' || task.status === 'failed' || task.status === 'skipped';

            // Time display
            let timeDisplay;
            if (isFinished && task.completedAt) {
                const completedDate = new Date(task.completedAt);
                const now = new Date();
                const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
                const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
                const taskDay = new Date(completedDate.getFullYear(), completedDate.getMonth(), completedDate.getDate());

                const timeStr = completedDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

                if (taskDay.getTime() === today.getTime()) {
                    // Today: just show time
                    timeDisplay = timeStr;
                } else if (taskDay.getTime() === yesterday.getTime()) {
                    // Yesterday
                    timeDisplay = `Yesterday ${timeStr}`;
                } else {
                    // Older: show date
                    const dateStr = `${completedDate.getMonth() + 1}/${completedDate.getDate()}`;
                    timeDisplay = `${dateStr} ${timeStr}`;
                }
            } else {
                timeDisplay = formatNextRun(task.nextRun);
            }

            // View icon for completed tasks with output (in actions area)
            const viewBtn = (task.status === 'completed' && task.outputConvId)
                ? `<button class="schedule-action-btn" onclick="loadConversation('${task.outputConvId}')" title="View Output">
                       <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                           <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                           <circle cx="12" cy="12" r="3"/>
                       </svg>
                   </button>`
                : '';

            // Toggle only for non-finished tasks
            const toggleHtml = !isFinished
                ? `<label class="schedule-toggle">
                       <input type="checkbox" ${task.enabled ? 'checked' : ''} onchange="toggleScheduledTask('${taskId}')">
                       <span class="toggle-slider"></span>
                   </label>`
                : `<span class="schedule-status-badge ${statusClass}">${statusText}</span>`;

            const taskNum = task.num ? `#${task.num}` : '';

            // Execution count display for cron tasks
            let execCountHtml = '';
            if (task.scheduleType === 'cron') {
                const count = task.executionCount || 0;
                if (task.maxExecutions) {
                    // Show progress: 0/3, 1/3, 2/3, 3/3
                    execCountHtml = `<span class="schedule-exec-count">${count}/${task.maxExecutions}</span>`;
                } else if (count > 0) {
                    // Show count only if executed at least once
                    execCountHtml = `<span class="schedule-exec-count">x${count}</span>`;
                }
            }

            return `
                <div class="panel-schedule-item ${statusClass}" data-task-id="${taskId}">
                    <div class="schedule-header">
                        <span class="schedule-num">${taskNum}</span>
                        <span class="schedule-icon">${icon}</span>
                        <span class="schedule-name">${escapeHtml(task.name)}</span>
                        ${execCountHtml}
                        ${toggleHtml}
                    </div>
                    <div class="schedule-details">
                        <span class="schedule-description">${scheduleDesc}</span>
                        <span class="schedule-next">${timeDisplay}</span>
                    </div>
                    <div class="schedule-actions">
                        ${viewBtn}
                        <button class="schedule-delete-btn" onclick="deleteScheduledTask('${taskId}')" title="Delete">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                            </svg>
                        </button>
                    </div>
                </div>
            `;
        }

        // Format schedule description for display
        function formatScheduleDescription(task) {
            const { scheduleType, scheduleValue } = task;

            if (scheduleType === 'cron') {
                return describeCron(scheduleValue);
            } else if (scheduleType === 'delay') {
                const mins = parseInt(scheduleValue);
                if (mins < 60) return `After ${mins} minute${mins > 1 ? 's' : ''}`;
                const hrs = Math.floor(mins / 60);
                const rem = mins % 60;
                return rem > 0 ? `After ${hrs}h ${rem}m` : `After ${hrs} hour${hrs > 1 ? 's' : ''}`;
            } else if (scheduleType === 'once') {
                const dt = new Date(scheduleValue);
                return `Once at ${dt.toLocaleString()}`;
            }
            return scheduleValue;
        }

        // Describe cron expression in human readable form
        function describeCron(cron) {
            const parts = cron.split(' ');
            if (parts.length !== 5) return `Cron: ${cron}`;

            const [minute, hour, day, month, weekday] = parts;

            // Every N minutes
            if (minute.startsWith('*/')) {
                const n = parseInt(minute.slice(2));
                return `Every ${n} minute${n > 1 ? 's' : ''}`;
            }

            // Every minute
            if (minute === '*' && hour === '*') {
                return 'Every minute';
            }

            // Daily at specific time
            if (minute !== '*' && hour !== '*' && day === '*' && month === '*' && weekday === '*') {
                const h = parseInt(hour);
                const m = parseInt(minute);
                return `Daily at ${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
            }

            // Weekly
            if (weekday !== '*' && day === '*') {
                const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
                const dayName = days[parseInt(weekday)] || weekday;
                const h = parseInt(hour);
                const m = parseInt(minute);
                if (!isNaN(h) && !isNaN(m)) {
                    return `Every ${dayName} at ${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
                }
                return `Every ${dayName}`;
            }

            return `Cron: ${cron}`;
        }

        // Format next run time
        function formatNextRun(nextRun) {
            if (!nextRun) return '';

            const now = Date.now();
            const diff = nextRun - now;

            if (diff < 0) return 'Overdue';

            if (diff < 60000) {
                return `In ${Math.round(diff / 1000)}s`;
            } else if (diff < 3600000) {
                return `In ${Math.round(diff / 60000)}m`;
            } else if (diff < 86400000) {
                const hrs = Math.floor(diff / 3600000);
                const mins = Math.round((diff % 3600000) / 60000);
                return mins > 0 ? `In ${hrs}h ${mins}m` : `In ${hrs}h`;
            } else {
                const date = new Date(nextRun);
                return `Next: ${date.toLocaleDateString()} ${date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`;
            }
        }

        // Start periodic update for next run times (every minute)
        setInterval(() => {
            if (Object.keys(scheduledTasks).length > 0) {
                updateSchedulesPanel();
            }
        }, 60000);

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

            // Scheduler tool result
            if (result.ui_update === 'schedules_panel') {
                handleSchedulerToolResult(result);
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
            saveWorkspaceCache();
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
                    saveWorkspaceCache();
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

        // ============ Team Mode ============

        window.toggleTeamMode = function() {
            // Cycle: off -> classic -> collaborative -> off
            const btn = document.getElementById('team-toggle');
            const input = document.getElementById('message-input');

            if (!teamModeEnabled) {
                // off -> classic
                teamModeEnabled = true;
                teamCollaborativeMode = false;
                btn.classList.add('active');
                btn.classList.remove('collab');
                btn.title = 'Team Mode: Classic (click again for Collaborative)';
                input.placeholder = 'Team Mode (Classic): agents work in parallel on your request...';
            } else if (!teamCollaborativeMode) {
                // classic -> collaborative
                teamCollaborativeMode = true;
                btn.classList.add('collab');
                btn.title = 'Team Mode: Collaborative (click again to disable)';
                input.placeholder = 'Team Mode (Collaborative): agents communicate and coordinate...';
            } else {
                // collaborative -> off
                teamModeEnabled = false;
                teamCollaborativeMode = false;
                btn.classList.remove('active', 'collab');
                btn.title = 'Team Mode - multi-agent collaboration';
                input.placeholder = 'Message Springo... (/ for skills)';
            }
        }

        async function sendTeamMessage(userMessage) {
            const input = document.getElementById('message-input');

            // Get or create conversation
            const thisConvId = currentConversationId || Date.now().toString();
            if (!currentConversationId) {
                currentConversationId = thisConvId;
                convRuntime[thisConvId] = { isStreaming: false, attachments: [], messages: [] };
            }
            const runtime = getConvRuntime(thisConvId);

            // Hide welcome
            const welcome = document.getElementById('welcome');
            if (welcome) welcome.style.display = 'none';

            // Add user message
            runtime.messages.push({ role: 'user', content: userMessage, timestamp: Date.now() });

            // Clear input
            input.value = '';
            input.style.height = 'auto';

            // Render
            if (currentConversationId === thisConvId) {
                renderMessages();
            }

            runtime.isStreaming = true;
            updateConversationStatus(thisConvId, 'running');
            updateStatus('running');
            updateSendButtonState();

            try {
                // Step 1: Spawn team
                const teamMode = teamCollaborativeMode ? 'collaborative' : 'classic';
                const spawnRes = await fetch(BASE_URL + '/v1/teams/spawn', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_request: userMessage, mode: teamMode })
                });

                if (!spawnRes.ok) {
                    throw new Error('Failed to spawn team: ' + spawnRes.statusText);
                }

                const spawnData = await spawnRes.json();
                const teamId = spawnData.team_id;

                // Step 2: Execute team with SSE streaming
                const execRes = await fetch(BASE_URL + '/v1/teams/' + teamId + '/execute', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ stream: true })
                });

                if (!execRes.ok) {
                    throw new Error('Failed to execute team: ' + execRes.statusText);
                }

                const reader = execRes.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let eventType = null;
                let synthesisText = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();

                    for (const line of lines) {
                        if (line.startsWith('event: ')) {
                            eventType = line.slice(7).trim();
                        } else if (line.startsWith('data: ')) {
                            const dataStr = line.slice(6);
                            if (dataStr === '[DONE]') continue;

                            try {
                                const data = JSON.parse(dataStr);

                                // Handle team SSE events
                                switch (eventType) {
                                    case 'team_spawned':
                                        initTeamSplitPanel(data.team_id, data.agents, data.user_request);
                                        break;
                                    case 'team_planning':
                                        updateTeamSplitStatus(data.team_id, 'planning', 'Planning...');
                                        break;
                                    case 'team_task_board':
                                        addTeamSplitAgents(data.team_id, data.tasks);
                                        updateTeamSplitStatus(data.team_id, 'executing', 'Agents working...');
                                        break;
                                    case 'team_agent_start':
                                        updateTeamSplitAgent(data.team_id, data.agent_id, data.role, 'thinking', data.task_title);
                                        break;
                                    case 'team_agent_progress':
                                        updateTeamSplitAgent(data.team_id, data.agent_id, data.role, 'executing', '', data.preview);
                                        break;
                                    case 'team_agent_complete':
                                        updateTeamSplitAgent(data.team_id, data.agent_id, data.role, 'complete', data.task_title, data.findings);
                                        break;
                                    case 'team_agent_error':
                                        updateTeamSplitAgent(data.team_id, data.agent_id, data.role, 'error', '', data.error);
                                        break;
                                    case 'team_agent_delta':
                                        appendTeamAgentDelta(data.team_id, data.agent_id, data.role, data.delta);
                                        break;
                                    case 'team_agent_tool':
                                        appendTeamAgentToolEvent(data.team_id, data.agent_id, data.role, data.tool_name, data.status, data.result_preview);
                                        break;
                                    case 'team_synthesis_delta':
                                        // Stream synthesis text into the chat window
                                        synthesisText += data.delta;
                                        if (currentConversationId === thisConvId) {
                                            debouncedUpdateAssistantMessage(thisConvId, synthesisText, [], false);
                                        }
                                        break;
                                    case 'team_synthesizing':
                                        updateTeamSplitStatus(data.team_id, 'synthesizing', 'Synthesizing...');
                                        break;
                                    case 'team_complete':
                                        updateTeamSplitStatus(data.team_id, 'complete', 'Complete');
                                        // Use streamed synthesis text, fall back to complete result
                                        if (!synthesisText && data.result) {
                                            synthesisText = data.result;
                                        }
                                        break;
                                    case 'team_error':
                                        updateTeamSplitStatus(data.team_id, 'error', data.error);
                                        break;
                                    // Collaborative team events
                                    case 'team_agent_message':
                                        appendTeamMessage(data.team_id, data.sender, data.recipient, data.content, data.summary);
                                        break;
                                    case 'team_agent_broadcast':
                                        appendTeamMessage(data.team_id, data.sender, 'all', data.content, data.summary, true);
                                        break;
                                    case 'team_agent_idle':
                                        updateTeamSplitAgent(data.team_id, null, null, 'idle', '', '', data.agent_name);
                                        break;
                                    case 'team_agent_shutdown':
                                        updateTeamSplitAgent(data.team_id, null, null, 'shutdown', '', '', data.agent_name);
                                        break;
                                    case 'team_task_created':
                                        addTeamTaskBoardItem(data.team_id, data.task_id, data.title, data.owner, 'pending');
                                        break;
                                    case 'team_task_updated':
                                        updateTeamTaskBoardItem(data.team_id, data.task_id, data.status, data.owner, data.title);
                                        break;
                                    case 'team_task_unblocked':
                                        updateTeamTaskBoardItem(data.team_id, data.task_id, 'unblocked', data.owner, data.title);
                                        break;
                                }
                            } catch (e) {
                                // ignore parse errors
                            }
                            eventType = null;
                        }
                    }
                }

                // Finalize the streamed assistant message
                if (synthesisText) {
                    // Clear any pending debounced updates
                    if (streamingUIDebounce.timers[thisConvId]) {
                        clearTimeout(streamingUIDebounce.timers[thisConvId]);
                        delete streamingUIDebounce.timers[thisConvId];
                    }
                    delete streamingUIDebounce.pending[thisConvId];

                    // Mark the message with _teamMode and do final render
                    const lastMsg = runtime.messages[runtime.messages.length - 1];
                    if (lastMsg && lastMsg.role === 'assistant') {
                        lastMsg.content = synthesisText;
                        lastMsg._teamMode = true;
                    } else {
                        runtime.messages.push({
                            role: 'assistant',
                            content: synthesisText,
                            timestamp: Date.now(),
                            _teamMode: true
                        });
                    }
                    updateAssistantMessage(thisConvId, synthesisText, [], true);
                }

                updateConversationStatus(thisConvId, 'completed');
                updateStatus('completed');

            } catch (e) {
                console.error('Team execution error:', e);
                updateConversationStatus(thisConvId, 'error');
                updateStatus('error', e.message);
            } finally {
                runtime.isStreaming = false;
                updateSendButtonState();
                saveConversation(thisConvId);
            }
        }

        // LTM Panel removed - LTM retrieval will be implemented via skill

        // ============ Terminal Panel ============

        let terminalCurrentPid = null;
        let terminalHistory = [];
        let terminalHistoryIndex = -1;

        // SSH state (terminal is SSH-only)
        let currentSSHConnectionId = null;

        function toggleTerminalPanel() {
            const panel = document.getElementById('right-panel');
            const btn = document.getElementById('terminal-toggle');

            if (panel.classList.contains('hidden')) {
                panel.classList.remove('hidden');
            }

            // Switch to terminal tab
            switchRightPanelTab('terminal');
            btn.classList.add('active');

            // Load SSH config hosts
            loadSSHConfig();

            // Focus the input
            setTimeout(() => {
                document.getElementById('terminal-input')?.focus();
            }, 100);
        }

        function clearTerminal() {
            const output = document.getElementById('terminal-panel-output');
            if (output) output.innerHTML = '';
        }

        // Terminal theme now follows the main app theme via CSS variables — no separate toggle needed
        function toggleTerminalTheme() {}
        function initTerminalTheme() {}

        function appendTerminalOutput(html, className) {
            const output = document.getElementById('terminal-panel-output');
            if (!output) return;
            const div = document.createElement('div');
            if (className) div.className = className;
            div.innerHTML = html;
            output.appendChild(div);
            output.scrollTop = output.scrollHeight;
        }

        async function executeTerminalCommand() {
            const input = document.getElementById('terminal-input');
            const command = input.value.trim();
            if (!command) return;

            // Terminal is SSH-only — require connection
            if (!currentSSHConnectionId) {
                appendTerminalOutput(`<span class="ansi-red">No SSH connection active. Please connect first.</span>`, 'terminal-error-line');
                return;
            }
            return executeSSHCommand(command);
        }

        function handleTerminalEvent(eventType, data) {
            switch (eventType) {
                case 'start':
                    terminalCurrentPid = data.pid;
                    if (data.working_dir) {
                        const cwd = data.working_dir.replace(/^\/Users\/[^/]+/, '~');
                        document.getElementById('terminal-cwd').textContent = cwd;
                    }
                    break;
                case 'output':
                    if (data.type === 'stderr') {
                        appendTerminalOutput(`<span class="ansi-stderr">${ansiToHtml(data.data)}</span>`);
                    } else {
                        appendTerminalOutput(ansiToHtml(data.data));
                    }
                    break;
                case 'exit':
                    if (data.exit_code !== 0) {
                        appendTerminalOutput(`<span class="ansi-dim">exit ${data.exit_code}</span>`, 'terminal-exit-line');
                    }
                    // Update prompt with current working directory from server
                    if (data.cwd) {
                        const cwdEl = document.getElementById('terminal-cwd');
                        const sshName = cwdEl?.dataset?.sshName || '';
                        const homeDir = `/home/${sshName.split('@')[0] || 'user'}`;
                        // Show ~ for home directory, basename for others
                        let displayPath = data.cwd;
                        if (data.cwd === homeDir) {
                            displayPath = '~';
                        } else if (data.cwd.startsWith(homeDir + '/')) {
                            displayPath = '~' + data.cwd.slice(homeDir.length);
                        }
                        const termPrompt = document.querySelector('.terminal-prompt');
                        if (termPrompt && sshName) {
                            termPrompt.textContent = `${sshName}:${displayPath}$`;
                        }
                    }
                    break;
                case 'error':
                    appendTerminalOutput(`<span class="ansi-red">${escapeHtml(data.message)}</span>`, 'terminal-error-line');
                    break;
            }
        }

        async function killTerminalProcess() {
            if (!terminalCurrentPid) return;
            try {
                await fetch(BASE_URL + '/v1/terminal/kill/' + terminalCurrentPid, { method: 'POST' });
            } catch (e) {
                console.error('Failed to kill process:', e);
            }
        }

        // Terminal input keyboard handling
        document.addEventListener('DOMContentLoaded', function() {
            // Initialize terminal theme from saved preference
            initTerminalTheme();
            
            const termInput = document.getElementById('terminal-input');
            if (termInput) {
                termInput.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        executeTerminalCommand();
                    } else if (e.key === 'ArrowUp') {
                        e.preventDefault();
                        if (terminalHistoryIndex > 0) {
                            terminalHistoryIndex--;
                            this.value = terminalHistory[terminalHistoryIndex];
                        }
                    } else if (e.key === 'ArrowDown') {
                        e.preventDefault();
                        if (terminalHistoryIndex < terminalHistory.length - 1) {
                            terminalHistoryIndex++;
                            this.value = terminalHistory[terminalHistoryIndex];
                        } else {
                            terminalHistoryIndex = terminalHistory.length;
                            this.value = '';
                        }
                    }
                });
            }
        });

        // Keyboard shortcut: Cmd+` to toggle terminal
        document.addEventListener('keydown', function(e) {
            if ((e.metaKey || e.ctrlKey) && e.key === '`') {
                e.preventDefault();
                toggleTerminalPanel();
            }
        });

        // ============ Terminal SSH Mode ============

        // SSH config hosts cache
        let sshConfigHosts = [];

        async function loadSSHConfig() {
            const select = document.getElementById('ssh-host-select');
            const container = document.getElementById('ssh-config-hosts');
            if (!select || !container) return;

            try {
                const res = await fetch(BASE_URL + '/v1/terminal/ssh/config');
                if (!res.ok) return;
                const data = await res.json();
                sshConfigHosts = data.hosts || [];

                if (sshConfigHosts.length === 0) {
                    container.style.display = 'none';
                    return;
                }

                // Populate dropdown
                select.innerHTML = '<option value="">-- Select from ~/.ssh/config --</option>';
                for (const host of sshConfigHosts) {
                    const label = host.user ? `${host.name} (${host.user}@${host.hostname || host.name})` : host.name;
                    const opt = document.createElement('option');
                    opt.value = host.name;
                    opt.textContent = label;
                    select.appendChild(opt);
                }
                container.style.display = '';
            } catch (e) {
                console.warn('Failed to load SSH config:', e);
            }
        }

        window.onSSHHostSelect = function(hostName) {
            if (!hostName) return;
            const host = sshConfigHosts.find(h => h.name === hostName);
            if (!host) return;

            // Auto-fill fields
            const hostInput = document.getElementById('ssh-host');
            const portInput = document.getElementById('ssh-port');
            const userInput = document.getElementById('ssh-username');
            const keyInput = document.getElementById('ssh-key-path');

            if (hostInput) hostInput.value = host.hostname || host.name;
            if (portInput) portInput.value = host.port || 22;
            if (userInput) userInput.value = host.user || '';
            if (keyInput) keyInput.value = host.identity_file || '';
        };

        async function sshConnect() {
            const host = document.getElementById('ssh-host')?.value?.trim();
            const port = parseInt(document.getElementById('ssh-port')?.value) || 22;
            const username = document.getElementById('ssh-username')?.value?.trim();
            const password = document.getElementById('ssh-password')?.value;
            const keyPath = document.getElementById('ssh-key-path')?.value?.trim();

            if (!host || !username) {
                updateSSHStatus('Host and username are required', 'error');
                return;
            }

            updateSSHStatus('Connecting...', 'connecting');

            try {
                const body = { host, port, username };
                if (keyPath) body.key_path = keyPath;
                if (password) body.password = password;

                const res = await fetch(BASE_URL + '/v1/terminal/ssh/connect', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });

                const data = await res.json();

                if (!res.ok) {
                    throw new Error(data.detail || 'Connection failed');
                }

                currentSSHConnectionId = data.connection_id;
                updateSSHStatus(`Connected: ${data.name}`, 'connected');

                // Update CWD to show SSH host
                const cwdEl = document.getElementById('terminal-cwd');
                cwdEl.textContent = data.name;
                cwdEl.dataset.sshName = data.name;

                // Enable terminal input and update prompt
                const termInput = document.getElementById('terminal-input');
                if (termInput) {
                    termInput.disabled = false;
                    termInput.placeholder = `Enter command...`;
                }
                const termPrompt = document.querySelector('.terminal-prompt');
                if (termPrompt) termPrompt.textContent = `${data.name}:~$`;

                // Add to connections list
                refreshSSHConnections();

                // Show success in terminal output
                appendTerminalOutput(`<span class="ansi-green">Connected to ${escapeHtml(data.name)}</span>`, 'terminal-cmd-line');

                document.getElementById('terminal-input')?.focus();

            } catch (e) {
                updateSSHStatus(e.message, 'error');
            }
        }

        function updateSSHStatus(message, type) {
            const el = document.getElementById('ssh-status');
            if (!el) return;
            el.textContent = message;
            el.className = 'ssh-status ' + (type || '');
        }

        async function refreshSSHConnections() {
            try {
                const res = await fetch(BASE_URL + '/v1/terminal/ssh/connections');
                const data = await res.json();

                const container = document.getElementById('ssh-connections');
                if (!container || !data.connections?.length) return;

                container.innerHTML = data.connections.map(c => `
                    <div class="ssh-connection-item ${c.connection_id === currentSSHConnectionId ? 'active' : ''}">
                        <span class="ssh-conn-name" onclick="switchSSHConnection('${c.connection_id}', '${escapeHtml(c.name)}')">${escapeHtml(c.name)}</span>
                        <button class="ssh-disconnect-btn" onclick="sshDisconnect('${c.connection_id}')" title="Disconnect">&times;</button>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Failed to refresh SSH connections:', e);
            }
        }

        function switchSSHConnection(connectionId, name) {
            currentSSHConnectionId = connectionId;
            const cwdEl = document.getElementById('terminal-cwd');
            cwdEl.textContent = name;
            cwdEl.dataset.sshName = name;
            const termInput = document.getElementById('terminal-input');
            if (termInput) {
                termInput.disabled = false;
                termInput.placeholder = `Enter command...`;
            }
            const termPrompt = document.querySelector('.terminal-prompt');
            if (termPrompt) termPrompt.textContent = `${name}:~$`;
            refreshSSHConnections();
            appendTerminalOutput(`<span class="ansi-cyan">Switched to ${escapeHtml(name)}</span>`, 'terminal-cmd-line');
        }

        async function sshDisconnect(connectionId) {
            try {
                await fetch(BASE_URL + '/v1/terminal/ssh/disconnect/' + connectionId, { method: 'POST' });

                if (connectionId === currentSSHConnectionId) {
                    currentSSHConnectionId = null;
                    updateSSHStatus('Disconnected', '');
                    document.getElementById('terminal-cwd').textContent = 'Not connected';
                    const termInput = document.getElementById('terminal-input');
                    if (termInput) {
                        termInput.disabled = true;
                        termInput.placeholder = 'Connect to SSH first...';
                    }
                    const termPrompt = document.querySelector('.terminal-prompt');
                    if (termPrompt) termPrompt.textContent = '>';
                }

                refreshSSHConnections();
                appendTerminalOutput(`<span class="ansi-yellow">Disconnected</span>`, 'terminal-cmd-line');
            } catch (e) {
                console.error('Disconnect error:', e);
            }
        }

        async function executeSSHCommand(command) {
            if (!currentSSHConnectionId) {
                appendTerminalOutput(`<span class="ansi-red">No SSH connection active. Please connect first.</span>`, 'terminal-error-line');
                return;
            }

            // Add to history
            terminalHistory.push(command);
            terminalHistoryIndex = terminalHistory.length;

            // Show command in output
            const promptPrefix = document.querySelector('.terminal-prompt')?.textContent || '>';
            appendTerminalOutput(`<span class="ansi-green">${escapeHtml(promptPrefix)}</span> <span class="ansi-cyan">${escapeHtml(command)}</span>`, 'terminal-cmd-line');

            // Clear input
            document.getElementById('terminal-input').value = '';

            // Show stop button
            document.getElementById('terminal-run-btn').style.display = 'none';
            document.getElementById('terminal-stop-btn').style.display = '';

            try {
                const response = await fetch(BASE_URL + '/v1/terminal/ssh/execute', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        connection_id: currentSSHConnectionId,
                        command: command,
                        timeout: 300
                    })
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let eventType = null;

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();

                    for (const line of lines) {
                        if (line.startsWith('event: ')) {
                            eventType = line.slice(7).trim();
                        } else if (line.startsWith('data: ')) {
                            const dataStr = line.slice(6);
                            if (dataStr === '[DONE]') continue;
                            try {
                                const data = JSON.parse(dataStr);
                                handleTerminalEvent(eventType, data);
                            } catch (e) {}
                            eventType = null;
                        }
                    }
                }
            } catch (e) {
                appendTerminalOutput(`<span class="ansi-red">SSH Error: ${escapeHtml(e.message)}</span>`, 'terminal-error-line');
            } finally {
                document.getElementById('terminal-run-btn').style.display = '';
                document.getElementById('terminal-stop-btn').style.display = 'none';
                document.getElementById('terminal-input')?.focus();
            }
        }

        // ============ #terminal — Read terminal output into chat ============

        function injectTerminalOutputToChat(userInput) {
            const thisConvId = currentConversationId || Date.now().toString();
            if (!currentConversationId) {
                currentConversationId = thisConvId;
                convRuntime[thisConvId] = { isStreaming: false, attachments: [], messages: [] };
            }
            const runtime = getConvRuntime(thisConvId);

            // Hide welcome
            const welcome = document.getElementById('welcome');
            if (welcome) welcome.style.display = 'none';

            // Read terminal panel output
            const outputEl = document.getElementById('terminal-panel-output');
            if (!outputEl || !outputEl.textContent.trim()) {
                runtime.messages.push({ role: 'user', content: userInput, timestamp: Date.now() });
                runtime.messages.push({
                    role: 'assistant',
                    content: 'Terminal panel is empty. Run some commands in the SSH terminal first.',
                    timestamp: Date.now()
                });
                if (currentConversationId === thisConvId) { renderMessages(); scrollToBottom(); }
                return;
            }

            // Extract text content from terminal output (preserving line structure)
            const terminalText = outputEl.innerText.trim();

            // Optional: user can add a question/instruction after #terminal
            const extra = userInput.trim().substring('#terminal'.length).trim();

            // Build the message that gets sent to AI:
            // Show #terminal as the visible user message, but append terminal content
            // so the AI can read and reason about it
            const messageForAI = extra
                ? `[SSH Terminal Output]\n\`\`\`\n${terminalText}\n\`\`\`\n\n${extra}`
                : `[SSH Terminal Output]\n\`\`\`\n${terminalText}\n\`\`\``;

            // Inject into input and let sendMessage() handle the full flow
            const input = document.getElementById('message-input');
            input.value = messageForAI;
            sendMessage();
        }

        // ============ /terminal — Execute command on remote SSH ============

        async function executeTerminalFromChat(command) {
            const thisConvId = currentConversationId || Date.now().toString();
            if (!currentConversationId) {
                currentConversationId = thisConvId;
                convRuntime[thisConvId] = { isStreaming: false, attachments: [], messages: [] };
            }
            const runtime = getConvRuntime(thisConvId);

            // Hide welcome
            const welcome = document.getElementById('welcome');
            if (welcome) welcome.style.display = 'none';

            // Add user message
            runtime.messages.push({
                role: 'user',
                content: `/terminal ${command}`,
                timestamp: Date.now()
            });
            if (currentConversationId === thisConvId) renderMessages();

            // SSH-only: require connection
            if (!currentSSHConnectionId) {
                runtime.messages.push({
                    role: 'assistant',
                    content: 'No SSH connection active. Please connect to a remote host first via the Terminal panel.',
                    timestamp: Date.now()
                });
                if (currentConversationId === thisConvId) { renderMessages(); scrollToBottom(); }
                return;
            }

            const url = BASE_URL + '/v1/terminal/ssh/execute';
            const body = { connection_id: currentSSHConnectionId, command, timeout: 300 };

            let outputLines = [];
            let exitCode = null;

            try {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });

                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || res.statusText);
                }

                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let eventType = null;

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();

                    for (const line of lines) {
                        if (line.startsWith('event: ')) {
                            eventType = line.slice(7).trim();
                        } else if (line.startsWith('data: ')) {
                            const dataStr = line.slice(6);
                            if (dataStr === '[DONE]') continue;
                            try {
                                const data = JSON.parse(dataStr);

                                // Also push to terminal panel
                                handleTerminalEvent(eventType, data);

                                if (eventType === 'output') {
                                    outputLines.push(data.data || '');
                                } else if (eventType === 'exit') {
                                    exitCode = data.exit_code;
                                } else if (eventType === 'error') {
                                    outputLines.push(`Error: ${data.message}`);
                                }
                            } catch (e) {}
                            eventType = null;
                        }
                    }
                }
            } catch (e) {
                outputLines.push(`Error: ${e.message}`);
            }

            // Build result message
            const outputText = outputLines.join('').trimEnd();
            const exitInfo = exitCode !== null ? `\n[exit code: ${exitCode}]` : '';
            const resultContent = `\`\`\`\n$ ${command}\n${outputText}${exitInfo}\n\`\`\``;

            runtime.messages.push({
                role: 'assistant',
                content: resultContent,
                timestamp: Date.now()
            });
            if (currentConversationId === thisConvId) {
                renderMessages();
                scrollToBottom();
            }

            // Also show command in terminal panel
            appendTerminalOutput(`<span class="ansi-blue">$ ${escapeHtml(command)}</span>`, 'terminal-cmd-line');
        }

        // ============ Team Split Panel ============

        // Drag-to-resize for individual agent cards
        function initTeamCardResize(card) {
            const handle = card.querySelector('.team-split-agent-resize');
            if (!handle) return;

            let startY = 0;
            let startH = 0;

            function onMouseDown(e) {
                e.preventDefault();
                startY = e.clientY;
                startH = card.getBoundingClientRect().height;
                handle.classList.add('dragging');
                document.addEventListener('mousemove', onMouseMove);
                document.addEventListener('mouseup', onMouseUp);
                document.body.style.cursor = 'ns-resize';
                document.body.style.userSelect = 'none';
            }

            function onMouseMove(e) {
                const delta = e.clientY - startY;
                const newH = Math.max(40, startH + delta);
                card.style.height = newH + 'px';
            }

            function onMouseUp() {
                handle.classList.remove('dragging');
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }

            handle.addEventListener('mousedown', onMouseDown);
        }

        let activeTeamSplitId = null;

        function initTeamSplitPanel(teamId, agents, userRequest) {
            activeTeamSplitId = teamId;

            const placeholder = document.getElementById('team-split-placeholder');
            const content = document.getElementById('team-split-content');
            const agentsContainer = document.getElementById('team-split-agents');
            const statusBadge = document.getElementById('team-split-status-badge');
            const requestPreview = document.getElementById('team-split-request-preview');

            if (!content || !agentsContainer) return;

            placeholder.style.display = 'none';
            content.style.display = '';

            // Set header
            statusBadge.textContent = 'Spawned';
            statusBadge.className = 'team-split-status-badge';
            if (requestPreview) {
                const preview = userRequest && userRequest.length > 80 ? userRequest.substring(0, 80) + '...' : (userRequest || '');
                requestPreview.textContent = preview;
            }

            // Detect collaborative mode (agents have name field)
            const isCollaborative = agents && agents.some(a => a.name);

            // Create agent cards
            agentsContainer.innerHTML = '';
            if (agents && agents.length > 0) {
                for (const a of agents) {
                    const cfg = getTeamRoleConfig(a.role);
                    const card = document.createElement('div');
                    card.className = 'team-split-agent-card';
                    card.setAttribute('data-agent-id', a.agent_id);
                    if (a.name) card.setAttribute('data-agent-name', a.name);
                    card.style.setProperty('--agent-color', cfg.color);
                    const nameLabel = a.name ? `${cfg.label} (${escapeHtml(a.name)})` : cfg.label;
                    card.innerHTML = `
                        <div class="team-split-agent-header">
                            <svg fill="none" stroke="${cfg.color}" viewBox="0 0 24 24" width="16" height="16">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${cfg.icon}"/>
                            </svg>
                            <span class="team-split-agent-role">${nameLabel}</span>
                            <span class="team-split-agent-badge idle">idle</span>
                        </div>
                        <div class="team-split-agent-task"></div>
                        <div class="team-split-agent-output"></div>
                        <div class="team-split-agent-resize"></div>
                    `;
                    initTeamCardResize(card);
                    agentsContainer.appendChild(card);
                }
            }

            // For collaborative mode: add messages container, task board, and message input
            if (isCollaborative) {
                // Messages container (chat log between agents)
                let messagesEl = document.getElementById('team-split-messages');
                if (!messagesEl) {
                    messagesEl = document.createElement('div');
                    messagesEl.id = 'team-split-messages';
                    messagesEl.className = 'team-split-messages';
                    messagesEl.style.display = 'none';
                    messagesEl.style.cssText = 'display:none;max-height:200px;overflow-y:auto;padding:8px;margin:8px 0;border:1px solid var(--border-color);border-radius:6px;font-size:12px;';
                    content.appendChild(messagesEl);
                }

                // Task board container
                let taskBoardEl = document.getElementById('team-split-task-board');
                if (!taskBoardEl) {
                    taskBoardEl = document.createElement('div');
                    taskBoardEl.id = 'team-split-task-board';
                    taskBoardEl.className = 'team-split-task-board';
                    taskBoardEl.style.display = 'none';
                    taskBoardEl.style.cssText = 'display:none;padding:8px;margin:8px 0;border:1px solid var(--border-color);border-radius:6px;font-size:12px;';
                    content.appendChild(taskBoardEl);
                }

                // Message input
                let inputEl = document.getElementById('team-split-input');
                if (!inputEl) {
                    inputEl = document.createElement('div');
                    inputEl.id = 'team-split-input';
                    inputEl.style.display = 'none';
                    inputEl.style.cssText = 'display:none;padding:8px;align-items:center;gap:6px;';
                    content.appendChild(inputEl);
                }
                initTeamMessageInput(teamId);
            }

            // Auto-switch to Team tab
            const panel = document.getElementById('right-panel');
            if (panel && panel.classList.contains('hidden')) {
                panel.classList.remove('hidden');
            }
            switchRightPanelTab('team');
        }

        function updateTeamSplitStatus(teamId, status, text) {
            if (teamId !== activeTeamSplitId) return;
            const badge = document.getElementById('team-split-status-badge');
            if (!badge) return;
            badge.textContent = text || status;
            badge.className = `team-split-status-badge ${status}`;
        }

        function addTeamSplitAgents(teamId, tasks) {
            if (teamId !== activeTeamSplitId) return;
            const agentsContainer = document.getElementById('team-split-agents');
            if (!agentsContainer) return;

            for (const task of tasks) {
                const existingCard = agentsContainer.querySelector(`[data-agent-id="${task.assigned_to}"]`);
                if (existingCard) {
                    // Update task title
                    const taskEl = existingCard.querySelector('.team-split-agent-task');
                    if (taskEl) taskEl.textContent = task.title;
                    continue;
                }
                const cfg = getTeamRoleConfig(task.role);
                const card = document.createElement('div');
                card.className = 'team-split-agent-card';
                card.setAttribute('data-agent-id', task.assigned_to);
                card.style.setProperty('--agent-color', cfg.color);
                card.innerHTML = `
                    <div class="team-split-agent-header">
                        <svg fill="none" stroke="${cfg.color}" viewBox="0 0 24 24" width="16" height="16">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${cfg.icon}"/>
                        </svg>
                        <span class="team-split-agent-role">${cfg.label}</span>
                        <span class="team-split-agent-badge idle">idle</span>
                    </div>
                    <div class="team-split-agent-task">${escapeHtml(task.title)}</div>
                    <div class="team-split-agent-output"></div>
                    <div class="team-split-agent-resize"></div>
                `;
                initTeamCardResize(card);
                agentsContainer.appendChild(card);
            }
        }

        function updateTeamSplitAgent(teamId, agentId, role, status, taskTitle, content, agentName) {
            if (teamId !== activeTeamSplitId) return;
            const agentsContainer = document.getElementById('team-split-agents');
            if (!agentsContainer) return;
            // Find card by agentId or agentName (collaborative mode uses names)
            let card = agentId ? agentsContainer.querySelector(`[data-agent-id="${agentId}"]`) : null;
            if (!card && agentName) {
                card = agentsContainer.querySelector(`[data-agent-name="${agentName}"]`);
            }
            if (!card) return;

            // Update badge
            const badge = card.querySelector('.team-split-agent-badge');
            if (badge) {
                badge.textContent = status;
                badge.className = `team-split-agent-badge ${status}`;
            }

            // Update task title if provided
            if (taskTitle) {
                const taskEl = card.querySelector('.team-split-agent-task');
                if (taskEl) taskEl.textContent = taskTitle;
            }

            // Pulsing animation
            if (status === 'thinking' || status === 'executing') {
                card.classList.add('active');
            } else {
                card.classList.remove('active');
            }

            // Show full output (not truncated, unlike chat cards)
            if (content) {
                const outputEl = card.querySelector('.team-split-agent-output');
                if (outputEl) {
                    // Don't overwrite if already has streamed content
                    const hasStreamed = outputEl.getAttribute('data-streaming') === 'true';
                    if (!hasStreamed || status === 'error') {
                        outputEl.textContent = content;
                    }
                    outputEl.style.display = 'block';
                    // Auto-expand card if not user-resized
                    if (!card.style.height) {
                        card.style.height = '180px';
                    }
                    outputEl.removeAttribute('data-streaming');
                    if (status === 'error') {
                        outputEl.classList.add('error');
                        outputEl.classList.remove('success');
                    } else if (status === 'complete') {
                        outputEl.classList.add('success');
                        outputEl.classList.remove('error');
                    }
                }
            } else if (status === 'complete' || status === 'error') {
                // Apply styling even without new content (streamed content already present)
                const outputEl = card.querySelector('.team-split-agent-output');
                if (outputEl && outputEl.style.display === 'block') {
                    outputEl.removeAttribute('data-streaming');
                    if (status === 'error') {
                        outputEl.classList.add('error');
                        outputEl.classList.remove('success');
                    } else if (status === 'complete') {
                        outputEl.classList.add('success');
                        outputEl.classList.remove('error');
                    }
                }
            }
        }

        function resetTeamSplitPanel() {
            activeTeamSplitId = null;
            const placeholder = document.getElementById('team-split-placeholder');
            const content = document.getElementById('team-split-content');
            const agentsContainer = document.getElementById('team-split-agents');

            if (placeholder) placeholder.style.display = '';
            if (content) content.style.display = 'none';
            if (agentsContainer) agentsContainer.innerHTML = '';
        }

        // === Collaborative Team UI Functions ===

        function appendTeamMessage(teamId, sender, recipient, content, summary, isBroadcast) {
            if (teamId !== activeTeamSplitId) return;
            const messagesContainer = document.getElementById('team-split-messages');
            if (!messagesContainer) return;

            messagesContainer.style.display = 'block';
            const msgEl = document.createElement('div');
            msgEl.className = `team-split-message ${isBroadcast ? 'broadcast' : 'dm'}`;
            const label = isBroadcast
                ? `${escapeHtml(sender)} -> all`
                : `${escapeHtml(sender)} -> ${escapeHtml(recipient)}`;
            msgEl.innerHTML = `
                <div class="team-msg-header">${label}</div>
                <div class="team-msg-content">${escapeHtml(summary || content.substring(0, 100))}</div>
            `;
            messagesContainer.appendChild(msgEl);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }

        function addTeamTaskBoardItem(teamId, taskId, title, owner, status) {
            if (teamId !== activeTeamSplitId) return;
            const taskBoard = document.getElementById('team-split-task-board');
            if (!taskBoard) return;

            taskBoard.style.display = 'block';
            const existing = taskBoard.querySelector(`[data-task-id="${taskId}"]`);
            if (existing) {
                updateTeamTaskBoardItem(teamId, taskId, status, owner, title);
                return;
            }

            const taskEl = document.createElement('div');
            taskEl.className = `team-task-item ${status}`;
            taskEl.setAttribute('data-task-id', taskId);
            taskEl.innerHTML = `
                <span class="team-task-id">#${escapeHtml(taskId)}</span>
                <span class="team-task-title">${escapeHtml(title)}</span>
                <span class="team-task-owner">${owner ? escapeHtml(owner) : ''}</span>
                <span class="team-task-status ${status}">${escapeHtml(status)}</span>
            `;
            taskBoard.appendChild(taskEl);
        }

        function updateTeamTaskBoardItem(teamId, taskId, status, owner, title) {
            if (teamId !== activeTeamSplitId) return;
            const taskBoard = document.getElementById('team-split-task-board');
            if (!taskBoard) return;

            const taskEl = taskBoard.querySelector(`[data-task-id="${taskId}"]`);
            if (!taskEl) {
                // If task doesn't exist yet, create it
                addTeamTaskBoardItem(teamId, taskId, title || '', owner, status);
                return;
            }

            taskEl.className = `team-task-item ${status}`;
            const statusEl = taskEl.querySelector('.team-task-status');
            if (statusEl) {
                statusEl.textContent = status;
                statusEl.className = `team-task-status ${status}`;
            }
            if (owner) {
                const ownerEl = taskEl.querySelector('.team-task-owner');
                if (ownerEl) ownerEl.textContent = owner;
            }
            if (title) {
                const titleEl = taskEl.querySelector('.team-task-title');
                if (titleEl) titleEl.textContent = title;
            }
        }

        function sendTeamPanelMessage(teamId, content) {
            if (!teamId || !content) return;
            fetch(`${CONFIG.API_URL}/v1/teams/${teamId}/message`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: content, recipient: 'team-lead' }),
            }).catch(err => console.error('Failed to send team message:', err));
        }

        function initTeamMessageInput(teamId) {
            const inputContainer = document.getElementById('team-split-input');
            if (!inputContainer) return;

            inputContainer.style.display = 'flex';
            inputContainer.innerHTML = `
                <input type="text" id="team-msg-input" placeholder="Send message to team lead..."
                       style="flex:1;padding:6px 10px;border:1px solid var(--border-color);border-radius:6px;background:var(--input-bg);color:var(--text-color);font-size:13px;">
                <button id="team-msg-send" style="margin-left:6px;padding:6px 12px;border:none;border-radius:6px;background:var(--accent-color);color:#fff;cursor:pointer;font-size:13px;">Send</button>
            `;

            const input = document.getElementById('team-msg-input');
            const sendBtn = document.getElementById('team-msg-send');

            function doSend() {
                const text = input.value.trim();
                if (!text) return;
                sendTeamPanelMessage(teamId, text);
                input.value = '';
            }

            sendBtn.addEventListener('click', doSend);
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    doSend();
                }
            });
        }

