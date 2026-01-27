"""
Simple performance test - no tools, just measure response time
"""

import asyncio
import time
from playwright.async_api import async_playwright


async def test_simple():
    """Simple performance test"""
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            page = browser.contexts[0].pages[0]
            print("Connected to Electron app")

            # Reload to get latest code
            await page.reload()
            await asyncio.sleep(2)

            # Create new conversation
            new_chat_btn = await page.query_selector('.new-chat-btn')
            if new_chat_btn:
                await new_chat_btn.click()
                await asyncio.sleep(1)

            # Send a simple message
            input_box = await page.query_selector('#message-input')
            if not input_box:
                print("ERROR: Could not find message input")
                return

            queries = [
                "What is Python? One sentence only.",
                "What is JavaScript? One sentence only.",
                "What is Rust? One sentence only."
            ]

            total_time = 0
            for i, query in enumerate(queries):
                await input_box.fill(query)
                await asyncio.sleep(0.1)
                await page.evaluate('document.getElementById("message-input").dispatchEvent(new Event("input"))')
                await asyncio.sleep(0.1)

                start_time = time.time()
                send_btn = await page.query_selector('#send-btn')
                if send_btn:
                    await send_btn.click()

                    for j in range(60):
                        await asyncio.sleep(0.5)
                        is_streaming = await page.evaluate("""
                            (() => {
                                const runtime = convRuntime[currentConversationId];
                                return runtime?.isStreaming || false;
                            })()
                        """)
                        if not is_streaming:
                            break

                    elapsed = time.time() - start_time
                    total_time += elapsed
                    print(f"Query {i+1}: {elapsed:.2f}s")

            print(f"\nTotal time for {len(queries)} queries: {total_time:.2f}s")
            print(f"Average per query: {total_time/len(queries):.2f}s")

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_simple())
