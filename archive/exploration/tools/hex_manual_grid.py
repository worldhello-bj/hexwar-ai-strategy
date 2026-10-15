# -*- coding: utf-8 -*-
"""按「词坐标聚类」重建手册页里的表格（解决斜网格/网格歧义）。

用法：
    py -3.13 tools/hex_manual_grid.py 29 27 28 30 31
"""
import sys

import fitz

PDF = r"d:\兵推\docs\WARGAMEAI.pdf"


def grid(page, ytol=4.0):
    words = page.get_text("words")          # (x0,y0,x1,y1,word,block,line,wordno)
    rows = []
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        yc = (w[1] + w[3]) / 2
        placed = False
        for r in rows:
            if abs(r["y"] - yc) <= ytol:
                r["items"].append((w[0], w[4]))
                r["y"] = (r["y"] * len(r["items"]) + yc) / (len(r["items"]) + 1)
                placed = True
                break
        if not placed:
            rows.append({"y": yc, "items": [(w[0], w[4])]})
    for r in rows:
        r["items"].sort()
    return sorted(rows, key=lambda r: r["y"])


def main():
    doc = fitz.open(PDF)
    pages = [int(x) for x in sys.argv[1:]] or [29]
    for p in pages:
        page = doc[p - 1]
        print("=" * 100)
        print("## 第 %d 页（词坐标聚类）" % p)
        for r in grid(page):
            cells = "  ".join("%s@%.0f" % (w, x) for x, w in r["items"])
            print("y=%6.1f | %s" % (r["y"], cells))


if __name__ == "__main__":
    main()
