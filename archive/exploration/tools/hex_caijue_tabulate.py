# -*- coding: utf-8 -*-
"""把所有已抓的裁决明细（Caijue_*.html）汇总成表，用于经验重建表4/表7。

扫描 7527_transport_capture/**/caijue*/caijue_*.html（以及 caijue/ 根目录），
按 (装甲级别, 攻击等级) 分组，列出 (随机数 → 战斗结果 / 最终战果)。

用法：
    py -3.13 tools/hex_caijue_tabulate.py [--dir 目录]
"""
import argparse
import glob
import io
import os
import re
from collections import defaultdict

CAP = r"d:\兵推\7527_transport_capture"


def dec_cell(b):
    b = b.strip()
    for enc in ("utf-8", "gb18030"):
        try:
            return b.decode(enc)
        except Exception:                                 # noqa: BLE001
            pass
    return b.decode("gb18030", "replace")


def parse(raw):
    cells = [dec_cell(b) for b in re.findall(rb"<td[^>]*>(.*?)</td>", raw, re.S)]

    def g(i):
        return cells[i].strip() if i < len(cells) else ""

    return {
        "射击单位": g(1), "目标单位": g(3), "武器": g(5), "距离": g(7),
        "高度差": g(9), "攻击等级": g(11), "随机数": g(13), "战斗结果": g(15),
        "射手状态": g(17), "目标状态": g(19), "x21": g(21), "装甲级别": g(23),
        "修正结果": g(25), "最终战果": g(27),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=CAP)
    args = ap.parse_args()

    files = sorted(set(
        glob.glob(os.path.join(args.dir, "**", "caijue*.html"), recursive=True)
        + glob.glob(os.path.join(args.dir, "**", "caijue", "*.html"), recursive=True)))
    rows = []
    for f in files:
        raw = open(f, "rb").read()
        if not raw.strip():
            continue
        d = parse(raw)
        d["file"] = os.path.relpath(f, args.dir)
        d["id"] = re.sub(r"\D", "", os.path.basename(f))
        rows.append(d)

    print("共 %d 条裁决样本\n" % len(rows))
    hdr = "%-10s %-5s %-6s %-6s %-6s %-8s %-6s %-6s %-10s %-8s %-8s" % (
        "裁决ID", "攻级", "随机数", "结果", "随机数2", "装甲", "修", "最终", "射手状态", "目标状态", "武器")
    print(hdr)
    print("-" * len(hdr))
    for d in sorted(rows, key=lambda x: int(x["id"] or 0)):
        print("%-10s %-5s %-6s %-6s %-6s %-8s %-6s %-6s %-10s %-8s %-8s" % (
            d["id"], d["攻击等级"], d["随机数"], d["战斗结果"], d.get("x21", "?"), d["装甲级别"],
            d["修正结果"], d["最终战果"], d["射手状态"], d["目标状态"], d["武器"]))

    # 按 (装甲, 攻级) 分组看 随机数→结果
    grp = defaultdict(list)
    for d in rows:
        grp[(d["装甲级别"], d["攻击等级"])].append(
            (d["随机数"], d.get("x21", "?"), d["战斗结果"], d["修正结果"], d["最终战果"]))
    print("\n== 按 (装甲, 攻击等级) 分组：随机数1 / 随机数2 → 结果 / 修正 / 最终 ==")
    for k in sorted(grp, key=lambda x: (x[0], -len(x[1]) if x[1].isdigit() else 0)):
        seq = sorted(grp[k], key=lambda t: (len(t[0]), t[0]))
        print("  %-8s 攻级=%-4s : %s" % (k[0], k[1], seq))

    out = os.path.join(args.dir, "caijue_summary.md")
    with io.open(out, "w", encoding="utf-8") as fh:
        fh.write("# 裁决样本汇总（自动生成）\n\n")
        fh.write("| 裁决ID | 攻级 | 随机数 | 随机数2 | 战斗结果 | 装甲 | 修正 | 最终战果 | 射手状态 | 目标状态 | 武器 | 距离 |\n")
        fh.write("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for d in sorted(rows, key=lambda x: int(x["id"] or 0)):
            fh.write("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n" % (
                d["id"], d["攻击等级"], d["随机数"], d.get("x21", ""), d["战斗结果"], d["装甲级别"],
                d["修正结果"], d["最终战果"], d["射手状态"], d["目标状态"], d["武器"], d["距离"]))
    print("\n写出 -> %s" % out)


if __name__ == "__main__":
    main()
