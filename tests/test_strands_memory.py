"""
Test the same task as before optimization:
"解释一下aws strands如何做长期记忆的"

Before optimization: ~3 minutes
Let's measure after optimization.
"""

import asyncio
import time
from playwright.async_api import async_playwright


async def test_strands_memory():
    """Test the AWS Strands long-term memory task"""
    print("=" * 60)
    print("Performance Test: AWS Strands 长期记忆查询")
    print("优化前: ~3 分钟 (180秒)")
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

            # Send the same task as before
            input_box = await page.query_selector('#message-input')
            if not input_box:
                print("ERROR: Could not find message input")
                return False

            test_query = "解释一下aws strands如何做长期记忆的"
            await input_box.fill(test_query)
            await asyncio.sleep(0.2)
            await page.evaluate('document.getElementById("message-input").dispatchEvent(new Event("input"))')
            await asyncio.sleep(0.2)

            print(f"\n任务: {test_query}")
            print("-" * 60)

            start_time = time.time()
            tool_count = 0
            last_status = ""

            send_btn = await page.query_selector('#send-btn')
            if send_btn:
                await send_btn.click()
                print(f"[0.0s] 开始执行...")

                # Monitor progress for up to 5 minutes
                for i in range(300):
                    await asyncio.sleep(1)
                    elapsed = time.time() - start_time

                    # Check status
                    status = await page.evaluate("""
                        (() => {
                            const runtime = convRuntime[currentConversationId];
                            const statusEl = document.getElementById('status-text');
                            return {
                                isStreaming: runtime?.isStreaming || false,
                                msgCount: runtime?.messages?.length || 0,
                                statusText: statusEl?.textContent || ''
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

                    # Print status changes
                    if status['statusText'] != last_status:
                        last_status = status['statusText']
                        if last_status:
                            print(f"[{elapsed:.1f}s] 状态: {last_status}")

                    if not status['isStreaming']:
                        total_time = time.time() - start_time
                        print(f"\n{'=' * 60}")
                        print(f"✓ 任务完成!")
                        print(f"  - 总时间: {total_time:.2f} 秒")
                        print(f"  - 工具调用: {tool_count} 次")
                        print(f"  - 消息数: {status['msgCount']}")
                        print(f"\n对比:")
                        print(f"  - 优化前: ~180 秒")
                        print(f"  - 优化后: {total_time:.2f} 秒")
                        if total_time < 180:
                            improvement = ((180 - total_time) / 180) * 100
                            print(f"  - 提升: {improvement:.1f}%")
                        break

                    # Progress update every 30 seconds
                    if i > 0 and i % 30 == 0:
                        print(f"[{elapsed:.1f}s] 仍在处理中... (消息数: {status['msgCount']}, 工具: {tool_count})")

                    if i == 299:
                        print("WARNING: 任务超时 (>5分钟)")

            # Get final response (first 500 chars)
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
            print(f"\n回答预览:\n{response_text[:500]}...")

            return True

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    result = asyncio.run(test_strands_memory())
    print(f"\nTest result: {'PASSED' if result else 'FAILED'}")
