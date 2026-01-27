"""Test real button click - expect dialog to appear"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        console_msgs = []
        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))

        # Get initial folders
        before = await page.evaluate('JSON.parse(localStorage.getItem("workingFolders") || "[]")')
        print(f"Folders before: {before}")

        # Click the button
        print("\nClicking add folder button...")
        print("A file dialog should appear. Please select a folder or press Cancel.")

        btn = page.locator(".add-folder-btn")
        await btn.click()

        print("Button clicked! Waiting for dialog interaction...")
        print("(The dialog should be visible now. Select a folder or Cancel)")

        # Wait for user to interact with dialog (up to 30 seconds)
        await asyncio.sleep(10)

        # Get folders after
        after = await page.evaluate('JSON.parse(localStorage.getItem("workingFolders") || "[]")')
        print(f"\nFolders after: {after}")
        print(f"Console messages: {console_msgs}")

        if len(after) > len(before):
            print("\n✓ SUCCESS: Folder was added!")
        else:
            print("\n✗ No new folder added (user may have cancelled)")

asyncio.run(test())
