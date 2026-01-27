"""Debug add folder function"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        console_msgs = []
        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))

        # Directly call addWorkingFolder with mocked selectFolder
        result = await page.evaluate("""async () => {
            // Mock selectFolder
            const orig = window.electronAPI.selectFolder;
            window.electronAPI.selectFolder = async () => {
                console.log('MOCK: selectFolder returning test folder');
                return ['/tmp/debug-test-folder'];
            };

            // Get initial folders
            const before = JSON.parse(localStorage.getItem('workingFolders') || '[]');
            console.log('Before:', JSON.stringify(before));

            // Call addWorkingFolder
            console.log('Calling addWorkingFolder...');
            try {
                await addWorkingFolder();
                console.log('addWorkingFolder completed');
            } catch (e) {
                console.error('Error:', e.message);
                return { error: e.message };
            }

            // Get final folders
            const after = JSON.parse(localStorage.getItem('workingFolders') || '[]');
            console.log('After:', JSON.stringify(after));

            // Restore
            window.electronAPI.selectFolder = orig;

            return { before, after, added: after.includes('/tmp/debug-test-folder') };
        }""")

        print(f"Result: {result}")
        print("\nConsole messages:")
        for msg in console_msgs:
            print(f"  {msg}")

        # Cleanup
        await page.evaluate("""() => {
            const f = JSON.parse(localStorage.getItem('workingFolders') || '[]');
            localStorage.setItem('workingFolders', JSON.stringify(f.filter(x => !x.includes('debug-test'))));
        }""")

asyncio.run(test())
