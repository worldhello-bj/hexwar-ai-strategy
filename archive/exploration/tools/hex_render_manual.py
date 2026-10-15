# -*- coding: utf-8 -*-
"""把手册指定页渲染成 PNG，供人工/视觉核对表格（表格文本提取有网格歧义）。"""
import os
import sys

import fitz

PDF = r"d:\兵推\docs\WARGAMEAI.pdf"
OUT = r"d:\兵推\analysis"

pages = [int(x) for x in sys.argv[1:]] or [27, 28, 29, 30, 31]
doc = fitz.open(PDF)
print("PDF 总页数:", doc.page_count)
for p in pages:
    if p < 1 or p > doc.page_count:
        print("跳过越界页", p)
        continue
    page = doc[p - 1]
    pix = page.get_pixmap(dpi=220)
    path = os.path.join(OUT, "manual_p%02d.png" % p)
    pix.save(path)
    print("wrote %s  (%dx%d)" % (path, pix.width, pix.height))
