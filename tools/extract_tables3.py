# -*- coding: utf-8 -*-
"""用表格线（lines/rects）确定真实网格，把文本落入单元格，重建表1-表10。"""
import os
import json
import pdfplumber

PDF = r"d:\兵推\docs\WARGAMEAI.pdf"
OUT = r"d:\兵推\analysis\tables3.md"
OUTJ = r"d:\兵推\snapshot\parsed\manual_grid.json"

res = {}
lines = ["# 裁决表（网格线重建）", ""]

def snap(vals, tol=4):
    """把坐标聚成网格线。"""
    vals = sorted(vals)
    out = []
    for v in vals:
        if not out or v - out[-1] > tol:
            out.append(v)
        else:
            out[-1] = (out[-1] + v) / 2
    return out

with pdfplumber.open(PDF) as pdf:
    for pi in range(26, 31):
        page = pdf.pages[pi]
        # 统一用 page.edges（含 line/rect/curve 的边）
        vs, hs = [], []
        for e in page.edges:
            o = e.get("orientation")
            if o == "v" and (e["y1"] - e["y0"]) > 3:
                vs.append(e["x0"])
            elif o == "h" and (e["x1"] - e["x0"]) > 3:
                hs.append(e["y0"])
        for l in page.lines:
            if abs(l["x0"] - l["x1"]) < 0.5 and abs(l["y1"] - l["y0"]) > 3:
                vs.append(l["x0"])
            if abs(l["y0"] - l["y1"]) < 0.5 and abs(l["x1"] - l["x0"]) > 3:
                hs.append(l["top"])
        for r in page.rects:
            if r["width"] > 3 and r["height"] > 3:
                vs += [r["x0"], r["x1"]]
                hs += [r["top"], r["bottom"]]
        for c in page.curves:
            if abs(c["x0"] - c["x1"]) < 0.5 and abs(c["y1"] - c["y0"]) > 3:
                vs.append(c["x0"])
            if abs(c["y0"] - c["y1"]) < 0.5 and abs(c["x1"] - c["x0"]) > 3:
                hs.append(c["top"])
        xs = snap(vs)
        ys = snap(hs)
        words = page.extract_words()
        grids = []
        for ri in range(len(ys) - 1):
            y0, y1 = ys[ri], ys[ri + 1]
            if y1 - y0 < 8:
                continue
            row = []
            for ci in range(len(xs) - 1):
                x0, x1 = xs[ci], xs[ci + 1]
                if x1 - x0 < 6:
                    row.append("")
                    continue
                txts = [w["text"] for w in words
                        if x0 - 1 <= (w["x0"] + w["x1"]) / 2 <= x1 + 1
                        and y0 - 1 <= (w["top"] + w["bottom"]) / 2 <= y1 + 1]
                row.append(" ".join(txts))
            grids.append({"y": [round(y0, 1), round(y1, 1)], "cells": row})
        res["p%d" % (pi + 1)] = {"xs": [round(v, 1) for v in xs],
                                 "ys": [round(v, 1) for v in ys],
                                 "grids": grids}
        lines.append("## 第 %d 页" % (pi + 1))
        lines.append("")
        lines.append("- 竖线 x: %s" % [round(v) for v in xs])
        lines.append("- 横线 y: %s" % [round(v) for v in ys])
        lines.append("")
        for g in grids:
            lines.append("| " + " | ".join(g["cells"]) + " |")
        lines.append("")

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
json.dump(res, open(OUTJ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok", {k: len(v["grids"]) for k, v in res.items()})
