# -*- coding: utf-8 -*-
"""探测更多智慧教育平台端点与优酷搜索"""
import json, urllib.request, urllib.parse, traceback

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")

def probe(url, referer="https://basic.smartedu.cn/"):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Referer": referer,
            "Accept": "application/json, text/plain, */*",
        })
        r = urllib.request.urlopen(req, timeout=15)
        body = r.read().decode("utf-8", errors="replace")
        print("URL:", url)
        print("STATUS:", r.status, "LEN:", len(body))
        print("BODY:", body[:400])
        print("---")
    except Exception as e:
        print("URL:", url)
        print("ERROR:", type(e).__name__, e)
        print("---")

# 学前教育相关站点探测
probe("https://www.smartedu.cn/")
probe("https://basic.smartedu.cn/eduResource")
probe("https://xueqian.smartedu.cn/")
# 尝试平台搜索接口（常见路径）
probe("https://basic.smartedu.cn/api/search?keyword=%E5%B9%BC%E5%84%BF%E5%9B%AD%E5%A4%A7%E7%8F%AD")
# 优酷站内搜索
probe("https://so.youku.com/search_video/q_%E5%B9%BC%E5%84%BF%E5%9B%AD%E5%A4%A7%E7%8F%AD%E6%95%99%E5%AD%A6%E8%A7%86%E9%A2%91", referer="https://www.youku.com/")
