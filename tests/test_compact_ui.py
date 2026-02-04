"""
Test compact functionality and UI display
Threshold set to 30% (60000 tokens)
"""
import asyncio
from playwright.async_api import async_playwright

async def test_compact_ui():
    """Test compact UI - will use session #169 which has 61,949 tokens (above 60000 threshold)"""
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        print("Connected to Electron app")
        print("Threshold: 60000 tokens (30%)")

        # Step 1: Navigate to session #169 (has 61,949 tokens)
        print("\n1. Navigating to session #169...")
        await page.reload()
        await asyncio.sleep(2)

        # Find and click on session #169
        session_found = False
        items = await page.query_selector_all('.conversation-item')
        for item in items:
            text = await item.inner_text()
            if '#169' in text:
                await item.click()
                session_found = True
                print(f"   Clicked on session: {text.strip()[:40]}")
                break

        if not session_found:
            print("   ERROR: Could not find session #169")
            return

        await asyncio.sleep(2)

        # Verify context percentage
        ctx_text = await page.evaluate('() => document.querySelector(".context-indicator")?.innerText || ""')
        print(f"   Current context: {ctx_text.strip()}")

        # Step 2: Capture before state
        await page.screenshot(path="tests/compact_before.png")
        print("\n2. Screenshot saved: tests/compact_before.png")

        # Step 3: Send message to trigger compact
        print("\n3. Sending message to trigger compact...")
        input_box = await page.query_selector('#message-input')
        if input_box:
            await input_box.fill("请简短回复'OK'")
            await asyncio.sleep(0.5)

            send_btn = await page.query_selector('#send-btn:not([disabled])')
            if send_btn:
                await send_btn.click()
                print("   Message sent - watching for compact status...")
            else:
                print("   ERROR: Send button not available")
                return
        else:
            print("   ERROR: Input box not found")
            return

        # Step 4: Watch for compact status
        print("\n4. Monitoring status changes...")

        compact_seen = False
        running_seen = False
        done_seen = False

        for i in range(60):  # Wait up to 60 seconds
            await asyncio.sleep(0.5)

            status_el = await page.query_selector('.context-indicator')
            if status_el:
                status_text = await status_el.inner_text()
                status_html = await status_el.inner_html()

                # Check for compacting state
                if 'Compacting' in status_text or 'compacting' in status_html.lower():
                    if not compact_seen:
                        print(f"   [{i*0.5:.1f}s] ✨ COMPACTING DETECTED!")
                        await page.screenshot(path="tests/compact_during.png")
                        print("   Screenshot saved: tests/compact_during.png")
                        compact_seen = True
                elif 'Running' in status_text or '◐' in status_text or 'spinner' in status_html.lower():
                    if not running_seen:
                        print(f"   [{i*0.5:.1f}s] Running...")
                        running_seen = True
                elif '✓' in status_text or 'Completed' in status_text:
                    if not done_seen:
                        print(f"   [{i*0.5:.1f}s] Completed")
                        done_seen = True
                        # Wait a bit more to see final state
                        await asyncio.sleep(2)
                        break

        # Step 5: Capture final state
        await page.screenshot(path="tests/compact_after.png")
        print("\n5. Final screenshot saved: tests/compact_after.png")

        # Get final context percentage
        final_ctx = await page.evaluate('() => document.querySelector(".context-indicator")?.innerText || ""')
        print(f"   Final context: {final_ctx.strip()}")

        # Summary
        print("\n" + "="*50)
        print("COMPACT TEST SUMMARY")
        print("="*50)

        if compact_seen:
            print("✅ SUCCESS: Compact UI was displayed!")
            print("   - 'Compacting...' status was shown during context compaction")
            print("   - Screenshots captured: compact_before.png, compact_during.png, compact_after.png")
        else:
            print("⚠️ Compact status not detected")
            print("   - Context may have been below threshold")
            print("   - Or compact happened too fast to capture")

if __name__ == "__main__":
    asyncio.run(test_compact_ui())
