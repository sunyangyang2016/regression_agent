"""
Shell 命令执行工具 — 让 AI 可以执行 Git clone、npm install 等命令
修复：Windows pipe 阻塞问题，使用行读取 + 超时 kill 机制
"""
import subprocess
import json
import os
import sys
import time
import queue
import threading

NAME = "run_command"
DESCRIPTION = "执行 Shell 命令（如 git clone、npm install、pip install、ls、dir 等），返回命令输出结果"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "在本地系统执行 Shell 命令（如 git clone、npm install、pip install、dir、ls 等），返回命令的标准输出和错误输出。注意：长时间运行的命令会有超时限制。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的命令，如 git clone --depth 1 https://github.com/xxx/xxx.git C:\\path\\to\\dir"
                    },
                    "cwd": {
                        "type": "string",
                        "description": "工作目录（可选），默认为项目根目录"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间（秒），默认 60，最大 300"
                    }
                },
                "required": ["command"]
            }
        }
    }
]

_mcp_bridge = None


def set_mcp_bridge(bridge):
    global _mcp_bridge
    _mcp_bridge = bridge


def _read_output(process, timeout: int, on_line: callable = None) -> str:
    """
    安全的输出读取函数（解决 Windows pipe 阻塞问题）
    
    使用行读取而非逐字节读取，并确保超时后 kill 进程
    支持 on_line 回调实现实时输出
    """
    output_lines = []
    line_queue = queue.Queue()
    STOP = object()
    
    def reader():
        """子线程：读取 stdout 的行，支持 \r 进度条即时输出"""
        try:
            buf = ""
            while True:
                char = process.stdout.read(1)
                if not char:
                    break
                if char == '\r':
                    # \r = 同一行刷新（如 pip 下载进度），立即输出
                    if buf:
                        line_queue.put(('progress', buf))
                    buf = ""
                elif char == '\n':
                    # \n = 新行
                    if buf:
                        line_queue.put(('line', buf))
                    buf = ""
                else:
                    buf += char
            if buf:
                line_queue.put(('line', buf))
        except Exception:
            pass
        finally:
            line_queue.put(('stop', None))
    
    t = threading.Thread(target=reader, daemon=True)
    t.start()
    
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        try:
            item = line_queue.get(timeout=1)
            if item[0] == 'stop':
                break
            text = item[1]
            if text:
                if item[0] == 'line':
                    output_lines.append(text)
                if on_line:
                    on_line(text)
        except queue.Empty:
            # 检查进程是否已退出
            if process.poll() is not None:
                # 进程已退出，等 reader 线程结束
                t.join(timeout=2)
                # 清空剩余行
                while True:
                    try:
                        item = line_queue.get_nowait()
                        if item[0] == 'stop':
                            break
                        text = item[1]
                        if text:
                            if item[0] == 'line':
                                output_lines.append(text)
                            if on_line:
                                on_line(text)
                    except queue.Empty:
                        break
                break
            continue
    else:
        # 超时！强制 kill 进程
        try:
            process.kill()
        except Exception:
            pass
        # 等待进程结束
        process.wait(timeout=3)
        output_lines.append(f"⏱️ 命令执行超时 ({timeout}秒)，已强制终止")
        return "\n".join(output_lines)
    
    return "\n".join(output_lines)


def run_command(arguments: dict) -> str:
    """执行 Shell 命令并返回输出，同时将输出打印到 UI 日志"""
    command = arguments.get("command", "")
    cwd = arguments.get("cwd", None)
    timeout = min(arguments.get("timeout", 60), 300)
    
    if not command:
        return "❌ 请提供要执行的命令"
    
    def log(msg):
        print(msg)
    
    log(f"[run_command] 执行: {command}")
    if cwd:
        log(f"[run_command] 工作目录: {cwd}")
    
    process = None
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,       # 使用 text 模式，readline 直接返回 str
            bufsize=1,       # 行缓冲
        )
        
        # 实时输出每一行，让 pip install 等长时间命令可见进度
        def on_line(line):
            print(f"  {line}")
        
        output = _read_output(process, timeout, on_line=on_line)
        
        # 关闭 stdout
        try:
            process.stdout.close()
        except Exception:
            pass
        
        return_code = process.poll()
        # 如果进程还没退出，wait 一下
        if return_code is None:
            try:
                return_code = process.wait(timeout=3)
            except Exception:
                return_code = -1
        
        if return_code == 0:
            log(f"[run_command] ✅ 成功 (code=0)")
            return f"✅ 命令执行成功 (code=0):\n{output[:4000]}"
        else:
            log(f"[run_command] ⚠️ 返回 code={return_code}")
            return f"⚠️ 命令返回 code={return_code}:\n{output[:4000]}"
            
    except Exception as e:
        if process:
            try:
                process.kill()
            except Exception:
                pass
        msg = f"❌ 执行失败: {str(e)[:200]}"
        log(msg)
        return msg