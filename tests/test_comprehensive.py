"""Comprehensive test for inline tool panel and final output"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://localhost:9222')
        page = browser.contexts[0].pages[0]

        # Hard refresh
        await page.evaluate("location.reload(true)")
        await asyncio.sleep(3)

        print("=== Test: Tool execution with final output ===\n")

        # Task that requires tools
        await page.fill('#message-input', '请创建一个hello.txt文件内容是"hello world"，然后读取它的内容告诉我')
        await page.click('#send-btn')
        print("Request sent...")

        # Track states during execution
        panel_appeared = False
        panel_collapsed = False

        for i in range(60):
            await asyncio.sleep(1)

            # Check inline panel
            panel_state = await page.evaluate("""
                () => {
                    const panel = document.getElementById('inline-chat-tool-panel');
                    return {
                        exists: !!panel,
                        collapsed: panel?.classList.contains('collapsed') || false
                    };
                }
            """)

            if panel_state['exists'] and not panel_appeared:
                panel_appeared = True
                print(f"[{i}s] Inline panel appeared")

            if panel_state['exists'] and panel_state['collapsed'] and not panel_collapsed:
                panel_collapsed = True
                print(f"[{i}s] Inline panel collapsed")

            status = await page.evaluate("() => document.getElementById('status-text')?.textContent || ''")
            if 'ready' in status.lower() and i > 5:
                print(f"[{i}s] Task completed")
                break

        await asyncio.sleep(2)

        # Final verification
        result = await page.evaluate("""
            () => {
                const messages = document.querySelectorAll('.message');
                const lastMsg = messages[messages.length - 1];
                const content = lastMsg?.querySelector('.message-content');
                const panel = document.getElementById('inline-chat-tool-panel');

                return {
                    totalMessages: messages.length,
                    isAssistantLast: lastMsg?.classList.contains('message-assistant'),
                    hasToolContainer: content?.innerHTML?.includes('chat-tool-container'),
                    hasText: content?.textContent?.length > 50,
                    panelExists: !!panel,
                    panelCollapsed: panel?.classList.contains('collapsed'),
                    contentLength: content?.innerHTML?.length || 0
                };
            }
        """)

        print(f"\n=== Results ===")
        print(f"Total messages: {result['totalMessages']}")
        print(f"Last message is assistant: {result['isAssistantLast']}")
        print(f"Has tool container: {result['hasToolContainer']}")
        print(f"Has text response: {result['hasText']}")
        print(f"Panel exists: {result['panelExists']}")
        print(f"Panel collapsed: {result['panelCollapsed']}")
        print(f"Content length: {result['contentLength']}")

        # Verify all conditions
        all_passed = all([
            result['isAssistantLast'],
            result['hasToolContainer'],
            result['hasText'],
            result['contentLength'] > 500,
            panel_appeared,
            panel_collapsed
        ])

        if all_passed:
            print(f"\n✓ ALL TESTS PASSED")
        else:
            print(f"\n✗ SOME TESTS FAILED")
            if not result['isAssistantLast']: print("  - Last message should be assistant")
            if not result['hasToolContainer']: print("  - Should have tool container")
            if not result['hasText']: print("  - Should have text response")
            if result['contentLength'] <= 500: print(f"  - Content length {result['contentLength']} should be > 500")
            if not panel_appeared: print("  - Inline panel should appear")
            if not panel_collapsed: print("  - Inline panel should collapse")

asyncio.run(test())
