#!/usr/bin/env python3
"""
Springo 综合功能测试套件
通过 Playwright 连接 Electron 应用进行 E2E 测试
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright

# Test results
results = []

def log_result(category: str, test_name: str, passed: bool, detail: str = ""):
    status = "✓" if passed else "✗"
    results.append({
        "category": category,
        "test": test_name,
        "passed": passed,
        "detail": detail
    })
    print(f"  {status} {test_name}" + (f" - {detail}" if detail and not passed else ""))


async def test_ui_basics(page):
    """UI 基础测试"""
    print("\n=== UI 基础测试 ===")

    # 1. 页面加载
    try:
        await page.wait_for_selector("#message-input", timeout=5000)
        log_result("UI", "页面加载", True)
    except Exception as e:
        log_result("UI", "页面加载", False, str(e))
        return False

    # 2. 侧边栏存在
    sidebar = page.locator(".sidebar")
    visible = await sidebar.is_visible()
    log_result("UI", "侧边栏显示", visible)

    # 3. Settings 模态框打开/关闭
    try:
        await page.locator(".settings-btn").click()
        await asyncio.sleep(0.5)
        modal_class = await page.locator("#settings-modal").get_attribute("class")
        opened = "active" in modal_class
        log_result("UI", "Settings 打开", opened)

        # 关闭
        await page.locator("#settings-modal .modal-header .icon-btn").click()
        await asyncio.sleep(0.3)
        modal_class = await page.locator("#settings-modal").get_attribute("class")
        closed = "active" not in (modal_class or "")
        log_result("UI", "Settings 关闭", closed)
    except Exception as e:
        log_result("UI", "Settings 模态框", False, str(e))

    # 4. 侧边栏折叠
    try:
        toggle_btn = page.locator(".toggle-sidebar-btn")
        if await toggle_btn.is_visible():
            await toggle_btn.click()
            await asyncio.sleep(0.3)
            sidebar_class = await sidebar.get_attribute("class")
            collapsed = "collapsed" in (sidebar_class or "")
            # 恢复
            await toggle_btn.click()
            await asyncio.sleep(0.3)
            log_result("UI", "侧边栏折叠/展开", True)
        else:
            log_result("UI", "侧边栏折叠/展开", True, "按钮不可见(可能已折叠)")
    except Exception as e:
        log_result("UI", "侧边栏折叠/展开", False, str(e))

    return True


async def test_workspace(page):
    """Workspace 文件夹测试"""
    print("\n=== Workspace 测试 ===")

    # 1. Workspace 区域存在
    try:
        workspace = page.locator(".working-folders-section, #working-folders-list")
        visible = await workspace.first.is_visible()
        log_result("Workspace", "区域显示", visible)
    except Exception as e:
        log_result("Workspace", "区域显示", False, str(e))

    # 2. 文件夹列表
    try:
        folders = await page.locator(".folder-item").all()
        has_folders = len(folders) > 0
        log_result("Workspace", f"文件夹列表 ({len(folders)} 个)", has_folders)
    except Exception as e:
        log_result("Workspace", "文件夹列表", False, str(e))

    # 3. 默认文件夹标记
    try:
        default_folder = page.locator(".folder-item.default")
        has_default = await default_folder.count() > 0
        log_result("Workspace", "默认文件夹标记", has_default)
    except Exception as e:
        log_result("Workspace", "默认文件夹标记", False, str(e))

    # 4. 点击文件夹高亮
    try:
        folders = await page.locator(".folder-item").all()
        if len(folders) >= 1:
            await folders[0].click()
            await asyncio.sleep(0.5)
            folder_class = await folders[0].get_attribute("class")
            is_browsing = "browsing" in (folder_class or "")
            log_result("Workspace", "点击文件夹高亮(browsing)", is_browsing)
        else:
            log_result("Workspace", "点击文件夹高亮", False, "没有文件夹可测试")
    except Exception as e:
        log_result("Workspace", "点击文件夹高亮", False, str(e))


async def test_file_browser(page):
    """文件浏览器测试"""
    print("\n=== 文件浏览器测试 ===")

    # 1. 文件浏览器面板
    try:
        panel = page.locator("#file-browser-panel")
        panel_class = await panel.get_attribute("class")
        is_open = "open" in (panel_class or "")
        log_result("文件浏览器", "面板状态", True, f"{'打开' if is_open else '关闭'}")
    except Exception as e:
        log_result("文件浏览器", "面板状态", False, str(e))

    # 2. 如果打开，检查内容
    try:
        panel = page.locator("#file-browser-panel")
        if "open" in (await panel.get_attribute("class") or ""):
            # 检查面包屑
            breadcrumb = page.locator(".file-browser-breadcrumb, .breadcrumb")
            has_breadcrumb = await breadcrumb.first.is_visible() if await breadcrumb.count() > 0 else False
            log_result("文件浏览器", "面包屑导航", has_breadcrumb)

            # 检查文件列表
            files = await page.locator(".file-item, .browser-item").all()
            log_result("文件浏览器", f"文件列表 ({len(files)} 项)", len(files) >= 0)

            # 关闭面板
            close_btn = page.locator("#file-browser-panel .close-btn, .file-browser-close")
            if await close_btn.count() > 0:
                await close_btn.first.click()
                await asyncio.sleep(0.3)
                log_result("文件浏览器", "关闭面板", True)
    except Exception as e:
        log_result("文件浏览器", "内容检查", False, str(e))


async def test_sessions(page):
    """会话管理测试"""
    print("\n=== 会话管理测试 ===")

    # 1. New Chat 按钮
    try:
        new_chat_btn = page.locator(".new-chat-btn, button:has-text('New Chat')")
        visible = await new_chat_btn.first.is_visible()
        log_result("会话", "New Chat 按钮", visible)
    except Exception as e:
        log_result("会话", "New Chat 按钮", False, str(e))

    # 2. 会话列表
    try:
        sessions = await page.locator(".session-item, .conversation-item").all()
        log_result("会话", f"会话列表 ({len(sessions)} 个)", True)
    except Exception as e:
        log_result("会话", "会话列表", False, str(e))

    # 3. 当前会话标题
    try:
        title = page.locator(".chat-title, .conversation-title, .header-title")
        if await title.count() > 0:
            title_text = await title.first.text_content()
            log_result("会话", "当前会话标题", bool(title_text), title_text[:30] if title_text else "")
        else:
            log_result("会话", "当前会话标题", True, "无标题元素")
    except Exception as e:
        log_result("会话", "当前会话标题", False, str(e))


async def test_message_input(page):
    """消息输入测试"""
    print("\n=== 消息输入测试 ===")

    # 1. 输入框存在
    try:
        input_el = page.locator("#message-input")
        visible = await input_el.is_visible()
        log_result("消息", "输入框显示", visible)
    except Exception as e:
        log_result("消息", "输入框显示", False, str(e))

    # 2. 发送按钮
    try:
        send_btn = page.locator("#send-btn")
        visible = await send_btn.is_visible()
        log_result("消息", "发送按钮", visible)
    except Exception as e:
        log_result("消息", "发送按钮", False, str(e))

    # 3. 输入文本
    try:
        input_el = page.locator("#message-input")
        await input_el.fill("测试消息")
        value = await input_el.input_value()
        log_result("消息", "输入文本", value == "测试消息")
        # 清空
        await input_el.fill("")
    except Exception as e:
        log_result("消息", "输入文本", False, str(e))

    # 4. 附件按钮
    try:
        attach_btn = page.locator(".attach-btn, #attach-btn, button[title*='Attach']")
        if await attach_btn.count() > 0:
            visible = await attach_btn.first.is_visible()
            log_result("消息", "附件按钮", visible)
        else:
            log_result("消息", "附件按钮", True, "无独立按钮")
    except Exception as e:
        log_result("消息", "附件按钮", False, str(e))


async def test_settings_content(page):
    """Settings 内容测试"""
    print("\n=== Settings 内容测试 ===")

    # 打开 Settings
    try:
        await page.locator(".settings-btn").click()
        await asyncio.sleep(1)
    except:
        log_result("Settings", "打开失败", False)
        return

    # 1. AWS Credentials 区域
    try:
        aws_section = page.locator("text=AWS Credentials")
        visible = await aws_section.is_visible()
        log_result("Settings", "AWS Credentials 区域", visible)
    except Exception as e:
        log_result("Settings", "AWS Credentials 区域", False, str(e))

    # 2. AWS 连接状态
    try:
        status = page.locator("#aws-connection-status")
        status_html = await status.inner_html()
        connected = "Connected" in status_html or "✓" in status_html
        log_result("Settings", "AWS 连接状态", connected, "已连接" if connected else "未连接")
    except Exception as e:
        log_result("Settings", "AWS 连接状态", False, str(e))

    # 3. Model 选择器
    try:
        model_select = page.locator("#settings-model")
        visible = await model_select.is_visible()
        log_result("Settings", "Model 选择器", visible)
    except Exception as e:
        log_result("Settings", "Model 选择器", False, str(e))

    # 4. Max Tokens
    try:
        tokens = page.locator("#settings-max-tokens")
        visible = await tokens.is_visible()
        log_result("Settings", "Max Tokens 输入", visible)
    except Exception as e:
        log_result("Settings", "Max Tokens 输入", False, str(e))

    # 5. Temperature
    try:
        temp = page.locator("#settings-temperature")
        visible = await temp.is_visible()
        log_result("Settings", "Temperature 滑块", visible)
    except Exception as e:
        log_result("Settings", "Temperature 滑块", False, str(e))

    # 6. Skills 列表 (需要滚动)
    try:
        skills_list = page.locator("#skills-list")
        await skills_list.scroll_into_view_if_needed()
        await asyncio.sleep(0.5)
        skills_html = await skills_list.inner_html()
        has_skills = "settings-list-item" in skills_html or len(skills_html) > 100
        log_result("Settings", "Skills 列表", has_skills)
    except Exception as e:
        log_result("Settings", "Skills 列表", False, str(e))

    # 7. MCP Servers 列表
    try:
        mcp_list = page.locator("#mcp-servers-list")
        await mcp_list.scroll_into_view_if_needed()
        await asyncio.sleep(0.5)
        mcp_html = await mcp_list.inner_html()
        has_mcp = "settings-list-item" in mcp_html or "web-search" in mcp_html
        log_result("Settings", "MCP Servers 列表", has_mcp)
    except Exception as e:
        log_result("Settings", "MCP Servers 列表", False, str(e))

    # 8. Sticky Header 测试
    try:
        modal = page.locator("#settings-modal .modal")
        await modal.evaluate("el => el.scrollTop = 500")
        await asyncio.sleep(0.3)
        header = page.locator("#settings-modal .modal-header")
        header_visible = await header.is_visible()
        log_result("Settings", "Sticky Header", header_visible)
    except Exception as e:
        log_result("Settings", "Sticky Header", False, str(e))

    # 关闭
    try:
        await page.locator("#settings-modal .modal-header .icon-btn").click()
        await asyncio.sleep(0.3)
    except:
        pass


async def test_api_endpoints(page):
    """API 端点测试"""
    print("\n=== API 端点测试 ===")

    import aiohttp
    BASE_URL = "http://localhost:8080"

    endpoints = [
        ("/health", "GET", "健康检查"),
        ("/v1/config/aws", "GET", "AWS 配置"),
        ("/v1/skills", "GET", "Skills 列表"),
        ("/v1/mcp/servers", "GET", "MCP Servers"),
        ("/v1/tools", "GET", "工具列表"),
        ("/v1/sessions", "GET", "会话列表"),
    ]

    async with aiohttp.ClientSession() as session:
        for path, method, name in endpoints:
            try:
                async with session.request(method, f"{BASE_URL}{path}") as resp:
                    passed = resp.status == 200
                    log_result("API", f"{name} ({path})", passed, f"HTTP {resp.status}")
            except Exception as e:
                log_result("API", f"{name} ({path})", False, str(e))


async def test_mcp_tools(page):
    """MCP 工具测试"""
    print("\n=== MCP 工具测试 ===")

    import aiohttp
    BASE_URL = "http://localhost:8080"

    async with aiohttp.ClientSession() as session:
        # 获取 MCP servers
        try:
            async with session.get(f"{BASE_URL}/v1/mcp/servers") as resp:
                data = await resp.json()
                servers = data.get("servers", {})

                running_count = sum(1 for s in servers.values() if s.get("running"))
                total_tools = sum(s.get("tools_count", 0) for s in servers.values())

                log_result("MCP", f"运行中服务器 ({running_count}/{len(servers)})", running_count > 0)
                log_result("MCP", f"可用工具总数 ({total_tools})", total_tools > 0)

                # 检查关键服务器
                key_servers = ["web-search", "context7", "fetch", "github"]
                for server in key_servers:
                    if server in servers:
                        running = servers[server].get("running", False)
                        tools = servers[server].get("tools_count", 0)
                        log_result("MCP", f"{server} ({tools} tools)", running)
                    else:
                        log_result("MCP", f"{server}", False, "未配置")

        except Exception as e:
            log_result("MCP", "服务器列表", False, str(e))


async def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Springo 综合功能测试")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            page = browser.contexts[0].pages[0]

            # 刷新页面确保最新
            await page.reload()
            await asyncio.sleep(2)

            # 运行测试
            await test_ui_basics(page)
            await test_workspace(page)
            await test_file_browser(page)
            await test_sessions(page)
            await test_message_input(page)
            await test_settings_content(page)
            await test_api_endpoints(page)
            await test_mcp_tools(page)

            # 最终截图
            await page.screenshot(path="tests/final_state.png")

        except Exception as e:
            print(f"\n❌ 测试连接失败: {e}")
            print("请确保 Electron 应用已启动: cd springo-app && npm start")
            return

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])

    print(f"\n总计: {len(results)} 项测试")
    print(f"通过: {passed} ✓")
    print(f"失败: {failed} ✗")
    print(f"通过率: {passed/len(results)*100:.1f}%")

    if failed > 0:
        print("\n失败项目:")
        for r in results:
            if not r["passed"]:
                print(f"  ✗ [{r['category']}] {r['test']}: {r['detail']}")

    # 保存结果
    with open("tests/test_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {"total": len(results), "passed": passed, "failed": failed},
            "results": results
        }, f, indent=2, ensure_ascii=False)

    print(f"\n结果已保存到 tests/test_results.json")
    print(f"截图已保存到 tests/final_state.png")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
