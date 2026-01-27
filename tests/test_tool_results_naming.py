#!/usr/bin/env python3
"""
测试 tool-results 命名规范:
1. Bedrock 工具: toolu_bdrk_{id}.txt
2. MCP 工具: mcp-{server}-{tool}-{ts}.txt
"""

import asyncio
import json
import os
import sys
import requests
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from context_manager import ContextManager

BASE_URL = "http://127.0.0.1:8080"
SESSIONS_DIR = os.path.expanduser("~/.springo/sessions")

def create_large_content(size_kb=35):
    """创建大于30KB的测试内容"""
    line = "This is test content line for tool result testing. " * 10 + "\n"
    lines_needed = (size_kb * 1024) // len(line) + 1
    return line * lines_needed

async def test_scenario_1_bedrock_tool():
    """场景1: 测试 Bedrock 工具大输出命名 (toolu_bdrk_{id}.txt)"""
    print("\n" + "=" * 60)
    print("场景1: Bedrock 工具大输出 (>30KB)")
    print("=" * 60)

    ctx = ContextManager()

    # 创建测试 session
    test_session_id = f"test-bedrock-{int(datetime.now().timestamp() * 1000)}"

    # 模拟 Bedrock 工具 ID
    tool_use_id = "toolu_bdrk_01ABC123XYZ"
    tool_name = "read_file"  # Bedrock 内置工具

    # 创建 35KB 测试内容
    large_content = create_large_content(35)
    content_size = len(large_content.encode('utf-8'))
    print(f"测试内容大小: {content_size / 1024:.1f} KB")

    # 保存 tool result
    result = ctx.save_tool_result(test_session_id, tool_use_id, large_content, tool_name)

    print(f"\n保存结果:")
    print(f"  - inline: {result.get('inline', 'N/A')}")
    print(f"  - size: {result.get('size', 'N/A')} bytes")

    if not result.get('inline'):
        file_path = result.get('file_path')
        print(f"  - file_path: {file_path}")

        # 验证文件名格式
        filename = os.path.basename(file_path)
        print(f"\n文件名验证:")
        print(f"  - 实际文件名: {filename}")
        print(f"  - 期望格式: toolu_bdrk_*.txt")

        if filename.startswith("toolu_bdrk_") and filename.endswith(".txt"):
            print(f"  ✅ 命名格式正确!")
        else:
            print(f"  ❌ 命名格式错误!")

        # 验证 API 查找功能
        print(f"\nAPI 查找测试:")
        found_path = ctx.find_tool_result_file(test_session_id, tool_use_id)
        if found_path and os.path.exists(found_path):
            print(f"  ✅ find_tool_result_file 成功找到文件")
        else:
            print(f"  ❌ find_tool_result_file 未能找到文件")

        # 通过 HTTP API 测试
        resp = requests.get(f"{BASE_URL}/v1/tool-results/{test_session_id}/{tool_use_id}")
        if resp.status_code == 200:
            print(f"  ✅ HTTP API 成功获取内容 (size: {resp.json().get('size')} bytes)")
        else:
            print(f"  ❌ HTTP API 失败: {resp.status_code}")
    else:
        print(f"  ⚠️ 内容被 inline 存储，未创建文件")

    # 清理
    session_dir = ctx.get_session_dir(test_session_id)
    if os.path.exists(session_dir):
        import shutil
        shutil.rmtree(session_dir)
        print(f"\n清理测试目录: {session_dir}")

    return not result.get('inline')

async def test_scenario_2_mcp_tool():
    """场景2: 测试 MCP 工具大输出命名 (mcp-{server}-{tool}-{ts}.txt)"""
    print("\n" + "=" * 60)
    print("场景2: MCP 工具大输出 (>30KB)")
    print("=" * 60)

    ctx = ContextManager()

    # 创建测试 session
    test_session_id = f"test-mcp-{int(datetime.now().timestamp() * 1000)}"

    # 模拟 MCP 工具 ID 和名称
    tool_use_id = "mcp_call_12345678"
    tool_name = "web-search__brave_web_search"  # MCP 工具格式: {server}__{tool}

    # 创建 40KB 测试内容
    large_content = create_large_content(40)
    content_size = len(large_content.encode('utf-8'))
    print(f"测试内容大小: {content_size / 1024:.1f} KB")

    # 保存 tool result
    result = ctx.save_tool_result(test_session_id, tool_use_id, large_content, tool_name)

    print(f"\n保存结果:")
    print(f"  - inline: {result.get('inline', 'N/A')}")
    print(f"  - size: {result.get('size', 'N/A')} bytes")

    if not result.get('inline'):
        file_path = result.get('file_path')
        print(f"  - file_path: {file_path}")

        # 验证文件名格式
        filename = os.path.basename(file_path)
        print(f"\n文件名验证:")
        print(f"  - 实际文件名: {filename}")
        print(f"  - 期望格式: mcp-web-search-brave_web_search-*.txt")

        if filename.startswith("mcp-") and "-" in filename and filename.endswith(".txt"):
            parts = filename.replace(".txt", "").split("-")
            if len(parts) >= 3:
                print(f"  ✅ 命名格式正确!")
                print(f"     - server: {parts[1]}")
                print(f"     - tool: {'-'.join(parts[2:-1])}")
                print(f"     - timestamp: {parts[-1]}")
            else:
                print(f"  ⚠️ 命名格式部分正确，但解析有问题")
        else:
            print(f"  ❌ 命名格式错误!")

        # 验证 API 查找功能
        print(f"\nAPI 查找测试:")
        found_path = ctx.find_tool_result_file(test_session_id, tool_use_id)
        if found_path and os.path.exists(found_path):
            print(f"  ✅ find_tool_result_file 成功找到文件")
        else:
            print(f"  ❌ find_tool_result_file 未能找到文件")

        # 通过 HTTP API 测试
        resp = requests.get(f"{BASE_URL}/v1/tool-results/{test_session_id}/{tool_use_id}")
        if resp.status_code == 200:
            print(f"  ✅ HTTP API 成功获取内容 (size: {resp.json().get('size')} bytes)")
        else:
            print(f"  ❌ HTTP API 失败: {resp.status_code}")
    else:
        print(f"  ⚠️ 内容被 inline 存储，未创建文件")

    # 清理
    session_dir = ctx.get_session_dir(test_session_id)
    if os.path.exists(session_dir):
        import shutil
        shutil.rmtree(session_dir)
        print(f"\n清理测试目录: {session_dir}")

    return not result.get('inline')

async def test_threshold():
    """测试 30KB 阈值"""
    print("\n" + "=" * 60)
    print("阈值测试: 30KB 边界")
    print("=" * 60)

    ctx = ContextManager()
    test_session_id = f"test-threshold-{int(datetime.now().timestamp() * 1000)}"

    # 测试 29KB (应该 inline)
    content_29kb = create_large_content(29)
    result_29 = ctx.save_tool_result(test_session_id, "toolu_bdrk_test29", content_29kb, "test")

    # 测试 31KB (应该存文件)
    content_31kb = create_large_content(31)
    result_31 = ctx.save_tool_result(test_session_id, "toolu_bdrk_test31", content_31kb, "test")

    print(f"29KB 内容: inline={result_29.get('inline')} (期望: True)")
    print(f"31KB 内容: inline={result_31.get('inline')} (期望: False)")

    threshold_ok = result_29.get('inline') == True and result_31.get('inline') == False
    if threshold_ok:
        print("✅ 30KB 阈值工作正常!")
    else:
        print("❌ 30KB 阈值有问题!")

    # 清理
    session_dir = ctx.get_session_dir(test_session_id)
    if os.path.exists(session_dir):
        import shutil
        shutil.rmtree(session_dir)

    return threshold_ok

async def main():
    print("\n" + "🔧" * 30)
    print("Tool Results 命名规范测试")
    print("🔧" * 30)

    results = {}

    # 测试阈值
    results['threshold'] = await test_threshold()

    # 场景1: Bedrock 工具
    results['bedrock'] = await test_scenario_1_bedrock_tool()

    # 场景2: MCP 工具
    results['mcp'] = await test_scenario_2_mcp_tool()

    # 总结
    print("\n" + "=" * 60)
    print("📊 测试结果总结")
    print("=" * 60)

    all_passed = all(results.values())

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test_name}: {status}")

    print("\n" + ("✅ 所有测试通过!" if all_passed else "❌ 部分测试失败!"))

    return all_passed

if __name__ == "__main__":
    asyncio.run(main())
