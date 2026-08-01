import os, re, glob

base = r'E:\workplace\agent\skills'
lines = []

# builtin skills
lines.append('=== builtin 技能 (python) ===')
for f in sorted(glob.glob(os.path.join(base, 'builtin', '*.py'))):
    if f.endswith('__init__.py'):
        continue
    name = os.path.splitext(os.path.basename(f))[0]
    try:
        content = open(f, encoding='utf-8').read()
        m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
        desc = re.search(r'"""(.*?)(?:"""|\n)', content, re.S)
        d = re.search(r'description\s*=\s*["\']([^"\']+)["\']', content)
        label = name
        if m: label = m.group(1)
        descline = d.group(1) if d else (desc.group(1).strip().split('\n')[0] if desc else '')
        lines.append('- %s | %s' % (label, descline))
    except Exception as e:
        lines.append('- %s | (error %s)' % (name, e))

# md skills
lines.append('')
lines.append('=== md 技能 ===')
for f in sorted(glob.glob(os.path.join(base, 'md', '*.md'))):
    name = os.path.splitext(os.path.basename(f))[0]
    content = open(f, encoding='utf-8').read()
    m = re.search(r'name\s*:\s*([^\n]+)', content)
    enabled = re.search(r'enabled\s*:\s*(\w+)', content)
    desc = re.search(r'description\s*:\s*([^\n]+)', content)
    lines.append('- %s | enabled=%s | %s' % (m.group(1).strip() if m else name, enabled.group(1) if enabled else '?', desc.group(1).strip() if desc else ''))

# triggers
lines.append('')
lines.append('=== 触发器 ===')
for f in sorted(glob.glob(os.path.join(base, 'triggers', '*.py'))):
    if f.endswith('__init__.py'):
        continue
    lines.append('- ' + os.path.splitext(os.path.basename(f))[0])

open(r'E:\workplace\agent\skills\_list_out.txt', 'w', encoding='utf-8').write('\n'.join(lines))
print('done')
