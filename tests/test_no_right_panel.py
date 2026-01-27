"""Test that right sidebar tool panel is disabled, only inline panel is used"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://localhost:9222')
        page = browser.contexts[0].pages[0]

        # Hard refresh
        await page.evaluate("location.reload(true)")
        await asyncio.sleep(3)

        print("=== Test: Only inline panel, no right sidebar tool panel ===\n")

        await page.fill('#message-input', '请创建一个panel_test.txt文件内容是"test"')
        await page.click('#send-btn')
        print("Request sent...")

        # Track panel visibility during execution
        right_panel_shown = False
        inline_panel_shown = False

        for i in range(30):
            await asyncio.sleep(0.5)

            panel_state = await page.evaluate("""
                () => {
                    const rightPanel = document.getElementById('tool-panel');
                    const inlinePanel = document.getElementById('inline-chat-tool-panel');
                    return {
                        rightPanelVisible: rightPanel?.classList.contains('visible') || false,
                        inlinePanelExists: !!inlinePanel
                    };
                }
            """)

            if panel_state['rightPanelVisible']:
                right_panel_shown = True
            if panel_state['inlinePanelExists']:
                inline_panel_shown = True

            status = await page.evaluate("() => document.getElementById('status-text')?.textContent || ''")
            if 'ready' in status.lower() and i > 5:
                print(f"[{i*0.5}s] Task completed")
                break

        print(f"\n=== Results ===")
        print(f"Right sidebar panel shown: {right_panel_shown}")
        print(f"Inline panel shown: {inline_panel_shown}")

        if not right_panel_shown and inline_panel_shown:
            print(f"\n✓ SUCCESS: Only inline panel used, right sidebar disabled!")
        else:
            print(f"\n✗ FAIL:")
            if right_panel_shown:
                print("  - Right sidebar panel should NOT be shown")
            if not inline_panel_shown:
                print("  - Inline panel should be shown")

asyncio.run(test())
