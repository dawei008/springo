#!/usr/bin/env python3
"""Screenshot MCP servers section"""

import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        await page.reload()
        await asyncio.sleep(2)

        # Open Settings
        modal = page.locator("#settings-modal")
        if "active" not in (await modal.get_attribute("class") or ""):
            await page.locator(".settings-btn").click()
            await asyncio.sleep(1)

        # Scroll to MCP section
        await page.locator("#mcp-servers-list").scroll_into_view_if_needed()
        await asyncio.sleep(0.5)

        # Screenshot
        await page.screenshot(path="tests/mcp_section.png")
        print("✓ Screenshot saved to tests/mcp_section.png")


if __name__ == "__main__":
    asyncio.run(main())
