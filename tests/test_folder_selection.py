#!/usr/bin/env python3
"""Test folder selection highlighting"""

import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        await page.reload()
        await asyncio.sleep(2)

        # Screenshot before clicking
        await page.screenshot(path="tests/folder_before.png")
        print("✓ Screenshot before click saved")

        # Find folder2 and click it
        folder2 = page.locator(".folder-item:has-text('folder2')")
        await folder2.click()
        await asyncio.sleep(1)

        # Screenshot after clicking folder2
        await page.screenshot(path="tests/folder_after.png")
        print("✓ Screenshot after clicking folder2 saved")

        # Check classes
        folder1_classes = await page.locator(".folder-item:has-text('folder1')").get_attribute("class")
        folder2_classes = await page.locator(".folder-item:has-text('folder2')").get_attribute("class")

        print(f"\nfolder1 classes: {folder1_classes}")
        print(f"folder2 classes: {folder2_classes}")


if __name__ == "__main__":
    asyncio.run(main())
