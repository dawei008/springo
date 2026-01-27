"""
Quick check of Springo state
"""

import asyncio
from playwright.async_api import async_playwright


async def quick_check():
    """Quick check of current Springo state"""
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            page = browser.contexts[0].pages[0]

            # Check current conversation state
            state = await page.evaluate("""
                (() => {
                    const runtime = convRuntime[currentConversationId];
                    const msgs = runtime?.messages || [];
                    return {
                        isStreaming: runtime?.isStreaming || false,
                        msgCount: msgs.length,
                        lastMsg: msgs[msgs.length - 1],
                        convId: currentConversationId
                    };
                })()
            """)

            print(f"Conversation ID: {state['convId']}")
            print(f"Is Streaming: {state['isStreaming']}")
            print(f"Message Count: {state['msgCount']}")

            if state['lastMsg']:
                role = state['lastMsg'].get('role', 'unknown')
                content = state['lastMsg'].get('content', '')
                if isinstance(content, str):
                    print(f"Last Message ({role}): {content[:200]}...")
                elif isinstance(content, list):
                    print(f"Last Message ({role}): [Array with {len(content)} blocks]")
                    for block in content[:3]:
                        if isinstance(block, dict):
                            print(f"  - {block.get('type', 'unknown')}")

            # Check for errors in console
            console_errors = await page.evaluate("""
                (() => {
                    return window._consoleErrors || [];
                })()
            """)
            if console_errors:
                print(f"\nConsole Errors: {console_errors}")

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(quick_check())
