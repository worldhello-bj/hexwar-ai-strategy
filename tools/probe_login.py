# -*- coding: utf-8 -*-
"""探测 www.hexwar.cn 登录入口页面的表单结构（只读）。"""
import os
import re
import sys
import requests
from bs4 import BeautifulSoup

OUT = r"d:\兵推\analysis\probe_login.md"
ENTRY = "http://www.hexwar.cn/WARGAMEAI/"

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
})

lines = []
def w(x=""):
    lines.append(x)

try:
    r = s.get(ENTRY, timeout=30, allow_redirects=True)
except Exception as e:
    w("请求失败: %r" % (e,))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("done")
    sys.exit(0)

w("# 登录入口探测")
w()
w("- URL: %s" % ENTRY)
w("- 最终 URL: %s" % r.url)
w("- 状态: %s" % r.status_code)
w("- 重定向历史: %s" % [(h.status_code, h.headers.get("Location")) for h in r.history])
w("- Content-Type: %s" % r.headers.get("Content-Type"))
w("- Server: %s" % r.headers.get("Server"))
w("- 长度: %d" % len(r.content))
w()
try:
    enc = r.apparent_encoding or "utf-8"
    html = r.content.decode(enc, errors="replace")
except Exception:
    html = r.text
w("- 探测编码: %s (apparent=%s)" % (r.encoding, r.apparent_encoding))
w()

w("## 页面中的 form")
w()
soup = BeautifulSoup(html, "lxml")
for i, form in enumerate(soup.find_all("form")):
    w("### form #%d" % i)
    w()
    w("- action: `%s`" % form.get("action"))
    w("- method: `%s`" % form.get("method"))
    w("- id/name: `%s` / `%s`" % (form.get("id"), form.get("name")))
    w()
    w("| tag | name | type | value |")
    w("|---|---|---|---|")
    for el in form.find_all(["input", "select", "textarea", "button"]):
        w("| %s | %s | %s | %s |" % (el.name, el.get("name"), el.get("type"), (el.get("value") or "")[:60]))
    w()

w("## 页面中所有 input（含未在 form 内）")
w()
w("| name | id | type | onfocus/onclick |")
w("|---|---|---|---|")
for el in soup.find_all("input"):
    w("| %s | %s | %s | %s |" % (el.get("name"), el.get("id"), el.get("type"),
                                 (el.get("onfocus") or el.get("onclick") or "")[:80]))
w()

w("## 页面内 script 中的关键字符串")
w()
for sc in soup.find_all("script"):
    t = sc.string or ""
    for m in re.finditer(r"[^\n]{0,120}(login|login\.asp|Login|password|passwd|md5|MD5|md5hash|document\.cookie)[^\n]{0,120}", t):
        w("- `%s`" % m.group(0).strip()[:240])
w()

w("## 原始 HTML（前 6000 字符）")
w()
w("```html")
w(html[:6000])
w("```")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("done")
