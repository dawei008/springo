"""Quick non-blocking test"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Mock selectFolder to not show dialog
        await page.evaluate("""() => {
            window.electronAPI.selectFolder = async () => {
                console.log('Mock: selectFolder called');
                return ['/tmp/test-folder'];
            };
        }""")

        # Click button
        await page.locator('.add-folder-btn').click()
        await asyncio.sleep(1)

        # Check if folder was added
        folders = await page.evaluate("JSON.parse(localStorage.getItem('workingFolders') || '[]')")
        print(f"Folders after click: {folders}")
        print(f"Test folder added: {'/tmp/test-folder' in folders}")

        # Cleanup
        await page.evaluate("""() => {
            const f = JSON.parse(localStorage.getItem('workingFolders') || '[]');
            localStorage.setItem('workingFolders', JSON.stringify(f.filter(x => x !== '/tmp/test-folder')));
        }""")

asyncio.run(test())
