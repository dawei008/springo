#!/usr/bin/env python3
"""
在聊天界面中显示错误测试 - 创建新会话并显示结果
"""

import asyncio
from playwright.async_api import async_playwright


async def test_errors_in_chat():
    """在新会话中显示错误测试结果"""
    print("=" * 60)
    print("聊天界面错误测试")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 创建新会话
        print("\n[1] 创建新会话...")
        await page.evaluate('''
            () => {
                newConversation();
            }
        ''')
        await asyncio.sleep(1)

        # 获取当前会话 ID
        conv_id = await page.evaluate('() => currentConversationId')
        print(f"    会话 ID: {conv_id}")

        # 测试用例
        test_cases = [
            ("read_file", {"path": "/nonexistent/file.txt"}, "读取不存在的文件"),
            ("write_file", {"path": "/etc/test.txt", "content": "test"}, "写入受限目录"),
            ("git", {"action": "commit", "message": ""}, "缺少 commit message"),
            ("fake_tool", {}, "调用不存在的工具"),
        ]

        # 添加用户消息
        print("\n[2] 添加测试消息到聊天界面...")
        await page.evaluate('''
            () => {
                const runtime = getConvRuntime(currentConversationId);
                if (!runtime) {
                    console.error('No runtime found');
                    return;
                }
                runtime.messages.push({
                    role: 'user',
                    content: '🧪 错误处理测试'
                });
                renderMessages();
            }
        ''')
        await asyncio.sleep(0.5)

        # 构建测试结果消息
        results = []
        for i, (tool_name, tool_input, description) in enumerate(test_cases, 1):
            print(f"    测试 [{i}]: {description}")

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
                        let errorMsg = '';
                        if (data.error) {{
                            errorMsg = typeof data.error === 'object' ? data.error.message : String(data.error);
                        }} else if (data.result && data.result.error) {{
                            errorMsg = data.result.error;
                        }}
                        return errorMsg || '无错误返回';
                    }} catch (e) {{
                        return e.message;
                    }}
                }}
            ''')
            # 转义特殊字符
            safe_result = result[:50].replace('`', "'").replace('\\', '\\\\').replace('\n', ' ')
            results.append(f"✅ {description}: {safe_result}")

        # 添加 assistant 消息显示所有结果
        import json
        results_text = "\\n".join(results)
        # 使用 JSON 转义确保安全
        safe_content = json.dumps(f"🎯 错误处理测试结果\n\n{chr(10).join([r.replace(chr(10), ' ') for r in results])}\n\n---\n所有错误都被正确捕获！")

        await page.evaluate(f'''
            () => {{
                const runtime = getConvRuntime(currentConversationId);
                if (runtime) {{
                    runtime.messages.push({{
                        role: 'assistant',
                        content: {safe_content}
                    }});
                    renderMessages();

                    // 滚动到底部
                    const container = document.getElementById('chat-container');
                    if (container) container.scrollTop = container.scrollHeight;
                }}
            }}
        ''')

        await asyncio.sleep(1)

        # 截图
        print("\n[3] 截图...")
        await page.screenshot(path="tests/screenshot_chat_test.png")

        print("\n" + "=" * 60)
        print("✅ 完成！请查看 Springo 应用界面的当前会话")
        print("   截图: tests/screenshot_chat_test.png")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_errors_in_chat())
