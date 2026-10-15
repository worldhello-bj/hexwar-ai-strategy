# -*- coding: utf-8 -*-
"""下载比赛手册（规则与裁决表来源），并转成可检索文本。"""
import os
import sys
import requests

BASE7 = "http://www.hexwar.cn/WARGAMEAI7/"
BASE = "http://www.hexwar.cn/WARGAMEAI/"
DOCS = r"d:\兵推\docs"
os.makedirs(DOCS, exist_ok=True)

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": BASE,
})

out = []
def w(x=""):
    out.append(str(x))

cands = [
    BASE + "WARGAMEAI.pdf",
    BASE7 + "WARGAMEAI.pdf",
    BASE7 + "doc/WARGAMEAI.pdf",
    BASE7 + "doc/7527.pdf",
]
dest = os.path.join(DOCS, "WARGAMEAI.pdf")
got = None
if os.path.exists(dest) and os.path.getsize(dest) > 100000:
    got = dest
    w("已存在: %s (%d 字节)" % (dest, os.path.getsize(dest)))
else:
    for u in cands:
        try:
            r = s.get(u, timeout=120, allow_redirects=True)
        except Exception as e:
            w("FAIL %s : %r" % (u, e))
            continue
        w("%s -> %s   %d bytes  %s" % (u, r.status_code, len(r.content), r.headers.get("Content-Type")))
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            open(dest, "wb").write(r.content)
            got = dest
            w("已保存 -> %s" % dest)
            break

open(r"d:\兵推\analysis\pdf_fetch.md", "w", encoding="utf-8").write("\n".join(out))

# 提取文本
if got:
    libs = []
    for name in ("pypdf", "PyPDF2", "pdfplumber", "fitz"):
        try:
            __import__(name)
            libs.append(name)
        except Exception:
            pass
    print("PDF ready:", got, os.path.getsize(got), "libs:", libs)
else:
    print("PDF NOT FETCHED")
