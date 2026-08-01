"""
web_search - 工具

可直接调用:
    exec_web_search(args) -> str
"""
import json, os, urllib.request, urllib.parse

# ===== 工具定义 =====
TOOLS = [
    {
            "name": "web_search",
            "description": "搜索网络获取最新信息，返回相关搜索结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"]
            }
        },
]

def exec_web_search(args):
    """搜索网络获取最新信息 — 可直接调用
    
    @param args: dict - {"query": "搜索关键词"}
    @return str - 搜索结果
    """
    query = args.get("query", "")
    if not query:
        return "请提供搜索关键词"
    try:
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = []
            if data.get("AbstractText"):
                results.append(f"摘要: {data['AbstractText']}")
            for topic in data.get("RelatedTopics", [])[:5]:
                if "Text" in topic:
                    results.append(topic["Text"])
            if results:
                return f"搜索: {query}\n\n" + "\n".join(results)
            return f"搜索: {query} (无结果)"
    except Exception as e:
        return f"搜索失败: {e}"

