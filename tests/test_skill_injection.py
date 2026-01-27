"""
Test Claude Code style skill injection
"""
import asyncio
from playwright.async_api import async_playwright


async def test_skill_injection():
    """Test skill injection with PPT task"""
    async with async_playwright() as p:
        print("Connecting to Electron app...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Listen for console messages
        page.on("console", lambda msg: print(f"[Console] {msg.type}: {msg.text}") if "skill" in msg.text.lower() or "inject" in msg.text.lower() else None)

        print("\n=== Sending test message ===")

        # Clear input and type message
        input_selector = '#message-input'
        await page.fill(input_selector, '')
        await page.fill(input_selector, '最近openai发了哪些内容，整理成一个ppt，2页')

        # Click send
        await page.click('#send-btn')
        print("Message sent, waiting for response...")

        # Monitor for skill injection event
        skill_injected = False
        ppt_skill_used = False

        # Wait and check for skill-related events
        for i in range(60):  # Wait up to 60 seconds
            await asyncio.sleep(1)

            # Check tool execution status
            tool_status = await page.evaluate("""
                () => {
                    const container = document.getElementById('tool-execution-list');
                    if (!container) return { html: '', count: 0 };
                    return {
                        html: container.innerHTML.substring(0, 2000),
                        count: container.children.length
                    };
                }
            """)

            if tool_status['count'] > 0:
                html = tool_status['html'].lower()
                if 'use_skill' in html or 'pptx' in html or 'skill' in html:
                    print(f"\n[{i}s] Tool status shows skill activity:")
                    print(f"  Children: {tool_status['count']}")
                    if 'use_skill' in html:
                        ppt_skill_used = True
                        print("  ✓ use_skill tool detected")

            # Check if response is complete
            is_processing = await page.evaluate("() => typeof isProcessing !== 'undefined' ? isProcessing : null")
            if is_processing is False and i > 5:
                print(f"\n[{i}s] Response complete")
                break

            if i % 10 == 0:
                print(f"[{i}s] Still waiting... (tools: {tool_status['count']})")

        # Final check
        print("\n=== Final Status ===")

        # Check messages for PPT creation
        final_html = await page.evaluate("""
            () => {
                const messages = document.getElementById('messages');
                return messages ? messages.innerHTML.substring(0, 3000) : '';
            }
        """)

        if 'ppt' in final_html.lower() or 'powerpoint' in final_html.lower():
            print("✓ PPT-related content found in response")
        else:
            print("? PPT content not found in response HTML")

        # Check server log for skill injection
        print("\n=== Server Log (skill-related) ===")

        print("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_skill_injection())
