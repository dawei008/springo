"""
Test performance with built-in tools (not external MCP servers)
This gives a fair comparison of the frontend optimizations.
"""

import asyncio
import time
from playwright.async_api import async_playwright


async def test_builtin_tools():
    """Test performance with built-in tools"""
    print("=" * 60)
    print("Performance Test: 内置工具性能测试")
    print("=" * 60)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            page = browser.contexts[0].pages[0]
            print("✓ Connected to Electron app")

            # Reload to get latest code with optimizations
            await page.reload()
            await asyncio.sleep(2)

            # Create new conversation
            new_chat_btn = await page.query_selector('.new-chat-btn')
            if new_chat_btn:
                await new_chat_btn.click()
                await asyncio.sleep(1)
                print("✓ Created new conversation")

            # Test task using built-in tools (glob, read_file)
            input_box = await page.query_selector('#message-input')
            if not input_box:
                print("ERROR: Could not find message input")
                return False

            # Task: find and read Python files, summarize
            test_query = "使用 glob 工具找出 /Users/awsdawei/claude/springo 目录下的所有 .py 文件，然后读取 mcp_tools.py 的前50行，总结它的主要功能。"
            await input_box.fill(test_query)
            await asyncio.sleep(0.2)
            await page.evaluate('document.getElementById("message-input").dispatchEvent(new Event("input"))')
            await asyncio.sleep(0.2)

            print(f"\n任务: {test_query[:50]}...")
            print("-" * 60)

            start_time = time.time()
            tool_count = 0

            send_btn = await page.query_selector('#send-btn')
            if send_btn:
                await send_btn.click()
                print(f"[0.0s] 开始执行...")

                # Monitor progress for up to 3 minutes
                for i in range(180):
                    await asyncio.sleep(1)
                    elapsed = time.time() - start_time

                    # Check status
                    status = await page.evaluate("""
                        (() => {
                            const runtime = convRuntime[currentConversationId];
                            return {
                                isStreaming: runtime?.isStreaming || false,
                                msgCount: runtime?.messages?.length || 0
                            };
                        })()
                    """)

                    # Check for tool executions
                    current_tools = await page.evaluate("""
                        (() => {
                            const executions = toolExecutionsPerConv[currentConversationId] || [];
                            return executions.map(t => t.name || 'unknown');
                        })()
                    """)

                    if len(current_tools) > tool_count:
                        for t in current_tools[tool_count:]:
                            print(f"[{elapsed:.1f}s] 工具执行: {t}")
                        tool_count = len(current_tools)

                    if not status['isStreaming']:
                        total_time = time.time() - start_time
                        print(f"\n{'=' * 60}")
                        print(f"✓ 任务完成!")
                        print(f"  - 总时间: {total_time:.2f} 秒")
                        print(f"  - 工具调用: {tool_count} 次")
                        print(f"  - 消息数: {status['msgCount']}")
                        break

                    # Progress update every 30 seconds
                    if i > 0 and i % 30 == 0:
                        print(f"[{elapsed:.1f}s] 仍在处理中... (消息数: {status['msgCount']}, 工具: {tool_count})")

                    if i == 179:
                        print("WARNING: 任务超时 (>3分钟)")

            # Get final response
            response_text = await page.evaluate("""
                (() => {
                    const runtime = convRuntime[currentConversationId];
                    const msgs = runtime?.messages || [];
                    const lastMsg = msgs[msgs.length - 1];
                    if (lastMsg?.role === 'assistant') {
                        if (typeof lastMsg.content === 'string') return lastMsg.content;
                        if (Array.isArray(lastMsg.content)) {
                            return lastMsg.content.find(b => b.type === 'text')?.text || '';
                        }
                    }
                    return '';
                })()
            """)
            print(f"\n回答预览:\n{response_text[:300]}...")

            return True

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    result = asyncio.run(test_builtin_tools())
    print(f"\nTest result: {'PASSED' if result else 'FAILED'}")
