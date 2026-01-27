#!/usr/bin/env python3
"""
E2E 测试: MCP 工具大输出 (场景2)
测试 mcp-{server}-{tool}-{ts}.txt 命名格式
"""

import asyncio
import os
import json
import time
import requests
from playwright.async_api import async_playwright

SESSIONS_DIR = os.path.expanduser("~/.springo/sessions")

async def main():
    print("\n" + "=" * 60)
    print("E2E 测试: MCP 工具大输出 (场景2)")
    print("=" * 60)

    async with async_playwright() as p:
        # 连接到 Electron
        print("\n1. 连接到 Electron 应用...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]
        print("   ✅ 已连接")

        # 刷新页面
        await page.reload()
        await asyncio.sleep(2)

        # 发送请求 - 使用 MCP 工具进行 web 搜索
        print("\n2. 发送测试请求 (MCP web search)...")
        input_selector = 'textarea'
        await page.wait_for_selector(input_selector, timeout=5000)

        # 使用 brave_web_search 搜索，并请求详细结果
        test_message = "使用 web search 搜索 'AWS Bedrock Claude models 2026' 并显示完整的搜索结果内容"
        await page.fill(input_selector, test_message)
        print(f"   消息: {test_message}")

        # 发送
        await page.keyboard.press("Enter")
        print("   ✅ 已发送")

        # 等待获取 session
        await asyncio.sleep(3)
        resp = requests.get("http://127.0.0.1:8080/v1/sessions")
        sessions = resp.json().get('sessions', [])
        if sessions:
            session_id = sessions[0]['session_id']
            print(f"   最新 Session ID: {session_id}")
        else:
            print("   ❌ 没有 session")
            return

        # 记录测试前状态
        session_dir = os.path.join(SESSIONS_DIR, session_id)
        tool_results_dir = os.path.join(session_dir, "tool-results")

        files_before = set()
        if os.path.exists(tool_results_dir):
            files_before = set(os.listdir(tool_results_dir))
        print(f"   测试前 tool-results 文件数: {len(files_before)}")

        # 等待响应
        print("\n3. 等待响应 (最多60秒)...")
        start_time = time.time()

        while time.time() - start_time < 60:
            if os.path.exists(tool_results_dir):
                files_after = set(os.listdir(tool_results_dir))
                new_files = files_after - files_before
                if new_files:
                    elapsed = time.time() - start_time
                    print(f"\n   ✅ 发现新文件! (耗时 {elapsed:.1f}s)")
                    break

            await asyncio.sleep(1)
            elapsed = int(time.time() - start_time)
            print(f"   等待中... {elapsed}s", end="\r")

        # 额外等待
        await asyncio.sleep(5)

        # 检查结果
        print("\n\n4. 检查 tool-results 目录...")
        print(f"   路径: {tool_results_dir}")

        mcp_files_found = False
        if os.path.exists(tool_results_dir):
            files_after = set(os.listdir(tool_results_dir))
            new_files = files_after - files_before

            print(f"\n   新创建的文件: {len(new_files)} 个")

            for filename in sorted(new_files):
                filepath = os.path.join(tool_results_dir, filename)
                size = os.path.getsize(filepath)

                print(f"\n   📄 文件名: {filename}")
                print(f"      大小: {size / 1024:.1f} KB")

                # 验证命名格式
                if filename.startswith("mcp-") and filename.endswith(".txt"):
                    print(f"      格式: ✅ MCP 工具命名正确")
                    mcp_files_found = True
                    # 解析文件名
                    parts = filename.replace(".txt", "").split("-")
                    if len(parts) >= 3:
                        print(f"      解析: server={parts[1]}, tool={parts[2]}, ts={parts[-1]}")
                elif filename.startswith("toolu_bdrk_") and filename.endswith(".txt"):
                    print(f"      格式: ✅ Bedrock 工具命名")

                # 显示元数据
                with open(filepath, 'r') as f:
                    first_line = f.readline().strip()
                    try:
                        metadata = json.loads(first_line)
                        print(f"      元数据:")
                        print(f"        - tool_use_id: {metadata.get('tool_use_id', 'N/A')}")
                        print(f"        - tool_name: {metadata.get('tool_name', 'N/A')}")
                        print(f"        - size: {metadata.get('size', 'N/A')} bytes")
                    except:
                        print(f"      首行: {first_line[:80]}...")

            if not new_files:
                print("\n   ⚠️ 没有新建 tool-results 文件")
                print("   (MCP web search 结果可能小于 30KB)")
        else:
            print("   ⚠️ tool-results 目录不存在")

        # 列出 session 目录
        print(f"\n   Session 目录内容:")
        if os.path.exists(session_dir):
            for item in os.listdir(session_dir):
                item_path = os.path.join(session_dir, item)
                if os.path.isdir(item_path):
                    sub_files = os.listdir(item_path)
                    print(f"   📁 {item}/ ({len(sub_files)} 个文件)")
                    for sf in sub_files[:5]:
                        sf_size = os.path.getsize(os.path.join(item_path, sf))
                        print(f"      └── {sf} ({sf_size / 1024:.1f} KB)")
                else:
                    size = os.path.getsize(item_path)
                    print(f"   📄 {item} ({size / 1024:.1f} KB)")

        # 截图
        screenshot_path = "/Users/awsdawei/claude/springo/tests/tool_results_mcp_e2e.png"
        await page.screenshot(path=screenshot_path)
        print(f"\n5. 截图: {screenshot_path}")

    print("\n" + "=" * 60)
    if mcp_files_found:
        print("✅ MCP 工具命名格式测试通过!")
    else:
        print("⚠️ MCP 工具可能返回结果小于 30KB，未触发文件存储")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
