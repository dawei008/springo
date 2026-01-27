"""
Test agentic task performance in Springo
Measures time for a task that requires tool execution
"""

import asyncio
import time
from playwright.async_api import async_playwright


async def test_agentic_performance():
    """Test performance for an agentic task that uses tools"""
    print("=" * 60)
    print("Testing Springo Agentic Task Performance")
    print("=" * 60)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            page = browser.contexts[0].pages[0]
            print("✓ Connected to Electron app")

            # Reload to get latest code
            await page.reload()
            await asyncio.sleep(2)

            # Create new conversation
            new_chat_btn = await page.query_selector('.new-chat-btn')
            if new_chat_btn:
                await new_chat_btn.click()
                await asyncio.sleep(1)
                print("✓ Created new conversation")

            # Send a task that requires file reading (tool execution)
            input_box = await page.query_selector('#message-input')
            if not input_box:
                print("ERROR: Could not find message input")
                return False

            # Simple agentic task: read a file and summarize
            test_query = "Read the file /Users/awsdawei/claude/springo/README.md and tell me what Springo is in one sentence."
            await input_box.fill(test_query)
            await asyncio.sleep(0.2)
            await page.evaluate('document.getElementById("message-input").dispatchEvent(new Event("input"))')
            await asyncio.sleep(0.2)

            print(f"\nTask: {test_query}")
            print("-" * 60)

            start_time = time.time()
            tool_count = 0
            last_tool_update = 0

            send_btn = await page.query_selector('#send-btn')
            if send_btn:
                await send_btn.click()
                print(f"[{0:.1f}s] Started task...")

                # Monitor progress
                for i in range(120):  # Max 2 minutes
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
                            return executions.length;
                        })()
                    """)

                    if current_tools > tool_count:
                        tool_count = current_tools
                        print(f"[{elapsed:.1f}s] Tool #{tool_count} executed")

                    if not status['isStreaming']:
                        total_time = time.time() - start_time
                        print(f"\n{'=' * 60}")
                        print(f"✓ Task completed in {total_time:.2f} seconds")
                        print(f"  - Tools executed: {tool_count}")
                        print(f"  - Messages: {status['msgCount']}")
                        break

                    if i == 119:
                        print("WARNING: Task took too long (>2 minutes)")

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
            print(f"\nResponse:\n{response_text[:500]}...")

            return True

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    result = asyncio.run(test_agentic_performance())
    print(f"\nTest result: {'PASSED' if result else 'FAILED'}")
