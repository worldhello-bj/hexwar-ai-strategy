# -*- coding: utf-8 -*-
"""实测夺控的边界口径：撤走后是否失守 / 失守是否扣分 / 重复夺回是否重复计分。

流程（同一个 run 里跑完）：
    A) 蓝方走到夺控点 → CityTake → 读计分页（预期：蓝方夺控分 +该点分值）
    B) 蓝方**撤远**（到距离 ≥ `--withdraw-distance` 格，并确认本格与 6 邻格无敌方地面单位）
       → 读计分页（问：归属会变吗？分会掉吗？）
    C) 红方走过来 → CityTake（问：红方加分吗？蓝方扣分吗？）
    D) 若 C 连续 `--max-tries` 次都失败，改让红方去占一个**仍为无主**的点
       （用来区分“红方的 CityTake 本身不可用”与“已被占领的点不能翻转”）。

★ 实测结果（2026-10-15，`score_flip_20261015-221433`）：
    蓝方占下 `次要` → 蓝 **50**；蓝方撤到 2 格外（flag 仍为蓝、分值不变）；
    红方走上该格并 CityTake → 页面变成「**红 50 / 蓝 0**」。
  ⇒ **失守方扣分、重夺方按同值加分**（不褒减、不封顶）；`PENDING_RULES` 随之清空，
    `engine/scoring.py` 里“按当前归属的夺控点分值求和”的实现在这就是**对的**。

★ 第一次跑（`score_flip_20261015-220254`）把“撤出”实现成了**走到邻格**，而手册 3.13 要求
  “本格与相邻 6 格无敌方地面单位” ⇒ 邻格的蓝方单位把红方的夺控全项了下去
  （RED 的 CityTake 连续返回空串）。所以现在默认撤到 **2 格**，并逐次把
  “本格/邻格有无敌方地面单位”写进日志，免得再把阻挡当成规则。
  （这个失败本身也反向验证了 3.13 的夺控门槛：撤远后一次就成功。）

产物：`7527_transport_capture/score_flip_<时间戳>/`（timeline.jsonl / score_changes.json / report.md）

用法：
    $env:HEXWAR_USER='...'; $env:HEXWAR_PASS='...'; $env:HEXWAR_USER2='...'; $env:HEXWAR_PASS2='...'
    $env:HEXWAR_ALLOW_HTTP='1'
    py -3.13 tools/hex_flip_probe.py --room 7 --city-name 次要 --minutes 12
"""
import argparse
import io
import json
import os
import re
import sys
import time
from urllib.parse import urlsplit

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"d:\兵推")
import hex_transport_capture as H            # noqa: E402
import hex_play_round as P                   # noqa: E402
import hex_combat_round as C                 # noqa: E402
import hex_score_probe as S                  # noqa: E402
from engine import geometry as GEO           # noqa: E402

CAP = r"d:\兵推\7527_transport_capture"
PRACTICE_HOSTS = ("www.hexwar.cn",)


def ground_units(units, color):
    return [k for k, a in units.items()
            if a.get("color") == color and str(a.get("blood")) not in ("0", "")
            and str(a.get("typeid")) in ("1", "2")]


def nearest_to(units, color, pos):
    best = None
    for k in ground_units(units, color):
        d = GEO.distance(int(units[k]["pos"]), pos)
        if best is None or d < best[0]:
            best = (d, k)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", type=int, default=7)
    ap.add_argument("--city-name", default="次要", choices=("次要", "主要"))
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--tick", type=float, default=1.0)
    ap.add_argument("--withdraw-distance", type=int, default=2,
                    help="蓝方要撤到距夺控点多少格以外（手册要求本格+6邻格无敌方地面单位）")
    ap.add_argument("--max-tries", type=int, default=40, help="红方连续夺控失败多少次后转 D 阶段")
    args = ap.parse_args()

    if urlsplit(H.HOST).hostname not in PRACTICE_HOSTS:
        sys.exit("只允许练习服 %s" % (PRACTICE_HOSTS,))
    H.guard()
    uA, pA = os.environ.get("HEXWAR_USER", ""), os.environ.get("HEXWAR_PASS", "")
    uB, pB = os.environ.get("HEXWAR_USER2", ""), os.environ.get("HEXWAR_PASS2", "")
    if not uB or not pB:
        sys.exit("请设置 HEXWAR_USER2 / HEXWAR_PASS2")

    base7 = "%s/WARGAMEAI%d/" % (H.HOST, args.room)
    H.BASE7 = base7
    stamp = time.strftime("%Y%m%d-%H%M%S")
    d = os.path.join(CAP, "score_flip_%s" % stamp)
    os.makedirs(d, exist_ok=True)
    timeline = io.open(os.path.join(d, "timeline.jsonl"), "w", encoding="utf-8")
    actions = io.open(os.path.join(d, "actions.jsonl"), "w", encoding="utf-8")
    log = []

    def w(x=""):
        log.append(str(x))
        print(x)

    def log_action(o):
        actions.write(json.dumps(o, ensure_ascii=False) + "\n")
        actions.flush()

    w("# 夺控边界口径实测  %s" % stamp)
    # ---- 复位 / 进房 / 开局（同 hex_score_probe）----
    sessA, _ = P.login_as(uA, pA)
    url = "%s/WARGAMEAI%d/Reset/Post.asp" % (H.HOST, args.room)
    r = P.get(sessA, url, params={"scenarioId": "7527", "roomId": str(args.room)})
    m = re.search(r'<form[^>]*action="([^"]*)"[^>]*>(.*?)</form>', H.decode(r.content), re.S)
    if m:
        data = {}
        for im in re.finditer(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>',
                              m.group(2), re.S):
            data[im.group(1)] = im.group(2).strip()
        P.sessA_post = sessA.post(requests.compat.urljoin(url, m.group(1)), data=data, timeout=30)
        w("- 复位房间 -> %s" % P.sessA_post.status_code)
    sessA, uidA = P.login_as(uA, pA)
    okA, _ = P.join(sessA, uidA, "NONE", args.room, base7)
    w("- A(导演 %s) 进房: %s" % (uidA, "在座" if okA else "不在座"))
    sessB, uidB = P.login_as(uB, pB)
    okB, _ = P.join(sessB, uidB, "RED", args.room, base7)
    time.sleep(1)
    okB, _ = P.in_room(sessB, base7)
    w("- B(RED %s) 进房: %s" % (uidB, "在座" if okB else "不在座"))
    H.S = sessA
    started = False
    for attempt in range(6):
        for v in ({"AIStart": "false", "RoomSecond": "0"},
                  {"AIStart": "true", "RoomSecond": "0"}):
            rs = P.get(sessA, base7 + "RoomStart.asp", params=v,
                       headers={"Referer": base7 + "main.html"})
            txt = H.decode(rs.content)
            w("- RoomStart(第%d次) -> %r" % (attempt + 1, txt[:90]))
            if txt.strip() not in ("-1", "0", ""):
                started = True
                break
            time.sleep(1.5)
        if started:
            break
    if not started:
        w("  !!! 开局失败")
    io.open(os.path.join(d, "setup_log.md"), "w", encoding="utf-8").write("\n".join(H.LOG))

    deadline = time.time() + args.minutes * 60
    tick = 0
    last = None
    changes = []
    # stage: 1=蓝方占点 2=蓝方撤远 3=红方夺回 4=红方改占无主点
    stage = 1
    blue_move, red_move = None, None
    city = None
    city2 = None
    tries = 0
    stage_tick = 0

    while time.time() < deadline:
        t0 = time.time()
        rec = P.sample(sessA, base7)
        rec["tick"] = tick
        rec["wall"] = time.strftime("%H:%M:%S")
        rec["score"] = S.parse_score(rec["report_all"])
        timeline.write(json.dumps(rec, ensure_ascii=False) + "\n")
        timeline.flush()
        units = rec["units"]
        cities = [c for c in rec["cities"] if c.get("pos")]
        ug = rec["user_get"] if isinstance(rec["user_get"], dict) else {}
        cur = S.flat(rec["score"])
        if cur != last:
            w("tick %2d %s RoomSecond=%-4s 计分: %s  归属=%s"
              % (tick, rec["wall"], ug.get("20"), cur,
                 {c.get("name"): c.get("flag") for c in cities}))
            changes.append({"tick": tick, "wall": rec["wall"], "flat": cur,
                            "score": rec["score"],
                            "flags": {c.get("id"): c.get("flag") for c in cities}})
            last = cur

        if not ug.get("3", "").strip() or not cities:
            tick += 1
            time.sleep(max(0.2, args.tick - (time.time() - t0)))
            continue

        if city is None:
            picks = [c for c in cities if c.get("name") == args.city_name]
            scored = []
            for c in picks:
                b = nearest_to(units, "BLUE", int(c["pos"]))
                r_ = nearest_to(units, "RED", int(c["pos"]))
                if b and r_:
                    scored.append((b[0] + r_[0], c, b, r_))
            if not scored:
                w("- 没有同时靠近蓝红方的目标点，退出")
                break
            scored.sort(key=lambda x: x[0])
            _tot, city, b, r_ = scored[0]
            blue_move, red_move = b[1], r_[1]
            w("→ 目标 %s(%s) @%s；蓝方执行 %s(距%d) 红方执行 %s(距%d)"
              % (city.get("name"), city.get("id"), GEO.hexid(int(city["pos"])),
                 blue_move, b[0], red_move, r_[0]))
            stage_tick = tick

        cpos = int(city["pos"])
        live = C.positions(sessA, base7, [blue_move, red_move, ]) or {}
        for k, v in live.items():
            if v:
                units.setdefault(k, {})["pos"] = str(v)
        flag = next((c.get("flag") for c in cities if c.get("id") == city.get("id")), None)
        bpos = int(units[blue_move]["pos"]) if blue_move in units else None
        rpos = int(units[red_move]["pos"]) if red_move in units else None

        if stage == 1:
            if bpos != cpos:
                to, st = S.step_toward(sessA, base7, blue_move, bpos, cpos, rec, log_action)
                if to:
                    w("  [蓝] 机动 %s→%s" % (GEO.hexid(bpos), GEO.hexid(to)))
                else:
                    w("  [蓝] 无法接近，退出")
                    break
            else:
                res = P.act_take_city(sessA, base7, blue_move, rec)
                log_action({"kind": "city_take", "side": "BLUE", **res})
                if flag == "BLUE":
                    w("  [蓝] 夺控成功（flag=BLUE）→ 进入 B 阶段：蓝方撤出")
                    stage = 2
                    stage_tick = tick
        elif stage == 2:
            # 撤远：朝"背离夺控点"的方向走，直到距离 ≥ withdraw-distance。
            if GEO.distance(bpos, cpos) < args.withdraw_distance:
                r0, c0 = GEO.split_mapid(cpos)
                r1, c1 = GEO.split_mapid(bpos)
                goal = GEO.make_mapid(r1 + 3 * (r1 - r0), c1 + 3 * (c1 - c0))
                if goal == bpos:                     # 已在点上：先迈出一步
                    goal = sorted(GEO.neighbors(cpos))[0]
                to, st = S.step_toward(sessA, base7, blue_move, bpos, goal, rec, log_action)
                w("  [蓝] 远撤 %s→%s（距点 %d）"
                  % (GEO.hexid(bpos), GEO.hexid(to or 0), GEO.distance(to or bpos, cpos)))
            elif tick > stage_tick + 1:
                blockers = [k for k in ground_units(units, "BLUE")
                            if GEO.distance(int(units[k]["pos"]), cpos) <= 1]
                w("  [蓝] 已撤到 %d 格外（flag 仍=%s：撤离不改变归属；本格+6邻格蓝方地面单位=%s）"
                  " → 进入 C 阶段：红方夺回"
                  % (GEO.distance(bpos, cpos), flag, blockers or "无"))
                stage = 3
                stage_tick = tick
        elif stage == 3:
            if rpos != cpos:
                to, st = S.step_toward(sessA, base7, red_move, rpos, cpos, rec, log_action)
                if to:
                    w("  [红] 机动 %s→%s" % (GEO.hexid(rpos), GEO.hexid(to)))
                else:
                    w("  [红] 无法接近，收工")
                    break
            else:
                blockers = [k for k in ground_units(units, "BLUE")
                            if GEO.distance(int(units[k]["pos"]), cpos) <= 1]
                res = P.act_take_city(sessA, base7, red_move, rec)
                log_action({"kind": "city_take", "side": "RED", "gate_blockers": blockers, **res})
                if flag == "RED":
                    w("  [红] 夺控成功（flag=RED）⇒ **已占点可以翻转**；再采 15 tick 看是否有二次计分")
                    if tick > stage_tick + 15:
                        break
                else:
                    tries += 1
                    if tries % 5 == 1:
                        w("  [红] 第 %d 次夺控未果（flag=%s；本格+6邻格蓝方地面单位=%s）"
                          % (tries, flag, blockers or "无"))
                    if tries >= args.max_tries:
                        w("  [红] 连续 %d 次夺控失败 ⇒ 转入 D 阶段：改去占一个无主点" % tries)
                        stage = 4
                        stage_tick = tick
        else:
            # D：红方去占一个仍为无主的点，用来验证"红方的 CityTake 本身是否可用"。
            if city2 is None:
                neutral = [c for c in cities if c.get("pos") and c.get("id") != city.get("id")
                           and str(c.get("flag") or "").strip().upper() not in ("BLUE", "RED")]
                if not neutral:
                    w("  [红] 没有无主夺控点可试，收工")
                    break
                neutral.sort(key=lambda c: GEO.distance(int(c["pos"]), rpos))
                city2 = neutral[0]
                w("  [红] D 阶段目标：%s(%s) @%s（归属=%s）"
                  % (city2.get("name"), city2.get("id"), GEO.hexid(int(city2["pos"])),
                     city2.get("flag")))
            cpos2 = int(city2["pos"])
            flag2 = next((c.get("flag") for c in cities if c.get("id") == city2.get("id")), None)
            if rpos != cpos2:
                to, st = S.step_toward(sessA, base7, red_move, rpos, cpos2, rec, log_action)
                if to:
                    w("  [红] 机动 %s→%s" % (GEO.hexid(rpos), GEO.hexid(to)))
                else:
                    w("  [红] 无法接近无主点，收工")
                    break
            else:
                res = P.act_take_city(sessA, base7, red_move, rec)
                log_action({"kind": "city_take", "side": "RED", "stage": "neutral", **res})
                if flag2 == "RED":
                    w("  [红] 占下无主点成功（flag=RED）⇒ 红方的 CityTake 可用"
                      "，所以 C 阶段失败的原因是**该点已被蓝方占领**")
                    if tick > stage_tick + 15:
                        break
                else:
                    w("  [红] 占无主点也失败（flag=%s）⇒ 问题在红方的 CityTake，不在归属" % flag2)
                    break
        tick += 1
        time.sleep(max(0.2, args.tick - (time.time() - t0)))

    io.open(os.path.join(d, "score_changes.json"), "w", encoding="utf-8").write(
        json.dumps(changes, ensure_ascii=False, indent=1))
    timeline.close()
    actions.close()
    w("")
    w("## 结果（%d tick）" % tick)
    for ch in changes:
        s = ch["score"]
        def g(k, side):
            v = (s or {}).get(k)
            return "-" if not v else v[side]
        w("  - tick %-3d %s 夺控 红%s/蓝%s 兵力 红%s/蓝%s 歼灭 红%s/蓝%s"
          % (ch["tick"], ch["wall"], g("captured", "red"), g("captured", "blue"),
             g("remaining", "red"), g("remaining", "blue"),
             g("killed", "red"), g("killed", "blue")))
    io.open(os.path.join(d, "report.md"), "w", encoding="utf-8").write("\n".join(log))
    print("ok ->", d)


if __name__ == "__main__":
    main()
