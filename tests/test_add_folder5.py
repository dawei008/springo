"""Test add folder button - full flow test with page reload"""
import asyncio
from playwright.async_api import async_playwright

async def test_add_folder():
    async with async_playwright() as p:
        print("Connecting to Electron app...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Reload page to clear any previous mocks
        print("Reloading page to clear mocks...")
        await page.reload()
        await asyncio.sleep(2)

        # Collect all console messages
        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))

        page_errors = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        print("\n=== Testing full flow with mocked selectFolder ===")

        # Mock selectFolder to return a test folder without showing dialog
        result = await page.evaluate("""async () => {
            // Mock selectFolder to return a fake folder
            const originalSelectFolder = window.electronAPI.selectFolder;
            window.electronAPI.selectFolder = async () => {
                console.log('Mock selectFolder called - returning test folder');
                return ['/tmp/test-folder-456'];
            };

            // Get initial state
            const initialFolders = JSON.parse(localStorage.getItem('workingFolders') || '[]');
            console.log('Initial folders:', JSON.stringify(initialFolders));

            try {
                // Call addWorkingFolder
                console.log('Calling addWorkingFolder...');
                await addWorkingFolder();
                console.log('addWorkingFolder completed');

                // Check if folder was added
                const newFolders = JSON.parse(localStorage.getItem('workingFolders') || '[]');
                console.log('New folders:', JSON.stringify(newFolders));

                // Restore original
                window.electronAPI.selectFolder = originalSelectFolder;

                return {
                    success: true,
                    initialFolders: initialFolders,
                    newFolders: newFolders,
                    folderAdded: newFolders.includes('/tmp/test-folder-456')
                };
            } catch (e) {
                console.error('Error in addWorkingFolder:', e);
                window.electronAPI.selectFolder = originalSelectFolder;
                return { error: e.message, stack: e.stack };
            }
        }""")

        print(f"Result: {result}")

        # Print console messages
        if console_messages:
            print("\nConsole messages:")
            for msg in console_messages:
                print(f"  {msg}")

        if page_errors:
            print("\nPage errors:")
            for err in page_errors:
                print(f"  {err}")

        # Clean up - remove test folder from localStorage
        await page.evaluate("""() => {
            const folders = JSON.parse(localStorage.getItem('workingFolders') || '[]');
            const filtered = folders.filter(f => !f.startsWith('/tmp/test-folder'));
            localStorage.setItem('workingFolders', JSON.stringify(filtered));
        }""")

        print("\nTest folder cleaned up from localStorage")

if __name__ == "__main__":
    asyncio.run(test_add_folder())
