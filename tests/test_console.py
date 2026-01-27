"""Quick test to check console output"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://localhost:9222')
        page = browser.contexts[0].pages[0]

        # Refresh to load new code
        await page.reload()
        await asyncio.sleep(2)

        # Set up console listener
        console_messages = []
        page.on('console', lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))

        # Send a simpler request
        await page.fill('#message-input', '')
        await page.fill('#message-input', '在当前目录创建一个test.txt文件，内容是hello world')
        await page.click('#send-btn')

        print("Request sent, monitoring console...")

        for i in range(60):
            await asyncio.sleep(1)
            # Print relevant console messages
            for msg in console_messages:
                if any(k in msg for k in ['updateAssistantMessage', 'Tools with results', 'Final', 'isFinal']):
                    print(f"[{i}s] {msg}")
            console_messages.clear()

            # Check if done
            status = await page.evaluate("() => document.getElementById('status-text')?.textContent || ''")
            if 'ready' in status.lower() and i > 5:
                print(f"\n[{i}s] Status: Ready")
                break

        # Final state
        await asyncio.sleep(2)
        result = await page.evaluate("""
            () => {
                const msgs = document.querySelectorAll('.message-assistant');
                const last = msgs[msgs.length - 1];
                const content = last?.querySelector('.message-content');
                return {
                    text: content?.textContent?.substring(0, 500) || 'NO CONTENT',
                    htmlLen: content?.innerHTML?.length || 0
                };
            }
        """)
        print(f"\nFinal message ({result['htmlLen']} chars HTML):")
        print(result['text'][:300])

asyncio.run(test())
