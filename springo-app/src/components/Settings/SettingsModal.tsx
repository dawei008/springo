import { useState, useEffect, useCallback, useRef } from 'react'
import { useSettingsStore } from '@/stores/settingsStore'
import { useUIStore } from '@/stores/uiStore'
import type { ModelInfo } from '@/types'

type SettingsTab = 'general' | 'models' | 'tools' | 'memory' | 'integrations'

const BASE_URL = 'http://127.0.0.1:8081'

export default function SettingsModal() {
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen)
  const showToast = useUIStore((s) => s.showToast)

  const settings = useSettingsStore((s) => s.settings)
  const saveSettings = useSettingsStore((s) => s.saveSettings)
  const models = useSettingsStore((s) => s.models)
  const modelsByProvider = useSettingsStore((s) => s.modelsByProvider)
  const defaultModel = useSettingsStore((s) => s.defaultModel)
  const defaultCompactModel = useSettingsStore((s) => s.defaultCompactModel)
  const workingDir = useSettingsStore((s) => s.workingDir)
  const workingFolders = useSettingsStore((s) => s.workingFolders)
  const defaultWorkingFolder = useSettingsStore((s) => s.defaultWorkingFolder)

  const [activeTab, setActiveTab] = useState<SettingsTab>(() => {
    return (localStorage.getItem('settingsTab') as SettingsTab) || 'general'
  })

  // General tab state
  const [localDefaultWorkdir, setLocalDefaultWorkdir] = useState(defaultWorkingFolder || '~/Downloads')

  // Models tab state
  const [awsAccessKey, setAwsAccessKey] = useState('')
  const [awsSecretKey, setAwsSecretKey] = useState('')
  const [awsRegion, setAwsRegion] = useState('us-west-2')
  const [awsTesting, setAwsTesting] = useState(false)
  const [awsStatus, setAwsStatus] = useState('')
  const [deepseekApiKey, setDeepseekApiKey] = useState('')
  const [deepseekTesting, setDeepseekTesting] = useState(false)
  const [deepseekStatus, setDeepseekStatus] = useState('')
  const [minimaxApiKey, setMinimaxApiKey] = useState('')
  const [minimaxTesting, setMinimaxTesting] = useState(false)
  const [minimaxStatus, setMinimaxStatus] = useState('')
  const [localModel, setLocalModel] = useState(settings.model || defaultModel)
  const [localEnable1mContext, setLocalEnable1mContext] = useState(settings.enable1mContext === true)
  const [localMaxTokens, setLocalMaxTokens] = useState(settings.maxTokens || 16384)
  const [localTemperature, setLocalTemperature] = useState(settings.temperature || 0.7)
  const [localCompactModel, setLocalCompactModel] = useState(settings.compactModel || defaultCompactModel)

  // Tools tab state
  const [skills, setSkills] = useState<Array<{ name: string; description?: string }>>([])
  const [mcpServers, setMcpServers] = useState<Array<{
    name: string; running: boolean; enabled: boolean;
    status: string; tools: number; cached_tools: number;
    description?: string; command?: string;
  }>>([])
  const [mcpAddFormOpen, setMcpAddFormOpen] = useState(false)
  const [mcpNewName, setMcpNewName] = useState('')
  const [mcpNewCommand, setMcpNewCommand] = useState('')
  const [mcpNewArgs, setMcpNewArgs] = useState('')
  const [mcpNewEnv, setMcpNewEnv] = useState('')

  // Memory tab state
  const [memEnabled, setMemEnabled] = useState(false)
  const [memBackend, setMemBackend] = useState('agentcore')
  const [memId, setMemId] = useState('')
  const [s3Bucket, setS3Bucket] = useState('')
  const [ltmStrategies, setLtmStrategies] = useState<Array<{ name: string; description?: string }> | null>(null)
  const [ltmRefreshing, setLtmRefreshing] = useState(false)

  // Integrations tab state
  const [feishuEnabled, setFeishuEnabled] = useState(false)
  const [feishuAppId, setFeishuAppId] = useState('')
  const [feishuAppSecret, setFeishuAppSecret] = useState('')
  const [feishuTesting, setFeishuTesting] = useState(false)
  const [feishuStatus, setFeishuStatus] = useState('')

  const backdropRef = useRef<HTMLDivElement>(null)

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        closeSettings()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  // --- Token limit calculation ---
  const selectedModel = models.find((m: ModelInfo) => m.id === localModel)
  const maxOutputTokens = selectedModel
    ? (selectedModel as unknown as { max_output?: number }).max_output || 64000
    : 64000
  const supportsExtended = selectedModel
    ? (selectedModel as unknown as { supports_extended_context?: boolean }).supports_extended_context
    : false

  // --- Tab switching ---
  const switchTab = useCallback((tab: SettingsTab) => {
    setActiveTab(tab)
    localStorage.setItem('settingsTab', tab)
  }, [])

  // --- Load data on mount ---
  useEffect(() => {
    loadMemorySettings()
    loadFeishuSettings()
    loadSkills()
    loadMcpServers()
  }, [])

  // Clamp maxTokens when model changes
  useEffect(() => {
    if (localMaxTokens > maxOutputTokens) {
      setLocalMaxTokens(Math.min(16384, maxOutputTokens))
    }
  }, [localModel, maxOutputTokens])

  // --- Load helpers ---
  async function loadMemorySettings() {
    try {
      const res = await fetch(`${BASE_URL}/v1/config/memory`)
      const data = await res.json()
      setMemEnabled(data.memory_enabled !== false)
      setMemBackend(data.memory_backend || 'agentcore')
      setMemId(data.memory_id || '')
    } catch { /* ignore */ }
    try {
      const s3Res = await fetch(`${BASE_URL}/v1/config/s3`)
      const s3Data = await s3Res.json()
      setS3Bucket(s3Data.s3_bucket || '')
    } catch { /* ignore */ }
  }

  async function loadFeishuSettings() {
    try {
      const res = await fetch(`${BASE_URL}/v1/config/feishu`)
      const data = await res.json()
      setFeishuEnabled(!!data.enabled)
      setFeishuAppId(data.app_id || '')
      if (data.running) {
        setFeishuStatus('Running (WebSocket connected)')
      } else if (data.enabled && data.app_id) {
        setFeishuStatus('Configured but not running')
      }
    } catch { /* ignore */ }
  }

  async function loadSkills() {
    try {
      const res = await fetch(`${BASE_URL}/v1/skills`)
      const data = await res.json()
      setSkills(data.skills || [])
    } catch { /* ignore */ }
  }

  async function loadMcpServers() {
    try {
      const res = await fetch(`${BASE_URL}/v1/mcp/servers`)
      const data = await res.json()
      setMcpServers(data.servers || [])
    } catch { /* ignore */ }
  }

  // --- Close (saves settings) ---
  function closeSettings() {
    saveSettings({
      model: localModel,
      maxTokens: localMaxTokens,
      temperature: localTemperature,
      compactModel: localCompactModel,
      enable1mContext: localEnable1mContext,
    })
    // Update default working dir
    if (localDefaultWorkdir.trim() && localDefaultWorkdir !== defaultWorkingFolder) {
      // Update Zustand store so createSession() picks it up
      useSettingsStore.setState({ defaultWorkingFolder: localDefaultWorkdir.trim() });
      if (window.electronAPI?.cache) {
        window.electronAPI.cache.set('workspace', {
          workingFolders,
          currentWorkingDir: workingDir,
          defaultWorkingFolder: localDefaultWorkdir.trim(),
        })
      }
    }
    // Save AWS credentials to backend if entered
    if (awsAccessKey && awsSecretKey) {
      fetch(`${BASE_URL}/v1/config/aws`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          access_key_id: awsAccessKey,
          secret_access_key: awsSecretKey,
          region: awsRegion,
        }),
      }).catch(() => {})
    }
    // Save DeepSeek key to backend if entered
    if (deepseekApiKey) {
      fetch(`${BASE_URL}/v1/config/vendor-keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vendor: 'deepseek', api_key: deepseekApiKey }),
      }).catch(() => {})
    }
    // Save MiniMax key to backend if entered
    if (minimaxApiKey) {
      fetch(`${BASE_URL}/v1/config/vendor-keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vendor: 'minimax', api_key: minimaxApiKey }),
      }).catch(() => {})
    }
    // Save memory settings to backend
    saveMemorySettings()
    // Save Feishu settings to backend
    saveFeishuSettings()
    setSettingsOpen(false)
  }

  // Click outside to close
  function handleOverlayClick(e: React.MouseEvent) {
    if (e.target === backdropRef.current) closeSettings()
  }

  // --- General tab: browse working directory ---
  async function browseDefaultWorkdir() {
    if (window.electronAPI?.selectFolder) {
      const folder = await window.electronAPI.selectFolder()
      if (folder) {
        setLocalDefaultWorkdir(folder)
      }
    }
  }

  // --- Models tab: AWS ---
  async function testAwsConnection() {
    setAwsTesting(true)
    setAwsStatus('')
    // Save credentials first if entered
    if (awsAccessKey && awsSecretKey) {
      try {
        await fetch(`${BASE_URL}/v1/config/aws`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            access_key_id: awsAccessKey,
            secret_access_key: awsSecretKey,
            region: awsRegion,
          }),
        })
      } catch { /* ignore */ }
    }
    try {
      const res = await fetch(`${BASE_URL}/v1/config/aws/test`)
      const data = await res.json()
      if (data.valid) {
        setAwsStatus(`\u2713 Connected (${data.account})`)
      } else {
        setAwsStatus(`\u2717 ${data.error || 'Connection failed'}`)
      }
    } catch (e) {
      setAwsStatus(`\u2717 ${(e as Error).message}`)
    } finally {
      setAwsTesting(false)
    }
  }

  // --- Models tab: DeepSeek ---
  async function testDeepSeekConnection() {
    setDeepseekTesting(true)
    setDeepseekStatus('')
    if (deepseekApiKey) {
      try {
        await fetch(`${BASE_URL}/v1/config/vendor-keys`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ vendor: 'deepseek', api_key: deepseekApiKey }),
        })
      } catch { /* ignore */ }
    }
    try {
      const res = await fetch(`${BASE_URL}/v1/config/vendor-keys/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vendor: 'deepseek', api_key: deepseekApiKey || 'use-stored' }),
      })
      const data = await res.json()
      if (data.success) {
        setDeepseekStatus(`\u2713 ${data.message || 'Connected'}`)
        useSettingsStore.getState().loadModels()
      } else {
        setDeepseekStatus(`\u2717 ${data.error || 'Connection failed'}`)
      }
    } catch (e) {
      setDeepseekStatus(`\u2717 ${(e as Error).message}`)
    } finally {
      setDeepseekTesting(false)
    }
  }

  // --- Models tab: MiniMax ---
  async function testMiniMaxConnection() {
    setMinimaxTesting(true)
    setMinimaxStatus('')
    if (minimaxApiKey) {
      try {
        await fetch(`${BASE_URL}/v1/config/vendor-keys`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ vendor: 'minimax', api_key: minimaxApiKey }),
        })
      } catch { /* ignore */ }
    }
    try {
      const res = await fetch(`${BASE_URL}/v1/config/vendor-keys/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vendor: 'minimax', api_key: minimaxApiKey || 'use-stored' }),
      })
      const data = await res.json()
      if (data.success) {
        setMinimaxStatus(`\u2713 ${data.message || 'Connected'}`)
        useSettingsStore.getState().loadModels()
      } else {
        setMinimaxStatus(`\u2717 ${data.error || 'Connection failed'}`)
      }
    } catch (e) {
      setMinimaxStatus(`\u2717 ${(e as Error).message}`)
    } finally {
      setMinimaxTesting(false)
    }
  }

  // --- Tools tab: Skills ---
  async function openSkillsFolder() {
    try {
      const res = await fetch(`${BASE_URL}/v1/skills/path`)
      const data = await res.json()
      if (data.path) {
        if (window.electronAPI?.openPath) {
          window.electronAPI.openPath(data.path)
        }
      }
    } catch { /* ignore */ }
  }

  async function reloadSkills() {
    setSkills([])
    try {
      await fetch(`${BASE_URL}/v1/skills/reload`, { method: 'POST' })
      await loadSkills()
    } catch { /* ignore */ }
  }

  // --- Tools tab: MCP ---
  async function refreshMcpTools() {
    try {
      await fetch(`${BASE_URL}/v1/mcp/refresh-tools`, { method: 'POST' })
      await loadMcpServers()
      showToast('MCP tools refreshed', 'info')
    } catch { /* ignore */ }
  }

  function toggleMcpAddForm() {
    setMcpAddFormOpen(!mcpAddFormOpen)
  }

  async function addMcpServer() {
    if (!mcpNewName || !mcpNewCommand) return
    const args = mcpNewArgs ? mcpNewArgs.split(',').map((s) => s.trim()) : []
    const env: Record<string, string> = {}
    if (mcpNewEnv) {
      mcpNewEnv.split(',').forEach((pair) => {
        const [k, ...rest] = pair.split('=')
        if (k && rest.length) env[k.trim()] = rest.join('=').trim()
      })
    }
    try {
      await fetch(`${BASE_URL}/v1/mcp/servers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: mcpNewName, command: mcpNewCommand, args, env }),
      })
      setMcpNewName('')
      setMcpNewCommand('')
      setMcpNewArgs('')
      setMcpNewEnv('')
      setMcpAddFormOpen(false)
      loadMcpServers()
      showToast(`Added MCP server: ${mcpNewName}`, 'success')
    } catch { /* ignore */ }
  }

  async function removeMcpServer(name: string) {
    try {
      await fetch(`${BASE_URL}/v1/mcp/servers/${name}`, { method: 'DELETE' })
      loadMcpServers()
      showToast(`Removed MCP server: ${name}`, 'info')
    } catch { /* ignore */ }
  }

  // --- Memory tab: save & LTM ---
  async function saveMemorySettings() {
    try {
      await fetch(`${BASE_URL}/v1/config/memory`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: memEnabled,
          agent_id: memId,
          memory_backend: memBackend,
        }),
      })
      await fetch(`${BASE_URL}/v1/config/s3`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bucket: s3Bucket,
          enabled: memEnabled && !!s3Bucket,
        }),
      })
    } catch { /* ignore */ }
  }

  async function refreshLtmStrategies() {
    setLtmRefreshing(true)
    try {
      await saveMemorySettings()
      const res = await fetch(`${BASE_URL}/v1/config/memory/strategies/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      const result = await res.json()
      if (result.success && result.strategies) {
        setLtmStrategies(result.strategies)
        showToast(`Connected -- ${result.strategies.length} strategies`, 'success')
      } else {
        setLtmStrategies(null)
        showToast(result.error || 'No strategies found', 'error')
      }
    } catch {
      showToast('Failed to connect to Memory', 'error')
    } finally {
      setLtmRefreshing(false)
    }
  }

  // --- Integrations tab: Feishu ---
  async function saveFeishuSettings() {
    const payload: Record<string, unknown> = { enabled: feishuEnabled, app_id: feishuAppId }
    if (feishuAppSecret) payload.app_secret = feishuAppSecret
    try {
      await fetch(`${BASE_URL}/v1/config/feishu`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    } catch { /* ignore */ }
  }

  async function testFeishuConnection() {
    setFeishuTesting(true)
    setFeishuStatus('')
    await saveFeishuSettings()
    try {
      const res = await fetch(`${BASE_URL}/v1/config/feishu/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      const data = await res.json()
      if (data.success) {
        setFeishuStatus(`\u2713 ${data.message}`)
      } else {
        setFeishuStatus(`\u2717 ${data.error}`)
      }
    } catch (e) {
      setFeishuStatus(`\u2717 Connection failed: ${(e as Error).message}`)
    } finally {
      setFeishuTesting(false)
    }
  }

  // --- Render model options grouped by provider ---
  function renderModelOptions() {
    const PROVIDER_LABELS: Record<string, string> = {
      bedrock: 'Amazon Bedrock',
      deepseek: 'DeepSeek (Direct)',
      minimax: 'MiniMax (Direct)',
      kimi: 'Kimi (Direct)',
      qwen: 'Qwen (Direct)',
      zhipu: 'Zhipu (Direct)',
    }
    const providers = Object.keys(modelsByProvider)
    if (providers.length) {
      return providers.map((provider) => (
        <optgroup key={provider} label={PROVIDER_LABELS[provider] || provider}>
          {modelsByProvider[provider].map((m: ModelInfo) => (
            <option key={m.id} value={m.id}>
              {(m as unknown as { display_name?: string }).display_name || m.name || m.id}
            </option>
          ))}
        </optgroup>
      ))
    }
    return models.map((m: ModelInfo) => (
      <option key={m.id} value={m.id}>
        {m.name || m.id}
      </option>
    ))
  }

  return (
    <div className="modal-overlay active" id="settings-modal" ref={backdropRef} onClick={handleOverlayClick}>
      <div className="modal">
        <div className="modal-header">
          <h2>Settings</h2>
          <button className="icon-btn" onClick={closeSettings}>
            <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 4l10 10M14 4L4 14" />
            </svg>
          </button>
        </div>
        <div className="modal-body">
          {/* Left Tab Bar */}
          <div className="settings-tabs">
            <button
              className={`settings-tab${activeTab === 'general' ? ' active' : ''}`}
              data-tab="general"
              onClick={() => switchTab('general')}
            >
              <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="3" /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
              </svg>
              General
            </button>
            <button
              className={`settings-tab${activeTab === 'models' ? ' active' : ''}`}
              data-tab="models"
              onClick={() => switchTab('models')}
            >
              <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <rect x="4" y="4" width="16" height="16" rx="2" /><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3" />
              </svg>
              Models
            </button>
            <button
              className={`settings-tab${activeTab === 'tools' ? ' active' : ''}`}
              data-tab="tools"
              onClick={() => switchTab('tools')}
            >
              <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z" />
              </svg>
              Tools
            </button>
            <button
              className={`settings-tab${activeTab === 'memory' ? ' active' : ''}`}
              data-tab="memory"
              onClick={() => switchTab('memory')}
            >
              <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 01-2 2h-4a2 2 0 01-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z" /><path d="M9 21h6M10 17v4M14 17v4" />
              </svg>
              Memory
            </button>
            <button
              className={`settings-tab${activeTab === 'integrations' ? ' active' : ''}`}
              data-tab="integrations"
              onClick={() => switchTab('integrations')}
            >
              <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path d="M16 3h5v5M4 20L21 3M21 16v5h-5M15 15l6 6M4 4l5 5" />
              </svg>
              Integrations
            </button>
          </div>

          {/* Right Content Area */}
          <div className="settings-content">

            {/* ====== General Tab ====== */}
            <div className={`settings-tab-panel${activeTab === 'general' ? ' active' : ''}`} id="tab-general">
              <h3 style={{ margin: '0 0 12px', fontSize: '14px', color: 'var(--text-secondary)' }}>Default Working Directory</h3>
              <div className="setting-group">
                <label>Path</label>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <input
                    type="text"
                    placeholder="~/Downloads"
                    style={{ flex: 1 }}
                    value={localDefaultWorkdir}
                    onChange={(e) => setLocalDefaultWorkdir(e.target.value)}
                  />
                  <button onClick={browseDefaultWorkdir} className="browse-btn">
                    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                    </svg>
                  </button>
                </div>
                <div className="hint">Default folder for new chats. Use absolute path (e.g., ~/Downloads)</div>
              </div>
            </div>

            {/* ====== Models Tab ====== */}
            <div className={`settings-tab-panel${activeTab === 'models' ? ' active' : ''}`} id="tab-models">

              {/* Provider 1: Amazon Bedrock */}
              <div className="provider-section">
                <h3 style={{ margin: '0 0 12px', fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>Amazon Bedrock</h3>
                <div className="hint" style={{ marginBottom: '12px', lineHeight: 1.5 }}>
                  Auto-detects from environment variables or <code>~/.aws/credentials</code>.<br />
                  Only enter below if not using those methods.
                </div>
                <div className="setting-group">
                  <label>Access Key ID</label>
                  <input
                    type="text"
                    placeholder="Enter your access key"
                    value={awsAccessKey}
                    onChange={(e) => setAwsAccessKey(e.target.value)}
                  />
                </div>
                <div className="setting-group">
                  <label>Secret Access Key</label>
                  <input
                    type="password"
                    placeholder="Enter your secret key"
                    value={awsSecretKey}
                    onChange={(e) => setAwsSecretKey(e.target.value)}
                  />
                </div>
                <div className="hint">Manual credentials will be saved to <code>~/.springo/.env</code></div>
                <div className="setting-group" style={{ marginTop: '8px' }}>
                  <label>Region</label>
                  <select value={awsRegion} onChange={(e) => setAwsRegion(e.target.value)}>
                    <option value="us-west-2">us-west-2 (Oregon)</option>
                    <option value="us-east-1">us-east-1 (N. Virginia)</option>
                    <option value="eu-west-1">eu-west-1 (Ireland)</option>
                    <option value="ap-northeast-1">ap-northeast-1 (Tokyo)</option>
                  </select>
                  <div className="hint" style={{ marginTop: '4px' }}>Bedrock API, AgentCore Memory, and S3 bucket should all be in this region</div>
                </div>
                <div className="setting-group" style={{ marginTop: '12px' }}>
                  <button onClick={testAwsConnection} disabled={awsTesting}>
                    {awsTesting ? 'Testing...' : 'Test Connection'}
                  </button>
                  <span style={{ marginLeft: '12px', fontSize: '13px' }}>{awsStatus}</span>
                </div>
              </div>

              <div className="setting-divider"></div>

              {/* Provider 2: DeepSeek (Direct API) */}
              <div className="provider-section">
                <h3 style={{ margin: '0 0 12px', fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>DeepSeek (Direct API)</h3>
                <div className="hint" style={{ marginBottom: '12px', lineHeight: 1.5 }}>
                  Calls DeepSeek API directly. Get your key from <code>platform.deepseek.com</code>.
                </div>
                <div className="setting-group">
                  <label>API Key</label>
                  <input
                    type="password"
                    placeholder="sk-..."
                    value={deepseekApiKey}
                    onChange={(e) => setDeepseekApiKey(e.target.value)}
                  />
                </div>
                <div className="setting-group" style={{ marginTop: '12px' }}>
                  <button onClick={testDeepSeekConnection} disabled={deepseekTesting}>
                    {deepseekTesting ? 'Testing...' : 'Test Connection'}
                  </button>
                  <span style={{ marginLeft: '12px', fontSize: '13px' }}>{deepseekStatus}</span>
                </div>
              </div>

              <div className="setting-divider"></div>

              {/* Provider 3: MiniMax (Direct API) */}
              <div className="provider-section">
                <h3 style={{ margin: '0 0 12px', fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>MiniMax (Direct API)</h3>
                <div className="hint" style={{ marginBottom: '12px', lineHeight: 1.5 }}>
                  Calls MiniMax API directly. Get your key from <code>platform.minimaxi.com</code>.
                </div>
                <div className="setting-group">
                  <label>API Key</label>
                  <input
                    type="password"
                    placeholder="eyJ..."
                    value={minimaxApiKey}
                    onChange={(e) => setMinimaxApiKey(e.target.value)}
                  />
                </div>
                <div className="setting-group" style={{ marginTop: '12px' }}>
                  <button onClick={testMiniMaxConnection} disabled={minimaxTesting}>
                    {minimaxTesting ? 'Testing...' : 'Test Connection'}
                  </button>
                  <span style={{ marginLeft: '12px', fontSize: '13px' }}>{minimaxStatus}</span>
                </div>
              </div>

              <div className="setting-divider"></div>

              {/* Model Settings */}
              <div className="provider-section">
                <h3 style={{ margin: '0 0 12px', fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>Model Settings</h3>
                <div className="setting-group">
                  <label>Default Model</label>
                  <select value={localModel} onChange={(e) => setLocalModel(e.target.value)}>
                    {renderModelOptions()}
                  </select>
                </div>
                <div
                  className="setting-group"
                  id="extended-context-group"
                  style={{ display: supportsExtended ? undefined : 'none' }}
                >
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      style={{ width: 'auto' }}
                      checked={localEnable1mContext}
                      onChange={(e) => setLocalEnable1mContext(e.target.checked)}
                    />
                    Enable 1M Context Window (Beta)
                  </label>
                  <div className="hint">Uses full 1,000,000 token context (vs standard 200,000). Requires Bedrock beta access.</div>
                </div>
                <div className="setting-group">
                  <label>Max Tokens</label>
                  <input
                    type="number"
                    value={localMaxTokens}
                    min={100}
                    max={maxOutputTokens}
                    onChange={(e) => setLocalMaxTokens(Number(e.target.value))}
                  />
                  <div className="hint">Maximum number of tokens in the response</div>
                </div>
                <div className="setting-group">
                  <label>Temperature</label>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.1}
                    value={localTemperature}
                    onChange={(e) => setLocalTemperature(Number(e.target.value))}
                  />
                  <div className="hint">Controls randomness: <span>{localTemperature}</span></div>
                </div>
                <div className="setting-group">
                  <label>Context Compact Model</label>
                  <select value={localCompactModel} onChange={(e) => setLocalCompactModel(e.target.value)}>
                    {renderModelOptions()}
                  </select>
                  <div className="hint">Model for context summarization (Haiku is faster &amp; cheaper)</div>
                </div>
              </div>
            </div>

            {/* ====== Tools Tab ====== */}
            <div className={`settings-tab-panel${activeTab === 'tools' ? ' active' : ''}`} id="tab-tools">
              <div className="settings-section-header">
                <h3>Skills</h3>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button onClick={openSkillsFolder}>Open Folder</button>
                  <button onClick={reloadSkills}>Reload</button>
                </div>
              </div>
              <div className="settings-list" id="skills-list">
                {skills.length === 0 ? (
                  <div className="settings-list-empty">No skills found in skills/ directory</div>
                ) : (
                  skills.map((skill) => (
                    <div key={skill.name} className="settings-list-item">
                      <div className="item-icon">
                        <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                        </svg>
                      </div>
                      <div className="item-info">
                        <div className="item-name">{skill.name}</div>
                        <div className="item-desc">{skill.description || 'No description'}</div>
                      </div>
                    </div>
                  ))
                )}
              </div>
              <div className="hint">Skills are loaded from the <code>skills/</code> directory. Each skill folder should contain a <code>SKILL.md</code> file.</div>

              <div className="setting-divider"></div>

              <div className="settings-section-header">
                <h3>MCP Servers</h3>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button onClick={refreshMcpTools} id="btn-refresh-mcp" title="Discover tools for newly added servers">Refresh Tools</button>
                  <button onClick={toggleMcpAddForm}>+ Add</button>
                </div>
              </div>
              <div className="settings-list" id="mcp-servers-list">
                {mcpServers.length === 0 ? (
                  <div className="settings-list-empty">No MCP servers configured</div>
                ) : (
                  mcpServers.map((server) => {
                    let statusClass = 'stopped'
                    let statusText = server.cached_tools > 0
                      ? `Ready (${server.cached_tools} tools)`
                      : 'No tools cached'
                    if (!server.enabled) {
                      statusClass = 'disabled'
                      statusText = 'Disabled'
                    } else if (server.running) {
                      statusClass = 'running'
                      statusText = `Running (${server.tools} tools)`
                    } else if (server.status === 'error') {
                      statusClass = 'error'
                      statusText = 'Error'
                    }
                    return (
                      <div key={server.name} className={`settings-list-item${!server.enabled ? ' disabled' : ''}`}>
                        <div className="item-icon">
                          <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                            <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                            <line x1="8" y1="21" x2="16" y2="21" />
                            <line x1="12" y1="17" x2="12" y2="21" />
                          </svg>
                        </div>
                        <div className="item-info">
                          <div className="item-name">{server.name}</div>
                          <div className="item-desc">{server.description || server.command || ''}</div>
                        </div>
                        <span className={`item-status ${statusClass}`}>{statusText}</span>
                        <div className="item-actions">
                          <button className="danger" onClick={() => removeMcpServer(server.name)}>Remove</button>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
              {mcpAddFormOpen && (
                <div id="mcp-add-form" className="settings-add-form">
                  <div className="form-row">
                    <input
                      type="text"
                      placeholder="Server name (e.g., filesystem)"
                      value={mcpNewName}
                      onChange={(e) => setMcpNewName(e.target.value)}
                    />
                  </div>
                  <div className="form-row">
                    <input
                      type="text"
                      placeholder="Command (e.g., npx)"
                      value={mcpNewCommand}
                      onChange={(e) => setMcpNewCommand(e.target.value)}
                    />
                  </div>
                  <div className="form-row">
                    <input
                      type="text"
                      placeholder="Arguments (comma separated)"
                      value={mcpNewArgs}
                      onChange={(e) => setMcpNewArgs(e.target.value)}
                    />
                  </div>
                  <div className="form-row">
                    <input
                      type="text"
                      placeholder="Environment (KEY=value, comma separated)"
                      value={mcpNewEnv}
                      onChange={(e) => setMcpNewEnv(e.target.value)}
                    />
                  </div>
                  <div className="form-actions">
                    <button className="btn-cancel" onClick={toggleMcpAddForm}>Cancel</button>
                    <button className="btn-add" onClick={addMcpServer}>Add Server</button>
                  </div>
                </div>
              )}
              <div className="hint">MCP servers provide additional tools. Config file: <code>~/.springo/mcp_servers.json</code></div>
            </div>

            {/* ====== Memory Tab ====== */}
            <div className={`settings-tab-panel${activeTab === 'memory' ? ' active' : ''}`} id="tab-memory">
              <h3 style={{ margin: '0 0 12px', fontSize: '14px', color: 'var(--text-secondary)' }}>Memory</h3>
              <div className="setting-group">
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    style={{ width: 'auto' }}
                    checked={memEnabled}
                    onChange={(e) => setMemEnabled(e.target.checked)}
                  />
                  Enable Memory Sync
                </label>
              </div>
              <div className="setting-group">
                <label>Backend</label>
                <select value={memBackend} onChange={(e) => setMemBackend(e.target.value)}>
                  <option value="agentcore">AgentCore Memory (AWS)</option>
                  <option value="local">Local Only (JSONL)</option>
                </select>
                <div className="hint" style={{ marginTop: '4px' }}>AgentCore syncs to cloud; Local stores only in JSONL files.</div>
              </div>
              <div id="agentcore-settings" style={{ display: memBackend === 'agentcore' ? undefined : 'none' }}>
                <div className="setting-group">
                  <label>Memory ID</label>
                  <input
                    type="text"
                    placeholder="e.g., springo_memory-xxxxx"
                    value={memId}
                    onChange={(e) => setMemId(e.target.value)}
                  />
                  <div className="hint" style={{ marginTop: '4px' }}>Create via <code>agentcore memory create --name springo_memory</code></div>
                </div>
                <div className="setting-group">
                  <label>S3 Bucket</label>
                  <input
                    type="text"
                    placeholder="e.g., my-springo-bucket"
                    value={s3Bucket}
                    onChange={(e) => setS3Bucket(e.target.value)}
                  />
                  <div className="hint" style={{ marginTop: '4px' }}>Pre-created S3 bucket for storing images and tool results</div>
                </div>
                <div className="setting-group" style={{ marginTop: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <label style={{ margin: 0 }}>LTM Strategies</label>
                    <button
                      onClick={refreshLtmStrategies}
                      className="secondary-btn"
                      style={{ fontSize: '11px', padding: '4px 10px' }}
                      disabled={ltmRefreshing}
                    >
                      <span className={ltmRefreshing ? 'spinning' : ''}>&#8635;</span> Refresh
                    </button>
                  </div>
                  {ltmStrategies && ltmStrategies.length > 0 && (
                    <div className="ltm-strategies-display">
                      {ltmStrategies.map((s, i) => (
                        <div key={i} className="strategy-item">
                          <span className="strategy-name">{s.name}</span>
                          {s.description && <span className="strategy-desc">{s.description}</span>}
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="hint" style={{ marginTop: '4px' }}>Fill in Memory ID, then click Refresh to test connection and discover strategies.</div>
                </div>
              </div>
            </div>

            {/* ====== Integrations Tab ====== */}
            <div className={`settings-tab-panel${activeTab === 'integrations' ? ' active' : ''}`} id="tab-integrations">

              {/* Feishu Bot */}
              <div className="provider-section">
                <h3 style={{ margin: '0 0 8px', fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>Feishu Bot</h3>
                <div className="hint" style={{ marginBottom: '16px', lineHeight: 1.6 }}>
                  Connect Springo to Feishu via WebSocket long-connection. No public IP needed.<br />
                  Create a bot at <code>open.feishu.cn</code> and enable <strong>Events Subscription</strong> with <strong>Long Connection</strong> mode.
                </div>
                <div className="setting-group">
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      style={{ width: 'auto' }}
                      checked={feishuEnabled}
                      onChange={(e) => setFeishuEnabled(e.target.checked)}
                    />
                    Enable Feishu Bot
                  </label>
                </div>
                <div className="setting-group">
                  <label>App ID</label>
                  <input
                    type="text"
                    placeholder="cli_xxxxxxxxxx"
                    value={feishuAppId}
                    onChange={(e) => setFeishuAppId(e.target.value)}
                  />
                </div>
                <div className="setting-group">
                  <label>App Secret</label>
                  <input
                    type="password"
                    placeholder="Enter app secret"
                    value={feishuAppSecret}
                    onChange={(e) => setFeishuAppSecret(e.target.value)}
                  />
                </div>
                <div className="setting-group" style={{ marginTop: '12px' }}>
                  <button onClick={testFeishuConnection} disabled={feishuTesting}>
                    {feishuTesting ? 'Testing...' : 'Test Connection'}
                  </button>
                  <span style={{ marginLeft: '12px', fontSize: '13px' }}>{feishuStatus}</span>
                </div>
              </div>

            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
