"""Test add folder button - detailed debugging"""
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

        # Collect page errors
        page_errors = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        print("\n=== Testing addWorkingFolder function directly ===")

        # Try calling the function directly and catch any errors
        result = await page.evaluate("""async () => {
            try {
                console.log('Starting addWorkingFolder test...');

                // Check if electronAPI exists
                if (!window.electronAPI) {
                    return { error: 'electronAPI not found' };
                }
                console.log('electronAPI exists');

                // Check if selectFolder exists
                if (!window.electronAPI.selectFolder) {
                    return { error: 'selectFolder not found' };
                }
                console.log('selectFolder exists');

                // Try calling selectFolder directly
                console.log('Calling selectFolder...');
                const folders = await window.electronAPI.selectFolder();
                console.log('selectFolder returned:', folders);

                return { success: true, folders: folders };
            } catch (e) {
                console.error('Error:', e);
                return { error: e.message, stack: e.stack };
            }
        }""")

        print(f"Result: {result}")

        # Wait a moment for any async operations
        await asyncio.sleep(2)

        # Print console messages
        if console_messages:
            print("\nConsole messages:")
            for msg in console_messages:
                print(f"  {msg}")

        # Print page errors
        if page_errors:
            print("\nPage errors:")
            for err in page_errors:
                print(f"  {err}")

if __name__ == "__main__":
    asyncio.run(test_add_folder())
