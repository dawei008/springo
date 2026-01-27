"""Test add folder button functionality"""
import asyncio
from playwright.async_api import async_playwright

async def test_add_folder():
    async with async_playwright() as p:
        print("Connecting to Electron app...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Reload to get latest changes
        print("Reloading page...")
        await page.reload()
        await asyncio.sleep(2)

        # Check if the add folder button exists
        print("Looking for add folder button...")
        add_btn = page.locator('.add-folder-btn')
        count = await add_btn.count()
        print(f"Found {count} add-folder-btn elements")

        if count > 0:
            # Check button properties
            is_visible = await add_btn.is_visible()
            is_enabled = await add_btn.is_enabled()
            print(f"Button visible: {is_visible}, enabled: {is_enabled}")

            # Get button HTML
            html = await add_btn.evaluate("el => el.outerHTML")
            print(f"Button HTML: {html}")

            # Check if addWorkingFolder function exists
            func_exists = await page.evaluate("typeof addWorkingFolder === 'function'")
            print(f"addWorkingFolder function exists: {func_exists}")

            # Check if electronAPI.selectFolder exists
            api_exists = await page.evaluate("typeof window.electronAPI?.selectFolder === 'function'")
            print(f"electronAPI.selectFolder exists: {api_exists}")

            # Try to click the button and see what happens
            print("\nTrying to click the button...")

            # Listen for console messages
            console_messages = []
            page.on("console", lambda msg: console_messages.append(f"{msg.type}: {msg.text}"))

            # Listen for page errors
            page_errors = []
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            try:
                # Click the button
                await add_btn.click()
                print("Button clicked!")

                # Wait a moment for any dialog to appear
                await asyncio.sleep(1)

                # Check for any dialogs
                print("\nChecking for dialogs...")

            except Exception as e:
                print(f"Error clicking button: {e}")

            # Print any console messages
            if console_messages:
                print("\nConsole messages:")
                for msg in console_messages:
                    print(f"  {msg}")

            # Print any page errors
            if page_errors:
                print("\nPage errors:")
                for err in page_errors:
                    print(f"  {err}")

        # Also check for any JavaScript errors in the page
        print("\nChecking for JS errors...")
        errors = await page.evaluate("""() => {
            // Try calling addWorkingFolder directly and catch any errors
            try {
                // Don't actually call it, just check if it's callable
                return {
                    functionType: typeof addWorkingFolder,
                    electronAPI: typeof window.electronAPI,
                    selectFolder: typeof window.electronAPI?.selectFolder
                };
            } catch (e) {
                return { error: e.message };
            }
        }""")
        print(f"Function check: {errors}")

if __name__ == "__main__":
    asyncio.run(test_add_folder())
