"""
Playwright UI tests for:
1. HTML Artifact Sandbox (extractHtmlArtifacts, createArtifactPlaceholder, activateArtifacts)
2. Universal Tool Visual Content Rendering (injectToolVisualContent)
3. /v1/images/file backend endpoint (already tested via curl, cross-check here)

Loads the Electron frontend in a Chromium browser and exercises each feature.
"""
import json
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8081"
FRONTEND_PATH = "/Users/awsdawei/claude/springo/springo-app/renderer/index.html"

results = []


def record(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def wait_for_app(page, timeout=10):
    """Wait for the app to initialize (BASE_URL set, formatContent available)."""
    for _ in range(timeout * 10):
        ready = page.evaluate("typeof formatContent === 'function' && typeof BASE_URL === 'string'")
        if ready:
            return True
        time.sleep(0.1)
    return False


# ================================================================
# Test Suite 1: HTML Artifact Sandbox
# ================================================================
def test_artifact_sandbox(page):
    print("\n=== Test Suite 1: HTML Artifact Sandbox ===")

    # 1a. extractHtmlArtifacts detects HTML in code fence
    result = page.evaluate("""
        extractHtmlArtifacts("Here is a demo:\\n```html\\n<!DOCTYPE html>\\n<html><head><title>Test</title></head><body><h1>Hello</h1></body></html>\\n```\\nDone.")
    """)
    has_placeholder = "artifact-container" in result
    record("extractHtmlArtifacts: detects HTML in code fence", has_placeholder,
           f"contains artifact-container: {has_placeholder}")

    # 1b. extractHtmlArtifacts ignores non-HTML code fences
    result2 = page.evaluate("""
        extractHtmlArtifacts("```python\\nprint('hello')\\n```")
    """)
    no_placeholder = "artifact-container" not in result2
    record("extractHtmlArtifacts: ignores non-HTML code", no_placeholder)

    # 1c. createArtifactPlaceholder returns iframe container
    placeholder = page.evaluate("""
        createArtifactPlaceholder('<html><body><p>Test</p></body></html>')
    """)
    has_iframe = "iframe" in placeholder.lower() and "artifact-container" in placeholder
    record("createArtifactPlaceholder: returns iframe HTML", has_iframe,
           f"length={len(placeholder)}")

    # 1d. Deduplication: same content returns same placeholder
    placeholder2 = page.evaluate("""
        createArtifactPlaceholder('<html><body><p>Test</p></body></html>')
    """)
    record("createArtifactPlaceholder: dedup same content", placeholder == placeholder2)

    # 1e. Different content returns different placeholder
    placeholder3 = page.evaluate("""
        createArtifactPlaceholder('<html><body><p>Different</p></body></html>')
    """)
    record("createArtifactPlaceholder: different content != same", placeholder3 != placeholder)

    # 1f. activateArtifacts injects srcdoc into iframe
    page.evaluate("""
        (() => {
            const div = document.createElement('div');
            div.id = 'test-artifact-container';
            div.innerHTML = createArtifactPlaceholder('<html><body><h1>Activated</h1></body></html>');
            document.body.appendChild(div);
            activateArtifacts(div);
        })()
    """)
    time.sleep(0.5)
    has_srcdoc = page.evaluate("""
        (() => {
            const iframe = document.querySelector('#test-artifact-container iframe');
            if (!iframe) return 'no iframe found';
            return iframe.srcdoc ? 'has srcdoc' : 'no srcdoc';
        })()
    """)
    record("activateArtifacts: injects srcdoc into iframe", has_srcdoc == "has srcdoc", has_srcdoc)

    # Cleanup
    page.evaluate("document.getElementById('test-artifact-container')?.remove()")

    # 1g. isFullHtmlDocument detection
    is_full = page.evaluate("isFullHtmlDocument('<!DOCTYPE html><html><body>hi</body></html>')")
    record("isFullHtmlDocument: detects full HTML doc", is_full == True)

    not_full = page.evaluate("isFullHtmlDocument('<div>just a fragment</div>')")
    record("isFullHtmlDocument: rejects fragment", not_full == False)


# ================================================================
# Test Suite 2: Universal Tool Visual Content Rendering
# ================================================================
def test_tool_visual_content(page):
    print("\n=== Test Suite 2: Universal Tool Visual Content Rendering ===")

    # Ensure chat-content exists
    page.evaluate("""
        (() => {
            if (!document.getElementById('chat-content')) {
                const div = document.createElement('div');
                div.id = 'chat-content';
                document.body.appendChild(div);
            }
        })()
    """)

    # 2a. Excalidraw create_view: renders from input elements
    page.evaluate("""
        (() => {
            const tu = {
                id: 'test-exc-001',
                name: 'excalidraw__create_view',
                input: {
                    elements: [
                        { type: 'rectangle', x: 10, y: 10, width: 100, height: 60, id: 'r1',
                          strokeColor: '#000', backgroundColor: 'transparent', fillStyle: 'hachure',
                          strokeWidth: 1, roughness: 1, opacity: 100, angle: 0, seed: 123,
                          version: 1, versionNonce: 1, isDeleted: false, boundElements: null,
                          updated: 1, link: null, locked: false }
                    ]
                },
                result: { content: [{ type: 'text', text: 'Diagram displayed!' }] },
                status: 'complete'
            };
            injectToolVisualContent(tu);
        })()
    """)
    time.sleep(0.3)
    exc_found = page.evaluate("""
        document.querySelector('[data-visual-id="excalidraw-test-exc-001"]') !== null
    """)
    record("injectToolVisualContent: excalidraw create_view renders", exc_found)

    # 2b. Image URL in tool result
    page.evaluate("""
        (() => {
            const tu = {
                id: 'test-url-002',
                name: 'some_screenshot_tool',
                input: {},
                result: 'Screenshot saved: https://example.com/test-image.png',
                status: 'complete'
            };
            injectToolVisualContent(tu);
        })()
    """)
    time.sleep(0.3)
    url_found = page.evaluate("""
        (() => {
            const el = document.querySelector('.tool-visual-content img[src*="example.com"]');
            return el !== null;
        })()
    """)
    record("injectToolVisualContent: image URL detected & rendered", url_found)

    # 2c. Image file path in tool result
    page.evaluate("""
        (() => {
            const tu = {
                id: 'test-path-003',
                name: 'diagram_tool',
                input: {},
                result: 'Image saved to /tmp/output/diagram.png successfully.',
                status: 'complete'
            };
            injectToolVisualContent(tu);
        })()
    """)
    time.sleep(0.3)
    path_found = page.evaluate("""
        (() => {
            const el = document.querySelector('.tool-visual-image[data-src="/tmp/output/diagram.png"]');
            return el !== null;
        })()
    """)
    record("injectToolVisualContent: image file path detected & rendered", path_found)

    # 2d. Base64 image in tool result
    # Minimal 1x1 red PNG in base64
    page.evaluate("""
        (() => {
            const tu = {
                id: 'test-b64-004',
                name: 'image_gen_tool',
                input: {},
                result: 'Generated image: data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==',
                status: 'complete'
            };
            injectToolVisualContent(tu);
        })()
    """)
    time.sleep(0.3)
    b64_found = page.evaluate("""
        (() => {
            const el = document.querySelector('[data-visual-id="b64-test-b64-004"] img');
            return el !== null && el.src.startsWith('data:image/png;base64,');
        })()
    """)
    record("injectToolVisualContent: base64 image detected & rendered", b64_found)

    # 2e. SVG content in tool result
    page.evaluate("""
        (() => {
            const tu = {
                id: 'test-svg-005',
                name: 'chart_tool',
                input: {},
                result: 'Chart: <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><circle cx="50" cy="50" r="40" fill="green"/></svg>',
                status: 'complete'
            };
            injectToolVisualContent(tu);
        })()
    """)
    time.sleep(0.3)
    svg_found = page.evaluate("""
        (() => {
            const el = document.querySelector('[data-visual-id="svg-test-svg-005"] svg');
            return el !== null;
        })()
    """)
    record("injectToolVisualContent: SVG content detected & rendered", svg_found)

    # 2f. Deduplication: calling same tool again should not create duplicate
    page.evaluate("""
        (() => {
            const tu = {
                id: 'test-svg-005',
                name: 'chart_tool',
                input: {},
                result: 'Chart: <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><circle cx="50" cy="50" r="40" fill="green"/></svg>',
                status: 'complete'
            };
            injectToolVisualContent(tu);
        })()
    """)
    time.sleep(0.2)
    svg_count = page.evaluate("""
        document.querySelectorAll('[data-visual-id="svg-test-svg-005"]').length
    """)
    record("injectToolVisualContent: dedup prevents duplicate SVG", svg_count == 1, f"count={svg_count}")

    # 2g. No visual content: plain text result should not inject anything
    before_count = page.evaluate("document.querySelectorAll('.tool-visual-content').length")
    page.evaluate("""
        (() => {
            const tu = {
                id: 'test-text-006',
                name: 'text_tool',
                input: {},
                result: 'This is just plain text with no visual content.',
                status: 'complete'
            };
            injectToolVisualContent(tu);
        })()
    """)
    time.sleep(0.2)
    after_count = page.evaluate("document.querySelectorAll('.tool-visual-content').length")
    record("injectToolVisualContent: no injection for plain text result", before_count == after_count,
           f"before={before_count}, after={after_count}")

    # 2h. Error result should not trigger visual injection
    page.evaluate("""
        (() => {
            const tu = {
                id: 'test-err-007',
                name: 'failing_tool',
                input: {},
                result: { error: 'Tool execution failed' },
                status: 'complete'
            };
            // Note: in the SSE handler we already gate on !result.error,
            // but test the function directly to confirm it handles gracefully
            injectToolVisualContent(tu);
        })()
    """)
    time.sleep(0.2)
    err_count = page.evaluate("document.querySelectorAll('.tool-visual-content').length")
    record("injectToolVisualContent: error result handled gracefully", err_count == after_count,
           f"count unchanged: {err_count}")

    # 2i. Replay from historical messages (replayToolVisualContent)
    # Clear previous visual elements
    page.evaluate("""
        document.querySelectorAll('[data-visual-id]').forEach(el => el.remove());
    """)

    page.evaluate("""
        (() => {
            const messages = [
                {
                    role: 'assistant',
                    content: [
                        {
                            type: 'tool_use',
                            id: 'hist-exc-001',
                            name: 'excalidraw__create_view',
                            input: {
                                elements: '[{"type":"rectangle","id":"r1","x":10,"y":10,"width":100,"height":60,"strokeColor":"#000","backgroundColor":"transparent","fillStyle":"hachure","strokeWidth":1,"roughness":1,"opacity":100}]'
                            }
                        }
                    ]
                },
                {
                    role: 'user',
                    content: [
                        {
                            type: 'tool_result',
                            tool_use_id: 'hist-exc-001',
                            content: { content: [{ type: 'text', text: 'Diagram displayed!' }] }
                        }
                    ]
                },
                {
                    role: 'assistant',
                    content: [
                        {
                            type: 'tool_use',
                            id: 'hist-svg-002',
                            name: 'chart_tool',
                            input: {}
                        }
                    ]
                },
                {
                    role: 'user',
                    content: [
                        {
                            type: 'tool_result',
                            tool_use_id: 'hist-svg-002',
                            content: 'Here is your chart: <svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="80" height="80" fill="blue"/></svg>'
                        }
                    ]
                }
            ];
            const container = document.getElementById('chat-content');
            replayToolVisualContent(messages, container);
        })()
    """)
    time.sleep(0.5)

    hist_exc = page.evaluate("document.querySelector('[data-visual-id=\"excalidraw-hist-exc-001\"]') !== null")
    record("replayToolVisualContent: excalidraw from history rendered", hist_exc)

    hist_svg = page.evaluate("document.querySelector('[data-visual-id=\"svg-hist-svg-002\"]') !== null")
    record("replayToolVisualContent: SVG from history rendered", hist_svg)

    # Cleanup test elements
    page.evaluate("""
        document.querySelectorAll('.tool-visual-content, .artifact-container, [data-visual-id]').forEach(el => el.remove());
    """)


# ================================================================
# Test Suite 3: buildExcalidrawPreview
# ================================================================
def test_excalidraw_preview(page):
    print("\n=== Test Suite 3: Excalidraw Preview Builder ===")

    # 3a. Valid elements produce SVG content
    result = page.evaluate("""
        buildExcalidrawPreview([
            { type: 'rectangle', x: 0, y: 0, width: 100, height: 50, id: 'r1',
              strokeColor: '#000', backgroundColor: 'transparent', fillStyle: 'hachure',
              strokeWidth: 1, roughness: 1, opacity: 100 }
        ])
    """)
    has_svg = "<svg" in result.lower() and "<rect" in result.lower()
    record("buildExcalidrawPreview: valid elements → SVG output", has_svg)

    # 3b. Contains excalidraw label
    has_excalidraw_label = "excalidraw" in result.lower()
    record("buildExcalidrawPreview: includes Excalidraw label", has_excalidraw_label)

    # 3c. Empty elements returns empty string
    empty_result = page.evaluate("buildExcalidrawPreview([])")
    record("buildExcalidrawPreview: empty elements → empty string", empty_result == "")

    # 3d. String input (JSON) is handled
    str_result = page.evaluate("""
        buildExcalidrawPreview(JSON.stringify([
            { type: 'ellipse', x: 10, y: 10, width: 80, height: 80, id: 'e1',
              strokeColor: '#000', backgroundColor: 'transparent', fillStyle: 'hachure',
              strokeWidth: 1, roughness: 1, opacity: 100 }
        ]))
    """)
    record("buildExcalidrawPreview: string JSON input handled", "<ellipse" in str_result.lower())

    # 3e. Filters out cameraUpdate elements
    filtered_result = page.evaluate("""
        buildExcalidrawPreview([
            { type: 'cameraUpdate', x: 0, y: 0 },
        ])
    """)
    record("buildExcalidrawPreview: filters cameraUpdate → empty", filtered_result == "")


# ================================================================
# Test Suite 4: loadToolVisualImages (integration with backend)
# ================================================================
def test_load_visual_images(page):
    print("\n=== Test Suite 4: loadToolVisualImages (backend integration) ===")

    # Use a real image file that we know exists
    test_image = "/Users/awsdawei/claude/springo/aliyun-servers.png"

    # Create a container with tool-visual-image div
    page.evaluate(f"""
        (() => {{
            const container = document.createElement('div');
            container.id = 'test-load-images';
            container.innerHTML = '<div class="tool-visual-image" data-src="{test_image}"></div>';
            document.body.appendChild(container);
        }})()
    """)

    # Call loadToolVisualImages and debug
    debug_result = page.evaluate("""
        (async () => {
            const container = document.getElementById('test-load-images');
            try {
                const testFetch = await fetch(window.BASE_URL + '/v1/images/file?path=/Users/awsdawei/claude/springo/aliyun-servers.png');
                if (!testFetch.ok) return 'fetch-status: ' + testFetch.status;
                await loadToolVisualImages(container);
                return 'fetch-ok';
            } catch (e) {
                return 'fetch-error: ' + e.message;
            }
        })()
    """)
    print(f"  [DEBUG] fetch test: {debug_result}")

    # Wait for async load
    time.sleep(2)

    img_loaded = page.evaluate("""
        (() => {
            const container = document.getElementById('test-load-images');
            const img = container.querySelector('img');
            if (!img) return 'no img element';
            if (img.src.startsWith('blob:')) return 'loaded-blob';
            return 'img-src: ' + img.src.substring(0, 80);
        })()
    """)
    record("loadToolVisualImages: loads real image via /v1/images/file", img_loaded == "loaded-blob", img_loaded)

    # Test with non-existent file
    page.evaluate("""
        (() => {
            const container = document.getElementById('test-load-images');
            container.innerHTML += '<div class="tool-visual-image" data-src="/tmp/nonexistent_xyz.png"></div>';
            loadToolVisualImages(container);
        })()
    """)
    time.sleep(1)

    error_shown = page.evaluate("""
        (() => {
            const container = document.getElementById('test-load-images');
            const errorEl = container.querySelector('.tool-visual-error');
            return errorEl ? errorEl.textContent : 'no error element';
        })()
    """)
    record("loadToolVisualImages: non-existent file shows error", "not found" in error_shown.lower() or "failed" in error_shown.lower(), error_shown)

    # Cleanup
    page.evaluate("document.getElementById('test-load-images')?.remove()")


# ================================================================
# Main
# ================================================================
def main():
    print("=" * 60)
    print("  Visual Rendering Feature Tests")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-web-security"])
        page = browser.new_page()

        # Load the frontend
        page.goto(f"file://{FRONTEND_PATH}")
        time.sleep(2)

        # Set BASE_URL so fetch calls work
        page.evaluate(f'window.BASE_URL = "{BASE_URL}"')

        # Wait for app functions to be available
        if not wait_for_app(page):
            print("WARN: App functions may not be fully loaded, proceeding anyway")

        # Run test suites
        test_artifact_sandbox(page)
        test_tool_visual_content(page)
        test_excalidraw_preview(page)
        test_load_visual_images(page)

        browser.close()

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(f"  Results: {passed} passed, {failed} failed, {len(results)} total")
    print("=" * 60)

    if failed:
        print("\nFailed tests:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  - {r['name']}" + (f" ({r['detail']})" if r['detail'] else ""))

    return failed == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
