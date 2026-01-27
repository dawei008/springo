import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://localhost:9222')
        page = browser.contexts[0].pages[0]

        # Hard refresh
        await page.evaluate("location.reload(true)")
        await asyncio.sleep(3)

        console_msgs = []
        page.on('console', lambda m: console_msgs.append(m.text))

        # Simple task
        await page.fill('#message-input', '创建一个test123.txt文件')
        await page.click('#send-btn')
        print("Sent request...")

        for i in range(45):
            await asyncio.sleep(1)
            for msg in console_msgs:
                if 'updateAssistantMessage' in msg or 'displayContent' in msg:
                    print(f"[{i}s] {msg}")
            console_msgs.clear()
            
            status = await page.evaluate("() => document.getElementById('status-text')?.textContent || ''")
            if 'ready' in status.lower() and i > 3:
                print(f"[{i}s] Done")
                break

        await asyncio.sleep(2)
        
        # Check DOM
        result = await page.evaluate("""
            () => {
                const chat = document.getElementById('chat-content');
                const msgs = chat?.querySelectorAll('.message');
                const lastMsg = msgs?.[msgs.length - 1];
                const content = lastMsg?.querySelector('.message-content');
                return {
                    totalMsgs: msgs?.length || 0,
                    lastMsgClass: lastMsg?.className || 'N/A',
                    contentHTML: content?.innerHTML?.substring(0, 500) || 'NO CONTENT',
                    contentLen: content?.innerHTML?.length || 0
                };
            }
        """)
        print(f"\nTotal messages: {result['totalMsgs']}")
        print(f"Last msg class: {result['lastMsgClass']}")
        print(f"Content length: {result['contentLen']}")
        print(f"Content:\n{result['contentHTML'][:300]}")

asyncio.run(test())
