"""Test if dialog appears when clicking add folder button"""
import asyncio
from playwright.async_api import async_playwright

async def test_dialog():
    async with async_playwright() as p:
        print("Connecting to Electron app...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))

        # Add logging to addWorkingFolder
        await page.evaluate("""() => {
            const original = window.addWorkingFolder;
            window.addWorkingFolder = async function() {
                console.log('[TEST] addWorkingFolder started');
                try {
                    const result = await original.apply(this, arguments);
                    console.log('[TEST] addWorkingFolder completed successfully');
                    return result;
                } catch (e) {
                    console.error('[TEST] addWorkingFolder error:', e.message);
                    throw e;
                }
            };
        }""")

        # Click the button
        print("Clicking add folder button...")
        add_btn = page.locator('.add-folder-btn')
        await add_btn.click()

        # Wait a moment to see if function starts
        await asyncio.sleep(0.5)

        print("\nConsole messages so far:")
        for msg in console_messages:
            print(f"  {msg}")

        print("\nThe dialog should be appearing now.")
        print("If you see '[TEST] addWorkingFolder started' but no dialog, check if it's behind other windows.")
        print("\nWaiting 5 seconds for user interaction with dialog...")
        await asyncio.sleep(5)

        print("\nFinal console messages:")
        for msg in console_messages:
            print(f"  {msg}")

if __name__ == "__main__":
    asyncio.run(test_dialog())
