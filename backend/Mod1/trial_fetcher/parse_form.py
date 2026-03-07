import re
import urllib.request
import urllib.parse

html = open('ctri_form.html', encoding='utf-8').read()
form_match = re.search(r'<form[\s\S]*?</form>', html, re.IGNORECASE)
if not form_match:
    print("No form found")
    exit()

form = form_match.group(0)
inputs = re.findall(r'<input[^>]+name=[\"\']([^\"\']+)[\"\'][^>]*>', form, re.I)
selects_raw = re.findall(r'<select[^>]+name=[\"\']([^\"\']+)[\"\'][^>]*>([\s\S]*?)</select>', form, re.I)

print("Inputs:", inputs)
for s_name, s_opts in selects_raw:
    opts = re.findall(r'<option[^>]*value=[\"\']([^\"\']*)[\"\'][^>]*>([^<]*)</option>', s_opts, re.I)
    print(f"Select: {s_name}")
    for val, text in opts:
        print(f"  {val} -> {text.strip()}")
