"""
github_get_issue - GitHub Issue 获取工具

可直接调用:
    github_get_issue(args) -> str
"""
import os, urllib.request, urllib.error, json

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "github_get_issue",
            "description": "获取 GitHub 仓库指定 Issue 的详细信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "仓库所有者"},
                    "repo": {"type": "string", "description": "仓库名称"},
                    "issue_number": {"type": "integer", "description": "Issue 编号"}
                },
                "required": ["owner", "repo", "issue_number"]
            }
        },
        "display": {"name_cn": "GitHub Issue", "description_cn": "获取GitHub Issue详情", "icon": "fa-github-alt"}
    }
]

def github_get_issue(args):
    """获取 GitHub Issue — 可直接调用

    @param args: dict - {"owner": "...", "repo": "...", "issue_number": 123}
    @return str - Issue 信息
    """
    owner = args.get("owner", "")
    repo = args.get("repo", "")
    issue_number = args.get("issue_number", 0)
    if not owner or not repo or not issue_number:
        return "请提供 owner、repo 和 issue_number"
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return f"标题: {data.get('title', '')}\n状态: {data.get('state', '')}\n创建: {data.get('created_at', '')}"
    except urllib.error.HTTPError as e:
        return f"HTTP 错误: {e.code}"
    except Exception as e:
        return f"获取失败: {e}"