#!/usr/bin/env python3
"""Test Settings sticky header"""

import asyncio
from playwright.async_api import async_playwright


async def test_sticky_header():
    """Test that Settings header stays fixed when scrolling"""
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        await page.reload()
        await asyncio.sleep(2)
        await page.wait_for_selector("#message-input", timeout=10000)

        # Open Settings modal
        modal = page.locator("#settings-modal")
        modal_class = await modal.get_attribute("class") or ""
        if "active" not in modal_class:
            await page.locator(".settings-btn").click()
            await asyncio.sleep(0.5)

        # Screenshot before scroll
        await page.screenshot(path="tests/settings_before_scroll.png")
        print("✓ Screenshot before scroll saved")

        # Scroll down the modal content
        modal_content = page.locator("#settings-modal .modal")
        await modal_content.evaluate("el => el.scrollTop = 400")
        await asyncio.sleep(0.3)

        # Screenshot after scroll
        await page.screenshot(path="tests/settings_after_scroll.png")
        print("✓ Screenshot after scroll saved")
        print("\n✓ Check that 'Settings' header is visible in both screenshots")


if __name__ == "__main__":
    asyncio.run(test_sticky_header())
