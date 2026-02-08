#!/usr/bin/env python3
"""
SSM iTerm2 Controller
在 iTerm2 中打开 SSM 会话，并支持发送命令和获取输出
"""

import iterm2
import asyncio
import sys
import json
import os

# 全局变量
INSTANCE_ID = "i-0b97257c660e08a0e"
REGION = "us-west-2"
SESSION_FILE = ".ssm_session"

async def start_ssm_session(connection):
    """在 iTerm2 中启动 SSM 会话"""
    app = await iterm2.async_get_app(connection)
    window = app.current_terminal_window
    
    if window is None:
        window = await iterm2.Window.async_create(connection)
        if window is None:
            return {"error": "Could not create window"}
    
    # 创建新 tab 用于 SSM
    tab = await window.async_create_tab()
    session = tab.current_session
    session_id = session.session_id
    
    # 设置 tab 标题
    await session.async_set_name(f"SSM: {INSTANCE_ID}")
    
    # 启动 SSM 会话
    ssm_command = f"aws ssm start-session --region {REGION} --target {INSTANCE_ID}"
    await session.async_send_text(ssm_command + "\n")
    
    # 等待连接建立
    await asyncio.sleep(4)
    
    # 保存 session ID
    with open(SESSION_FILE, "w") as f:
        f.write(session_id)
    
    return {
        "status": "success",
        "session_id": session_id,
        "instance_id": INSTANCE_ID,
        "message": "SSM session started in iTerm2"
    }

async def send_command(connection, command, session_id):
    """向 SSM 会话发送命令"""
    app = await iterm2.async_get_app(connection)
    
    # 找到 SSM session
    for window in app.terminal_windows:
        for tab in window.tabs:
            session = tab.current_session
            if session.session_id == session_id:
                await session.async_send_text(command + "\n")
                await asyncio.sleep(1.5)  # 等待命令执行
                return {"status": "success", "command": command}
    
    return {"error": "SSM session not found", "session_id": session_id}

async def get_screen_content(connection, session_id):
    """获取当前屏幕内容"""
    app = await iterm2.async_get_app(connection)
    
    for window in app.terminal_windows:
        for tab in window.tabs:
            session = tab.current_session
            if session.session_id == session_id:
                # 获取屏幕内容
                screen = await session.async_get_screen_contents()
                lines = []
                for i in range(screen.number_of_lines):
                    line = screen.line(i)
                    lines.append(line.string)
                # 过滤空行
                content = "\n".join([l for l in lines if l.strip()])
                return {"status": "success", "content": content}
    
    return {"error": "SSM session not found", "session_id": session_id}

async def exec_and_read(connection, command, session_id):
    """执行命令并读取输出"""
    app = await iterm2.async_get_app(connection)
    
    for window in app.terminal_windows:
        for tab in window.tabs:
            session = tab.current_session
            if session.session_id == session_id:
                # 发送命令
                await session.async_send_text(command + "\n")
                await asyncio.sleep(2)  # 等待命令执行
                
                # 获取屏幕内容
                screen = await session.async_get_screen_contents()
                lines = []
                for i in range(screen.number_of_lines):
                    line = screen.line(i)
                    lines.append(line.string)
                
                content = "\n".join([l for l in lines if l.strip()])
                return {"status": "success", "command": command, "output": content}
    
    return {"error": "SSM session not found"}

async def main(connection):
    """主函数"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python ssm_iterm_controller.py start           - Start SSM session")
        print("  python ssm_iterm_controller.py exec <cmd>      - Execute command")
        print("  python ssm_iterm_controller.py read            - Read screen content")
        print("  python ssm_iterm_controller.py run <cmd>       - Exec and read output")
        return
    
    action = sys.argv[1]
    
    if action == "start":
        result = await start_ssm_session(connection)
        print(json.dumps(result, indent=2))
    
    elif action == "exec":
        if not os.path.exists(SESSION_FILE):
            print(json.dumps({"error": "No SSM session. Run 'start' first."}))
            return
        
        with open(SESSION_FILE, "r") as f:
            session_id = f.read().strip()
        
        if len(sys.argv) > 2:
            command = " ".join(sys.argv[2:])
            result = await send_command(connection, command, session_id)
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps({"error": "No command provided"}))
    
    elif action == "read":
        if not os.path.exists(SESSION_FILE):
            print(json.dumps({"error": "No SSM session. Run 'start' first."}))
            return
        
        with open(SESSION_FILE, "r") as f:
            session_id = f.read().strip()
        
        result = await get_screen_content(connection, session_id)
        print(json.dumps(result, indent=2))
    
    elif action == "run":
        if not os.path.exists(SESSION_FILE):
            print(json.dumps({"error": "No SSM session. Run 'start' first."}))
            return
        
        with open(SESSION_FILE, "r") as f:
            session_id = f.read().strip()
        
        if len(sys.argv) > 2:
            command = " ".join(sys.argv[2:])
            result = await exec_and_read(connection, command, session_id)
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps({"error": "No command provided"}))
    
    else:
        print(json.dumps({"error": f"Unknown action: {action}"}))

if __name__ == "__main__":
    iterm2.run_until_complete(main)
