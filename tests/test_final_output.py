"""Test that final output with tools is displayed correctly"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://localhost:9222')
        page = browser.contexts[0].pages[0]

        # Hard refresh to load latest code
        await page.evaluate("location.reload(true)")
        await asyncio.sleep(3)

        # Simple task that uses tools
        await page.fill('#message-input', '请创建一个test_verify.txt文件，内容是"verification test"')
        await page.click('#send-btn')
        print("Request sent...")

        # Wait for completion
        for i in range(60):
            await asyncio.sleep(1)
            status = await page.evaluate("() => document.getElementById('status-text')?.textContent || ''")
            if 'ready' in status.lower() and i > 3:
                print(f"[{i}s] Status: Ready")
                break

        await asyncio.sleep(2)

        # Check final result
        result = await page.evaluate("""
            () => {
                const messages = document.querySelectorAll('.message');
                const lastMsg = messages[messages.length - 1];
                const content = lastMsg?.querySelector('.message-content');

                return {
                    totalMessages: messages.length,
                    lastMessageRole: lastMsg?.classList.contains('message-assistant') ? 'assistant' :
                                    lastMsg?.classList.contains('message-user') ? 'user' : 'unknown',
                    hasToolContainer: content?.innerHTML?.includes('chat-tool-container') || false,
                    contentLength: content?.innerHTML?.length || 0,
                    contentPreview: content?.innerHTML?.substring(0, 200) || 'NO CONTENT'
                };
            }
        """)

        print(f"\n=== Final Result ===")
        print(f"Total messages: {result['totalMessages']}")
        print(f"Last message role: {result['lastMessageRole']}")
        print(f"Has tool container: {result['hasToolContainer']}")
        print(f"Content length: {result['contentLength']}")
        print(f"Preview: {result['contentPreview'][:150]}...")

        # Verify
        if result['lastMessageRole'] == 'assistant' and result['hasToolContainer'] and result['contentLength'] > 500:
            print("\n✓ SUCCESS: Final output with tools is displayed correctly!")
        else:
            print("\n✗ FAIL: Final output is not correct")
            if result['lastMessageRole'] != 'assistant':
                print(f"  - Expected last message to be 'assistant', got '{result['lastMessageRole']}'")
            if not result['hasToolContainer']:
                print(f"  - Expected tool container in content")
            if result['contentLength'] <= 500:
                print(f"  - Expected content length > 500, got {result['contentLength']}")

asyncio.run(test())
