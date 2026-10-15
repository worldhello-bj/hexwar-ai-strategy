# -*- coding: utf-8 -*-
"""把 `snapshot/parsed/units.json` 对齐到**平台的真实开局**（RoomStart 后的 Obj_Get）。

背景（2026-10-15 实测）：`snapshot/parsed` 里的单位状态是从 HAR 采到的，属于**中局**——
  ① 15 条"乘员"被写成 `pos=0 / blood=0 / color=''`（那是真人点过"全员上车"之后的状态）；
  ② `坦克1排`(ZTZ100) 的位置已经前出（160062），而平台开局在 190096。
而平台**开局**的实际状态是：36 个单位**全部在场**，乘员与载具**同格**、各自是独立单位，
其 `blood` 就等于编制。

本工具用一份"实时开局"（`score_probe_*`/任何 `timeline.jsonl` 的第一条）把快照修回去：
  - 按 (army, ico) 配对；
  - 采用实时的 pos / blood / color；
  - 其它字段（id/data/score/son/…）保留快照原值，避免动到别的东西；
  - 旧文件备份成 `units.har.json`（可回滚）。

用法：
    py -3.13 tools/hex_sync_snapshot_opening.py [--live <timeline.jsonl>] [--apply]
不加 `--apply` 只打印差异（dry-run）。
"""
import argparse
import io
import json
import os
import shutil
import sys

ROOT = r"d:\兵推"
SNAP_DIR = os.path.join(ROOT, "snapshot", "parsed")
SNAP = os.path.join(SNAP_DIR, "units.json")
DEFAULT_LIVE = os.path.join(ROOT, "7527_transport_capture",
                            "score_probe_kill_20261015-222414", "timeline.jsonl")


def key(u):
    return (str(u.get("army") or "").strip(), str(u.get("ico") or "").strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", default=DEFAULT_LIVE)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with io.open(args.live, encoding="utf-8") as fh:
        live = json.loads(fh.readline())["units"]
    with io.open(SNAP, encoding="utf-8") as fh:
        snap = json.load(fh)

    live_by = {}
    for u in live.values():
        live_by.setdefault(key(u), []).append(u)
    snap_by = {}
    for i, u in enumerate(snap):
        snap_by.setdefault(key(u), []).append(i)

    unknown, changed = [], []
    for k, idxs in sorted(snap_by.items()):
        cands = live_by.get(k)
        if not cands:
            unknown.append(k)
            continue
        # 同组配对：**先配完全一致的**（避免把两个同型号单位的格号对调），剩下按顺序补。
        pairs = []
        rest_s = list(idxs)
        rest_l = list(cands)
        for i in list(rest_s):
            a = snap[i]
            for lu in list(rest_l):
                if (str(a.get("pos")), str(a.get("blood")),
                        str(a.get("color") or "")) == (str(lu.get("pos")), str(lu.get("blood")),
                                                       str(lu.get("color") or "")):
                    pairs.append((i, lu))
                    rest_s.remove(i)
                    rest_l.remove(lu)
                    break
        for i, lu in zip(rest_s, sorted(rest_l, key=lambda x: (str(x.get("pos")), str(x.get("blood"))))):
            pairs.append((i, lu))
        for idx, lu in pairs:
            a = snap[idx]
            new_pos, new_blood = str(lu.get("pos")), str(lu.get("blood"))
            new_color = str(lu.get("color") or "")
            before = (str(a.get("pos")), str(a.get("blood")), str(a.get("color") or ""))
            after = (new_pos, new_blood, new_color)
            if before != after:
                changed.append((a.get("id"), k, before, after))
                a["pos"] = new_pos
                if str(a.get("pos2")) in ("0", "", "None") or a.get("pos2") == a.get("pos"):
                    a["pos2"] = new_pos
                a["blood"] = new_blood
                a["color"] = new_color
                # 事件说明：这一条原本是"车内"记录，现在按开局落回格上
                a["_opening_synced"] = "was_inside" if before[0] in ("0", "", "None") else "was_moved"
    out = []
    out.append("# 快照对齐平台开局  (live=%s)" % os.path.relpath(args.live, ROOT))
    out.append("- 实时开局单位 %d 条；快照 %d 条" % (len(live), len(snap)))
    out.append("- 未能按 (army, ico) 配对上的快照分组: %s" % (unknown or "无"))
    out.append("- 需要改动的条目 %d 条：" % len(changed))
    for uid, k, before, after in changed:
        out.append("  %-14s %-28s pos/blood/color %s -> %s" % (uid, str(k), before, after))
    text = "\n".join(out)
    print(text)

    if args.apply:
        if os.path.exists(SNAP) and not os.path.exists(os.path.join(SNAP_DIR, "units.har.json")):
            shutil.copy2(SNAP, os.path.join(SNAP_DIR, "units.har.json"))
        with io.open(SNAP, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(snap, ensure_ascii=False, indent=1))
        rep = os.path.join(ROOT, "analysis", "snapshot_opening_sync.md")
        io.open(rep, "w", encoding="utf-8").write(text + "\n（已写入 %s）\n" % SNAP)
        print("applied ->", SNAP)
    else:
        print("(dry-run；加 --apply 才写盘)")


if __name__ == "__main__":
    main()
