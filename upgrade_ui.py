import re

with open('src/dashboard.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace tk widgets with ttk widgets for native theming
content = re.sub(r'tk\.Label\(', 'ttk.Label(', content)
content = re.sub(r'tk\.Frame\(', 'ttk.Frame(', content)
content = re.sub(r'tk\.Button\(', 'ttk.Button(', content)
content = re.sub(r'tk\.Checkbutton\(', 'ttk.Checkbutton(', content)
content = re.sub(r'tk\.Scale\(', 'ttk.Scale(', content)

# Remove bg, fg, font, relief, cursor arguments from ttk widgets since sv_ttk handles it
content = re.sub(r',?\s*bg=[^,\)]+', '', content)
content = re.sub(r',?\s*fg=[^,\)]+', '', content)
content = re.sub(r',?\s*relief=[^,\)]+', '', content)
content = re.sub(r',?\s*cursor=[^,\)]+', '', content)
content = re.sub(r',?\s*activebackground=[^,\)]+', '', content)
content = re.sub(r',?\s*activeforeground=[^,\)]+', '', content)
content = re.sub(r',?\s*selectcolor=[^,\)]+', '', content)
content = re.sub(r',?\s*highlightthickness=[^,\)]+', '', content)
# content = re.sub(r',?\s*font=\([^\)]+\)', '', content) # risky, might remove too much, let's just leave font alone for now.

# Inject sv_ttk
content = content.replace('style.theme_use("clam")', 'import sv_ttk\n        sv_ttk.set_theme("dark")')

with open('src/dashboard.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('UI Upgraded to sv_ttk')
