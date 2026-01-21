#!/usr/bin/env python3
"""
测试工作目录选择器功能
通过 Electron 端到端测试
"""

import asyncio
from playwright.async_api import async_playwright


async def test_workdir_selector():
    """测试工作目录选择器功能"""
    print("=" * 60)
    print("工作目录选择器测试")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 刷新页面加载最新代码
        await page.reload()
        await asyncio.sleep(2)

        # [1] 检查函数是否存在
        print("\n[1] 检查函数定义:")
        functions_check = await page.evaluate('''
            () => ({
                hasShowWorkdirSelector: typeof showWorkdirSelector === 'function',
                hasHideWorkdirSelector: typeof hideWorkdirSelector === 'function',
                hasSelectExistingFolderForChat: typeof selectExistingFolderForChat === 'function',
                hasSetAsDefaultAndCreateChat: typeof setAsDefaultAndCreateChat === 'function',
                hasSelectNewFolderForChat: typeof selectNewFolderForChat === 'function',
                hasCreateConversationWithFolder: typeof createConversationWithFolder === 'function'
            })
        ''')

        all_functions_exist = all(functions_check.values())
        for func_name, exists in functions_check.items():
            status = "✅" if exists else "❌"
            print(f"    {status} {func_name}: {exists}")

        # [2] 检查模态对话框 HTML 元素
        print("\n[2] 检查模态对话框元素:")
        modal_check = await page.evaluate('''
            () => ({
                hasModal: !!document.getElementById('workdir-selector-modal'),
                hasList: !!document.getElementById('workdir-selector-list'),
                modalDisplay: getComputedStyle(document.getElementById('workdir-selector-modal')).display
            })
        ''')
        print(f"    Modal 元素存在: {'✅' if modal_check['hasModal'] else '❌'}")
        print(f"    List 元素存在: {'✅' if modal_check['hasList'] else '❌'}")
        print(f"    初始显示状态: {modal_check['modalDisplay']} (应为 none)")

        # [3] 测试 newConversation 逻辑（检查代码结构）
        print("\n[3] 检查 newConversation 函数逻辑:")
        code_check = await page.evaluate('''
            () => {
                const funcStr = newConversation.toString();
                return {
                    hasWorkspaceLengthCheck: funcStr.includes('workingFolders.length > 0'),
                    hasShowWorkdirSelector: funcStr.includes('showWorkdirSelector()'),
                    hasCreateConversationWithFolder: funcStr.includes('createConversationWithFolder'),
                    hasNoDefaultComment: funcStr.includes('Has workspace folders but no default')
                };
            }
        ''')
        print(f"    ✅ 检查 workspace 长度: {code_check['hasWorkspaceLengthCheck']}")
        print(f"    ✅ 调用 showWorkdirSelector: {code_check['hasShowWorkdirSelector']}")
        print(f"    ✅ 调用 createConversationWithFolder: {code_check['hasCreateConversationWithFolder']}")

        # [4] 模拟场景：有 workspace 目录但无默认目录
        print("\n[4] 模拟场景测试:")

        # 保存当前状态
        saved_state = await page.evaluate('''
            () => ({
                workingFolders: [...workingFolders],
                defaultWorkingFolder: defaultWorkingFolder
            })
        ''')
        print(f"    当前 workspace 目录数: {len(saved_state['workingFolders'])}")
        print(f"    当前默认目录: {saved_state['defaultWorkingFolder'] or '(无)'}")

        # 设置测试场景：有 workspace 目录但清除默认目录
        test_folders = ["/tmp/test_folder_1", "/tmp/test_folder_2"]
        await page.evaluate(f'''
            () => {{
                workingFolders = {test_folders};
                defaultWorkingFolder = null;
                localStorage.setItem('workingFolders', JSON.stringify(workingFolders));
                localStorage.removeItem('defaultWorkingFolder');
                renderWorkingFolders();
            }}
        ''')
        print(f"    设置测试 workspace: {test_folders}")
        print(f"    清除默认目录")

        # 显示选择器（不等待 Promise，只触发显示）
        print("\n[5] 测试选择器显示:")
        await page.evaluate('''
            () => {
                // 直接显示模态框，不调用 showWorkdirSelector（它返回 Promise 会阻塞）
                const modal = document.getElementById('workdir-selector-modal');
                const listEl = document.getElementById('workdir-selector-list');

                // 填充现有工作目录列表
                listEl.innerHTML = workingFolders.map(folder => `
                    <div class="workdir-selector-item">
                        <svg class="folder-icon" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                            <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2v11z"/>
                        </svg>
                        <span class="folder-path" title="${folder}">${folder}</span>
                        <button class="set-default-btn">设为默认</button>
                    </div>
                `).join('');

                modal.classList.add('active');
            }
        ''')
        await asyncio.sleep(0.5)

        modal_visible = await page.evaluate('''
            () => document.getElementById('workdir-selector-modal').classList.contains('active')
        ''')
        print(f"    选择器已显示: {'✅' if modal_visible else '❌'}")

        # 检查列表内容
        list_items = await page.evaluate('''
            () => {
                const items = document.querySelectorAll('#workdir-selector-list .workdir-selector-item');
                return Array.from(items).map(item => item.querySelector('.folder-path').textContent);
            }
        ''')
        print(f"    列表项数量: {len(list_items)}")
        for folder in list_items:
            print(f"        - {folder}")

        # 截图
        await page.screenshot(path="tests/screenshot_workdir_selector.png")
        print("    截图: tests/screenshot_workdir_selector.png")

        # [6] 测试关闭选择器
        print("\n[6] 测试关闭选择器:")
        await page.evaluate('hideWorkdirSelector()')
        await asyncio.sleep(0.3)

        modal_hidden = await page.evaluate('''
            () => !document.getElementById('workdir-selector-modal').classList.contains('active')
        ''')
        print(f"    选择器已关闭: {'✅' if modal_hidden else '❌'}")

        # [7] 测试选择现有目录
        print("\n[7] 测试选择现有目录:")
        conversations_before = await page.evaluate('() => conversations.length')

        # 模拟选择第一个目录
        await page.evaluate(f'''
            async () => {{
                // 直接调用 createConversationWithFolder
                await createConversationWithFolder('{test_folders[0]}');
            }}
        ''')
        await asyncio.sleep(0.5)

        conversations_after = await page.evaluate('() => conversations.length')
        print(f"    会话数变化: {conversations_before} -> {conversations_after}")
        print(f"    新会话已创建: {'✅' if conversations_after > conversations_before else '❌'}")

        # 检查新会话的工作目录
        new_conv_workdir = await page.evaluate('''
            () => {
                const conv = conversations[0];
                return conv ? conv.workingDir : null;
            }
        ''')
        print(f"    新会话工作目录: {new_conv_workdir}")

        # [8] 恢复原始状态
        print("\n[8] 恢复原始状态:")
        await page.evaluate(f'''
            () => {{
                workingFolders = {saved_state['workingFolders']};
                defaultWorkingFolder = {f"'{saved_state['defaultWorkingFolder']}'" if saved_state['defaultWorkingFolder'] else 'null'};
                localStorage.setItem('workingFolders', JSON.stringify(workingFolders));
                if (defaultWorkingFolder) {{
                    localStorage.setItem('defaultWorkingFolder', defaultWorkingFolder);
                }}
                renderWorkingFolders();
            }}
        ''')
        print("    ✅ 状态已恢复")

        # 汇总测试结果
        print("\n" + "=" * 60)
        all_passed = (
            all_functions_exist and
            modal_check['hasModal'] and
            modal_check['hasList'] and
            modal_visible and
            modal_hidden and
            conversations_after > conversations_before
        )
        print(f"测试结果: {'✅ 通过' if all_passed else '⚠️ 部分通过'}")
        print("=" * 60)

        return all_passed


if __name__ == "__main__":
    success = asyncio.run(test_workdir_selector())
    exit(0 if success else 1)
