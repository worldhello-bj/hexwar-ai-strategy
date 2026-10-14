# -*- coding: utf-8 -*-
"""按词坐标重建手册裁决表（第 27-31 页），输出为规整的行列表 + JSON。"""
import os
import json
import pdfplumber

PDF = r"d:\兵推\docs\WARGAMEAI.pdf"
OUT = r"d:\兵推\analysis\tables2.md"
OUTJ = r"d:\兵推\snapshot\parsed\manual_tables2.json"

res = {}
lines = ["# 裁决表（按坐标重建）", ""]

with pdfplumber.open(PDF) as pdf:
    for pi in range(26, min(31, len(pdf.pages))):
        page = pdf.pages[pi]
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False,
                                   extra_attrs=["size"])
        # 按 y 聚类成行
        rows = []
        for w in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
            placed = False
            for r in rows:
                if abs(r["y"] - w["top"]) < 6:
                    r["ws"].append(w)
                    placed = True
                    break
            if not placed:
                rows.append({"y": w["top"], "ws": [w]})
        rows.sort(key=lambda r: r["y"])
        out_rows = []
        for r in rows:
            ws = sorted(r["ws"], key=lambda w: w["x0"])
            cells = ["%s@%.0f" % (w["text"], w["x0"]) for w in ws]
            out_rows.append({"y": round(r["y"], 1), "cells": cells,
                             "text": " ".join(w["text"] for w in ws)})
        res["p%d" % (pi + 1)] = out_rows
        lines.append("## 第 %d 页" % (pi + 1))
        lines.append("")
        for r in out_rows:
            lines.append("`y=%-6.0f` %s" % (r["y"], r["text"]))
        lines.append("")
        lines.append("坐标明细：")
        lines.append("")
        lines.append("```")
        for r in out_rows:
            lines.append(" | ".join(r["cells"]))
        lines.append("```")
        lines.append("")

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
json.dump(res, open(OUTJ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok", list(res))
