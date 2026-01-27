"""Test add folder button - click test with timeout"""
import asyncio
from playwright.async_api import async_playwright

async def test_add_folder():
    async with async_playwright() as p:
        print("Connecting to Electron app...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Collect all console messages
        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))

        print("\n=== Testing button click ===")

        # Add a test wrapper to track if the function is called
        await page.evaluate("""() => {
            // Wrap addWorkingFolder to log when it's called
            const original = window.addWorkingFolder;
            window.addWorkingFolderCalled = false;
            window.addWorkingFolder = async function() {
                console.log('>>> addWorkingFolder was called! <<<');
                window.addWorkingFolderCalled = true;
                // Don't actually call the original (would show dialog)
                // return original.apply(this, arguments);
                return;  // Just return without doing anything
            };
        }""")

        # Click the button
        add_btn = page.locator('.add-folder-btn')
        print("Clicking button...")
        await add_btn.click()

        # Wait a moment
        await asyncio.sleep(0.5)

        # Check if function was called
        was_called = await page.evaluate("window.addWorkingFolderCalled")
        print(f"addWorkingFolder was called: {was_called}")

        # Print console messages
        if console_messages:
            print("\nConsole messages:")
            for msg in console_messages:
                print(f"  {msg}")

        # Restore original function
        await page.evaluate("""() => {
            // Just reload to restore
        }""")

        # Now test clicking the SVG inside the button
        print("\n=== Testing SVG click ===")
        await page.reload()
        await asyncio.sleep(1)

        # Re-add wrapper
        await page.evaluate("""() => {
            const original = window.addWorkingFolder;
            window.addWorkingFolderCalled = false;
            window.addWorkingFolder = async function() {
                console.log('>>> addWorkingFolder was called! <<<');
                window.addWorkingFolderCalled = true;
                return;
            };
        }""")

        # Click the SVG inside the button
        svg = page.locator('.add-folder-btn svg')
        print("Clicking SVG...")
        await svg.click()

        await asyncio.sleep(0.5)

        was_called = await page.evaluate("window.addWorkingFolderCalled")
        print(f"addWorkingFolder was called (SVG click): {was_called}")

if __name__ == "__main__":
    asyncio.run(test_add_folder())
