#!/usr/bin/env python3
"""
测试工作目录和显示路径一致性问题
通过 Electron 端到端测试
"""

import asyncio
import aiohttp
from playwright.async_api import async_playwright


async def test_directory_consistency():
    """测试工作目录和显示路径的一致性"""
    print("=" * 60)
    print("工作目录与显示路径一致性测试")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 1. 获取 UI 上显示的工作目录
        print("\n[1] 检查 UI 显示的工作目录...")

        # 尝试多种可能的选择器获取显示的路径
        ui_path = None

        # 检查是否有工作目录显示元素
        selectors_to_try = [
            "#current-path",
            "#working-directory",
            "#cwd",
            ".current-path",
            ".working-directory",
            "[data-path]",
            "#path-display",
            ".path-display",
            "#directory-path",
        ]

        for selector in selectors_to_try:
            element = await page.query_selector(selector)
            if element:
                ui_path = await element.text_content()
                print(f"    找到元素 {selector}: {ui_path}")
                break

        if not ui_path:
            # 尝试通过 JavaScript 获取
            ui_path = await page.evaluate("""
                () => {
                    // 查找可能包含路径的元素
                    const pathElements = document.querySelectorAll('[class*="path"], [id*="path"], [class*="directory"], [id*="directory"]');
                    const results = [];
                    pathElements.forEach(el => {
                        if (el.textContent && el.textContent.includes('/')) {
                            results.push({
                                selector: el.id || el.className,
                                text: el.textContent.trim()
                            });
                        }
                    });
                    return results;
                }
            """)
            print(f"    通过 JS 查找路径元素: {ui_path}")

        # 2. 获取全局变量中的工作目录
        print("\n[2] 检查 JavaScript 全局变量...")
        js_vars = await page.evaluate("""
            () => {
                return {
                    currentWorkingDirectory: window.currentWorkingDirectory || null,
                    workingDirectory: window.workingDirectory || null,
                    cwd: window.cwd || null,
                    currentPath: window.currentPath || null,
                    BASE_URL: window.BASE_URL || null,
                    // 检查可能的状态对象
                    appState: window.appState ? JSON.stringify(window.appState) : null,
                    state: window.state ? JSON.stringify(window.state) : null,
                }
            }
        """)
        print(f"    JavaScript 变量:")
        for key, value in js_vars.items():
            if value:
                print(f"      {key}: {value}")

        # 3. 通过后端 API 获取实际工作目录
        print("\n[3] 检查后端 API 返回的工作目录...")
        async with aiohttp.ClientSession() as session:
            # 测试 computer_info 工具获取系统信息
            payload = {"name": "computer_info", "input": {}}
            async with session.post("http://localhost:8080/v1/tools/execute", json=payload) as resp:
                data = await resp.json()
                if "result" in data:
                    result_str = str(data['result'])
                    print(f"    computer_info 返回: {result_str[:200]}...")

            # 测试 bash 工具获取 pwd
            payload = {"name": "bash", "input": {"command": "pwd"}}
            async with session.post("http://localhost:8080/v1/tools/execute", json=payload) as resp:
                data = await resp.json()
                print(f"    bash pwd 原始返回: {data}")
                result = data.get("result", data)
                if isinstance(result, dict):
                    backend_cwd = result.get("output", str(result))
                else:
                    backend_cwd = str(result).strip()
                print(f"    后端 pwd 返回: {backend_cwd}")

            # 获取后端的工作目录配置
            try:
                async with session.get("http://localhost:8080/api/workspace") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"    /api/workspace 返回: {data}")
            except:
                print("    /api/workspace 端点不存在")

        # 4. 检查 Electron 主进程的工作目录
        print("\n[4] 检查 Electron preload 暴露的 API...")
        electron_api = await page.evaluate("""
            () => {
                if (window.electronAPI) {
                    return {
                        hasElectronAPI: true,
                        methods: Object.keys(window.electronAPI),
                        cwd: window.electronAPI.cwd ? window.electronAPI.cwd() : null,
                        getWorkingDirectory: window.electronAPI.getWorkingDirectory ? window.electronAPI.getWorkingDirectory() : null,
                    }
                }
                return { hasElectronAPI: false }
            }
        """)
        print(f"    Electron API: {electron_api}")

        # 5. 模拟用户操作检查路径变化
        print("\n[5] 检查文件浏览器中的路径...")
        # 查找文件浏览相关的元素
        file_browser_info = await page.evaluate("""
            () => {
                const info = {};

                // 查找文件浏览器相关元素
                const fileBrowser = document.querySelector('#file-browser, .file-browser, [class*="file-browser"]');
                if (fileBrowser) {
                    info.fileBrowserExists = true;
                    info.fileBrowserHTML = fileBrowser.innerHTML.substring(0, 500);
                }

                // 查找路径面包屑
                const breadcrumb = document.querySelector('.breadcrumb, #breadcrumb, [class*="breadcrumb"]');
                if (breadcrumb) {
                    info.breadcrumb = breadcrumb.textContent;
                }

                // 查找所有包含路径的输入框
                const inputs = document.querySelectorAll('input[type="text"]');
                inputs.forEach((input, i) => {
                    if (input.value && input.value.includes('/')) {
                        info[`input_${i}`] = input.value;
                    }
                });

                return info;
            }
        """)
        print(f"    文件浏览器信息: {file_browser_info}")

        # 6. 截图保存当前状态
        print("\n[6] 截图保存当前 UI 状态...")
        await page.screenshot(path="tests/screenshot_directory_test.png", full_page=True)
        print("    已保存截图: tests/screenshot_directory_test.png")

        print("\n" + "=" * 60)
        print("测试完成，请分析上述输出查找不一致问题")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_directory_consistency())
