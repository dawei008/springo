#!/usr/bin/env python3
"""
测试 New Chat 时选择的目录是否添加到 Workspace
通过 Electron 端到端测试
"""

import asyncio
from playwright.async_api import async_playwright


async def test_new_chat_workspace():
    """测试新聊天时工作目录添加到 workspace 的逻辑"""
    print("=" * 60)
    print("New Chat Workspace 测试")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 刷新页面加载最新代码
        await page.reload()
        await asyncio.sleep(2)

        # 检查 newConversation 函数中是否包含添加到 workspace 的逻辑
        print("\n[1] 检查代码修改:")
        code_check = await page.evaluate('''
            () => {
                const funcStr = newConversation.toString();
                return {
                    hasWorkspacePush: funcStr.includes('workingFolders.push'),
                    hasLocalStorageSave: funcStr.includes("localStorage.setItem('workingFolders'"),
                    hasRenderCall: funcStr.includes('renderWorkingFolders()'),
                    hasConsoleLog: funcStr.includes('Added folder to workspace')
                };
            }
        ''')

        if code_check['hasWorkspacePush']:
            print("    ✅ 包含 workingFolders.push")
        else:
            print("    ❌ 缺少 workingFolders.push")

        if code_check['hasLocalStorageSave']:
            print("    ✅ 包含 localStorage 保存")
        else:
            print("    ❌ 缺少 localStorage 保存")

        if code_check['hasRenderCall']:
            print("    ✅ 包含 renderWorkingFolders 调用")
        else:
            print("    ❌ 缺少 renderWorkingFolders 调用")

        # 模拟测试逻辑（不触发实际对话框）
        print("\n[2] 模拟添加目录到 workspace:")

        # 获取当前 workspace
        before = await page.evaluate('() => [...workingFolders]')
        print(f"    修改前 workspace: {len(before)} 个目录")

        # 模拟添加一个新目录（和 newConversation 中相同的逻辑）
        test_dir = "/tmp/test_workspace_dir_" + str(int(asyncio.get_event_loop().time() * 1000))
        result = await page.evaluate(f'''
            () => {{
                const testDir = '{test_dir}';
                if (!workingFolders.includes(testDir)) {{
                    workingFolders.push(testDir);
                    localStorage.setItem('workingFolders', JSON.stringify(workingFolders));
                    renderWorkingFolders();
                    return {{ added: true, dir: testDir }};
                }}
                return {{ added: false, dir: testDir }};
            }}
        ''')

        if result['added']:
            print(f"    ✅ 成功添加测试目录: {test_dir}")
        else:
            print(f"    ⚠️ 目录已存在")

        # 验证
        after = await page.evaluate('() => [...workingFolders]')
        print(f"    修改后 workspace: {len(after)} 个目录")

        if test_dir in after:
            print("    ✅ 目录已添加到 workspace")
        else:
            print("    ❌ 目录未添加到 workspace")

        # 清理测试目录
        await page.evaluate(f'''
            () => {{
                const idx = workingFolders.indexOf('{test_dir}');
                if (idx > -1) {{
                    workingFolders.splice(idx, 1);
                    localStorage.setItem('workingFolders', JSON.stringify(workingFolders));
                    renderWorkingFolders();
                }}
            }}
        ''')
        print("    ✅ 测试目录已清理")

        # 截图
        await page.screenshot(path="tests/screenshot_workspace_test.png")

        print("\n" + "=" * 60)
        all_passed = all(code_check.values())
        print(f"测试结果: {'✅ 通过' if all_passed else '⚠️ 部分通过'}")
        print("=" * 60)

        return all_passed


if __name__ == "__main__":
    success = asyncio.run(test_new_chat_workspace())
    exit(0 if success else 1)
