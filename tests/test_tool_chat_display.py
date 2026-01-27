#!/usr/bin/env python3
"""测试工具调用在聊天中的显示"""

import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 刷新页面加载新代码
        await page.reload()
        await asyncio.sleep(2)

        print("页面已刷新，新代码已加载")
        print("\n请手动发送一条消息触发工具调用（比如：'列出当前目录的文件'）")
        print("然后查看聊天窗口中工具调用的显示效果")
        print("\n预期效果：")
        print("- 工具调用显示在聊天消息中")
        print("- 固定高度容器，内容可滚动")
        print("- 显示工具名称、输入参数、输出结果")

        # 截图当前状态
        await page.screenshot(path="tests/tool_chat_ready.png")
        print("\n截图已保存到 tests/tool_chat_ready.png")


if __name__ == "__main__":
    asyncio.run(main())
