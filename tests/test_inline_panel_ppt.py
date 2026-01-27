"""
Test inline chat tool panel with PPT generation task
This is a longer task that shows multiple tool executions
"""
import asyncio
import os
import glob
from playwright.async_api import async_playwright


async def test_inline_panel_ppt():
    """Test inline panel with PPT task"""
    async with async_playwright() as p:
        print("Connecting to Electron app...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Refresh to load latest code
        print("Refreshing page...")
        await page.reload()
        await asyncio.sleep(2)

        working_dir = "/Users/awsdawei/Downloads/folder1"
        existing_pptx = set(glob.glob(f"{working_dir}/*.pptx"))
        print(f"Existing PPTX files: {len(existing_pptx)}")

        print("\n=== Sending PPT Request ===")

        await page.wait_for_selector('#message-input', state='visible', timeout=10000)
        await page.fill('#message-input', '')
        await page.fill('#message-input', '最近openai发了哪些内容，整理成一个ppt，2页')
        await page.click('#send-btn')
        print("Message sent, monitoring inline panel...")

        # Track panel and tool states
        panel_appeared = False
        panel_in_chat = False
        max_items = 0
        tools_seen = set()
        panel_collapsed = False

        for i in range(180):  # 3 minutes max
            await asyncio.sleep(1)

            state = await page.evaluate("""
                () => {
                    const panel = document.getElementById('inline-chat-tool-panel');
                    const list = panel?.querySelector('.inline-panel-list');
                    const items = list ? Array.from(list.children) : [];
                    return {
                        exists: !!panel,
                        inChatContent: !!document.querySelector('#chat-content #inline-chat-tool-panel'),
                        isCollapsed: panel?.classList.contains('collapsed'),
                        itemCount: items.length,
                        statusText: panel?.querySelector('.inline-panel-status')?.textContent,
                        toolNames: items.map(item => item.querySelector('.item-name')?.textContent)
                    };
                }
            """)

            # Track panel appearance
            if state['exists'] and state['inChatContent'] and not panel_appeared:
                panel_appeared = True
                panel_in_chat = True
                print(f"\n[{i}s] ✓ Inline panel APPEARED in chat area")

            # Track new tools
            if state['toolNames']:
                for name in state['toolNames']:
                    if name and name not in tools_seen:
                        tools_seen.add(name)
                        print(f"[{i}s] Tool: {name}")

            # Track max items
            if state['itemCount'] > max_items:
                max_items = state['itemCount']
                print(f"[{i}s] Items: {max_items}, Status: {state['statusText']}")

            # Check for collapse
            if state['isCollapsed'] and panel_appeared and not panel_collapsed:
                panel_collapsed = True
                print(f"[{i}s] ✓ Panel COLLAPSED")

            # Check for new PPT file
            current_pptx = set(glob.glob(f"{working_dir}/*.pptx"))
            new_files = current_pptx - existing_pptx
            if new_files:
                ppt_file = list(new_files)[0]
                file_size = os.path.getsize(ppt_file)
                print(f"\n[{i}s] ✓ PPT CREATED: {os.path.basename(ppt_file)} ({file_size} bytes)")

                # Wait for response to fully complete and panel to collapse
                print("Waiting for response to complete (10s)...")
                await asyncio.sleep(10)
                final_state = await page.evaluate("""
                    () => ({
                        isCollapsed: document.getElementById('inline-chat-tool-panel')?.classList.contains('collapsed')
                    })
                """)
                if final_state['isCollapsed']:
                    panel_collapsed = True
                break

            # Progress indicator
            if i % 15 == 0 and i > 0:
                print(f"[{i}s] Still working... (items: {state['itemCount']})")

        # Take screenshot
        await page.screenshot(path='inline_panel_ppt_test.png')

        print("\n=== Test Results ===")
        print(f"Panel appeared in chat: {'✓' if panel_in_chat else '✗'}")
        print(f"Max tools displayed: {max_items}")
        print(f"Tools seen: {', '.join(tools_seen)}")
        print(f"Panel collapsed: {'✓' if panel_collapsed else '✗'}")
        print("\nScreenshot saved: inline_panel_ppt_test.png")


if __name__ == "__main__":
    asyncio.run(test_inline_panel_ppt())
