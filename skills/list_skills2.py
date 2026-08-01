import os, re, glob

base = r'E:\workplace\agent\skills'
lines = []

lines.append('=== builtin ===')
for f in sorted(glob.glob(os.path.join(base, 'builtin', '*.py'))):
    if f.endswith('__init__.py'):
        continue
    name = os.path.splitext(os.path.basename(f))[0]
    try:
        content = open(f, encoding='utf-8', errors='replace').read()
        m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
        d = re.search(r'description\s*=\s*["\']([^"\']+)["\']', content)
        label = m.group(1) if m else name
        descline = d.group(1) if d else ''
        lines.append('%s | %s' % (label, descline))
    except Exception as e:
        lines.append('%s | ERR %s' % (name, e))

lines.append('')
lines.append('=== md ===')
for f in sorted(glob.glob(os.path.join(base, 'md', '*.md'))):
    name = os.path.splitext(os.path.basename(f))[0]
    content = open(f, encoding='utf-8', errors='replace').read()
    m = re.search(r'name\s*:\s*([^\n]+)', content)
    enabled = re.search(r'enabled\s*:\s*(\w+)', content)
    desc = re.search(r'description\s*:\s*([^\n]+)', content)
    lines.append('%s | enabled=%s | %s' % (m.group(1).strip() if m else name, enabled.group(1) if enabled else '?', desc.group(1).strip() if desc else ''))

open(r'E:\workplace\agent\skills\_list_out.txt', 'w', encoding='utf-8', errors='replace').write('\n'.join(lines))
print('ok')
