#!/usr/bin/env python3
"""
可视化错误测试 - 在 Springo 界面上显示测试结果
"""

import asyncio
from playwright.async_api import async_playwright


async def test_errors_visible():
    """在 Springo 界面上显示错误测试结果"""
    print("=" * 60)
    print("可视化错误测试 - 结果将显示在 Springo 界面上")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 测试用例
        test_cases = [
            ("read_file", {"path": "/nonexistent/file.txt"}, "读取不存在的文件"),
            ("list_directory", {"path": "/nonexistent/dir"}, "列出不存在的目录"),
            ("read_file", {"path": "/tmp"}, "读取目录而非文件"),
            ("write_file", {"path": "/etc/test.txt", "content": "test"}, "写入受限目录"),
            ("git", {"action": "commit", "message": ""}, "缺少 commit message"),
            ("fake_tool", {}, "调用不存在的工具"),
        ]

        # 在界面上添加测试消息
        await page.evaluate('''
            () => {
                // 获取当前会话
                const runtime = getConvRuntime(currentConversationId);
                if (!runtime) return;

                // 添加测试开始消息
                runtime.messages.push({
                    role: 'user',
                    content: '🧪 开始错误处理测试...'
                });
                renderMessages();
            }
        ''')

        await asyncio.sleep(0.5)

        # 执行每个测试并在界面上显示结果
        for i, (tool_name, tool_input, description) in enumerate(test_cases, 1):
            print(f"[{i}] 测试: {description}")

            # 在 Electron 内调用工具并获取结果
            result = await page.evaluate(f'''
                async () => {{
                    try {{
                        const response = await fetch(BASE_URL + '/v1/tools/execute', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{
                                name: '{tool_name}',
                                input: {str(tool_input).replace("'", '"')}
                            }})
                        }});
                        const data = await response.json();

                        // 提取错误信息
                        let errorMsg = '';
                        if (data.error) {{
                            errorMsg = typeof data.error === 'object' ? data.error.message : data.error;
                        }} else if (data.result && data.result.error) {{
                            errorMsg = data.result.error;
                        }}

                        // 在聊天界面显示结果
                        const runtime = getConvRuntime(currentConversationId);
                        if (runtime) {{
                            const testResult = errorMsg
                                ? `✅ [{i}] {description}\\n\\n错误信息: ${{errorMsg}}`
                                : `❌ [{i}] {description}\\n\\n未返回预期错误`;

                            runtime.messages.push({{
                                role: 'assistant',
                                content: testResult
                            }});
                            renderMessages();
                        }}

                        return {{ success: !!errorMsg, error: errorMsg }};
                    }} catch (e) {{
                        return {{ success: false, error: e.message }};
                    }}
                }}
            ''')

            if result['success']:
                print(f"    ✅ 错误: {result['error'][:50]}...")
            else:
                print(f"    ❌ 失败: {result.get('error', 'unknown')}")

            await asyncio.sleep(0.3)

        # 添加测试完成消息
        await page.evaluate('''
            () => {
                const runtime = getConvRuntime(currentConversationId);
                if (runtime) {
                    runtime.messages.push({
                        role: 'assistant',
                        content: '🎉 错误处理测试完成！\\n\\n以上测试验证了 Springo 客户端的错误处理功能。'
                    });
                    renderMessages();
                }
            }
        ''')

        # 滚动到底部
        await page.evaluate('''
            () => {
                const container = document.getElementById('chat-container');
                if (container) container.scrollTop = container.scrollHeight;
            }
        ''')

        # 截图
        await asyncio.sleep(1)
        await page.screenshot(path="tests/screenshot_visible_test.png", full_page=True)

        print("\n" + "=" * 60)
        print("✅ 测试完成！请查看 Springo 应用界面")
        print("   截图: tests/screenshot_visible_test.png")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_errors_visible())
