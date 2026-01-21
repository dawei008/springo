#!/usr/bin/env python3
"""
验证测试确实在 Electron 应用内运行
"""

import asyncio
from playwright.async_api import async_playwright


async def verify_electron():
    print("=" * 60)
    print("验证测试环境")
    print("=" * 60)

    async with async_playwright() as p:
        # 连接到 Electron 应用
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]

        # 获取 Electron 环境信息
        info = await page.evaluate('''
            () => {
                return {
                    // 页面信息
                    title: document.title,
                    url: window.location.href,

                    // Electron 特有 API
                    hasElectronAPI: typeof window.electronAPI !== 'undefined',
                    electronAPIMethods: window.electronAPI ? Object.keys(window.electronAPI) : [],

                    // 判断运行环境
                    userAgent: navigator.userAgent,
                    isElectron: navigator.userAgent.includes('Electron'),

                    // 应用变量
                    hasBaseURL: typeof BASE_URL !== 'undefined',
                    baseURL: typeof BASE_URL !== 'undefined' ? BASE_URL : null,
                }
            }
        ''')

        print(f"\n[1] 页面信息:")
        print(f"    标题: {info['title']}")
        print(f"    URL: {info['url']}")

        print(f"\n[2] Electron 环境检测:")
        print(f"    是否 Electron: {'✅ 是' if info['isElectron'] else '❌ 否'}")
        print(f"    User-Agent: {info['userAgent'][:80]}...")

        print(f"\n[3] Electron API:")
        print(f"    electronAPI 存在: {'✅ 是' if info['hasElectronAPI'] else '❌ 否'}")
        if info['electronAPIMethods']:
            print(f"    可用方法: {', '.join(info['electronAPIMethods'][:5])}...")

        print(f"\n[4] 应用配置:")
        print(f"    BASE_URL 存在: {'✅ 是' if info['hasBaseURL'] else '❌ 否'}")
        print(f"    BASE_URL 值: {info['baseURL']}")

        # 在 Electron 内执行一个测试调用
        print(f"\n[5] 在 Electron 内执行 API 调用:")
        result = await page.evaluate('''
            async () => {
                const response = await fetch(BASE_URL + '/health');
                const data = await response.json();
                return {
                    status: data.status,
                    backend: data.backend,
                    calledFrom: 'Electron 渲染进程'
                };
            }
        ''')
        print(f"    健康检查: {result['status']}")
        print(f"    后端类型: {result['backend']}")
        print(f"    调用来源: {result['calledFrom']}")

        print("\n" + "=" * 60)
        if info['isElectron'] and info['hasElectronAPI']:
            print("✅ 确认：测试在 Electron 应用内运行")
        else:
            print("❌ 警告：可能不是在 Electron 内运行")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(verify_electron())
