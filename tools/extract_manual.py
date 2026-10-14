# -*- coding: utf-8 -*-
"""提取手册文本（本地分析用）。"""
import os
import re
import fitz  # PyMuPDF

PDF = r"d:\兵推\docs\WARGAMEAI.pdf"
OUT = r"d:\兵推\analysis\manual_text.md"

doc = fitz.open(PDF)
lines = []
lines.append("# 手册文本提取（本地资料，勿外传）\n")
lines.append("- 页数: %d" % doc.page_count)
lines.append("")

def garbled_ratio(t):
    if not t:
        return 1.0
    good = sum(1 for c in t if c.isascii() or '\u4e00' <= c <= '\u9fff' or c in "，。、；：？！（）《》“”‘’—…·")
    return 1 - good / len(t)

for i in range(doc.page_count):
    page = doc[i]
    t = page.get_text("text") or ""
    imgs = page.get_images(full=True)
    lines.append("## 第 %d 页  (字符 %d, 图片 %d, 可疑占比 %.3f)" % (i + 1, len(t), len(imgs), garbled_ratio(t)))
    lines.append("")
    lines.append("```")
    lines.append(t.strip()[:8000])
    lines.append("```")
    lines.append("")

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("pages:", doc.page_count, "->", OUT)
# 摘要
for i in range(doc.page_count):
    t = doc[i].get_text("text") or ""
    print("p%02d chars=%5d imgs=%2d garbled=%.2f  %s" % (
        i + 1, len(t), len(doc[i].get_images()), garbled_ratio(t), t.strip()[:40].replace("\n", " ")))
