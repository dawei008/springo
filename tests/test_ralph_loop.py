"""
Ralph Loop Test - Complex scenario with 10+ tool calls
Tests: panel collapse, final output, no tool errors
"""
import asyncio
import os
import glob
from playwright.async_api import async_playwright


async def wait_for_stream_end(page, timeout=120):
    """Wait for stream to end (Ready status)"""
    for i in range(timeout):
        await asyncio.sleep(1)
        state = await page.evaluate("""
            () => {
                const statusEl = document.getElementById('status-text');
                return statusEl?.textContent || '';
            }
        """)
        if 'ready' in state.lower():
            return True, i + 1
    return False, timeout


async def get_panel_state(page):
    """Get inline panel state"""
    return await page.evaluate("""
        () => {
            const panel = document.getElementById('inline-chat-tool-panel');
            const list = panel?.querySelector('.inline-panel-list');
            const items = list ? Array.from(list.children) : [];
            return {
                exists: !!panel,
                isCollapsed: panel?.classList.contains('collapsed'),
                itemCount: items.length,
                statusText: panel?.querySelector('.inline-panel-status')?.textContent || '',
                hasErrors: items.some(item => item.classList.contains('error')),
                errorTools: items.filter(item => item.classList.contains('error'))
                    .map(item => item.querySelector('.item-name')?.textContent)
            };
        }
    """)


async def get_chat_state(page):
    """Get chat content state"""
    return await page.evaluate("""
        () => {
            const chatContent = document.getElementById('chat-content');
            const messages = chatContent?.querySelectorAll('.message') || [];
            const lastMessage = messages[messages.length - 1];
            const lastContent = lastMessage?.querySelector('.message-content')?.textContent || '';
            return {
                messageCount: messages.length,
                lastMessageLength: lastContent.length,
                hasFinalOutput: lastContent.length > 50,
                preview: lastContent.substring(0, 200)
            };
        }
    """)


async def test_ralph_loop():
    """Main test with comprehensive checks"""
    async with async_playwright() as p:
        print("=" * 60)
        print("🔄 RALPH LOOP TEST - Complex Scenario (10+ tools)")
        print("=" * 60)

        print("\n[1/6] Connecting to Electron app...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        print("[2/6] Refreshing page...")
        await page.reload()
        await asyncio.sleep(2)

        working_dir = "/Users/awsdawei/Downloads/folder1"
        existing_pptx = set(glob.glob(f"{working_dir}/**/*.pptx", recursive=True))
        print(f"[3/6] Existing PPTX files: {len(existing_pptx)}")

        # Send complex task
        print("\n[4/6] Sending complex PPT task...")
        await page.wait_for_selector('#message-input', state='visible', timeout=10000)
        await page.fill('#message-input', '')
        task = "搜索最近OpenAI的新闻，整理成一个PPT，包含3页：1.封面 2.主要新闻 3.总结展望"
        await page.fill('#message-input', task)
        await page.click('#send-btn')
        print(f"   Task: {task[:50]}...")

        # Monitor execution
        print("\n[5/6] Monitoring execution...")
        max_tools = 0
        tools_seen = set()
        errors_seen = []
        panel_appeared = False

        for i in range(180):  # 3 minutes max
            await asyncio.sleep(1)

            panel = await get_panel_state(page)

            if panel['exists'] and not panel_appeared:
                panel_appeared = True
                print(f"   [{i}s] ✓ Panel appeared")

            if panel['itemCount'] > max_tools:
                max_tools = panel['itemCount']
                print(f"   [{i}s] Tools: {max_tools} | Status: {panel['statusText']}")

            if panel['hasErrors']:
                for err_tool in panel['errorTools']:
                    if err_tool and err_tool not in errors_seen:
                        errors_seen.append(err_tool)
                        print(f"   [{i}s] ⚠ Error in: {err_tool}")

            # Check for new PPT
            current_pptx = set(glob.glob(f"{working_dir}/**/*.pptx", recursive=True))
            new_files = current_pptx - existing_pptx
            if new_files:
                ppt_file = list(new_files)[0]
                file_size = os.path.getsize(ppt_file)
                print(f"\n   [{i}s] ✓ PPT Created: {os.path.basename(ppt_file)} ({file_size} bytes)")

                # Wait for stream to fully end
                print("   Waiting for stream to end...")
                ended, wait_time = await wait_for_stream_end(page, timeout=60)
                if ended:
                    print(f"   ✓ Stream ended after {wait_time}s")
                else:
                    print(f"   ⚠ Stream still running after {wait_time}s")

                # Wait for collapse animation
                await asyncio.sleep(3)
                break

            if i % 30 == 0 and i > 0:
                print(f"   [{i}s] Still working...")

        # Final state check
        print("\n[6/6] Final State Check...")
        await asyncio.sleep(2)

        final_panel = await get_panel_state(page)
        final_chat = await get_chat_state(page)

        # Take screenshot
        await page.screenshot(path='test_ralph_loop_result.png')

        # Results
        print("\n" + "=" * 60)
        print("📊 TEST RESULTS")
        print("=" * 60)

        results = {
            "Panel appeared": panel_appeared,
            "Panel collapsed": final_panel.get('isCollapsed', False),
            "Tools executed": max_tools,
            "No tool errors": len(errors_seen) == 0,
            "Final output shown": final_chat.get('hasFinalOutput', False),
            "PPT created": len(new_files) > 0 if 'new_files' in dir() else False
        }

        all_passed = True
        for check, passed in results.items():
            status = "✓" if passed else "✗"
            print(f"  {status} {check}: {passed}")
            if not passed:
                all_passed = False

        if errors_seen:
            print(f"\n  Errors in tools: {', '.join(errors_seen)}")

        print(f"\n  Final panel status: {final_panel.get('statusText', 'N/A')}")
        print(f"  Chat preview: {final_chat.get('preview', 'N/A')[:100]}...")
        print(f"\n  Screenshot: test_ralph_loop_result.png")

        print("\n" + "=" * 60)
        if all_passed:
            print("🎉 ALL TESTS PASSED!")
        else:
            print("❌ SOME TESTS FAILED - See details above")
        print("=" * 60)

        return all_passed


if __name__ == "__main__":
    asyncio.run(test_ralph_loop())
