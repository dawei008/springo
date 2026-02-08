#!/usr/bin/env python3
"""
iTerm2 SSM Session Controller
通过 iTerm2 Python API 打开 SSM 会话并执行命令
"""

import iterm2
import asyncio
import sys
import time

async def main(connection):
    app = await iterm2.async_get_app(connection)
    
    # 创建新窗口或使用当前窗口
    window = app.current_terminal_window
    if window is None:
        window = await iterm2.Window.async_create(connection)
        if window is None:
            print("ERROR: Could not create window")
            return
    
    # 创建新 tab
    tab = await window.async_create_tab()
    session = tab.current_session
    
    # 启动 SSM 会话
    ssm_command = "aws ssm start-session --region us-west-2 --target i-0b97257c660e08a0e"
    await session.async_send_text(ssm_command + "\n")
    
    print("SSM session started in iTerm2")
    print("Session ID:", session.session_id)
    
    # 等待连接建立
    await asyncio.sleep(3)
    
    # 如果有命令参数，执行它
    if len(sys.argv) > 1:
        command = " ".join(sys.argv[1:])
        await session.async_send_text(command + "\n")
        print(f"Executed: {command}")

# 运行脚本
iterm2.run_until_complete(main)
