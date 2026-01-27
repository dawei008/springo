"""Test that chat auto-scrolls during tool execution"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://localhost:9222')
        page = browser.contexts[0].pages[0]

        # Hard refresh
        await page.evaluate("location.reload(true)")
        await asyncio.sleep(3)

        print("=== Test: Auto-scroll during tool execution ===\n")

        await page.fill('#message-input', '请创建一个scroll_test.txt文件内容是"scroll test"')
        await page.click('#send-btn')
        print("Request sent...")

        # Track scroll positions during execution
        scroll_data = []

        for i in range(30):
            await asyncio.sleep(0.5)

            scroll_info = await page.evaluate("""
                () => {
                    const container = document.getElementById('chat-container');
                    return {
                        scrollTop: container.scrollTop,
                        scrollHeight: container.scrollHeight,
                        clientHeight: container.clientHeight,
                        isAtBottom: (container.scrollTop + container.clientHeight) >= (container.scrollHeight - 50)
                    };
                }
            """)
            scroll_data.append(scroll_info)

            status = await page.evaluate("() => document.getElementById('status-text')?.textContent || ''")
            if 'ready' in status.lower() and i > 5:
                print(f"[{i*0.5}s] Task completed")
                break

        # Analyze scroll behavior
        at_bottom_count = sum(1 for s in scroll_data if s['isAtBottom'])
        total_samples = len(scroll_data)

        print(f"\n=== Scroll Analysis ===")
        print(f"Total samples: {total_samples}")
        print(f"At bottom count: {at_bottom_count}")
        print(f"At bottom percentage: {at_bottom_count/total_samples*100:.1f}%")

        if at_bottom_count / total_samples >= 0.8:
            print(f"\n✓ SUCCESS: Chat stays at bottom during updates (>80%)")
        else:
            print(f"\n✗ FAIL: Chat not staying at bottom")

asyncio.run(test())
