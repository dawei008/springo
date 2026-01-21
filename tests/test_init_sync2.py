#!/usr/bin/env python3
"""
测试页面初始化时的工作目录同步问题 - 通过清除后端状态来模拟
通过 Electron 端到端测试
"""

import asyncio
import aiohttp
from playwright.async_api import async_playwright


async def test_init_sync():
    """测试初始化同步问题"""
    print("=" * 60)
    print("页面初始化工作目录同步测试")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 1. 获取前端当前工作目录
        print("\n[1] 获取前端状态:")
        frontend_cwd = await page.evaluate("() => currentWorkingDir")
        print(f"    前端 currentWorkingDir: {frontend_cwd}")

        ui_display = await page.evaluate("() => document.getElementById('workdir-path-display')?.textContent")
        print(f"    UI 显示: {ui_display}")

        # 2. 清除后端工作目录（模拟服务器重启后的状态）
        print("\n[2] 清除后端工作目录 (模拟服务器重启):")
        async with aiohttp.ClientSession() as session:
            # 设置一个空目录来清除（或者设置一个不存在的路径会返回错误，我们用 /tmp）
            async with session.post(
                "http://localhost:8080/v1/config/working-dir",
                json={"working_dir": "/tmp"}
            ) as resp:
                data = await resp.json()
                print(f"    设置 /tmp 结果: {data}")

        # 验证后端状态
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8080/v1/config/working-dir") as resp:
                data = await resp.json()
                backend_cwd = data.get("working_dir", "")
        print(f"    后端目录: {backend_cwd}")

        # 3. 检查前端是否会检测到不一致并自动同步
        print("\n[3] 等待 5 秒看前端是否自动同步...")
        await asyncio.sleep(5)

        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8080/v1/config/working-dir") as resp:
                data = await resp.json()
                backend_after_wait = data.get("working_dir", "")
        print(f"    5秒后后端目录: {backend_after_wait}")

        if backend_after_wait == frontend_cwd:
            print("    ✅ 前端自动同步了")
        else:
            print("    ❌ 前端没有自动同步")

        # 4. 触发 checkConnection (模拟健康检查)
        print("\n[4] 触发 checkConnection:")
        await page.evaluate("() => checkConnection()")
        await asyncio.sleep(2)

        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8080/v1/config/working-dir") as resp:
                data = await resp.json()
                backend_after_check = data.get("working_dir", "")
        print(f"    checkConnection 后后端目录: {backend_after_check}")

        # 5. 分析 checkConnection 代码
        print("\n[5] 分析:")
        print("    checkConnection 只在 '连接恢复' 时同步工作目录")
        print("    如果连接一直正常，不会触发同步")
        print(f"    当前前端 lastConnectionHealthy 状态未知")

        # 6. 恢复正确的工作目录
        print("\n[6] 恢复工作目录:")
        if frontend_cwd:
            await page.evaluate(f"() => selectWorkingDir('{frontend_cwd}')")
            await asyncio.sleep(1)

            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:8080/v1/config/working-dir") as resp:
                    data = await resp.json()
                    final_backend = data.get("working_dir", "")
            print(f"    恢复后后端目录: {final_backend}")

        print("\n" + "=" * 60)
        print("结论: 问题在于页面加载时 DOMContentLoaded 中的同步调用")
        print("可能原因:")
        print("  1. updateServerWorkingDir 是 async 但没有被 await")
        print("  2. 服务器在前端调用时还没完全启动")
        print("  3. 同步失败后没有重试机制在初始化时生效")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_init_sync())
