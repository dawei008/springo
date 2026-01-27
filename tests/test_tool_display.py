#!/usr/bin/env python3
"""查看工具调用显示"""

import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 找一个有工具调用的会话
        sessions = await page.locator(".session-item").all()
        print(f"找到 {len(sessions)} 个会话")

        # 截取当前聊天内容
        await page.screenshot(path="tests/tool_display_current.png", full_page=False)
        print("截图已保存")

        # 检查工具相关元素
        tool_elements = {
            ".tool-panel": "工具面板",
            ".tool-execution-item": "工具执行项",
            ".tool-call-inline": "内联工具调用",
            ".right-sidebar": "右侧边栏"
        }

        for selector, name in tool_elements.items():
            count = await page.locator(selector).count()
            if count > 0:
                visible = await page.locator(selector).first.is_visible()
                print(f"  {name} ({selector}): {count} 个, 可见: {visible}")
            else:
                print(f"  {name} ({selector}): 0 个")


if __name__ == "__main__":
    asyncio.run(main())
