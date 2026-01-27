#!/usr/bin/env python3
"""
E2E 测试: 通过 Electron 前端测试 tool-results 功能
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
    print("E2E 测试: Tool Results 通过 Electron 前端")
    print("=" * 60)

    # 获取当前工作目录
    resp = requests.get("http://127.0.0.1:8080/v1/config/working-dir")
    working_dir = resp.json().get('working_dir', '/tmp')
    print(f"\n0. 当前工作目录: {working_dir}")

    # 在工作目录下创建测试文件 (50KB)
    test_file = os.path.join(working_dir, "large_test_file_for_tool_results.txt")

    with open(test_file, 'w') as f:
        for i in range(1500):
            f.write(f"Line {i+1}: This is test content for verifying large tool output storage. " * 2 + "\n")

    file_size = os.path.getsize(test_file)
    print(f"\n1. 创建测试文件: {test_file} ({file_size / 1024:.1f} KB)")

    async with async_playwright() as p:
        # 连接到 Electron
        print("\n2. 连接到 Electron 应用...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]
        print("   ✅ 已连接")

        # 刷新页面
        await page.reload()
        await asyncio.sleep(2)

        # 发送请求
        print(f"\n3. 发送测试请求...")
        input_selector = 'textarea'
        await page.wait_for_selector(input_selector, timeout=5000)

        # 输入请求：读取大文件
        test_message = f"请使用 read_file 工具读取 {test_file} 文件的全部内容，然后统计有多少行"
        await page.fill(input_selector, test_message)
        print(f"   消息: {test_message[:70]}...")

        # 发送
        await page.keyboard.press("Enter")
        print("   ✅ 已发送")

        # 等待一会让消息处理
        await asyncio.sleep(3)

        # 从后端获取最新 session
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
        print("\n4. 等待响应 (最多120秒)...")
        start_time = time.time()
        found_new_file = False

        while time.time() - start_time < 120:
            # 检查新文件
            if os.path.exists(tool_results_dir):
                files_after = set(os.listdir(tool_results_dir))
                new_files = files_after - files_before
                if new_files:
                    elapsed = time.time() - start_time
                    print(f"\n   ✅ 发现新文件! (耗时 {elapsed:.1f}s)")
                    found_new_file = True
                    break

            await asyncio.sleep(1)
            elapsed = int(time.time() - start_time)
            print(f"   等待中... {elapsed}s", end="\r")

        # 额外等待确保完成
        await asyncio.sleep(5)

        # 检查结果
        print("\n\n5. 检查 tool-results 目录...")
        print(f"   路径: {tool_results_dir}")

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
                if filename.startswith("toolu_bdrk_") and filename.endswith(".txt"):
                    print(f"      格式: ✅ Bedrock 工具命名正确")
                elif filename.startswith("mcp-") and filename.endswith(".txt"):
                    print(f"      格式: ✅ MCP 工具命名正确")
                else:
                    print(f"      格式: ⚠️ 未知命名格式")

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
                print("   可能原因:")
                print("   - 工具输出小于 30KB 阈值")
                print("   - 响应还未完成")
                print("   - Claude 选择不使用工具")
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
        else:
            print(f"   ⚠️ Session 目录不存在")

        # 截图
        screenshot_path = "/Users/awsdawei/claude/springo/tests/tool_results_e2e.png"
        await page.screenshot(path=screenshot_path)
        print(f"\n6. 截图: {screenshot_path}")

    # 清理测试文件
    if os.path.exists(test_file):
        os.remove(test_file)
        print(f"\n7. 已清理测试文件")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
