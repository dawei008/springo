"""
测试: anthropic最新的agent博客问题 v2
改进: 更好的等待和内容捕获
"""
import asyncio
from playwright.async_api import async_playwright

async def test_agent_blog_question():
    async with async_playwright() as p:
        print("连接到 Electron 应用...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 先检查历史对话中是否有已完成的回答
        print("\n" + "="*60)
        print("检查现有对话列表...")
        print("="*60)

        # 点击第一个历史对话 (#63) 来查看之前的回答
        history_item = page.locator('.conversation-item').first
        if await history_item.count() > 0:
            await history_item.click()
            await asyncio.sleep(2)

            # 截图查看已有对话
            await page.screenshot(path="/Users/awsdawei/claude/springo/tests/existing_chat.png")
            print("已有对话截图: tests/existing_chat.png")

            # 获取对话内容
            content = await page.evaluate("""
                () => {
                    const messages = document.querySelectorAll('.message');
                    return Array.from(messages).map(m => {
                        const role = m.querySelector('.message-role')?.textContent || 'unknown';
                        const content = m.querySelector('.message-content')?.textContent || m.textContent;
                        return `[${role}] ${content.substring(0, 500)}`;
                    }).join('\\n\\n');
                }
            """)
            print("\n对话内容预览:")
            print(content[:2000] if content else "无法获取内容")

        # 现在发送新的测试消息并等待完成
        print("\n" + "="*60)
        print("发送新测试消息...")
        print("="*60)

        # 点击 New Chat
        new_chat_btn = page.locator('text=New Chat').first
        await new_chat_btn.click()
        await asyncio.sleep(1)

        # 输入测试问题
        test_question = "anthropic最新的agent博客讲了什么"
        input_box = page.locator('#message-input')
        await input_box.fill(test_question)
        await asyncio.sleep(0.5)

        # 发送
        send_btn = page.locator('#send-btn')
        await send_btn.click()
        print(f"已发送: {test_question}")

        # 等待响应完成 - 通过检测 "Running..." 状态
        print("等待响应完成...")
        max_wait = 120  # 最多等待120秒
        waited = 0

        while waited < max_wait:
            await asyncio.sleep(2)
            waited += 2

            # 检查是否还在 Running 状态
            status_text = await page.locator('.status-bar, [class*="status"]').first.text_content()
            is_running = "Running" in (status_text or "")

            if not is_running and waited > 5:
                print(f"  响应完成! (耗时 {waited}s)")
                break

            print(f"  等待中... {waited}s (状态: {'Running' if is_running else 'Idle'})")

        await asyncio.sleep(2)  # 额外等待渲染

        # 获取完整响应
        print("\n" + "="*60)
        print("AI 响应内容:")
        print("="*60)

        # 获取助手消息
        response = await page.evaluate("""
            () => {
                const messages = document.querySelectorAll('.message');
                let assistantMessages = [];
                messages.forEach(m => {
                    const role = m.querySelector('.message-role')?.textContent?.toLowerCase() || '';
                    if (role.includes('assistant') || role.includes('springo') || role.includes('claude')) {
                        const content = m.querySelector('.message-content');
                        if (content) {
                            assistantMessages.push(content.innerText || content.textContent);
                        }
                    }
                });
                return assistantMessages.join('\\n---\\n');
            }
        """)

        if response:
            print(response[:3000])
            if len(response) > 3000:
                print(f"\n... (共 {len(response)} 字符)")
        else:
            # 备用方法：获取所有消息容器的内容
            all_content = await page.evaluate("""
                () => document.querySelector('#messages-container')?.innerText || 'No content'
            """)
            print("备用方法获取内容:")
            print(all_content[:3000])

        # 检查工具调用情况
        print("\n" + "="*60)
        print("工具调用分析:")
        print("="*60)

        tool_analysis = await page.evaluate("""
            () => {
                const html = document.body.innerHTML;
                const innerText = document.body.innerText;

                return {
                    // 检查是否有 web_search 相关内容
                    hasWebSearchInHtml: html.includes('web_search') || html.includes('brave_web_search'),
                    hasWebSearchInText: innerText.includes('搜索') || innerText.includes('search'),

                    // 检查是否提到了具体年份
                    mentions2024: innerText.includes('2024'),
                    mentions2025: innerText.includes('2025'),
                    mentions2026: innerText.includes('2026'),

                    // 检查是否有工具结果显示
                    hasToolResults: html.includes('tool-result') || html.includes('tool_result'),

                    // 检查是否有链接
                    hasAnthropicLinks: html.includes('anthropic.com'),

                    // 提取任何 URL
                    urls: (html.match(/https?:\/\/[^\s"'<>]+anthropic[^\s"'<>]*/g) || []).slice(0, 5)
                };
            }
        """)

        print(f"Web Search 调用 (HTML): {tool_analysis.get('hasWebSearchInHtml')}")
        print(f"Web Search 调用 (文本): {tool_analysis.get('hasWebSearchInText')}")
        print(f"提到 2024 年: {tool_analysis.get('mentions2024')}")
        print(f"提到 2025 年: {tool_analysis.get('mentions2025')}")
        print(f"提到 2026 年: {tool_analysis.get('mentions2026')}")
        print(f"有工具结果: {tool_analysis.get('hasToolResults')}")
        print(f"有 Anthropic 链接: {tool_analysis.get('hasAnthropicLinks')}")
        print(f"找到的 URLs: {tool_analysis.get('urls')}")

        # 保存最终截图
        await page.screenshot(path="/Users/awsdawei/claude/springo/tests/agent_blog_final.png", full_page=True)
        print("\n最终截图: tests/agent_blog_final.png")

if __name__ == "__main__":
    asyncio.run(test_agent_blog_question())
