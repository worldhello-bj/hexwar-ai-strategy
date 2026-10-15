# -*- coding: utf-8 -*-
"""检测离线站点里所有文本资源的真实编码，找出被错误声明为 UTF-8 的 GBK 文件。"""
import os
import json

SITE = r"d:\兵推\offline\site"
OUT = r"d:\兵推\analysis\encoding_scan.md"

TEXT_EXT = {".html", ".htm", ".js", ".css", ".txt", ".json", ".asp"}

def probe(path):
    b = open(path, "rb").read()
    if not b:
        return "empty", False
    nonascii = any(c > 127 for c in b)
    res = {}
    for enc in ("utf-8", "gb18030"):
        try:
            b.decode(enc)
            res[enc] = True
        except Exception:
            res[enc] = False
    return res, nonascii

rows = []
for root, dirs, files in os.walk(SITE):
    for fn in files:
        p = os.path.join(root, fn)
        ext = os.path.splitext(fn)[1].lower()
        if ext not in TEXT_EXT:
            continue
        res, nonascii = probe(p)
        if res == "empty":
            continue
        rel = os.path.relpath(p, SITE).replace("\\", "/")
        if not nonascii:
            kind = "纯 ASCII"
        elif res["utf-8"] and not res["gb18030"]:
            kind = "UTF-8"
        elif res["gb18030"] and not res["utf-8"]:
            kind = "**GBK**"
        elif res["utf-8"] and res["gb18030"]:
            kind = "UTF-8/GBK 均可解"
        else:
            kind = "**两者都失败**"
        rows.append((rel, kind, len(open(p, "rb").read())))

L = ["# 离线站点文本资源编码扫描", ""]
L.append("| 文件 | 编码 | 字节 |")
L.append("|---|---|---|")
for rel, kind, n in sorted(rows):
    L.append("| `%s` | %s | %d |" % (rel, kind, n))
L.append("")
L.append("## 需要按 GBK 提供的文件")
L.append("")
for rel, kind, n in sorted(rows):
    if kind == "**GBK**":
        L.append("- `%s` (%d 字节)" % (rel, n))

open(OUT, "w", encoding="utf-8").write("\n".join(L))
bad = [r for r in rows if r[1] == "**GBK**"]
print("GBK files:", len(bad))
for r in bad:
    print("  ", r[0], r[2])
print("total text assets:", len(rows))
