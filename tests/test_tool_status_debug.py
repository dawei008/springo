"""
Debug test for tool execution status visibility
"""
import asyncio
import json
from playwright.async_api import async_playwright


async def debug_tool_status():
    """Debug tool execution status display"""
    async with async_playwright() as p:
        print("Connecting to Electron app...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # Enable console logging
        page.on("console", lambda msg: print(f"[Console] {msg.type}: {msg.text}"))

        # Listen for network events
        async def log_response(response):
            if "messages" in response.url:
                print(f"[Network] {response.status} {response.url}")
        page.on("response", log_response)

        print("\n=== Checking current state ===")

        # Check if tool execution sidebar exists
        sidebar_exists = await page.evaluate("""
            () => {
                const sidebar = document.getElementById('tool-execution-sidebar');
                return {
                    exists: !!sidebar,
                    display: sidebar ? getComputedStyle(sidebar).display : null,
                    visibility: sidebar ? getComputedStyle(sidebar).visibility : null,
                    className: sidebar ? sidebar.className : null
                };
            }
        """)
        print(f"Tool execution sidebar: {sidebar_exists}")

        # Check if there's a tool execution container
        container_info = await page.evaluate("""
            () => {
                const container = document.getElementById('tool-executions');
                return {
                    exists: !!container,
                    innerHTML: container ? container.innerHTML.substring(0, 500) : null,
                    childCount: container ? container.children.length : 0
                };
            }
        """)
        print(f"Tool executions container: {container_info}")

        # Check current conversation state
        conv_state = await page.evaluate("""
            () => {
                return {
                    currentConversationId: typeof currentConversationId !== 'undefined' ? currentConversationId : null,
                    isProcessing: typeof isProcessing !== 'undefined' ? isProcessing : null,
                    toolUsesLength: typeof toolUses !== 'undefined' ? toolUses.length : null
                };
            }
        """)
        print(f"Conversation state: {conv_state}")

        print("\n=== Injecting debug hooks ===")

        # Inject debug hooks for SSE events
        await page.evaluate("""
            () => {
                // Store original functions
                window._debugToolEvents = [];

                // Hook into event handling
                const originalAddToolExecution = window.addToolExecution;
                if (typeof originalAddToolExecution === 'function') {
                    window.addToolExecution = function(...args) {
                        console.log('[DEBUG] addToolExecution called:', JSON.stringify(args));
                        window._debugToolEvents.push({type: 'addToolExecution', args: args, time: Date.now()});
                        return originalAddToolExecution.apply(this, args);
                    };
                }

                const originalUpdateToolExecution = window.updateToolExecution;
                if (typeof originalUpdateToolExecution === 'function') {
                    window.updateToolExecution = function(...args) {
                        console.log('[DEBUG] updateToolExecution called:', JSON.stringify(args));
                        window._debugToolEvents.push({type: 'updateToolExecution', args: args, time: Date.now()});
                        return originalUpdateToolExecution.apply(this, args);
                    };
                }

                console.log('[DEBUG] Hooks installed');
                return 'Hooks installed';
            }
        """)

        print("\n=== Sending test message ===")

        # Clear input and type message
        input_selector = '#message-input'
        await page.fill(input_selector, '')
        await page.fill(input_selector, '现在是几点？')  # Simple test that should trigger date tool

        # Click send
        await page.click('#send-btn')
        print("Message sent, waiting for response...")

        # Wait and collect events
        await asyncio.sleep(10)

        # Check what events were captured
        debug_events = await page.evaluate("() => window._debugToolEvents || []")
        print(f"\n=== Debug events captured: {len(debug_events)} ===")
        for event in debug_events[:10]:  # Show first 10
            print(f"  {event}")

        # Check sidebar state after
        sidebar_after = await page.evaluate("""
            () => {
                const sidebar = document.getElementById('tool-execution-sidebar');
                const container = document.getElementById('tool-executions');
                return {
                    sidebarClass: sidebar ? sidebar.className : null,
                    containerHTML: container ? container.innerHTML.substring(0, 1000) : null,
                    childCount: container ? container.children.length : 0
                };
            }
        """)
        print(f"\n=== Sidebar state after: ===")
        print(f"Class: {sidebar_after.get('sidebarClass')}")
        print(f"Children: {sidebar_after.get('childCount')}")
        print(f"HTML preview: {sidebar_after.get('containerHTML', '')[:500]}")

        # Check for any errors
        errors = await page.evaluate("""
            () => {
                return window._consoleErrors || [];
            }
        """)
        if errors:
            print(f"\n=== Console errors: ===")
            for err in errors:
                print(f"  {err}")

        print("\n=== Test complete ===")


if __name__ == "__main__":
    asyncio.run(debug_tool_status())
