"""
Test streaming output in Springo Electron app
"""

import asyncio
from playwright.async_api import async_playwright


async def test_streaming():
    """Test that streaming output works correctly by monitoring DOM updates"""
    print("Connecting to Electron app...")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            page = browser.contexts[0].pages[0]
            print("Connected to Electron app")

            # Reload to ensure latest code
            await page.reload()
            await asyncio.sleep(2)

            # Create a NEW conversation to ensure clean state
            print("Creating new conversation...")
            new_chat_btn = await page.query_selector('.new-chat-btn')
            if new_chat_btn:
                await new_chat_btn.click()
                await asyncio.sleep(1)

            # Count existing assistant messages
            existing_msgs = await page.query_selector_all('.message-assistant')
            initial_count = len(existing_msgs)
            print(f"Initial assistant messages: {initial_count}")

            # Type message
            input_box = await page.query_selector('#message-input')
            if not input_box:
                print("ERROR: Could not find message input")
                return False

            await input_box.fill("Tell me a very short joke")
            await asyncio.sleep(0.3)

            # Trigger input event to enable button
            await page.evaluate('document.getElementById("message-input").dispatchEvent(new Event("input"))')
            await asyncio.sleep(0.3)

            print("Entered test message")

            # Track text length changes in the NEW assistant message
            text_lengths = []

            async def monitor_new_message():
                """Monitor for a new assistant message and track its text length"""
                while True:
                    try:
                        # Get ALL assistant message contents
                        msgs = await page.query_selector_all('.message-assistant')
                        if len(msgs) > initial_count:
                            # New message appeared! Track the last one
                            last_msg = msgs[-1]
                            content_el = await last_msg.query_selector('.message-content')
                            if content_el:
                                text = await content_el.inner_text()
                                text_lengths.append(len(text))
                        await asyncio.sleep(0.05)  # Check every 50ms
                    except:
                        break

            # Start monitoring in background
            monitor_task = asyncio.create_task(monitor_new_message())

            # Click send
            send_btn = await page.query_selector('#send-btn')
            if send_btn:
                await send_btn.click()
                print("Clicked send button, monitoring for new assistant message...")

                # Wait for response to appear and complete
                for i in range(30):  # Max 30 seconds
                    await asyncio.sleep(1)

                    msgs = await page.query_selector_all('.message-assistant')
                    if len(msgs) > initial_count:
                        last_msg = msgs[-1]
                        content_el = await last_msg.query_selector('.message-content')
                        if content_el:
                            current_text = await content_el.inner_text()
                            current_len = len(current_text)
                            print(f"  Second {i+1}: new message length = {current_len} chars (captured {len(text_lengths)} samples)")

                            # Check if stable (same length for 2 seconds and not empty)
                            if current_len > 10 and len(text_lengths) > 20:
                                recent = text_lengths[-20:]
                                if len(set(recent)) == 1:  # All same
                                    print("Response appears complete (text stable)")
                                    break
                    else:
                        print(f"  Second {i+1}: waiting for new message...")

            # Stop monitoring
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

            # Analyze results
            print(f"\n{'='*50}")
            print(f"Total text length samples captured: {len(text_lengths)}")

            if len(text_lengths) < 5:
                print("❌ STREAMING NOT WORKING - too few samples captured")
                return False

            # Remove consecutive duplicates to see growth pattern
            unique_lengths = []
            for l in text_lengths:
                if not unique_lengths or l != unique_lengths[-1]:
                    unique_lengths.append(l)

            print(f"Unique text lengths observed: {len(unique_lengths)}")
            print(f"Text length progression: {unique_lengths[:30]}...")

            if len(unique_lengths) > 3:
                print("\n✅ STREAMING WORKING! Multiple distinct text lengths observed during response")
                print(f"   Text grew from {unique_lengths[0]} to {unique_lengths[-1]} characters")
                print(f"   Number of growth steps: {len(unique_lengths)}")
                return True
            else:
                print("\n❌ STREAMING NOT WORKING - text appeared all at once (non-streaming)")
                print(f"   Only {len(unique_lengths)} distinct lengths observed")
                return False

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    result = asyncio.run(test_streaming())
    print(f"\n{'='*50}")
    print(f"Test result: {'PASSED' if result else 'FAILED'}")
