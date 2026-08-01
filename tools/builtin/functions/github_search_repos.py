"""
github_search_repos - GitHub 仓库搜索工具

可直接调用:
    github_search_repos(args) -> str
"""
import os, urllib.request, urllib.error, json

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "github_search_repos",
            "description": "搜索 GitHub 仓库，返回匹配的仓库列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"]
            }
        },
        "display": {"name_cn": "GitHub搜索", "description_cn": "搜索GitHub仓库", "icon": "fa-github"}
    }
]

def github_search_repos(args):
    """搜索 GitHub 仓库 — 可直接调用

    @param args: dict - {"query": "python"}
    @return str - 搜索结果列表
    """
    query = args.get("query", "") if isinstance(args, dict) else args
    if not query:
        return "请提供搜索关键词"
    try:
        url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("items", [])[:5]
            if not items:
                return "未找到匹配的仓库"
            result = []
            for item in items:
                result.append(f"  {item['full_name']} ({item['stargazers_count']}⭐)")
            return "搜索结果:\n" + "\n".join(result)
    except urllib.error.HTTPError as e:
        return f"HTTP 错误: {e.code}"
    except Exception as e:
        return f"搜索失败: {e}"