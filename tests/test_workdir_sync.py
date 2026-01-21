#!/usr/bin/env python3
"""
测试前端显示路径与后端工作目录的同步问题
通过 Electron 端到端测试
"""

import asyncio
import aiohttp
from playwright.async_api import async_playwright


async def test_workdir_sync():
    """测试前后端工作目录同步"""
    print("=" * 60)
    print("工作目录同步测试")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 1. 获取前端显示的工作目录
        print("\n[1] 前端显示的工作目录:")
        ui_path = await page.evaluate("""
            () => {
                const pathDisplay = document.getElementById('workdir-path-display');
                return pathDisplay ? pathDisplay.textContent : null;
            }
        """)
        print(f"    UI 显示路径: {ui_path}")

        # 获取前端 JavaScript 变量
        frontend_vars = await page.evaluate("""
            () => {
                return {
                    currentWorkingDir: typeof currentWorkingDir !== 'undefined' ? currentWorkingDir : null,
                    workingFolders: typeof workingFolders !== 'undefined' ? workingFolders : null,
                    currentConversationId: typeof currentConversationId !== 'undefined' ? currentConversationId : null,
                }
            }
        """)
        print(f"    currentWorkingDir 变量: {frontend_vars.get('currentWorkingDir')}")
        print(f"    workingFolders 变量: {frontend_vars.get('workingFolders')}")

        # 获取当前会话的工作目录
        conv_workdir = await page.evaluate("""
            () => {
                if (typeof conversations !== 'undefined' && typeof currentConversationId !== 'undefined') {
                    const conv = conversations.find(c => c.id === currentConversationId);
                    return conv ? { id: conv.id, workingDir: conv.workingDir } : null;
                }
                return null;
            }
        """)
        print(f"    当前会话工作目录: {conv_workdir}")

        # 2. 获取后端的工作目录
        print("\n[2] 后端工作目录:")
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8080/v1/config/working-dir") as resp:
                data = await resp.json()
                backend_workdir = data.get("working_dir", "")
                print(f"    后端工作目录: {backend_workdir}")

        # 3. 比较分析
        print("\n[3] 同步状态分析:")
        ui_display = ui_path.strip() if ui_path else ""
        frontend_var = frontend_vars.get('currentWorkingDir') or ""
        conv_dir = conv_workdir.get('workingDir') if conv_workdir else ""
        backend_dir = backend_workdir or ""

        print(f"    UI 显示:        '{ui_display}'")
        print(f"    前端变量:       '{frontend_var}'")
        print(f"    会话工作目录:   '{conv_dir}'")
        print(f"    后端工作目录:   '{backend_dir}'")

        # 检查不一致
        issues = []
        if ui_display != frontend_var:
            issues.append(f"UI显示({ui_display}) != 前端变量({frontend_var})")
        if frontend_var != backend_dir:
            issues.append(f"前端变量({frontend_var}) != 后端目录({backend_dir})")
        if ui_display != backend_dir:
            issues.append(f"UI显示({ui_display}) != 后端目录({backend_dir})")
        if conv_dir and conv_dir != frontend_var:
            issues.append(f"会话目录({conv_dir}) != 前端变量({frontend_var})")

        print("\n[4] 发现的问题:")
        if issues:
            for issue in issues:
                print(f"    ❌ {issue}")
        else:
            print("    ✅ 所有路径一致")

        # 4. 测试切换工作目录后的同步
        print("\n[5] 测试目录切换同步:")
        if frontend_vars.get('workingFolders') and len(frontend_vars['workingFolders']) > 1:
            # 获取另一个工作目录
            other_folder = None
            for f in frontend_vars['workingFolders']:
                if f != frontend_var:
                    other_folder = f
                    break

            if other_folder:
                print(f"    切换到: {other_folder}")

                # 通过 UI 切换
                await page.evaluate(f"""
                    () => {{
                        selectWorkingDir('{other_folder}');
                    }}
                """)
                await asyncio.sleep(1)  # 等待同步

                # 再次检查
                new_ui_path = await page.evaluate("""
                    () => document.getElementById('workdir-path-display')?.textContent
                """)
                async with aiohttp.ClientSession() as session:
                    async with session.get("http://localhost:8080/v1/config/working-dir") as resp:
                        data = await resp.json()
                        new_backend_dir = data.get("working_dir", "")

                print(f"    切换后 UI 显示: {new_ui_path}")
                print(f"    切换后后端目录: {new_backend_dir}")

                if new_ui_path and new_ui_path.strip() == new_backend_dir:
                    print("    ✅ 切换后同步正常")
                else:
                    print("    ❌ 切换后不同步!")

                # 切换回原来的目录
                if frontend_var:
                    await page.evaluate(f"""
                        () => {{
                            selectWorkingDir('{frontend_var}');
                        }}
                    """)
        else:
            print("    跳过 (只有一个工作目录)")

        # 5. 截图
        await page.screenshot(path="tests/screenshot_workdir_sync.png")
        print("\n已保存截图: tests/screenshot_workdir_sync.png")

        print("\n" + "=" * 60)
        return len(issues) == 0


if __name__ == "__main__":
    success = asyncio.run(test_workdir_sync())
    print(f"\n测试结果: {'通过' if success else '发现问题'}")
