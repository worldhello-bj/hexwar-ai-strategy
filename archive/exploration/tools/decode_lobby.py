# -*- coding: utf-8 -*-
"""按 GBK 重新解码 SetUp 大厅页面，提取推演室列表结构。"""
import re
import os
from bs4 import BeautifulSoup

SRC = r"d:\兵推\snapshot\setup_dir.html"
OUT = r"d:\兵推\analysis\lobby.md"

raw = open(SRC, "rb").read()
html = raw.decode("gb18030", errors="replace")

with open(r"d:\兵推\snapshot\setup_dir_utf8.html", "w", encoding="utf-8") as f:
    f.write(html)

soup = BeautifulSoup(html, "lxml")
lines = []
def w(x=""):
    lines.append(x)

w("# 推演大厅（GB18030 解码）")
w()
w("字符数: %d" % len(html))
w()

w("## 页面可见文本")
w()
w("```")
w(soup.get_text("\n", strip=True)[:3000])
w("```")
w()

w("## 所有带 name/value 的 input")
w()
for el in soup.find_all("input"):
    w("- name=`%s` value=`%s` id=`%s` class=`%s`" % (el.get("name"), el.get("value"), el.get("id"), el.get("class")))
w()

w("## 表格结构")
w()
for ti, t in enumerate(soup.find_all("table")):
    w("### table #%d" % ti)
    w()
    for ri, tr in enumerate(t.find_all("tr")):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        w("- row %d: %s" % (ri, " | ".join(cells)))
    w()

w("## 页面内 script")
w()
for sc in soup.find_all("script"):
    t = sc.string or ""
    if t.strip():
        w("```javascript")
        w(t[:4000])
        w("```")
        w()

w("## 所有 onclick / 自定义属性")
w()
for el in soup.find_all(attrs={"onclick": True}):
    w("- <%s ...> onclick=`%s`" % (el.name, (el.get("onclick") or "")[:120]))
w()

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("lobby written")
