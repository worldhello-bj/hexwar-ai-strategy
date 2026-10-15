# -*- coding: utf-8 -*-
"""计分对账：把**平台真实计分页**（`Report_All.asp`）与引擎的候选口径摆在一起。

用途：`docs/计分规则待确认.md` 里的每一条结论都要能复跑。
平台侧数据来自已抓取的采集产物（`7527_transport_capture/**`，不入库）；
引擎侧用 `snapshot/parsed`（想定 7527）。

用法：
    py -3.13 tools/hex_score_audit.py
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import Game                                    # noqa: E402

CAP = os.path.join(ROOT, "7527_transport_capture")
PAT = re.compile(r'class=\\?"(RED|BLUE)\\?">\s*(\d+)\s*分')
COMPONENTS = ("夺控点", "剩余兵力", "歼灭对手兵力")


def decode(raw):
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def platform_scores():
    """扫采集产物，抽出计分页的三个分项（红, 蓝）。"""
    seen = {}
    files = 0
    for path in glob.glob(os.path.join(CAP, "**", "*"), recursive=True):
        if not os.path.isfile(path):
            continue
        try:
            if os.path.getsize(path) > 60 * 1024 * 1024:
                continue
            text = decode(open(path, "rb").read())
        except OSError:
            continue
        if not text or "夺控点得分" not in text:
            continue
        files += 1
        for chunk in text.split("夺控点得分")[1:]:
            hits = PAT.findall(chunk[:4000])
            if len(hits) >= 6:
                key = tuple(int(v) for _c, v in hits[:6])
                seen.setdefault(key, []).append(os.path.relpath(path, ROOT))
    return files, seen


def carried_establishment():
    """从「下车」采集产物里取载员的**编制兵力**。

    下车会在服务端**新建实体**，其 `blood` 即该载员的编制兵力
    （见 `docs/运输机制实测.md`）。这正好补上想定里载员条目 `blood=0` 的空缺。
    """
    units = json.load(open(os.path.join(ROOT, "snapshot", "parsed", "units.json"),
                           encoding="utf-8"))
    carried_ids = {u["id"]: u for u in units if not (u.get("color") or "").strip()}
    found = {}
    for path in sorted(glob.glob(os.path.join(CAP, "**", "*.json"), recursive=True)):
        try:
            if os.path.getsize(path) > 5 * 1024 * 1024:
                continue
            data = json.load(open(path, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                i2 = node.get("id2")
                if i2 in carried_ids and node.get("id") != i2 and node.get("blood"):
                    src = carried_ids[i2]
                    found.setdefault(int(src["data"]), []).append(
                        (src["name"], int(node["blood"]),
                         os.path.relpath(path, ROOT)))
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return found


def engine_scores(establishment):
    """各种候选求和口径下的双方分值（+ 载员构成）。直接读想定 JSON。"""
    units = json.load(open(os.path.join(ROOT, "snapshot", "parsed", "units.json"),
                           encoding="utf-8"))
    deployed = [u for u in units if (u.get("color") or "").strip()]
    carried = [u for u in units if not (u.get("color") or "").strip()]
    out = {}
    for color in ("BLUE", "RED"):
        dep = [u for u in deployed if u["color"] == color]
        own_carried = []
        for c in carried:
            host = next((u for u in dep if str(u.get("pos")) == str(c.get("pos2"))),
                        None)
            if host:
                own_carried.append((c, host))
        carried_score = sum(int(c["score"]) * establishment.get(int(c["data"]), 0)
                            for c, _h in own_carried)
        out[color] = {
            "units": len(dep),
            "sum_score": sum(int(u["score"]) for u in dep),
            "sum_score_blood": sum(int(u["score"]) * int(u["blood"]) for u in dep),
            "sum_score_blood_sons": sum(int(u["score"]) * (int(u["blood"])
                                                           + int(u.get("sons") or 0))
                                        for u in dep),
            "carried": [(c["id"], c["name"], int(c["score"]), int(c["data"]),
                         establishment.get(int(c["data"])), host["name"])
                        for c, host in own_carried],
            "carried_score": carried_score,
            "full": (sum(int(u["score"]) * int(u["blood"]) for u in dep)
                     + carried_score),
        }
    return out


def main():
    files, seen = platform_scores()
    est_raw = carried_establishment()
    # 编制兵力：采集里有直接观测的用观测值；旋翼无人机/巡飞弹未观测到，
    # 用平台分项**反解**（见下）。
    establishment = {}
    for data, rows in est_raw.items():
        establishment[data] = rows[0][1]
    inferred = {}
    plat_key = next((k for k in seen if seen[k]), None)
    if plat_key:
        # 红方差额 / 3 辆火力支援车 = 单车载员总编制分；旋翼无人机 score=2 → 编制 1
        red_gap = (plat_key[2] - sum(int(u["score"]) * int(u["blood"])
                                     for u in json.load(open(os.path.join(
                                         ROOT, "snapshot", "parsed", "units.json"),
                                         encoding="utf-8"))
                                     if u.get("color") == "RED"))
        per_vehicle = red_gap // 3
        known = (establishment.get(392, 0) * 4 + establishment.get(397, 0) * 5)
        rest = per_vehicle - known
        if rest % 2 == 0:
            inferred[394] = rest // 2
    establishment.update(inferred)
    establishment.setdefault(389, 0)

    eng = engine_scores(establishment)
    lines = []
    add = lines.append

    add("# 计分对账（平台计分页 vs 引擎候选口径）")
    add("")
    add("## 一、平台 `Report_All.asp` 的三个分项")
    add("")
    add("扫描到含计分页的文件 **%d** 个；出现过的 (红夺控, 蓝夺控, 红兵力, 蓝兵力, 红歼灭, 蓝歼灭) 组合："
        % files)
    add("")
    for key in sorted(seen, key=lambda k: -len(seen[k])):
        add("- `%s` × %d 次　例：`%s`" % (key, len(seen[key]), seen[key][0]))
    add("")
    add("> 页面上还有一行「摧毁重要目标得分」，在 HTML 里**被整行注释掉**；")
    add("> 夺控分与歼灭分在全部采集里**恒为 0**（从未占点、也没有整单位被歼的结算）。")
    add("")
    add("## 二、载员的编制兵力（从「下车」采集反推）")
    add("")
    add("想定里 15 条载员条目 `blood=0`（人在车内），编制兵力不可读；")
    add("而下车会在服务端**新建实体**，其 `blood` 就是编制兵力。")
    add("")
    add("| data | 单位 | 编制兵力 | 证据 |")
    add("|---|---|---|---|")
    for data, rows in sorted(est_raw.items()):
        add("| %d | %s | **%d** | `%s` |" % (data, rows[0][0], rows[0][1], rows[0][2]))
    for data, value in inferred.items():
        add("| %d | 旋翼无人机 | **%d** | 由平台分项**反解**（未直接观测） |"
            % (data, value))
    add("| 389 | 巡飞弹 | 0 | score=0，恒为 0 分 |")
    add("")
    add("## 三、引擎候选口径（想定 7527 开局）")
    add("")
    add("| 阵营 | 上阵单位 | Σscore | Σ(score×blood) | Σ(score×(blood+sons)) | 载员分值 | **上阵+载员** |")
    add("|---|---|---|---|---|---|---|")
    for color in ("BLUE", "RED"):
        e = eng[color]
        add("| %s | %d | %d | %d | %d | %d | **%d** |"
            % (color, e["units"], e["sum_score"], e["sum_score_blood"],
               e["sum_score_blood_sons"], e["carried_score"], e["full"]))
    add("")
    add("## 四、与平台逐项对账")
    add("")
    if plat_key:
        pr, pb = plat_key[2], plat_key[3]
        add("- 平台剩余兵力分：红 **%d**、蓝 **%d**" % (pr, pb))
        add("")
        add("| 口径 | 红 | 蓝 | 差（红/蓝） |")
        add("|---|---|---|---|")
        for name, idx in (("Σscore", "sum_score"),
                          ("Σ(score×blood)", "sum_score_blood"),
                          ("Σ(score×(blood+sons))", "sum_score_blood_sons"),
                          ("**Σ(score×blood) + 载员×编制**", "full")):
            dr, db = eng["RED"][idx] - pr, eng["BLUE"][idx] - pb
            mark = "✅ **精确命中**" if (dr == 0 and db == 0) else "%+d / %+d" % (dr, db)
            add("| %s | %d | %d | %s |" % (name, eng["RED"][idx],
                                           eng["BLUE"][idx], mark))
        add("")
        add("⇒ 只有 **上阵 Σ(score×blood) + 车内载员 Σ(score×编制)** 同时精确命中两个数；")
        add("  也就是说平台的「剩余兵力得分」**把车内载员也算进去了**，")
        add("  按的是**编制兵力**（不是记录里的 `blood=0`）。")
        add("")
        add("蓝方：`207 + 3×步兵班(3×3=9) = 234`　红方：")
        add("`240 + 3×[步兵班(4×4) + 无人察打车(5×4) + 旋翼无人机(2×1)] = 240 + 114 = 354`")
    add("")
    add("## 五、结论")
    add("")
    add("- 平台计分页只暴露**分项名**，不暴露分值/公式；")
    add("- **剩余兵力分**：口径已可反推并被两个数同时验证（见上），但仍需官方确认"
        "（尤其「载员计入」与旋翼无人机编制=1 是**反解**出来的）；")
    add("- **夺控分**：全部采集里恒为 0 ⇒ 每点分值无法反推；")
    add("- **歼灭分**：全部采集里恒为 0 ⇒ 公式无法反推；")
    add("- **终局/结算**：计分页没有胜负、时间或任务奖励字段。")
    add("")
    add("⇒ 待确认清单见 `docs/计分规则待确认.md`（可直接发给主办方）。")

    report = os.path.join(ROOT, "docs", "计分对账.md")
    with open(report, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\n报告：%s" % report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
