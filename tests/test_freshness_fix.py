"""
测试: freshness 参数修复效果验证
"""
import asyncio
from playwright.async_api import async_playwright

async def test_freshness_fix():
    async with async_playwright() as p:
        print("连接到 Electron 应用...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 刷新页面确保加载最新代码
        await page.reload()
        await asyncio.sleep(3)

        # 点击 New Chat
        new_chat_btn = page.locator('text=New Chat').first
        await new_chat_btn.click()
        await asyncio.sleep(1)

        # 发送测试问题
        test_question = "anthropic最新的agent博客讲了什么"
        print(f"\n发送测试问题: {test_question}")

        input_box = page.locator('#message-input')
        await input_box.fill(test_question)
        await asyncio.sleep(0.5)

        send_btn = page.locator('#send-btn')
        await send_btn.click()

        print("等待响应...")

        # 等待响应完成
        max_wait = 120
        waited = 0

        while waited < max_wait:
            await asyncio.sleep(3)
            waited += 3

            # 检查状态
            status_text = await page.evaluate("document.body.innerText")
            is_running = "Running" in status_text

            if not is_running and waited > 10:
                print(f"  响应完成! (耗时 {waited}s)")
                break

            print(f"  等待中... {waited}s")

        await asyncio.sleep(2)

        # 截图
        await page.screenshot(path="/Users/awsdawei/claude/springo/tests/freshness_test_result.png")

        # 获取响应内容
        content = await page.evaluate("""
            () => {
                const container = document.getElementById('messages-container');
                return container ? container.innerText : document.body.innerText;
            }
        """)

        print("\n" + "="*60)
        print("检查关键指标:")
        print("="*60)

        # 检查是否提到了最新内容
        checks = {
            "提到 2025 年": "2025" in content,
            "提到 2026 年": "2026" in content,
            "提到 Agent Skills": "Agent Skills" in content or "agent skills" in content.lower(),
            "提到 Cowork": "Cowork" in content or "cowork" in content.lower(),
            "提到 Opus 4.5": "Opus 4.5" in content or "opus 4.5" in content.lower(),
            "仍提到旧的 Building Effective Agents (2024)": "Building Effective Agents" in content and "2024" in content,
        }

        for check, result in checks.items():
            status = "✅" if result else "❌"
            print(f"{status} {check}")

        # 检查工具调用
        print("\n" + "="*60)
        print("工具调用检查:")
        print("="*60)

        tool_info = await page.evaluate("""
            () => {
                const html = document.body.innerHTML;
                return {
                    hasFreshness: html.includes('freshness') || html.includes('pm') || html.includes('past_month'),
                    hasBraveSearch: html.includes('brave_web_search') || html.includes('web_search'),
                };
            }
        """)

        print(f"使用了 freshness 参数: {tool_info.get('hasFreshness')}")
        print(f"调用了搜索工具: {tool_info.get('hasBraveSearch')}")

        print("\n" + "="*60)
        print("响应内容预览 (前2000字符):")
        print("="*60)
        print(content[:2000] if content else "无内容")

        print(f"\n截图已保存: tests/freshness_test_result.png")

if __name__ == "__main__":
    asyncio.run(test_freshness_fix())
