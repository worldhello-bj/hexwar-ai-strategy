# -*- coding: utf-8 -*-
"""用 pdfplumber 还原手册第 27-31 页的裁决表为结构化矩阵。"""
import os
import json
import pdfplumber

PDF = r"d:\兵推\docs\WARGAMEAI.pdf"
OUT = r"d:\兵推\analysis\tables.md"
OUTJ = r"d:\兵推\snapshot\parsed\manual_tables.json"

res = {}
lines = ["# 手册表格抽取（第 5 章 裁决表）", ""]

with pdfplumber.open(PDF) as pdf:
    for pi in range(26, pdf.pages.__len__()):
        page = pdf.pages[pi]
        txt = (page.extract_text() or "").strip()
        # 标题行：形如 “表N 直瞄武器对……”
        title = ""
        for ln in txt.splitlines():
            s = ln.strip()
            if s.startswith("表") and len(s) > 3:
                title = s
                break
        tables = page.extract_tables()
        lines.append("## 第 %d 页 %s" % (pi + 1, title))
        lines.append("")
        key = "p%d" % (pi + 1)
        res[key] = {"page": pi + 1, "title": title, "tables": []}
        if not tables:
            lines.append("（未识别出表格）")
            lines.append("")
            lines.append("```")
            lines.append(txt[:2000])
            lines.append("```")
            lines.append("")
            continue
        for ti, tb in enumerate(tables):
            lines.append("### 表 %d.%d  (%d 行 × %d 列)" % (pi + 1, ti, len(tb), max(len(r) for r in tb)))
            lines.append("")
            # 归一化：去 None，去空白
            norm = [[(c or "").replace("\n", " ").strip() for c in row] for row in tb]
            res[key]["tables"].append(norm)
            for r in norm:
                lines.append("| " + " | ".join(r) + " |")
            lines.append("")
        # 表外的散落文本
        lines.append("#### 脚注/说明文本")
        lines.append("")
        lines.append("```")
        lines.append(txt[:1500])
        lines.append("```")
        lines.append("")

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
json.dump(res, open(OUTJ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("tables:", {k: len(v["tables"]) for k, v in res.items()})
