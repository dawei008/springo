"""
Accurate timing test - checks every 0.5 seconds
"""

import asyncio
import time
from playwright.async_api import async_playwright


async def test_accurate():
    """Accurate timing test with fast polling"""
    print("=" * 60)
    print("准确计时测试 (每 0.5 秒检查)")
    print("=" * 60)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            page = browser.contexts[0].pages[0]
            print("✓ Connected")

            # Reload and create new conversation
            await page.reload()
            await asyncio.sleep(2)
            new_chat_btn = await page.query_selector('.new-chat-btn')
            if new_chat_btn:
                await new_chat_btn.click()
                await asyncio.sleep(1)

            input_box = await page.query_selector('#message-input')
            if not input_box:
                print("ERROR: No input box")
                return

            # Simple task with built-in tool
            test_query = "读取 /Users/awsdawei/claude/springo/README.md 文件并用一句话总结 Springo 是什么"
            await input_box.fill(test_query)
            await asyncio.sleep(0.1)
            await page.evaluate('document.getElementById("message-input").dispatchEvent(new Event("input"))')
            await asyncio.sleep(0.1)

            print(f"\n任务: {test_query}")
            print("-" * 60)

            start_time = time.time()
            tool_count = 0
            last_msg_count = 0

            send_btn = await page.query_selector('#send-btn')
            await send_btn.click()
            print(f"[0.0s] 开始...")

            # Check every 0.5 seconds
            for i in range(240):  # 2 minutes max
                await asyncio.sleep(0.5)
                elapsed = time.time() - start_time

                status = await page.evaluate("""
                    (() => {
                        const runtime = convRuntime[currentConversationId];
                        const executions = toolExecutionsPerConv[currentConversationId] || [];
                        return {
                            isStreaming: runtime?.isStreaming || false,
                            msgCount: runtime?.messages?.length || 0,
                            tools: executions.map(t => t.name || 'unknown')
                        };
                    })()
                """)

                # Report tool executions
                if len(status['tools']) > tool_count:
                    for t in status['tools'][tool_count:]:
                        print(f"[{elapsed:.1f}s] 工具: {t}")
                    tool_count = len(status['tools'])

                # Report message changes
                if status['msgCount'] > last_msg_count:
                    print(f"[{elapsed:.1f}s] 消息数: {last_msg_count} -> {status['msgCount']}")
                    last_msg_count = status['msgCount']

                if not status['isStreaming']:
                    total_time = time.time() - start_time
                    print(f"\n{'=' * 60}")
                    print(f"✓ 完成! 总时间: {total_time:.2f} 秒")
                    print(f"  - 工具调用: {tool_count}")
                    print(f"  - 消息数: {status['msgCount']}")

                    # Get response
                    resp = await page.evaluate("""
                        (() => {
                            const runtime = convRuntime[currentConversationId];
                            const msgs = runtime?.messages || [];
                            const lastMsg = msgs[msgs.length - 1];
                            if (lastMsg?.role === 'assistant' && typeof lastMsg.content === 'string') {
                                return lastMsg.content;
                            }
                            return '';
                        })()
                    """)
                    print(f"\n回答: {resp[:200]}...")
                    return

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_accurate())
