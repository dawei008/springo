#!/usr/bin/env python3
"""
测试页面初始化时的工作目录同步问题
通过 Electron 端到端测试
"""

import asyncio
import aiohttp
from playwright.async_api import async_playwright


async def test_init_sync():
    """测试页面刷新后的工作目录同步"""
    print("=" * 60)
    print("页面初始化工作目录同步测试")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 获取初始状态
        print("\n[1] 刷新前状态:")
        ui_path_before = await page.evaluate("""
            () => document.getElementById('workdir-path-display')?.textContent
        """)
        print(f"    UI 显示: {ui_path_before}")

        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8080/v1/config/working-dir") as resp:
                data = await resp.json()
                backend_before = data.get("working_dir", "")
        print(f"    后端目录: {backend_before}")

        # 收集控制台日志
        console_logs = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

        # 刷新页面
        print("\n[2] 刷新页面...")
        await page.reload()
        await asyncio.sleep(3)  # 等待初始化完成和同步

        # 获取刷新后状态
        print("\n[3] 刷新后状态:")
        ui_path_after = await page.evaluate("""
            () => document.getElementById('workdir-path-display')?.textContent
        """)
        print(f"    UI 显示: {ui_path_after}")

        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8080/v1/config/working-dir") as resp:
                data = await resp.json()
                backend_after = data.get("working_dir", "")
        print(f"    后端目录: {backend_after}")

        # 分析控制台日志
        print("\n[4] 相关控制台日志:")
        workdir_logs = [log for log in console_logs if 'work' in log.lower() or 'sync' in log.lower() or 'dir' in log.lower()]
        for log in workdir_logs[:10]:
            print(f"    {log}")

        # 检查是否有错误日志
        error_logs = [log for log in console_logs if '[error]' in log.lower() or 'failed' in log.lower()]
        if error_logs:
            print("\n[5] 错误日志:")
            for log in error_logs[:5]:
                print(f"    {log}")

        # 分析结果
        print("\n[6] 分析结果:")
        if ui_path_after and ui_path_after.strip() == backend_after:
            print("    ✅ 刷新后同步成功")
            return True
        else:
            print(f"    ❌ 刷新后不同步!")
            print(f"       UI: '{ui_path_after}'")
            print(f"       后端: '{backend_after}'")

            # 进一步调查
            print("\n[7] 进一步调查:")
            # 检查 BASE_URL
            base_url = await page.evaluate("() => typeof BASE_URL !== 'undefined' ? BASE_URL : null")
            print(f"    BASE_URL: {base_url}")

            # 检查 currentWorkingDir 变量
            cwd = await page.evaluate("() => typeof currentWorkingDir !== 'undefined' ? currentWorkingDir : null")
            print(f"    currentWorkingDir 变量: {cwd}")

            # 手动触发同步
            print("\n[8] 手动触发同步:")
            if cwd:
                result = await page.evaluate(f"""
                    async () => {{
                        const result = await updateServerWorkingDir('{cwd}');
                        return result;
                    }}
                """)
                print(f"    手动同步结果: {result}")

                await asyncio.sleep(1)
                async with aiohttp.ClientSession() as session:
                    async with session.get("http://localhost:8080/v1/config/working-dir") as resp:
                        data = await resp.json()
                        backend_manual = data.get("working_dir", "")
                print(f"    手动同步后后端目录: {backend_manual}")

                if backend_manual == cwd:
                    print("    ✅ 手动同步成功，说明初始化时同步调用有问题")
                else:
                    print("    ❌ 手动同步也失败")

            return False


if __name__ == "__main__":
    success = asyncio.run(test_init_sync())
    print(f"\n最终结果: {'通过' if success else '发现问题'}")
