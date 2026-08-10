# -*- coding: utf-8 -*-
"""深入解析优酷搜索 JSON 数据结构"""
import json, re, urllib.request, urllib.parse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")

def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://www.youku.com/",
    })
    r = urllib.request.urlopen(req, timeout=20)
    return r.read().decode("utf-8", errors="replace")

keyword = "幼儿园大班 教学视频"
url = "https://so.youku.com/search_video/q_" + urllib.parse.quote(keyword)
html = fetch(url)
m = re.search(r"window\.__INITIAL_DATA__\s*=\s*(\{.*?\});", html, re.DOTALL)
data = json.loads(m.group(1))

# 分析 data 字段结构
d = data.get("data")
print("data type:", type(d).__name__)
if isinstance(d, dict):
    print("data keys:", list(d.keys()))
    for k in list(d.keys())[:10]:
        v = d[k]
        print(f"  {k}: {type(v).__name__}", end="")
        if isinstance(v, list):
            print(f" len={len(v)}")
            if v:
                print("    first item type:", type(v[0]).__name__)
                if isinstance(v[0], dict):
                    print("    first item keys:", list(v[0].keys())[:20])
                    # 打印第一个条目的标题类字段
                    for fk, fv in v[0].items():
                        if isinstance(fv, str) and len(fv) < 100:
                            print(f"      {fk}: {fv[:70]}")
        elif isinstance(v, str):
            print(f" = {v[:80]}")
        else:
            print()
elif isinstance(d, list):
    print("data len:", len(d))
    if d:
        print("first item:", json.dumps(d[0], ensure_ascii=False)[:500])
