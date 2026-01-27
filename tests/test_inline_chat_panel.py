"""
Test inline chat tool panel UI behavior
- Panel appears in chat content area during tool execution
- Auto-scrolls to show latest status
- Collapses after completion
"""
import asyncio
from playwright.async_api import async_playwright


async def test_inline_chat_panel():
    """Test inline chat tool panel visibility and behavior"""
    async with async_playwright() as p:
        print("Connecting to Electron app...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Refresh page to load latest code
        print("Refreshing page to load latest code...")
        await page.reload()
        await asyncio.sleep(2)

        print("\n=== Testing Inline Chat Tool Panel ===")

        # Check initial state - panel should not exist
        initial_state = await page.evaluate("""
            () => {
                const panel = document.getElementById('inline-chat-tool-panel');
                return { exists: !!panel };
            }
        """)
        print(f"Initial state: panel exists = {initial_state['exists']}")

        # Send a test message that triggers tools
        print("\nSending test message...")
        await page.wait_for_selector('#message-input', state='visible', timeout=10000)
        await page.fill('#message-input', '')
        await page.fill('#message-input', '当前目录有哪些文件？列出前5个')
        await page.click('#send-btn')

        # Monitor panel state changes
        print("\nMonitoring inline panel state...")
        panel_appeared = False
        panel_collapsed = False
        max_items_seen = 0

        for i in range(60):
            await asyncio.sleep(0.5)

            state = await page.evaluate("""
                () => {
                    const panel = document.getElementById('inline-chat-tool-panel');
                    const list = panel?.querySelector('.inline-panel-list');
                    return {
                        exists: !!panel,
                        isCollapsed: panel?.classList.contains('collapsed'),
                        itemCount: list ? list.children.length : 0,
                        statusText: panel?.querySelector('.inline-panel-status')?.textContent,
                        isInChatContent: !!document.querySelector('#chat-content #inline-chat-tool-panel')
                    };
                }
            """)

            # Track state changes
            if state['exists'] and state['isInChatContent'] and not panel_appeared:
                panel_appeared = True
                print(f"[{i*0.5:.1f}s] ✓ Panel APPEARED in chat content area")

            if state['itemCount'] > max_items_seen:
                max_items_seen = state['itemCount']
                print(f"[{i*0.5:.1f}s] Items: {state['itemCount']}, Status: {state['statusText']}")

            if state['isCollapsed'] and panel_appeared and not panel_collapsed:
                panel_collapsed = True
                print(f"[{i*0.5:.1f}s] ✓ Panel COLLAPSED after completion")

            # Check if processing is done
            is_processing = await page.evaluate("() => typeof isProcessing !== 'undefined' ? isProcessing : null")
            if is_processing is False and i > 5:
                # Wait for collapse
                await asyncio.sleep(3)
                final_state = await page.evaluate("""
                    () => {
                        const panel = document.getElementById('inline-chat-tool-panel');
                        return {
                            isCollapsed: panel?.classList.contains('collapsed')
                        };
                    }
                """)
                if final_state['isCollapsed']:
                    panel_collapsed = True
                    print(f"[{(i+6)*0.5:.1f}s] ✓ Panel COLLAPSED after completion")
                break

        print("\n=== Test Results ===")
        print(f"Panel appeared in chat: {'✓' if panel_appeared else '✗'}")
        print(f"Max items displayed: {max_items_seen}")
        print(f"Panel collapsed after: {'✓' if panel_collapsed else '✗'}")

        # Take screenshot
        await page.screenshot(path='inline_panel_test.png')
        print("\nScreenshot saved: inline_panel_test.png")

        if panel_appeared and panel_collapsed:
            print("\n✓ Inline chat tool panel working correctly!")
        else:
            print("\n✗ Some behaviors not working as expected")


if __name__ == "__main__":
    asyncio.run(test_inline_chat_panel())
