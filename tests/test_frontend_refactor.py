"""
Test frontend refactoring - verify CSS and JS load correctly
"""
import asyncio
from playwright.async_api import async_playwright


async def test_frontend_refactor():
    print("=" * 60)
    print("Testing Frontend Refactoring")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Reload to get fresh CSS/JS
        print("\n1. Reloading page...")
        await page.reload()
        await asyncio.sleep(2)

        # Check if external CSS loaded
        print("\n2. Checking CSS loading...")
        css_link = await page.query_selector('link[href="styles/main.css"]')
        if css_link:
            print("   ✓ External CSS link found")
        else:
            print("   ✗ External CSS link NOT found")
            return False

        # Check if external JS loaded
        print("\n3. Checking JS loading...")
        js_script = await page.query_selector('script[src="js/app.js"]')
        if js_script:
            print("   ✓ External JS script found")
        else:
            print("   ✗ External JS script NOT found")
            return False

        # Check if CSS variables are applied (theme working)
        print("\n4. Checking CSS variables...")
        bg_color = await page.evaluate("""
            getComputedStyle(document.body).getPropertyValue('--bg-primary')
        """)
        if bg_color and bg_color.strip():
            print(f"   ✓ CSS variables working: --bg-primary = {bg_color.strip()}")
        else:
            print("   ✗ CSS variables not working")
            return False

        # Check if JavaScript functions are defined
        print("\n5. Checking JavaScript functions...")
        js_functions = await page.evaluate("""
            () => ({
                sendMessage: typeof sendMessage === 'function',
                newConversation: typeof newConversation === 'function',
                openSettings: typeof openSettings === 'function',
                toggleSidebar: typeof toggleSidebar === 'function',
                addWorkingFolder: typeof addWorkingFolder === 'function'
            })
        """)

        all_defined = True
        for func, defined in js_functions.items():
            status = "✓" if defined else "✗"
            print(f"   {status} {func}: {'defined' if defined else 'NOT defined'}")
            if not defined:
                all_defined = False

        if not all_defined:
            return False

        # Check UI elements render correctly
        print("\n6. Checking UI elements...")
        elements = {
            "Sidebar": ".sidebar",
            "Header": ".header",
            "Chat container": ".chat-container",
            "Input area": ".input-area",
            "Welcome screen": ".welcome"
        }

        for name, selector in elements.items():
            el = await page.query_selector(selector)
            visible = await el.is_visible() if el else False
            status = "✓" if visible else "✗"
            print(f"   {status} {name}")

        # Check status connection
        print("\n7. Checking backend connection...")
        status_text = await page.text_content("#status")
        if status_text and "Ready" in status_text:
            print(f"   ✓ Status: {status_text}")
        else:
            print(f"   ⚠ Status: {status_text} (may need a moment)")

        # Test theme toggle
        print("\n8. Testing theme functionality...")
        current_theme = await page.evaluate("document.body.dataset.theme")
        print(f"   Current theme: {current_theme}")

        # Take screenshot
        print("\n9. Taking screenshot...")
        await page.screenshot(path="tests/frontend_refactor_test.png")
        print("   ✓ Screenshot saved to tests/frontend_refactor_test.png")

        print("\n" + "=" * 60)
        print("Frontend Refactoring Test: PASSED")
        print("=" * 60)
        return True


if __name__ == "__main__":
    result = asyncio.run(test_frontend_refactor())
    exit(0 if result else 1)
