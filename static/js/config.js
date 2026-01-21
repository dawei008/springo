// AWS Bedrock 认证配置 - 前端交互逻辑

document.addEventListener('DOMContentLoaded', function() {
    // 初始化
    loadStatus();
    loadProfiles();
    setupTabNavigation();
    setupEventListeners();
});

// ==================== Tab 导航 ====================

function setupTabNavigation() {
    const tabBtns = document.querySelectorAll('.tab-btn');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;

            // 更新按钮状态
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // 更新内容区域
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`${tabId}-tab`).classList.add('active');
        });
    });
}

// ==================== 事件监听 ====================

function setupEventListeners() {
    // 测试连接
    document.getElementById('test-btn').addEventListener('click', testConnection);

    // 保存配置
    document.getElementById('save-btn').addEventListener('click', saveConfig);

    // SSO 登录
    document.getElementById('sso-login-btn').addEventListener('click', startSSOLogin);

    // SSO 账户选择
    document.getElementById('sso-account-select').addEventListener('change', loadSSOHoles);

    // SSO 角色选择
    document.getElementById('sso-role-select').addEventListener('change', selectSSORole);
}

// ==================== 状态加载 ====================

async function loadStatus() {
    try {
        const response = await fetch('/config/api/status');
        const status = await response.json();

        updateStatusIndicator(status.connected);

        // 根据当前方法切换到对应 Tab
        if (status.method === 'aws_profile') {
            switchToTab('profile');
            if (status.profile_name) {
                setTimeout(() => {
                    document.getElementById('profile-select').value = status.profile_name;
                }, 500);
            }
        } else if (status.method === 'manual_keys') {
            switchToTab('manual');
            if (status.access_key_id) {
                document.getElementById('access-key-id').value = status.access_key_id;
            }
        } else if (status.method === 'sso') {
            switchToTab('sso');
            if (status.sso_start_url) {
                document.getElementById('sso-start-url').value = status.sso_start_url;
            }
            if (status.configured) {
                showSSOAccountSection();
            }
        }

        // 显示身份信息
        if (status.connected && status.identity) {
            showIdentity(status.identity);
        }

    } catch (error) {
        console.error('Failed to load status:', error);
    }
}

function switchToTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `${tabName}-tab`);
    });
}

function updateStatusIndicator(connected) {
    const indicator = document.getElementById('status-indicator');
    const text = indicator.querySelector('.status-text');

    if (connected) {
        indicator.classList.add('connected');
        indicator.classList.remove('disconnected');
        text.textContent = '已连接';
    } else {
        indicator.classList.remove('connected');
        indicator.classList.add('disconnected');
        text.textContent = '未连接';
    }
}

// ==================== Profile 加载 ====================

async function loadProfiles() {
    try {
        const response = await fetch('/config/api/profiles');
        const data = await response.json();

        const select = document.getElementById('profile-select');
        select.innerHTML = '';

        if (data.profiles && data.profiles.length > 0) {
            data.profiles.forEach(profile => {
                const option = document.createElement('option');
                option.value = profile.name;
                option.textContent = profile.name;
                if (profile.has_sso) {
                    option.textContent += ' (SSO)';
                }
                if (profile.region) {
                    option.textContent += ` [${profile.region}]`;
                }
                select.appendChild(option);
            });
        } else {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = '未找到 AWS Profile';
            select.appendChild(option);
        }

    } catch (error) {
        console.error('Failed to load profiles:', error);
        showMessage('加载 AWS Profile 失败', 'error');
    }
}

// ==================== 测试连接 ====================

async function testConnection() {
    const btn = document.getElementById('test-btn');
    btn.disabled = true;
    btn.textContent = '测试中...';

    // 先保存当前配置
    await saveConfigSilent();

    try {
        const response = await fetch('/config/api/test');
        const result = await response.json();

        if (result.status === 'ok') {
            showMessage('连接成功！', 'success');
            updateStatusIndicator(true);
            showIdentity(result.identity);
        } else {
            showMessage(`连接失败: ${result.error || result.message}`, 'error');
            updateStatusIndicator(false);
            hideIdentity();
        }

    } catch (error) {
        showMessage(`测试失败: ${error.message}`, 'error');
        updateStatusIndicator(false);
    } finally {
        btn.disabled = false;
        btn.textContent = '测试连接';
    }
}

// ==================== 保存配置 ====================

async function saveConfig() {
    const btn = document.getElementById('save-btn');
    btn.disabled = true;
    btn.textContent = '保存中...';

    try {
        const config = getCurrentConfig();
        const response = await fetch('/config/api/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        const result = await response.json();

        if (response.ok) {
            showMessage('配置已保存', 'success');
        } else {
            showMessage(`保存失败: ${result.error}`, 'error');
        }

    } catch (error) {
        showMessage(`保存失败: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '保存配置';
    }
}

async function saveConfigSilent() {
    try {
        const config = getCurrentConfig();
        await fetch('/config/api/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
    } catch (error) {
        console.error('Silent save failed:', error);
    }
}

function getCurrentConfig() {
    const activeTab = document.querySelector('.tab-btn.active').dataset.tab;

    if (activeTab === 'profile') {
        return {
            method: 'aws_profile',
            profile_name: document.getElementById('profile-select').value
        };
    } else if (activeTab === 'manual') {
        return {
            method: 'manual_keys',
            access_key_id: document.getElementById('access-key-id').value,
            secret_access_key: document.getElementById('secret-access-key').value,
            session_token: document.getElementById('session-token').value || null
        };
    } else if (activeTab === 'sso') {
        return {
            method: 'sso',
            sso_start_url: document.getElementById('sso-start-url').value,
            sso_region: document.getElementById('sso-region').value || 'us-east-1',
            sso_account_id: document.getElementById('sso-account-select').value || null,
            sso_role_name: document.getElementById('sso-role-select').value || null
        };
    }

    return {};
}

// ==================== SSO 登录 ====================

let ssoPollingInterval = null;

async function startSSOLogin() {
    const startUrl = document.getElementById('sso-start-url').value;
    const ssoRegion = document.getElementById('sso-region').value || 'us-east-1';

    if (!startUrl) {
        showMessage('请输入 SSO Start URL', 'error');
        return;
    }

    const btn = document.getElementById('sso-login-btn');
    btn.disabled = true;
    btn.textContent = '启动中...';

    try {
        const response = await fetch('/config/api/sso/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ start_url: startUrl, sso_region: ssoRegion })
        });

        const result = await response.json();

        if (response.ok) {
            showDeviceCode(result);
            startSSOPolling(result.interval || 5, result.expires_in || 600);
        } else {
            showMessage(`SSO 启动失败: ${result.error}`, 'error');
            btn.disabled = false;
            btn.textContent = '开始 SSO 登录';
        }

    } catch (error) {
        showMessage(`SSO 启动失败: ${error.message}`, 'error');
        btn.disabled = false;
        btn.textContent = '开始 SSO 登录';
    }
}

function showDeviceCode(data) {
    document.getElementById('sso-login-section').classList.add('hidden');
    document.getElementById('sso-device-code').classList.remove('hidden');

    document.getElementById('sso-user-code').textContent = data.user_code;
    document.getElementById('sso-verification-link').href = data.verification_uri_complete;
}

function startSSOPolling(interval, expiresIn) {
    let remaining = expiresIn;
    const countdown = document.getElementById('sso-countdown');

    // 更新倒计时
    const countdownInterval = setInterval(() => {
        remaining--;
        countdown.textContent = `(${Math.floor(remaining / 60)}:${(remaining % 60).toString().padStart(2, '0')})`;

        if (remaining <= 0) {
            clearInterval(countdownInterval);
            clearInterval(ssoPollingInterval);
            resetSSOUI();
            showMessage('SSO 登录超时，请重试', 'error');
        }
    }, 1000);

    // 轮询 SSO 状态
    ssoPollingInterval = setInterval(async () => {
        try {
            const response = await fetch('/config/api/sso/poll', { method: 'POST' });
            const result = await response.json();

            if (result.status === 'success') {
                clearInterval(countdownInterval);
                clearInterval(ssoPollingInterval);
                showMessage('SSO 登录成功！', 'success');
                document.getElementById('sso-device-code').classList.add('hidden');
                loadSSOAccounts();
            } else if (result.status === 'error') {
                clearInterval(countdownInterval);
                clearInterval(ssoPollingInterval);
                resetSSOUI();
                showMessage(`SSO 登录失败: ${result.error}`, 'error');
            }
            // status === 'pending' 继续等待

        } catch (error) {
            console.error('SSO polling error:', error);
        }
    }, interval * 1000);
}

function resetSSOUI() {
    document.getElementById('sso-device-code').classList.add('hidden');
    document.getElementById('sso-login-section').classList.remove('hidden');

    const btn = document.getElementById('sso-login-btn');
    btn.disabled = false;
    btn.textContent = '开始 SSO 登录';
}

async function loadSSOAccounts() {
    try {
        const response = await fetch('/config/api/sso/accounts');
        const data = await response.json();

        if (data.accounts && data.accounts.length > 0) {
            const select = document.getElementById('sso-account-select');
            select.innerHTML = '<option value="">请选择账户</option>';

            data.accounts.forEach(account => {
                const option = document.createElement('option');
                option.value = account.accountId;
                option.textContent = `${account.accountName} (${account.accountId})`;
                select.appendChild(option);
            });

            showSSOAccountSection();
        }

    } catch (error) {
        console.error('Failed to load SSO accounts:', error);
        showMessage('加载 SSO 账户失败', 'error');
    }
}

function showSSOAccountSection() {
    document.getElementById('sso-login-section').classList.add('hidden');
    document.getElementById('sso-device-code').classList.add('hidden');
    document.getElementById('sso-account-section').classList.remove('hidden');
}

async function loadSSOHoles() {
    const accountId = document.getElementById('sso-account-select').value;
    const roleSelect = document.getElementById('sso-role-select');

    if (!accountId) {
        roleSelect.disabled = true;
        roleSelect.innerHTML = '<option value="">请先选择账户</option>';
        return;
    }

    try {
        const response = await fetch(`/config/api/sso/roles/${accountId}`);
        const data = await response.json();

        roleSelect.innerHTML = '<option value="">请选择角色</option>';

        if (data.roles && data.roles.length > 0) {
            data.roles.forEach(role => {
                const option = document.createElement('option');
                option.value = role.roleName;
                option.textContent = role.roleName;
                roleSelect.appendChild(option);
            });
            roleSelect.disabled = false;
        }

    } catch (error) {
        console.error('Failed to load SSO roles:', error);
        showMessage('加载 SSO 角色失败', 'error');
    }
}

async function selectSSORole() {
    const accountId = document.getElementById('sso-account-select').value;
    const roleName = document.getElementById('sso-role-select').value;

    if (!accountId || !roleName) return;

    try {
        const response = await fetch('/config/api/sso/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account_id: accountId, role_name: roleName })
        });

        if (response.ok) {
            showMessage('SSO 角色已选择', 'success');
            testConnection();
        }

    } catch (error) {
        console.error('Failed to select SSO role:', error);
    }
}

// ==================== UI 辅助函数 ====================

function showMessage(text, type = 'info') {
    const msg = document.getElementById('message');
    msg.textContent = text;
    msg.className = `message ${type}`;
    msg.classList.remove('hidden');

    setTimeout(() => {
        msg.classList.add('hidden');
    }, 5000);
}

function showIdentity(identity) {
    document.getElementById('identity-account').textContent = identity.account || '-';
    document.getElementById('identity-arn').textContent = identity.arn || '-';
    document.getElementById('identity-info').classList.remove('hidden');
}

function hideIdentity() {
    document.getElementById('identity-info').classList.add('hidden');
}
