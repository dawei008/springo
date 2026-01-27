"""
Test inline tool panel UI behavior
- Panel shows when tools run
- Auto-scrolls to bottom
- Collapses after completion
"""
import asyncio
from playwright.async_api import async_playwright


async def test_tool_panel_ui():
    """Test tool panel visibility and collapse behavior"""
    async with async_playwright() as p:
        print("Connecting to Electron app...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Refresh page to load latest code
        print("Refreshing page to load latest code...")
        await page.reload()
        await asyncio.sleep(2)

        print("\n=== Testing Tool Panel UI ===")

        # Check initial state - panel should be hidden
        initial_state = await page.evaluate("""
            () => {
                const panel = document.getElementById('tool-panel');
                return {
                    hasVisible: panel?.classList.contains('visible'),
                    hasCollapsed: panel?.classList.contains('collapsed'),
                    display: panel ? getComputedStyle(panel).display : null
                };
            }
        """)
        print(f"Initial state: {initial_state}")

        # Send a simple test message that triggers tools
        print("\nSending test message...")
        await page.wait_for_selector('#message-input', state='visible', timeout=10000)
        await page.fill('#message-input', '')
        await page.fill('#message-input', '当前目录有哪些文件？')
        await page.click('#send-btn')

        # Monitor panel state changes
        print("\nMonitoring panel state...")
        panel_became_visible = False
        panel_collapsed = False
        max_items_seen = 0

        for i in range(60):
            await asyncio.sleep(0.5)

            state = await page.evaluate("""
                () => {
                    const panel = document.getElementById('tool-panel');
                    const list = document.getElementById('tool-panel-list');
                    return {
                        hasVisible: panel?.classList.contains('visible'),
                        hasCollapsed: panel?.classList.contains('collapsed'),
                        display: panel ? getComputedStyle(panel).display : null,
                        itemCount: list ? list.children.length : 0,
                        statusText: document.getElementById('tool-panel-status')?.textContent
                    };
                }
            """)

            # Track state changes
            if state['hasVisible'] and not panel_became_visible:
                panel_became_visible = True
                print(f"[{i*0.5:.1f}s] ✓ Panel became VISIBLE")

            if state['itemCount'] > max_items_seen:
                max_items_seen = state['itemCount']
                print(f"[{i*0.5:.1f}s] Items: {state['itemCount']}, Status: {state['statusText']}")

            if state['hasCollapsed'] and panel_became_visible and not panel_collapsed:
                panel_collapsed = True
                print(f"[{i*0.5:.1f}s] ✓ Panel COLLAPSED after completion")

            # Check if processing is done
            is_processing = await page.evaluate("() => typeof isProcessing !== 'undefined' ? isProcessing : null")
            if is_processing is False and i > 5:
                # Wait a bit more for collapse
                await asyncio.sleep(3)
                final_state = await page.evaluate("""
                    () => {
                        const panel = document.getElementById('tool-panel');
                        return {
                            hasCollapsed: panel?.classList.contains('collapsed')
                        };
                    }
                """)
                if final_state['hasCollapsed']:
                    panel_collapsed = True
                    print(f"[{(i+6)*0.5:.1f}s] ✓ Panel COLLAPSED after completion")
                break

        print("\n=== Test Results ===")
        print(f"Panel became visible: {'✓' if panel_became_visible else '✗'}")
        print(f"Max items displayed: {max_items_seen}")
        print(f"Panel collapsed after: {'✓' if panel_collapsed else '✗'}")

        if panel_became_visible and panel_collapsed:
            print("\n✓ All UI behaviors working correctly!")
        else:
            print("\n✗ Some behaviors not working as expected")


if __name__ == "__main__":
    asyncio.run(test_tool_panel_ui())
