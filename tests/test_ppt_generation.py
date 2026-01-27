"""
Test PPT generation with skill injection
Wait until PPT file is created
"""
import asyncio
import os
import glob
from playwright.async_api import async_playwright


async def test_ppt_generation():
    """Test PPT generation flow"""
    async with async_playwright() as p:
        print("Connecting to Electron app...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Get working directory
        working_dir = "/Users/awsdawei/Downloads/folder1"

        # Check existing pptx files before test
        existing_pptx = set(glob.glob(f"{working_dir}/*.pptx"))
        print(f"Existing PPTX files: {len(existing_pptx)}")

        # Listen for relevant console messages
        def log_handler(msg):
            text = msg.text.lower()
            if any(k in text for k in ['skill', 'pptx', 'ppt', 'inject', 'write_file', 'error']):
                print(f"[Console] {msg.text[:200]}")

        page.on("console", log_handler)

        print("\n=== Sending PPT request ===")

        # Wait for input to be ready
        await page.wait_for_selector('#message-input', state='visible', timeout=10000)

        # Clear and type message
        await page.fill('#message-input', '')
        await page.fill('#message-input', '最近openai发了哪些内容，整理成一个ppt，2页')

        # Click send button
        await page.wait_for_selector('#send-btn', state='visible', timeout=5000)
        await page.click('#send-btn')
        print("Message sent, waiting for PPT generation...")

        # Wait for PPT file to be created (up to 3 minutes)
        ppt_created = False
        new_ppt_file = None

        for i in range(180):  # 3 minutes max
            await asyncio.sleep(1)

            # Check for new pptx files
            current_pptx = set(glob.glob(f"{working_dir}/*.pptx"))
            new_files = current_pptx - existing_pptx

            if new_files:
                new_ppt_file = list(new_files)[0]
                ppt_created = True
                print(f"\n✓ PPT file created: {new_ppt_file}")
                break

            # Check processing status
            is_processing = await page.evaluate("() => typeof isProcessing !== 'undefined' ? isProcessing : null")

            # Show progress every 10 seconds
            if i % 10 == 0:
                tool_count = await page.evaluate("""
                    () => {
                        const list = document.getElementById('tool-execution-list');
                        return list ? list.children.length : 0;
                    }
                """)
                print(f"[{i}s] Processing: {is_processing}, Tools executed: {tool_count}")

            # If processing is done and still no file after a few seconds, check messages
            if is_processing is False and i > 30:
                # Wait a bit more in case file is being written
                await asyncio.sleep(5)
                current_pptx = set(glob.glob(f"{working_dir}/*.pptx"))
                new_files = current_pptx - existing_pptx
                if new_files:
                    new_ppt_file = list(new_files)[0]
                    ppt_created = True
                    print(f"\n✓ PPT file created: {new_ppt_file}")
                break

        print("\n=== Test Result ===")

        if ppt_created and new_ppt_file:
            file_size = os.path.getsize(new_ppt_file)
            print(f"✓ SUCCESS: PPT generated")
            print(f"  File: {new_ppt_file}")
            print(f"  Size: {file_size} bytes")
        else:
            print("✗ PPT file not found")

            # Check server log for errors
            print("\n=== Recent Server Log ===")

        # Check for skill injection in server log
        print("\n=== Skill Injection Check ===")


if __name__ == "__main__":
    asyncio.run(test_ppt_generation())
