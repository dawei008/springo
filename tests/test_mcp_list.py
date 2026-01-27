#!/usr/bin/env python3
"""Test MCP servers list in Settings UI"""

import asyncio
from playwright.async_api import async_playwright


async def test_mcp_list():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        await page.reload()
        await asyncio.sleep(2)
        await page.wait_for_selector("#message-input", timeout=10000)

        # Open Settings
        modal = page.locator("#settings-modal")
        if "active" not in (await modal.get_attribute("class") or ""):
            await page.locator(".settings-btn").click()
            await asyncio.sleep(1)

        # Wait for MCP list to load
        await asyncio.sleep(2)

        # Get MCP servers list content
        mcp_list = page.locator("#mcp-servers-list")
        mcp_html = await mcp_list.inner_html()
        print("=== MCP Servers List HTML ===")
        print(mcp_html[:2000])

        # Check for web-search
        if "web-search" in mcp_html:
            print("\n✓ web-search found in MCP list")
        else:
            print("\n✗ web-search NOT found in MCP list")

        # List all server names found
        items = await mcp_list.locator(".item-name").all_text_contents()
        print(f"\n=== Server names in UI ===")
        for item in items:
            print(f"  - {item}")

        # Take screenshot
        await page.screenshot(path="tests/mcp_list.png")
        print("\n✓ Screenshot saved to tests/mcp_list.png")


if __name__ == "__main__":
    asyncio.run(test_mcp_list())
