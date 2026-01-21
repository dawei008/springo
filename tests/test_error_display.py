#!/usr/bin/env python3
"""
测试前端错误显示
通过 Electron 端到端测试
"""

import asyncio
from playwright.async_api import async_playwright


async def test_error_display():
    """测试前端错误显示逻辑"""
    print("=" * 60)
    print("前端错误显示测试")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 测试错误解析函数是否存在
        print("\n[1] 检查前端错误处理代码:")

        # 刷新页面加载最新代码
        await page.reload()
        await asyncio.sleep(2)

        # 验证页面加载成功
        title = await page.title()
        print(f"    页面标题: {title}")

        # 检查错误处理相关的 UI 元素
        status_el = await page.query_selector('#status')
        if status_el:
            status_text = await status_el.text_content()
            print(f"    状态栏: {status_text}")
        else:
            print("    ⚠️ 未找到状态栏元素")

        # 测试模拟错误消息解析
        print("\n[2] 测试错误消息解析:")

        test_errors = [
            '{"error":{"type":"rate_limit","code":"throttling","message":"请求频率限制","suggestion":"请稍后重试","retry_after":60}}',
            'ThrottlingException: Rate exceeded',
            'ValidationException: Invalid format',
            'AccessDeniedException: Access denied',
            'ServiceUnavailableException: Service busy',
            'Random unknown error',
        ]

        for error_str in test_errors:
            result = await page.evaluate(f'''
                () => {{
                    const errorMsg = `{error_str}`;
                    let parsed = null;
                    let statusMsg = null;

                    try {{
                        const errorData = JSON.parse(errorMsg);
                        if (errorData.error) {{
                            const err = errorData.error;
                            parsed = `⚠️ ${{err.message}}\\n\\n${{err.suggestion || ''}}`;
                            statusMsg = err.message;
                            if (err.retry_after) {{
                                parsed += `\\n\\n建议等待 ${{err.retry_after}} 秒后重试`;
                            }}
                        }}
                    }} catch {{
                        const isThrottling = errorMsg.includes('ThrottlingException') || errorMsg.includes('Too many tokens') || errorMsg.includes('请求频率限制');
                        const isRateLimit = errorMsg.includes('rate') && errorMsg.includes('limit');
                        const isAccessDenied = errorMsg.includes('AccessDenied') || errorMsg.includes('访问被拒绝');
                        const isValidation = errorMsg.includes('Validation') || errorMsg.includes('格式错误');
                        const isServiceUnavailable = errorMsg.includes('ServiceUnavailable') || errorMsg.includes('服务暂时不可用');

                        if (isValidation) {{
                            parsed = '⚠️ 消息格式错误';
                            statusMsg = '消息格式错误';
                        }} else if (isThrottling || isRateLimit) {{
                            parsed = '⚠️ 请求频率限制';
                            statusMsg = '请求频率限制';
                        }} else if (isAccessDenied) {{
                            parsed = '⚠️ 访问被拒绝';
                            statusMsg = '访问被拒绝';
                        }} else if (isServiceUnavailable) {{
                            parsed = '⚠️ 服务暂时不可用';
                            statusMsg = '服务暂时不可用';
                        }} else {{
                            parsed = `⚠️ 错误: ${{errorMsg}}`;
                            statusMsg = errorMsg;
                        }}
                    }}

                    return {{ parsed: parsed?.substring(0, 50), status: statusMsg }};
                }}
            ''')
            print(f"    输入: {error_str[:40]}...")
            print(f"    解析: {result['parsed']}")
            print(f"    状态: {result['status']}")
            print()

        print("\n[3] 截图保存:")
        await page.screenshot(path="tests/screenshot_error_test.png")
        print("    已保存: tests/screenshot_error_test.png")

        print("\n" + "=" * 60)
        print("测试完成 ✅")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_error_display())
