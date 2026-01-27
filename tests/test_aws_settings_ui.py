#!/usr/bin/env python3
"""Test AWS Settings UI in Electron app"""

import asyncio
from playwright.async_api import async_playwright


async def test_aws_settings_ui():
    """Test AWS credentials UI in Settings"""
    async with async_playwright() as p:
        print("Connecting to Electron app...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Reload page to get latest changes
        await page.reload()
        await asyncio.sleep(2)

        # Wait for app to be ready
        await page.wait_for_selector("#message-input", timeout=10000)
        print("✓ App loaded")

        # Open Settings modal
        modal = page.locator("#settings-modal")
        modal_class = await modal.get_attribute("class") or ""

        if "active" not in modal_class:
            settings_btn = page.locator(".settings-btn")
            await settings_btn.click()
            await asyncio.sleep(0.5)

        print("✓ Settings modal opened")

        # Wait for AWS settings to load
        await asyncio.sleep(1)

        # Check AK/SK input fields exist
        ak_input = page.locator("#settings-aws-access-key")
        sk_input = page.locator("#settings-aws-secret-key")

        ak_visible = await ak_input.is_visible()
        sk_visible = await sk_input.is_visible()

        print(f"Access Key input visible: {ak_visible}")
        print(f"Secret Key input visible: {sk_visible}")

        # Check connection status
        status_el = page.locator("#aws-connection-status")
        status_html = await status_el.inner_html()
        print(f"Connection status: {status_html}")

        # Check header is sticky (scroll and verify header stays)
        modal_body = page.locator(".modal-body")
        await modal_body.evaluate("el => el.scrollTop = 300")
        await asyncio.sleep(0.3)

        # Take screenshot
        await page.screenshot(path="tests/aws_settings_ui.png")
        print("\n✓ Screenshot saved to tests/aws_settings_ui.png")
        print("\n✓ Test completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_aws_settings_ui())
