# -*- coding: utf-8 -*-
"""探测国家智慧教育平台搜索接口"""
import json, urllib.request, urllib.parse, traceback

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")

def probe(url, extra_headers=None):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Referer": "https://basic.smartedu.cn/",
            "Accept": "application/json, text/plain, */*",
        })
        if extra_headers:
            for k, v in extra_headers.items():
                req.add_header(k, v)
        r = urllib.request.urlopen(req, timeout=15)
        body = r.read().decode("utf-8", errors="replace")
        print("URL:", url)
        print("STATUS:", r.status, "LEN:", len(body))
        print("BODY:", body[:500])
        print("---")
    except Exception as e:
        print("URL:", url)
        print("ERROR:", e)
        print("---")

probe("https://basic.smartedu.cn/")
probe("https://basic.smartedu.cn/api/home/index")
probe("https://so.smartedu.cn/sousou/searchList?keyword=%E5%B9%BC%E5%84%BF%E5%9B%AD%E5%A4%A7%E7%8F%AD&type=video")
