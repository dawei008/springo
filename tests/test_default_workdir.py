#!/usr/bin/env python3
"""
E2E 测试: 默认工作目录设置
验证:
1. Settings 中显示默认工作目录设置
2. 默认值为 ~/Downloads
3. Workspace 面板不再显示设置默认按钮
"""

import asyncio
from playwright.async_api import async_playwright

async def main():
    print("\n" + "=" * 60)
    print("E2E 测试: 默认工作目录设置")
    print("=" * 60)

    async with async_playwright() as p:
        # 连接到 Electron
        print("\n1. 连接到 Electron 应用...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]
        print("   ✅ 已连接")

        # 刷新页面
        await page.reload()
        await asyncio.sleep(2)

        # 测试 1: 检查 Settings 中的默认工作目录设置
        print("\n2. 打开 Settings...")
        settings_btn = page.locator('.settings-btn')
        await settings_btn.click()
        await asyncio.sleep(0.5)

        # 检查设置输入框
        workdir_input = page.locator('#settings-default-workdir')
        is_visible = await workdir_input.is_visible()
        print(f"   默认工作目录输入框可见: {'✅' if is_visible else '❌'}")

        # 检查默认值
        value = await workdir_input.input_value()
        print(f"   当前值: {value}")
        has_default = value == '~/Downloads' or value.endswith('/Downloads')
        print(f"   默认值正确 (~/Downloads): {'✅' if has_default else '⚠️'}")

        # 检查 Browse 按钮
        browse_btn = page.locator('button:has-text("Browse")').first
        browse_visible = await browse_btn.is_visible()
        print(f"   Browse 按钮可见: {'✅' if browse_visible else '❌'}")

        # 关闭 Settings
        close_btn = page.locator('#settings-modal .icon-btn')
        await close_btn.click()
        await asyncio.sleep(0.3)

        # 测试 2: 检查 Workspace 面板不再显示设置默认按钮
        print("\n3. 检查 Workspace 面板...")

        # 先添加一个工作目录(如果没有的话)
        add_folder_btn = page.locator('.add-folder-btn')
        if await add_folder_btn.is_visible():
            # 检查是否有已存在的文件夹
            folder_items = page.locator('.folder-item')
            folder_count = await folder_items.count()

            if folder_count > 0:
                # 检查文件夹项是否还有 set-default-btn
                set_default_btn = page.locator('.set-default-btn')
                has_star_btn = await set_default_btn.count() > 0
                print(f"   文件夹数量: {folder_count}")
                print(f"   设置默认按钮已移除: {'✅' if not has_star_btn else '❌ (还有 ' + str(await set_default_btn.count()) + ' 个)'}")
            else:
                print("   ⚠️ 没有工作目录，跳过此检查")
        else:
            print("   ⚠️ 无法找到添加文件夹按钮")

        # 测试 3: 验证修改设置能保存
        print("\n4. 测试修改设置...")
        await settings_btn.click()
        await asyncio.sleep(0.5)

        # 修改值
        test_path = "~/Documents"
        await workdir_input.fill(test_path)
        print(f"   输入新路径: {test_path}")

        # 关闭保存
        await close_btn.click()
        await asyncio.sleep(0.3)

        # 重新打开验证
        await settings_btn.click()
        await asyncio.sleep(0.5)
        saved_value = await workdir_input.input_value()
        print(f"   保存后的值: {saved_value}")
        print(f"   设置保存正确: {'✅' if saved_value == test_path else '❌'}")

        # 恢复默认值
        await workdir_input.fill("~/Downloads")
        await close_btn.click()
        await asyncio.sleep(0.3)
        print("   已恢复默认值 ~/Downloads")

        # 截图
        screenshot_path = "/Users/awsdawei/claude/springo/tests/default_workdir_test.png"
        await page.screenshot(path=screenshot_path)
        print(f"\n5. 截图: {screenshot_path}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
