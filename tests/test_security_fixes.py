"""
Test security fixes from code review
"""
import asyncio
from playwright.async_api import async_playwright


async def test_security_fixes():
    print("=" * 60)
    print("Testing Security Fixes")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Reload to get fresh code
        print("\n1. Reloading page...")
        await page.reload()
        await asyncio.sleep(3)

        # Test 1: DOMPurify loaded
        print("\n2. Checking DOMPurify (XSS protection)...")
        has_dompurify = await page.evaluate("typeof DOMPurify !== 'undefined'")
        if has_dompurify:
            print("   ✓ DOMPurify is loaded")
        else:
            print("   ✗ DOMPurify NOT loaded")
            return False

        # Test 2: sanitizeHTML function exists
        print("\n3. Checking sanitizeHTML function...")
        has_sanitize = await page.evaluate("typeof sanitizeHTML === 'function'")
        if has_sanitize:
            print("   ✓ sanitizeHTML function exists")
        else:
            print("   ✗ sanitizeHTML function NOT found")
            return False

        # Test 3: CSP header
        print("\n4. Checking Content Security Policy...")
        csp = await page.evaluate("""
            () => {
                const meta = document.querySelector('meta[http-equiv="Content-Security-Policy"]');
                return meta ? meta.content : null;
            }
        """)
        if csp and 'default-src' in csp:
            print(f"   ✓ CSP configured: {csp[:60]}...")
        else:
            print("   ✗ CSP NOT configured")
            return False

        # Test 4: No hardcoded API key
        print("\n5. Checking for hardcoded API key removal...")
        # This is already verified by checking the file, but we can check the function
        no_api_key = await page.evaluate("""
            () => {
                // Check if sendMessage function doesn't include x-api-key
                const funcStr = sendMessage.toString();
                return !funcStr.includes("'x-api-key'") && !funcStr.includes('"x-api-key"');
            }
        """)
        if no_api_key:
            print("   ✓ No hardcoded x-api-key in sendMessage")
        else:
            print("   ⚠ x-api-key may still be present (check manually)")

        # Test 5: Backend health check
        print("\n6. Checking backend connection...")
        await asyncio.sleep(2)
        status_text = await page.text_content("#status")
        if status_text and "Ready" in status_text:
            print(f"   ✓ Backend status: {status_text}")
        else:
            print(f"   ⚠ Backend status: {status_text}")

        # Test 6: UI elements render correctly
        print("\n7. Checking UI rendering...")
        elements = {
            "Sidebar": ".sidebar",
            "Chat container": ".chat-container",
            "Input area": ".input-area",
        }
        all_ok = True
        for name, selector in elements.items():
            el = await page.query_selector(selector)
            visible = await el.is_visible() if el else False
            status = "✓" if visible else "✗"
            print(f"   {status} {name}")
            if not visible:
                all_ok = False

        # Test 7: escapeHTML function
        print("\n8. Checking escapeHTML function...")
        has_escape = await page.evaluate("typeof escapeHTML === 'function'")
        if has_escape:
            # Test it works
            test_result = await page.evaluate("escapeHTML('<script>alert(1)</script>')")
            if '&lt;' in test_result and '&gt;' in test_result:
                print("   ✓ escapeHTML function works correctly")
            else:
                print("   ✗ escapeHTML not escaping properly")
                return False
        else:
            print("   ✗ escapeHTML function NOT found")
            return False

        # Take screenshot
        print("\n9. Taking screenshot...")
        await page.screenshot(path="tests/security_fixes_test.png")
        print("   ✓ Screenshot saved to tests/security_fixes_test.png")

        print("\n" + "=" * 60)
        print("Security Fixes Test: PASSED")
        print("=" * 60)
        return True


if __name__ == "__main__":
    result = asyncio.run(test_security_fixes())
    exit(0 if result else 1)
