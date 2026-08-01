"""
docker_ps - Docker 容器列表工具

可直接调用:
    docker_ps(args) -> str
"""
import subprocess

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "docker_ps",
            "description": "列出当前运行的 Docker 容器列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "all": {"type": "boolean", "description": "是否显示所有容器（包括已停止的）"}
                }
            }
        },
        "display": {"name_cn": "Docker容器", "description_cn": "列出运行中的Docker容器", "icon": "fa-docker"}
    }
]

def docker_ps(args):
    """列出 Docker 容器 — 可直接调用

    @param args: dict - {"all": true/false}
    @return str - 容器列表
    """
    show_all = args.get("all", False) if isinstance(args, dict) else False
    try:
        cmd = ["docker", "ps"]
        if show_all:
            cmd.append("-a")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            output = result.stdout.strip()
            if output:
                return f"Docker:\n{output}"
            return "没有运行的容器"
        return f"Docker 失败: {result.stderr.strip()}"
    except FileNotFoundError:
        return "未找到 Docker 命令"
    except subprocess.TimeoutExpired:
        return "执行超时"
    except Exception as e:
        return f"执行失败: {e}"