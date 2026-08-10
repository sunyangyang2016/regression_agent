# -*- coding: utf-8 -*-
"""从优酷搜索页提取幼儿园大班教学视频列表"""
import json, re, urllib.request, urllib.parse, sys

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")

def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://www.youku.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    r = urllib.request.urlopen(req, timeout=20)
    return r.read().decode("utf-8", errors="replace")

keyword = "幼儿园大班 教学视频"
url = "https://so.youku.com/search_video/q_" + urllib.parse.quote(keyword)
html = fetch(url)
print("PAGE LEN:", len(html))

# 尝试提取 JSON 数据
# 优酷搜索页通常有 window.__INITIAL_DATA__ 或 appData
patterns = [
    r"window\.__INITIAL_DATA__\s*=\s*(\{.*?\});",
    r"window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});",
    r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});",
    r"window\.appData\s*=\s*(\{.*?\});",
]
found = False
for pat in patterns:
    m = re.search(pat, html, re.DOTALL)
    if m:
        print("FOUND PATTERN:", pat[:50])
        data = json.loads(m.group(1))
        print("JSON keys:", list(data.keys())[:20])
        found = True
        # 递归查找视频标题
        def walk(obj, path="", depth=0):
            if depth > 4:
                return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("title", "name", "video_title") and isinstance(v, str) and v:
                        print("TITLE @", path + "/" + k, ":", v[:60])
                    walk(v, path + "/" + k, depth + 1)
            elif isinstance(obj, list):
                for i, v in enumerate(obj[:3]):
                    walk(v, path + f"[{i}]", depth + 1)
        walk(data)
        break

if not found:
    print("未找到已知 JSON 模式，尝试提取 <script> 中的 video 数据...")
    # 尝试从 HTML 中提取视频链接
    vid_ids = re.findall(r"id_([A-Za-z0-9=]+)", html)
    print("vid ids found:", len(vid_ids), vid_ids[:5])
    # 提取标题
    titles = re.findall(r"<title>([^<]+)</title>", html)
    print("titles:", titles[:5])
    # 尝试通用的 script JSON 提取
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    print("scripts:", len(scripts))
    for s in scripts:
        if "video" in s.lower() and len(s) > 500:
            print("SCRIPT SAMPLE:", s[:300])
            break
