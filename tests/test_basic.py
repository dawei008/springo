#!/usr/bin/env python3
"""
Springo 基本功能测试
基于 Electron 应用进行测试
"""

import asyncio
import aiohttp
from playwright.async_api import async_playwright


async def test_backend_health():
    """测试后端服务器健康状态"""
    print("\n[1] 测试后端服务器健康状态...")
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:8080/health") as resp:
            data = await resp.json()
            assert data["status"] == "healthy", f"后端状态异常: {data}"
            print(f"    ✅ 后端健康: {data}")
    return True


async def test_electron_connection():
    """测试 Electron 应用连接"""
    print("\n[2] 测试 Electron 应用连接...")
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        contexts = browser.contexts
        assert len(contexts) > 0, "没有找到浏览器上下文"

        page = contexts[0].pages[0]
        title = await page.title()
        print(f"    ✅ 已连接到 Electron，页面标题: {title}")

        # 检查页面基本元素
        url = page.url
        print(f"    ✅ 当前 URL: {url}")
    return True


async def test_ui_elements():
    """测试 UI 基本元素"""
    print("\n[3] 测试 UI 基本元素...")
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 检查聊天容器
        chat_container = await page.query_selector("#chat-container")
        if chat_container:
            print("    ✅ 聊天容器存在")
        else:
            print("    ⚠️ 未找到聊天容器")

        # 检查输入框
        input_box = await page.query_selector("#user-input")
        if input_box:
            print("    ✅ 输入框存在")
        else:
            print("    ⚠️ 未找到输入框")

        # 检查发送按钮
        send_btn = await page.query_selector("#send-btn")
        if send_btn:
            print("    ✅ 发送按钮存在")
        else:
            print("    ⚠️ 未找到发送按钮")

    return True


async def test_tools_api():
    """测试工具 API"""
    print("\n[4] 测试工具 API...")
    async with aiohttp.ClientSession() as session:
        # 测试 computer_info 工具
        payload = {
            "name": "computer_info",
            "input": {}
        }
        async with session.post(
            "http://localhost:8080/v1/tools/execute",
            json=payload
        ) as resp:
            data = await resp.json()
            if "error" not in data:
                print(f"    ✅ computer_info 工具正常")
            else:
                print(f"    ⚠️ computer_info 返回: {data}")
    return True


async def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("Springo 基本功能测试")
    print("=" * 50)

    tests = [
        ("后端健康检查", test_backend_health),
        ("Electron 连接", test_electron_connection),
        ("UI 元素检查", test_ui_elements),
        ("工具 API", test_tools_api),
    ]

    results = []
    for name, test_func in tests:
        try:
            await test_func()
            results.append((name, True, None))
        except Exception as e:
            print(f"    ❌ 失败: {e}")
            results.append((name, False, str(e)))

    # 汇总
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed

    for name, ok, err in results:
        status = "✅ 通过" if ok else f"❌ 失败: {err}"
        print(f"  {name}: {status}")

    print(f"\n总计: {passed} 通过, {failed} 失败")
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
