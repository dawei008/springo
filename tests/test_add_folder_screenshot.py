"""Test add folder button with screenshot"""
import asyncio
from playwright.async_api import async_playwright

async def test_add_folder():
    async with async_playwright() as p:
        print("Connecting to Electron app...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Take screenshot before click
        print("Taking screenshot before click...")
        await page.screenshot(path="/tmp/before_click.png")

        # Get button location
        add_btn = page.locator('.add-folder-btn')
        box = await add_btn.bounding_box()
        print(f"Button bounding box: {box}")

        # Check button's computed styles
        styles = await page.evaluate("""() => {
            const btn = document.querySelector('.add-folder-btn');
            if (!btn) return { error: 'Button not found' };
            const style = window.getComputedStyle(btn);
            return {
                display: style.display,
                visibility: style.visibility,
                pointerEvents: style.pointerEvents,
                opacity: style.opacity,
                position: style.position,
                zIndex: style.zIndex
            };
        }""")
        print(f"Button computed styles: {styles}")

        # Check if there's anything overlapping the button
        overlap_check = await page.evaluate("""() => {
            const btn = document.querySelector('.add-folder-btn');
            const rect = btn.getBoundingClientRect();
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;
            const elementAtPoint = document.elementFromPoint(centerX, centerY);
            return {
                buttonRect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
                elementAtPoint: elementAtPoint ? elementAtPoint.tagName + '.' + elementAtPoint.className : null,
                isButton: elementAtPoint === btn || btn.contains(elementAtPoint)
            };
        }""")
        print(f"Element at button center: {overlap_check}")

        print("\nScreenshot saved to /tmp/before_click.png")

if __name__ == "__main__":
    asyncio.run(test_add_folder())
