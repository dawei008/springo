"""
Final performance comparison test
Multiple runs to get average times
"""

import asyncio
import time
from playwright.async_api import async_playwright


async def run_single_test(page, query, test_name):
    """Run a single test and return timing"""
    # Create new conversation
    new_chat_btn = await page.query_selector('.new-chat-btn')
    if new_chat_btn:
        await new_chat_btn.click()
        await asyncio.sleep(0.5)

    input_box = await page.query_selector('#message-input')
    if not input_box:
        return None

    await input_box.fill(query)
    await asyncio.sleep(0.1)
    await page.evaluate('document.getElementById("message-input").dispatchEvent(new Event("input"))')
    await asyncio.sleep(0.1)

    start_time = time.time()
    tool_count = 0

    send_btn = await page.query_selector('#send-btn')
    await send_btn.click()

    # Wait for completion (check every 0.5s)
    for i in range(120):  # 1 minute max
        await asyncio.sleep(0.5)

        status = await page.evaluate("""
            (() => {
                const runtime = convRuntime[currentConversationId];
                const executions = toolExecutionsPerConv[currentConversationId] || [];
                return {
                    isStreaming: runtime?.isStreaming || false,
                    toolCount: executions.length
                };
            })()
        """)

        tool_count = status['toolCount']

        if not status['isStreaming']:
            elapsed = time.time() - start_time
            return {'time': elapsed, 'tools': tool_count, 'name': test_name}

    return {'time': 60, 'tools': tool_count, 'name': test_name, 'timeout': True}


async def main():
    print("=" * 60)
    print("性能对比测试")
    print("=" * 60)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            page = browser.contexts[0].pages[0]

            await page.reload()
            await asyncio.sleep(2)

            tests = [
                ("简单问答 (无工具)", "Python 是什么？一句话回答"),
                ("文件读取 (1个工具)", "读取 /Users/awsdawei/claude/springo/README.md 的前10行"),
                ("多文件操作 (2个工具)", "用 glob 找出 springo 目录下的 .md 文件，然后读取 README.md")
            ]

            results = []
            for test_name, query in tests:
                print(f"\n测试: {test_name}")
                print(f"查询: {query[:40]}...")
                result = await run_single_test(page, query, test_name)
                if result:
                    status = "超时" if result.get('timeout') else "完成"
                    print(f"  结果: {result['time']:.2f}s, {result['tools']} 个工具 ({status})")
                    results.append(result)
                await asyncio.sleep(1)

            # Summary
            print("\n" + "=" * 60)
            print("测试总结")
            print("=" * 60)
            print(f"{'测试名称':<25} {'时间':>10} {'工具数':>8}")
            print("-" * 60)
            for r in results:
                status = " (超时)" if r.get('timeout') else ""
                print(f"{r['name']:<25} {r['time']:>8.2f}s {r['tools']:>8}{status}")

            # Calculate average
            if results:
                avg_time = sum(r['time'] for r in results) / len(results)
                print("-" * 60)
                print(f"{'平均时间':<25} {avg_time:>8.2f}s")

            print("\n优化前参考: 简单任务 ~3 分钟 (180s)")

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
