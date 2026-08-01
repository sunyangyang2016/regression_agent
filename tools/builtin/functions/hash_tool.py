"""
hash_tool - 工具

可直接调用:
    exec_hash_tool(args) -> str
"""
import os
import hashlib, base64, secrets
import json, os
import subprocess
import math

# ===== 工具定义 =====
TOOLS = [
    {
      "name": "hash_tool",
      "description": "生成哈希值、Base64编码/解码、Token等加密工具",
      "parameters": {
        "type": "object",
        "properties": {
          "action": {
            "type": "string",
            "description": "操作类型: md5, sha256, base64_encode, base64_decode, generate_token, generate_api_key"
          },
          "text": {
            "type": "string",
            "description": "要处理的文本"
          }
        },
        "required": [
          "action",
          "text"
        ]
      ,
        "display": {"name_cn": "哈希编码", "description_cn": "MD5/SHA256/Base64/Token生成", "icon": "fa-hashtag"}}
    ,
        "display": {"name_cn": "哈希编码", "description_cn": "MD5/SHA256/Base64/Token生成", "icon": "fa-hashtag"}},
]

def exec_hash_tool(args):
    action = args.get('action', '')
    text = args.get('text', '')
    if not action or not text:
        return '请提供 action 和 text'
    try:
        if action == 'md5':
            return hashlib.md5(text.encode()).hexdigest()
        elif action == 'sha256':
            return hashlib.sha256(text.encode()).hexdigest()
        elif action == 'base64_encode':
            return base64.b64encode(text.encode()).decode()
        elif action == 'base64_decode':
            return base64.b64decode(text).decode()
        elif action == 'generate_token':
            return secrets.token_hex(32)
        elif action == 'generate_api_key':
            return 'sk-' + secrets.token_hex(24)
        return f'未知操作: {action}'
    except Exception as e:
        return f'失败: {e}'

