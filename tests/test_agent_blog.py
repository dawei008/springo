"""
测试: anthropic最新的agent博客问题
目的: 找出为什么回答的是2024年的内容
"""
import asyncio
from playwright.async_api import async_playwright

async def test_agent_blog_question():
    async with async_playwright() as p:
        print("连接到 Electron 应用...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 刷新页面确保最新状态
        await page.reload()
        await asyncio.sleep(2)

        # 清空之前的对话（如果有清空按钮的话）
        clear_btn = page.locator('button:has-text("Clear")')
        if await clear_btn.count() > 0:
            await clear_btn.click()
            await asyncio.sleep(1)

        # 输入测试问题
        test_question = "anthropic最新的agent博客讲了什么"
        print(f"\n发送测试问题: {test_question}")

        # 找到输入框并输入 (ID: message-input)
        input_box = page.locator('#message-input')
        await input_box.fill(test_question)
        await asyncio.sleep(0.5)

        # 点击发送按钮 (ID: send-btn)
        send_btn = page.locator('#send-btn')
        await send_btn.click()

        print("等待响应...")

        # 等待响应完成（监控消息容器变化）
        await asyncio.sleep(3)

        # 持续等待直到响应完成
        max_wait = 60  # 最多等待60秒
        waited = 0
        last_content = ""
        stable_count = 0

        while waited < max_wait:
            await asyncio.sleep(2)
            waited += 2

            # 获取最新的消息内容
            messages = await page.locator('.message-content, .assistant-message, [class*="message"]').all()
            if messages:
                current_content = await messages[-1].text_content()
                if current_content == last_content:
                    stable_count += 1
                    if stable_count >= 2:  # 内容稳定2次则认为完成
                        break
                else:
                    stable_count = 0
                    last_content = current_content

            print(f"  等待中... {waited}s")

        # 获取完整响应
        print("\n" + "="*60)
        print("响应内容:")
        print("="*60)

        # 尝试获取所有消息
        all_messages = await page.evaluate("""
            () => {
                const messages = document.querySelectorAll('.message-content, .assistant-message, [class*="message"]');
                return Array.from(messages).map(m => m.textContent).join('\\n---\\n');
            }
        """)
        print(all_messages[-3000:] if len(all_messages) > 3000 else all_messages)

        # 检查是否有工具调用的迹象
        print("\n" + "="*60)
        print("检查工具调用:")
        print("="*60)

        tool_calls = await page.evaluate("""
            () => {
                const html = document.body.innerHTML;
                const hasWebSearch = html.includes('web_search') || html.includes('WebSearch') || html.includes('brave');
                const hasWebFetch = html.includes('web_fetch') || html.includes('WebFetch');
                const hasToolUse = html.includes('tool_use') || html.includes('tool-use');
                return {
                    hasWebSearch,
                    hasWebFetch,
                    hasToolUse,
                    // 查找工具相关的元素
                    toolElements: document.querySelectorAll('[class*="tool"]').length
                };
            }
        """)
        print(f"WebSearch 调用: {tool_calls.get('hasWebSearch', False)}")
        print(f"WebFetch 调用: {tool_calls.get('hasWebFetch', False)}")
        print(f"工具使用标记: {tool_calls.get('hasToolUse', False)}")
        print(f"工具相关元素数: {tool_calls.get('toolElements', 0)}")

        # 截图保存
        await page.screenshot(path="/Users/awsdawei/claude/springo/tests/agent_blog_test.png")
        print("\n截图已保存到: tests/agent_blog_test.png")

if __name__ == "__main__":
    asyncio.run(test_agent_blog_question())
