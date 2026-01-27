"""
测试: 检查工具调用的实际参数
"""
import asyncio
from playwright.async_api import async_playwright

async def test_tool_params():
    async with async_playwright() as p:
        print("连接到 Electron 应用...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 刷新页面
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

        print("等待响应并监控工具调用...")

        # 等待响应完成，同时收集工具调用信息
        max_wait = 120
        waited = 0
        tool_calls = []

        while waited < max_wait:
            await asyncio.sleep(3)
            waited += 3

            # 尝试从 Tool Execution 面板获取工具调用详情
            tool_info = await page.evaluate("""
                () => {
                    // 查找工具执行面板中的所有工具调用
                    const toolItems = document.querySelectorAll('.tool-execution-item, [class*="tool-item"], [class*="tool-call"]');
                    const tools = [];

                    toolItems.forEach(item => {
                        const name = item.querySelector('.tool-name, [class*="name"]')?.textContent || '';
                        const input = item.querySelector('.tool-input, [class*="input"], pre')?.textContent || '';
                        if (name || input) {
                            tools.push({ name, input: input.substring(0, 500) });
                        }
                    });

                    // 也检查整个页面的 JSON 内容
                    const pageText = document.body.innerText;
                    const hasFreshness = pageText.includes('freshness') && (
                        pageText.includes('"pm"') ||
                        pageText.includes('"pw"') ||
                        pageText.includes('"pd"') ||
                        pageText.includes("'pm'") ||
                        pageText.includes("'pw'")
                    );

                    return {
                        tools,
                        hasFreshnessInPage: hasFreshness,
                        pageSnippet: pageText.substring(0, 1000)
                    };
                }
            """)

            if tool_info.get('tools'):
                tool_calls = tool_info['tools']

            # 检查是否完成
            status_text = await page.evaluate("document.body.innerText")
            is_running = "Running" in status_text

            if not is_running and waited > 10:
                print(f"  响应完成! (耗时 {waited}s)")
                break

            print(f"  等待中... {waited}s")

        # 打开 Tool Execution 面板（如果有的话）
        tool_btn = page.locator('[class*="tool-execution"], button:has-text("Tool")')
        if await tool_btn.count() > 0:
            try:
                await tool_btn.first.click()
                await asyncio.sleep(1)
            except:
                pass

        # 截图 Tool Execution 面板
        await page.screenshot(path="/Users/awsdawei/claude/springo/tests/tool_params_result.png")

        # 获取完整的工具调用信息
        print("\n" + "="*60)
        print("工具调用详情:")
        print("="*60)

        detailed_info = await page.evaluate("""
            () => {
                const html = document.body.innerHTML;

                // 查找所有看起来像工具参数的 JSON
                const jsonMatches = html.match(/\\{[^{}]*"query"[^{}]*\\}/g) || [];

                // 检查是否有 freshness 参数
                const freshnessMatches = html.match(/freshness['":\\s]*(["']?)(pd|pw|pm|py)\\1/gi) || [];

                return {
                    jsonSnippets: jsonMatches.slice(0, 5),
                    freshnessParams: freshnessMatches,
                    hasFreshnessInHtml: html.includes('freshness')
                };
            }
        """)

        print(f"发现 freshness 参数: {detailed_info.get('freshnessParams')}")
        print(f"HTML 中包含 freshness: {detailed_info.get('hasFreshnessInHtml')}")
        print(f"\nJSON 片段:")
        for i, snippet in enumerate(detailed_info.get('jsonSnippets', [])[:3]):
            print(f"  {i+1}. {snippet[:200]}...")

        print(f"\n截图已保存: tests/tool_params_result.png")

if __name__ == "__main__":
    asyncio.run(test_tool_params())
