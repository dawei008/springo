"""Test that tool details are only in inline panel, not in chat message"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://localhost:9222')
        page = browser.contexts[0].pages[0]

        # Hard refresh
        await page.evaluate("location.reload(true)")
        await asyncio.sleep(3)

        print("=== Test: Tool details only in inline panel ===\n")

        await page.fill('#message-input', '请创建一个test_no_dup.txt文件内容是"test"')
        await page.click('#send-btn')
        print("Request sent...")

        for i in range(60):
            await asyncio.sleep(1)
            status = await page.evaluate("() => document.getElementById('status-text')?.textContent || ''")
            if 'ready' in status.lower() and i > 3:
                print(f"[{i}s] Task completed")
                break

        await asyncio.sleep(2)

        result = await page.evaluate("""
            () => {
                const messages = document.querySelectorAll('.message');
                const lastMsg = messages[messages.length - 1];
                const content = lastMsg?.querySelector('.message-content');
                const panel = document.getElementById('inline-chat-tool-panel');

                return {
                    // Chat message should NOT have tool container
                    hasToolContainerInChat: content?.innerHTML?.includes('chat-tool-container') || false,
                    // Inline panel should exist
                    panelExists: !!panel,
                    panelCollapsed: panel?.classList.contains('collapsed'),
                    // Chat should just have text
                    chatContentLength: content?.innerHTML?.length || 0,
                    chatTextPreview: content?.textContent?.substring(0, 200) || 'NO CONTENT'
                };
            }
        """)

        print(f"\n=== Results ===")
        print(f"Tool container in chat: {result['hasToolContainerInChat']}")
        print(f"Inline panel exists: {result['panelExists']}")
        print(f"Inline panel collapsed: {result['panelCollapsed']}")
        print(f"Chat content length: {result['chatContentLength']}")
        print(f"Chat text: {result['chatTextPreview']}")

        # Verify: NO tool container in chat, but inline panel exists
        if not result['hasToolContainerInChat'] and result['panelExists']:
            print(f"\n✓ SUCCESS: Tool details only in inline panel, not duplicated in chat!")
        else:
            print(f"\n✗ FAIL:")
            if result['hasToolContainerInChat']:
                print("  - Tool container should NOT be in chat message")
            if not result['panelExists']:
                print("  - Inline panel should exist")

asyncio.run(test())
