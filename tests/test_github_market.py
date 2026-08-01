"""
Test: Explore GitHub Issues based MCP marketplace
"""
import urllib.request, json, re

# 1. Get issues from cline/mcp-marketplace
url = "https://api.github.com/repos/cline/mcp-marketplace/issues?state=open&per_page=5"
req = urllib.request.Request(url, headers={
    'User-Agent': 'Agent-MCP/1.0',
    'Accept': 'application/vnd.github.v3+json'
})
resp = urllib.request.urlopen(req, timeout=20)
data = json.loads(resp.read())

print(f"Total issues returned: {len(data)}")
print("="*60)

for issue in data:
    print(f"\n#{issue['number']} - {issue['title']}")
    print(f"  Labels: {[l['name'] for l in issue['labels']]}")
    print(f"  State: {issue['state']}")
    print(f"  Created: {issue['created_at']}")
    print(f"  Body (first 500 chars): {issue['body'][:500] if issue['body'] else 'N/A'}")
    print(f"  User: {issue['user']['login']}")
    print("-"*40)