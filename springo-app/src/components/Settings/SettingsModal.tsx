import { useState, useEffect, useCallback, useRef } from 'react'
import { useSettingsStore } from '@/stores/settingsStore'
import { useUIStore } from '@/stores/uiStore'
import { api } from '@/services/api'
import type { ModelInfo } from '@/types'

type SettingsTab = 'general' | 'working-dir' | 'aws' | 'vendor-keys' | 'mcp' | 'memory' | 'feishu'

// Provider display labels
const PROVIDER_LABELS: Record<string, string> = {
  bedrock: 'Amazon Bedrock',
  deepseek: 'DeepSeek (Direct)',
  minimax: 'MiniMax (Direct)',
  kimi: 'Kimi (Direct)',
  qwen: 'Qwen (Direct)',
  zhipu: 'Zhipu (Direct)',
}

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
  const setWorkingDir = useSettingsStore((s) => s.setWorkingDir)

  const [activeTab, setActiveTab] = useState<SettingsTab>(() => {
    return (localStorage.getItem('settingsTab') as SettingsTab) || 'general'
  })

  // Local form state
  const [localModel, setLocalModel] = useState(settings.model || defaultModel)
  const [localMaxTokens, setLocalMaxTokens] = useState(settings.maxTokens || 16384)
  const [localTemperature, setLocalTemperature] = useState(settings.temperature || 0.7)
  const [localCompactModel, setLocalCompactModel] = useState(settings.compactModel || defaultCompactModel)
  const [localSystemPrompt, setLocalSystemPrompt] = useState((settings.systemPrompt as string) || '')
  const [localEnable1mContext, setLocalEnable1mContext] = useState(settings.enable1mContext !== false)
  const [localDefaultWorkdir, setLocalDefaultWorkdir] = useState(defaultWorkingFolder || '~/Downloads')

  // AWS state
  const [awsStatus, setAwsStatus] = useState('')
  const [awsAccessKey, setAwsAccessKey] = useState('')
  const [awsSecretKey, setAwsSecretKey] = useState('')
  const [awsTesting, setAwsTesting] = useState(false)

  // Vendor keys state
  const [vendorKeys, setVendorKeys] = useState<Record<string, { configured: boolean; masked: string }>>({})
  const [vendorKeyInputs, setVendorKeyInputs] = useState<Record<string, string>>({})
  const [vendorTesting, setVendorTesting] = useState<Record<string, boolean>>({})
  const [vendorStatus, setVendorStatus] = useState<Record<string, string>>({})

  // MCP servers state
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

  // Memory state
  const [memEnabled, setMemEnabled] = useState(false)
  const [memRegion, setMemRegion] = useState('us-west-2')
  const [memId, setMemId] = useState('')
  const [memBackend, setMemBackend] = useState('agentcore')
  const [s3Bucket, setS3Bucket] = useState('')

  // Feishu state
  const [feishuEnabled, setFeishuEnabled] = useState(false)
  const [feishuAppId, setFeishuAppId] = useState('')
  const [feishuAppSecret, setFeishuAppSecret] = useState('')
  const [feishuStatus, setFeishuStatus] = useState('')
  const [feishuTesting, setFeishuTesting] = useState(false)

  // Skills state
  const [skills, setSkills] = useState<Array<{ name: string; description?: string }>>([])

  const backdropRef = useRef<HTMLDivElement>(null)

  // --- Tab switching ---
  const switchTab = useCallback((tab: SettingsTab) => {
    setActiveTab(tab)
    localStorage.setItem('settingsTab', tab)
  }, [])

  // --- Load data on mount ---
  useEffect(() => {
    loadAwsSettings()
    loadVendorKeys()
    loadMcpServers()
    loadMemorySettings()
    loadFeishuSettings()
    loadSkills()
  }, [])

  // --- Token limit calculation ---
  const selectedModel = models.find((m: ModelInfo) => m.id === localModel)
  const maxOutputTokens = selectedModel
    ? (selectedModel as unknown as { max_output?: number }).max_output || 64000
    : 64000
  const supportsExtended = selectedModel
    ? (selectedModel as unknown as { supports_extended_context?: boolean }).supports_extended_context
    : false

  // --- Load helpers ---
  async function loadAwsSettings() {
    try {
      const res = await api.config.aws.get()
      if (res.ok && res.data) {
        const data = res.data as Record<string, unknown>
        if ((data as { connected?: boolean }).connected) {
          const method = (data as { method?: string }).method
          const identity = (data as { identity?: { account?: string } }).identity
          let source = ''
          if (method === 'aws_profile') source = 'via ~/.aws/credentials'
          else if (method === 'env_vars') source = 'via env vars'
          else if (method === 'env_file') source = 'via ~/.springo/.env'
          setAwsStatus(`Connected (${identity?.account || ''}) ${source}`)
        } else {
          setAwsStatus('Not connected')
        }
      }
    } catch {
      setAwsStatus('')
    }
  }

  async function loadVendorKeys() {
    try {
      const res = await api.config.vendorKeys.get()
      if (res.ok && res.data) {
        const keys = (res.data as { vendor_keys?: Record<string, { configured: boolean; api_key_masked: string }> }).vendor_keys || {}
        const parsed: Record<string, { configured: boolean; masked: string }> = {}
        for (const [vendor, info] of Object.entries(keys)) {
          parsed[vendor] = { configured: info.configured, masked: info.api_key_masked || '' }
        }
        setVendorKeys(parsed)
      }
    } catch { /* ignore */ }
  }

  async function loadMcpServers() {
    try {
      const res = await api.mcp.listServers()
      if (res.ok && res.data) {
        setMcpServers((res.data as { servers?: typeof mcpServers }).servers || [])
      }
    } catch { /* ignore */ }
  }

  async function loadMemorySettings() {
    try {
      const res = await api.config.memory.get()
      if (res.ok && res.data) {
        const d = res.data as Record<string, unknown>
        setMemEnabled((d.memory_enabled as boolean) !== false)
        setMemRegion((d.memory_region as string) || 'us-west-2')
        setMemId((d.memory_id as string) || '')
        setMemBackend((d.memory_backend as string) || 'agentcore')
      }
      const s3Res = await api.config.s3.get()
      if (s3Res.ok && s3Res.data) {
        setS3Bucket((s3Res.data as Record<string, unknown>).s3_bucket as string || '')
      }
    } catch { /* ignore */ }
  }

  async function loadFeishuSettings() {
    try {
      const res = await api.config.feishu.get()
      if (res.ok && res.data) {
        const d = res.data as Record<string, unknown>
        setFeishuEnabled(!!d.enabled)
        setFeishuAppId((d.app_id as string) || '')
        if (d.running) {
          setFeishuStatus('Running (WebSocket connected)')
        } else if (d.enabled && d.app_id) {
          setFeishuStatus('Configured but not running')
        } else {
          setFeishuStatus('Not configured')
        }
      }
    } catch { /* ignore */ }
  }

  async function loadSkills() {
    try {
      const res = await api.skills.list()
      if (res.ok && res.data) {
        setSkills((res.data as { skills?: typeof skills }).skills || [])
      }
    } catch { /* ignore */ }
  }

  // --- Save / close ---
  function handleClose() {
    // Persist general settings
    saveSettings({
      model: localModel,
      maxTokens: localMaxTokens,
      temperature: localTemperature,
      compactModel: localCompactModel,
      systemPrompt: localSystemPrompt || undefined,
      enable1mContext: localEnable1mContext,
    })
    // Update default working dir
    if (localDefaultWorkdir.trim() && localDefaultWorkdir !== defaultWorkingFolder) {
      // Persist via Electron cache (handled by store)
      if (window.electronAPI?.cache) {
        window.electronAPI.cache.set('workspace', {
          workingFolders,
          currentWorkingDir: workingDir,
          defaultWorkingFolder: localDefaultWorkdir.trim(),
        })
      }
    }
    setSettingsOpen(false)
  }

  // Click outside to close
  function handleBackdropClick(e: React.MouseEvent) {
    if (e.target === backdropRef.current) handleClose()
  }

  // --- AWS actions ---
  async function testAwsConnection() {
    setAwsTesting(true)
    setAwsStatus('')
    // Save credentials first if entered
    if (awsAccessKey && awsSecretKey) {
      await api.config.aws.set({
        region: 'us-east-1',
        access_key_id: awsAccessKey,
        secret_access_key: awsSecretKey,
      })
    }
    try {
      const res = await api.config.aws.test()
      if (res.ok && res.data) {
        const d = res.data as Record<string, unknown>
        if (d.valid) {
          setAwsStatus(`Connected (${d.account || ''})`)
          loadAwsSettings()
        } else {
          setAwsStatus(`Error: ${d.error || 'Connection failed'}`)
        }
      } else {
        setAwsStatus(`Error: ${res.error || 'Connection failed'}`)
      }
    } catch (e) {
      setAwsStatus(`Error: ${(e as Error).message}`)
    } finally {
      setAwsTesting(false)
    }
  }

  // --- Vendor key actions ---
  async function saveVendorKey(vendor: string) {
    const key = vendorKeyInputs[vendor]
    if (!key) return
    await api.config.vendorKeys.set({ vendor, api_key: key } as unknown as Record<string, string>)
    loadVendorKeys()
    useSettingsStore.getState().loadModels()
  }

  async function testVendorKey(vendor: string) {
    setVendorTesting((prev) => ({ ...prev, [vendor]: true }))
    setVendorStatus((prev) => ({ ...prev, [vendor]: '' }))
    const key = vendorKeyInputs[vendor]
    if (key) await saveVendorKey(vendor)
    try {
      const res = await api.config.vendorKeys.test(vendor)
      if (res.ok && res.data) {
        const d = res.data as Record<string, unknown>
        if (d.success) {
          setVendorStatus((prev) => ({ ...prev, [vendor]: (d.message as string) || 'Connected' }))
          loadVendorKeys()
        } else {
          setVendorStatus((prev) => ({ ...prev, [vendor]: `Error: ${d.error || 'Failed'}` }))
        }
      } else {
        setVendorStatus((prev) => ({ ...prev, [vendor]: `Error: ${res.error || 'Failed'}` }))
      }
    } catch (e) {
      setVendorStatus((prev) => ({ ...prev, [vendor]: `Error: ${(e as Error).message}` }))
    } finally {
      setVendorTesting((prev) => ({ ...prev, [vendor]: false }))
    }
  }

  // --- MCP actions ---
  async function removeMcpServer(name: string) {
    await api.mcp.removeServer(name)
    loadMcpServers()
    showToast(`Removed MCP server: ${name}`, 'info')
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
    await api.mcp.addServer({ name: mcpNewName, command: mcpNewCommand, args, env })
    setMcpNewName('')
    setMcpNewCommand('')
    setMcpNewArgs('')
    setMcpNewEnv('')
    setMcpAddFormOpen(false)
    loadMcpServers()
    showToast(`Added MCP server: ${mcpNewName}`, 'success')
  }

  async function refreshMcpTools() {
    await api.mcp.refreshTools()
    loadMcpServers()
    showToast('MCP tools refreshed', 'info')
  }

  // --- Memory actions ---
  async function saveMemory() {
    await api.config.memory.set({
      enabled: memEnabled,
      agent_id: memId,
      region: memRegion,
    })
    await api.config.s3.set({
      bucket: s3Bucket,
      enabled: memEnabled && !!s3Bucket,
    })
    showToast('Memory & S3 settings saved', 'success')
  }

  // --- Feishu actions ---
  async function saveFeishu() {
    const payload: Record<string, unknown> = { enabled: feishuEnabled, app_id: feishuAppId }
    if (feishuAppSecret) payload.app_secret = feishuAppSecret
    const res = await api.config.feishu.set(payload as { enabled?: boolean; app_id?: string; app_secret?: string })
    if (res.ok && res.data) {
      const d = res.data as Record<string, unknown>
      if (d.running) setFeishuStatus('Running (WebSocket connected)')
      else if (!feishuEnabled) setFeishuStatus('Disabled')
      else setFeishuStatus('Not running')
    }
  }

  async function testFeishu() {
    setFeishuTesting(true)
    setFeishuStatus('')
    await saveFeishu()
    try {
      const res = await api.config.feishu.test()
      if (res.ok && res.data) {
        const d = res.data as Record<string, unknown>
        if (d.success) setFeishuStatus((d.message as string) || 'Connected')
        else setFeishuStatus(`Error: ${d.error || 'Failed'}`)
      }
    } catch (e) {
      setFeishuStatus(`Error: ${(e as Error).message}`)
    } finally {
      setFeishuTesting(false)
    }
  }

  // --- Working dir ---
  async function chooseFolder() {
    if (!window.electronAPI?.selectFolder) return
    const folder = await window.electronAPI.selectFolder()
    if (folder) {
      setWorkingDir(folder)
      await api.config.workingDir.set(folder)
    }
  }

  // --- Render model options grouped by provider ---
  function renderModelOptions() {
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

  // Clamp maxTokens when model changes
  useEffect(() => {
    if (localMaxTokens > maxOutputTokens) {
      setLocalMaxTokens(Math.min(16384, maxOutputTokens))
    }
  }, [localModel, maxOutputTokens])

  const TABS: { key: SettingsTab; label: string }[] = [
    { key: 'general', label: 'General' },
    { key: 'working-dir', label: 'Working Dir' },
    { key: 'aws', label: 'AWS' },
    { key: 'vendor-keys', label: 'Vendor Keys' },
    { key: 'mcp', label: 'MCP Servers' },
    { key: 'memory', label: 'Memory & S3' },
    { key: 'feishu', label: 'Feishu' },
  ]

  const VENDOR_LIST = ['deepseek', 'minimax', 'kimi', 'qwen', 'zhipu'] as const

  return (
    <div className="settings-modal-backdrop active" ref={backdropRef} onClick={handleBackdropClick}>
      <div className="settings-modal">
        {/* Header */}
        <div className="settings-header">
          <h2>Settings</h2>
          <button className="settings-close-btn" onClick={handleClose} title="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="settings-tabs">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              className={`settings-tab${activeTab === tab.key ? ' active' : ''}`}
              onClick={() => switchTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Panels */}
        <div className="settings-body">
          {/* ====== General ====== */}
          {activeTab === 'general' && (
            <div className="settings-tab-panel active">
              <div className="settings-group">
                <label className="settings-label">Model</label>
                <select
                  className="settings-select"
                  value={localModel}
                  onChange={(e) => setLocalModel(e.target.value)}
                >
                  {renderModelOptions()}
                </select>
              </div>

              {supportsExtended && (
                <div className="settings-group">
                  <label className="settings-label">
                    <input
                      type="checkbox"
                      checked={localEnable1mContext}
                      onChange={(e) => setLocalEnable1mContext(e.target.checked)}
                    />{' '}
                    Enable Extended Context (1M tokens)
                  </label>
                </div>
              )}

              <div className="settings-group">
                <label className="settings-label">
                  Max Tokens: {localMaxTokens}
                </label>
                <input
                  type="range"
                  className="settings-range"
                  min={256}
                  max={maxOutputTokens}
                  step={256}
                  value={localMaxTokens}
                  onChange={(e) => setLocalMaxTokens(Number(e.target.value))}
                />
              </div>

              <div className="settings-group">
                <label className="settings-label">
                  Temperature: {localTemperature}
                </label>
                <input
                  type="range"
                  className="settings-range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={localTemperature}
                  onChange={(e) => setLocalTemperature(Number(e.target.value))}
                />
              </div>

              <div className="settings-group">
                <label className="settings-label">Compact Model</label>
                <select
                  className="settings-select"
                  value={localCompactModel}
                  onChange={(e) => setLocalCompactModel(e.target.value)}
                >
                  {renderModelOptions()}
                </select>
              </div>

              <div className="settings-group">
                <label className="settings-label">System Prompt (optional)</label>
                <textarea
                  className="settings-textarea"
                  rows={4}
                  value={localSystemPrompt}
                  onChange={(e) => setLocalSystemPrompt(e.target.value)}
                  placeholder="Custom system instructions..."
                />
              </div>
            </div>
          )}

          {/* ====== Working Directory ====== */}
          {activeTab === 'working-dir' && (
            <div className="settings-tab-panel active">
              <div className="settings-group">
                <label className="settings-label">Current Working Directory</label>
                <div className="settings-row">
                  <input
                    type="text"
                    className="settings-input"
                    value={workingDir}
                    readOnly
                    placeholder="No directory selected"
                  />
                  <button className="settings-btn" onClick={chooseFolder}>
                    Choose Folder
                  </button>
                </div>
              </div>

              <div className="settings-group">
                <label className="settings-label">Default Working Folder</label>
                <input
                  type="text"
                  className="settings-input"
                  value={localDefaultWorkdir}
                  onChange={(e) => setLocalDefaultWorkdir(e.target.value)}
                  placeholder="~/Downloads"
                />
              </div>

              {workingFolders.length > 0 && (
                <div className="settings-group">
                  <label className="settings-label">Recent Folders</label>
                  <div className="settings-list">
                    {workingFolders.map((folder) => (
                      <div
                        key={folder}
                        className={`settings-list-item clickable${folder === workingDir ? ' active' : ''}`}
                        onClick={() => {
                          setWorkingDir(folder)
                          api.config.workingDir.set(folder)
                        }}
                      >
                        <span className="item-name">{folder}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ====== AWS ====== */}
          {activeTab === 'aws' && (
            <div className="settings-tab-panel active">
              <div className="settings-group">
                <label className="settings-label">Connection Status</label>
                <div className={`settings-status ${awsStatus.startsWith('Error') ? 'error' : awsStatus.includes('Connected') ? 'success' : ''}`}>
                  {awsStatus || 'Loading...'}
                </div>
              </div>

              <div className="settings-group">
                <label className="settings-label">Access Key ID</label>
                <input
                  type="text"
                  className="settings-input"
                  value={awsAccessKey}
                  onChange={(e) => setAwsAccessKey(e.target.value)}
                  placeholder="AKIA..."
                />
              </div>

              <div className="settings-group">
                <label className="settings-label">Secret Access Key</label>
                <input
                  type="password"
                  className="settings-input"
                  value={awsSecretKey}
                  onChange={(e) => setAwsSecretKey(e.target.value)}
                  placeholder="Secret key..."
                />
              </div>

              <button
                className="settings-btn primary"
                onClick={testAwsConnection}
                disabled={awsTesting}
              >
                {awsTesting ? 'Testing...' : 'Test Connection'}
              </button>
            </div>
          )}

          {/* ====== Vendor Keys ====== */}
          {activeTab === 'vendor-keys' && (
            <div className="settings-tab-panel active">
              {VENDOR_LIST.map((vendor) => (
                <div key={vendor} className="settings-group settings-vendor-group">
                  <label className="settings-label">{PROVIDER_LABELS[vendor] || vendor}</label>
                  <div className="settings-status-inline">
                    {vendorKeys[vendor]?.configured
                      ? `Key configured (${vendorKeys[vendor].masked})`
                      : 'Not configured'}
                  </div>
                  <div className="settings-row">
                    <input
                      type="password"
                      className="settings-input"
                      value={vendorKeyInputs[vendor] || ''}
                      onChange={(e) =>
                        setVendorKeyInputs((prev) => ({ ...prev, [vendor]: e.target.value }))
                      }
                      placeholder="API key..."
                    />
                    <button
                      className="settings-btn"
                      onClick={() => testVendorKey(vendor)}
                      disabled={vendorTesting[vendor]}
                    >
                      {vendorTesting[vendor] ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                  {vendorStatus[vendor] && (
                    <div className={`settings-status ${vendorStatus[vendor].startsWith('Error') ? 'error' : 'success'}`}>
                      {vendorStatus[vendor]}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* ====== MCP Servers ====== */}
          {activeTab === 'mcp' && (
            <div className="settings-tab-panel active">
              <div className="settings-row" style={{ marginBottom: 12 }}>
                <button className="settings-btn" onClick={() => setMcpAddFormOpen(!mcpAddFormOpen)}>
                  + Add Server
                </button>
                <button className="settings-btn" onClick={refreshMcpTools}>
                  Refresh Tools
                </button>
              </div>

              {mcpAddFormOpen && (
                <div className="settings-group mcp-add-form">
                  <input
                    type="text"
                    className="settings-input"
                    value={mcpNewName}
                    onChange={(e) => setMcpNewName(e.target.value)}
                    placeholder="Server name"
                  />
                  <input
                    type="text"
                    className="settings-input"
                    value={mcpNewCommand}
                    onChange={(e) => setMcpNewCommand(e.target.value)}
                    placeholder="Command (e.g. npx)"
                  />
                  <input
                    type="text"
                    className="settings-input"
                    value={mcpNewArgs}
                    onChange={(e) => setMcpNewArgs(e.target.value)}
                    placeholder="Args (comma-separated)"
                  />
                  <input
                    type="text"
                    className="settings-input"
                    value={mcpNewEnv}
                    onChange={(e) => setMcpNewEnv(e.target.value)}
                    placeholder="Env vars (KEY=val,KEY2=val2)"
                  />
                  <button className="settings-btn primary" onClick={addMcpServer}>
                    Add
                  </button>
                </div>
              )}

              <div className="settings-list">
                {mcpServers.length === 0 ? (
                  <div className="settings-list-empty">No MCP servers configured</div>
                ) : (
                  mcpServers.map((server) => {
                    let statusClass = 'stopped'
                    let statusText = server.cached_tools > 0 ? `Ready (${server.cached_tools} tools)` : 'No tools cached'
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
                          <button
                            className="settings-btn danger"
                            onClick={() => removeMcpServer(server.name)}
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>

              {/* Skills list */}
              <div className="settings-group" style={{ marginTop: 20 }}>
                <label className="settings-label">Skills</label>
                <div className="settings-list">
                  {skills.length === 0 ? (
                    <div className="settings-list-empty">No skills found</div>
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
              </div>
            </div>
          )}

          {/* ====== Memory & S3 ====== */}
          {activeTab === 'memory' && (
            <div className="settings-tab-panel active">
              <div className="settings-group">
                <label className="settings-label">
                  <input
                    type="checkbox"
                    checked={memEnabled}
                    onChange={(e) => setMemEnabled(e.target.checked)}
                  />{' '}
                  Enable Memory
                </label>
              </div>

              <div className="settings-group">
                <label className="settings-label">Backend</label>
                <select
                  className="settings-select"
                  value={memBackend}
                  onChange={(e) => setMemBackend(e.target.value)}
                >
                  <option value="agentcore">AgentCore</option>
                  <option value="local">Local</option>
                </select>
              </div>

              <div className="settings-group">
                <label className="settings-label">Region</label>
                <select
                  className="settings-select"
                  value={memRegion}
                  onChange={(e) => setMemRegion(e.target.value)}
                >
                  <option value="us-east-1">us-east-1</option>
                  <option value="us-west-2">us-west-2</option>
                  <option value="eu-west-1">eu-west-1</option>
                  <option value="ap-northeast-1">ap-northeast-1</option>
                </select>
              </div>

              {memBackend === 'agentcore' && (
                <div className="settings-group">
                  <label className="settings-label">Memory ID</label>
                  <input
                    type="text"
                    className="settings-input"
                    value={memId}
                    onChange={(e) => setMemId(e.target.value)}
                    placeholder="AgentCore memory ID..."
                  />
                </div>
              )}

              <div className="settings-group">
                <label className="settings-label">S3 Bucket</label>
                <input
                  type="text"
                  className="settings-input"
                  value={s3Bucket}
                  onChange={(e) => setS3Bucket(e.target.value)}
                  placeholder="my-springo-bucket"
                />
              </div>

              <button className="settings-btn primary" onClick={saveMemory}>
                Save Memory & S3 Settings
              </button>
            </div>
          )}

          {/* ====== Feishu ====== */}
          {activeTab === 'feishu' && (
            <div className="settings-tab-panel active">
              <div className="settings-group">
                <label className="settings-label">
                  <input
                    type="checkbox"
                    checked={feishuEnabled}
                    onChange={(e) => setFeishuEnabled(e.target.checked)}
                  />{' '}
                  Enable Feishu Bot
                </label>
              </div>

              <div className="settings-group">
                <label className="settings-label">Status</label>
                <div className={`settings-status ${feishuStatus.startsWith('Error') ? 'error' : feishuStatus.includes('Running') ? 'success' : ''}`}>
                  {feishuStatus || 'Loading...'}
                </div>
              </div>

              <div className="settings-group">
                <label className="settings-label">App ID</label>
                <input
                  type="text"
                  className="settings-input"
                  value={feishuAppId}
                  onChange={(e) => setFeishuAppId(e.target.value)}
                  placeholder="cli_..."
                />
              </div>

              <div className="settings-group">
                <label className="settings-label">App Secret</label>
                <input
                  type="password"
                  className="settings-input"
                  value={feishuAppSecret}
                  onChange={(e) => setFeishuAppSecret(e.target.value)}
                  placeholder="Enter new secret..."
                />
              </div>

              <div className="settings-row">
                <button className="settings-btn primary" onClick={saveFeishu}>
                  Save
                </button>
                <button
                  className="settings-btn"
                  onClick={testFeishu}
                  disabled={feishuTesting}
                >
                  {feishuTesting ? 'Testing...' : 'Test Connection'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="settings-footer">
          <button className="settings-btn primary" onClick={handleClose}>
            Save & Close
          </button>
        </div>
      </div>
    </div>
  )
}
