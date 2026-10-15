# -*- coding: utf-8 -*-
"""实测计分口径：夺控分每点分值 / 是否按时间重复计分 / 歼灭分公式。

为什么需要它：已采集的 33 个产物**全在开局态**，夺控分与歼灭分恒为 0，
所以 `docs/计分规则待确认.md` 里这两项一直标着"无法反推"。
本脚本把那两个动作**真做出来**，并逐 tick 读 `Report_All.asp` 对账：

    --phase capture  把一支蓝方地面单位走到夺控点 → 反复 CityTake → 占住不动继续采样
                     （看：占一次值多少分？主要/次要同分吗？是否按持续时间重复加分？）
    --phase kill     把最近的可射手推进到"通视 + 射程内" → 连续开火 → 直到目标被歼灭
                     （看：整单位被歼时"歼灭对手兵力得分"跳多少？）

产物：`7527_transport_capture/score_probe_<时间戳>/`
    timeline.jsonl（逐 tick 全量）、score_changes.json（**每次计分页变化的快照**）、
    actions.jsonl（每个动作的原始请求/响应）、report.md（人读汇总）。

安全边界：
    * 只在**练习服**（默认 `www.hexwar.cn`）的个人推演室操作；`HEXWAR_BASE` 指向别处会直接拒绝。
    * 必须显式设置 `HEXWAR_ALLOW_HTTP=1`（站点无 HTTPS）。
    * 凭证只从环境变量读；产物不写 Cookie / 密码 / 认证头。

用法：
    $env:HEXWAR_USER='...'; $env:HEXWAR_PASS='...'
    $env:HEXWAR_USER2='...'; $env:HEXWAR_PASS2='...'; $env:HEXWAR_ALLOW_HTTP='1'
    py -3.13 tools/hex_score_probe.py --room 7 --phase capture --minutes 10
    py -3.13 tools/hex_score_probe.py --room 7 --phase kill    --minutes 15
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
import hex_play_round as P                   # noqa: E402  （复用：登录/进房/采样/机动/夺控）
import hex_combat_round as C                 # noqa: E402  （复用：通视/选武器/开火）
from engine import geometry as GEO           # noqa: E402
from engine.equip import WEAPONS             # noqa: E402

CAP = r"d:\兵推\7527_transport_capture"
PRACTICE_HOSTS = ("www.hexwar.cn",)

# Report_All 的三个分项顺序固定：红在前、蓝在后（hex_score_audit.py 已验证 413 次）
SECTIONS = (("captured", "夺控点得分"),
            ("remaining", "剩余兵力得分"),
            ("killed", "歼灭对手兵力得分"))
PAT = re.compile(r'class=\\?"(RED|BLUE)\\?">\s*(\d+)\s*分')


def parse_score(text):
    """从 Report_All 原文里切出三分项 → {red, blue}。返回 None 表示没解析到。

    两个实测踩到的坑（自检 `analysis/_probe_selftest.py` 就是因此加的）：

    1. 分项名在**同一行里出现两次**（`红方夺控点得分</td><td width="50%">蓝方夺控点得分`）
       ⇒ 必须 `split(head, 1)[1]`（只切第一处）；用 `split(head)[1]` 只会拿到两个表头
       之间那 26 个字符，永远看不到数值。
    2. 页面里分项名内部可能带空格（「剩余兵力 得分」），所以先把所有空白压掉再找。
    """
    text = "".join(text.split())
    out = {}
    for key, head in SECTIONS:
        if head not in text:
            out[key] = None
            continue
        chunk = text.split(head, 1)[1][:4000]
        hits = PAT.findall(chunk)
        out[key] = {"red": int(hits[0][1]), "blue": int(hits[1][1])} if len(hits) >= 2 else None
    return out


def flat(score):
    """压成一行便于逐 tick 比较。"""
    if not score:
        return None
    parts = []
    for key, _head in SECTIONS:
        s = score.get(key)
        parts.append("%s:%s/%s" % (key, "-" if not s else s["red"],
                                   "-" if not s else s["blue"]))
    return " ".join(parts)


def weapon_ready(sess, base7, unit):
    """`com/ObjWeaponReady.asp`：每成功一发后 `att` 变 1，必须复位才能再开火。"""
    r = P.get(sess, base7 + "com/ObjWeaponReady.asp", params={"ObjID": unit},
              headers={"Referer": base7 + "main.html"})
    return H.decode(r.content).strip()[:80]


def weapon_range(wid):
    info = WEAPONS.get(int(wid))
    return info[2] if info else 0


def pick_shooter(units):
    """蓝方活着的地面单位里，选"武器射程最长"的那个当射手。"""
    best = None
    for uid, a in units.items():
        if a.get("color") != "BLUE" or str(a.get("blood")) in ("0", ""):
            continue
        if str(a.get("typeid")) == "4":
            continue
        ids = [int(x) for x in str(a.get("wz") or "").replace(" ", "").split(",")
               if x.strip().isdigit()]
        rng = max([weapon_range(w) for w in ids] or [0])
        if best is None or rng > best[1]:
            best = (uid, rng, ids)
    return best


def nearest(units, frm, want_color):
    best = None
    for uid, a in units.items():
        if a.get("color") != want_color or str(a.get("blood")) in ("0", ""):
            continue
        d = GEO.distance(frm, int(a.get("pos") or 0))
        if best is None or d < best[1]:
            best = (uid, d, int(a.get("pos") or 0))
    return best


def step_toward(sess, base7, unit, frm, goal, rec, log_action):
    """朝目标格走一格（选"离目标最近且 `updatePos` 不为 0"的邻格）。"""
    cands = sorted(GEO.neighbors(frm), key=lambda n: GEO.distance(n, goal))
    for to in cands[:3]:
        step = P.act_move(sess, base7, unit, frm, to, rec)
        log_action({"kind": "move", "unit": unit, "frm": frm, "to": to,
                    "updatePos_ms": step.get("updatePos_ms"),
                    "move_end": step.get("move_end"), "com_post": step.get("com_post")})
        if str(step.get("updatePos_ms") or "0") != "0":
            return to, step
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", type=int, default=7)
    ap.add_argument("--color2", default="RED")
    ap.add_argument("--phase", choices=("capture", "kill"), default="capture")
    ap.add_argument("--city-name", default="次要", choices=("次要", "主要"),
                    help="capture 阶段的目标点类型（先次要，再主要）")
    ap.add_argument("--minutes", type=float, default=10.0, help="真实时间上限（分钟）")
    ap.add_argument("--tick", type=float, default=1.0, help="采样间隔（秒）；1 Hz 才能让服务端时钟正常推进")
    ap.add_argument("--hold-ticks", type=int, default=40,
                    help="capture 成功后再占住采样的 tick 数（检测是否按时间重复加分）")
    ap.add_argument("--max-shots", type=int, default=12, help="kill 阶段最多开火次数")
    ap.add_argument("--max-move", type=int, default=60, help="kill 阶段最多机动步数")
    args = ap.parse_args()

    if urlsplit(H.HOST).hostname not in PRACTICE_HOSTS:
        sys.exit("只允许练习服 %s；HEXWAR_BASE 现为 %s（拒绝在比赛服实测）"
                 % (PRACTICE_HOSTS, H.HOST))
    H.guard()
    uA, pA = os.environ.get("HEXWAR_USER", ""), os.environ.get("HEXWAR_PASS", "")
    uB, pB = os.environ.get("HEXWAR_USER2", ""), os.environ.get("HEXWAR_PASS2", "")
    if not uB or not pB:
        sys.exit("请设置 HEXWAR_USER2 / HEXWAR_PASS2（两个账号才能开局）")

    base7 = "%s/WARGAMEAI%d/" % (H.HOST, args.room)
    H.BASE7 = base7
    stamp = time.strftime("%Y%m%d-%H%M%S")
    d = os.path.join(CAP, "score_probe_%s_%s" % (args.phase, stamp))
    os.makedirs(d, exist_ok=True)
    timeline = io.open(os.path.join(d, "timeline.jsonl"), "w", encoding="utf-8")
    actions = io.open(os.path.join(d, "actions.jsonl"), "w", encoding="utf-8")
    log = []

    def w(x=""):
        log.append(str(x))
        print(x)

    def log_action(obj):
        actions.write(json.dumps(obj, ensure_ascii=False) + "\n")
        actions.flush()

    w("# 计分口径实测  phase=%s  %s" % (args.phase, stamp))
    w("- 客户端目录 %s  采样 %.1fs  上限 %.0f 分钟" % (base7, args.tick, args.minutes))

    # ---------- 1) 复位房间 ----------
    sessA, _ = P.login_as(uA, pA)
    url = "%s/WARGAMEAI%d/Reset/Post.asp" % (H.HOST, args.room)
    r = P.get(sessA, url, params={"scenarioId": "7527", "roomId": str(args.room)})
    m = re.search(r'<form[^>]*action="([^"]*)"[^>]*>(.*?)</form>', H.decode(r.content), re.S)
    if m:
        data = {}
        for im in re.finditer(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>',
                              m.group(2), re.S):
            data[im.group(1)] = im.group(2).strip()
        r2 = sessA.post(requests.compat.urljoin(url, m.group(1)), data=data, timeout=30)
        w("- 复位房间 -> %s" % r2.status_code)
    else:
        w("- 复位房间：未拿到表单（可能无需复位）")

    # ---------- 2) 两个账号进房 ----------
    sessA, uidA = P.login_as(uA, pA)
    okA, partsA = P.join(sessA, uidA, "NONE", args.room, base7)
    w("- A(导演 %s) 进房: %s" % (uidA, "在座" if okA else "**不在座**"))
    sessB, uidB = P.login_as(uB, pB)
    okB, _ = P.join(sessB, uidB, args.color2, args.room, base7)
    time.sleep(1)
    okB, _ = P.in_room(sessB, base7)
    w("- B(%s %s) 进房: %s" % (args.color2, uidB, "在座" if okB else "**不在座**"))

    # ---------- 3) 开局 ----------
    H.S = sessA
    started = False
    for attempt in range(6):
        for v in ({"AIStart": "false", "RoomSecond": "0"},
                  {"AIStart": "true", "RoomSecond": "0"}):
            rs = P.get(sessA, base7 + "RoomStart.asp", params=v,
                       headers={"Referer": base7 + "main.html"})
            txt = H.decode(rs.content)
            w("- RoomStart(第%d次) %s -> %r" % (attempt + 1, v, txt[:100]))
            if txt.strip() not in ("-1", "0", ""):
                w("  >>> 开局成功 Time1=%s" % txt.split(",")[0])
                started = True
                break
            time.sleep(1.5)
        if started:
            break
        okB, _ = P.in_room(sessB, base7)
        if not okB:
            okB, _ = P.join(sessB, uidB, args.color2, args.room, base7)
            w("  - B 不在座，已重新进房：%s" % ("在座" if okB else "仍不在座"))
    if not started:
        w("  !!! 开局失败：只有观测、没有推演推进，本次数据无效")
    io.open(os.path.join(d, "setup_log.md"), "w", encoding="utf-8").write("\n".join(H.LOG))

    # ---------- 4) 逐 tick 主循环 ----------
    deadline = time.time() + args.minutes * 60
    tick = 0
    last_flat = None
    changes = []
    # 阶段状态
    state = {"unit": None, "city": None, "dest": None, "arrived": False,
             "taken": False, "hold": 0, "shots": 0, "moves": 0, "target": None,
             "ready_early": False, "goal": None, "stuck": 0}

    while time.time() < deadline:
        t0 = time.time()
        rec = P.sample(sessA, base7)
        rec["tick"] = tick
        rec["wall"] = time.strftime("%H:%M:%S")
        rec["score"] = parse_score(rec["report_all"])
        timeline.write(json.dumps(rec, ensure_ascii=False) + "\n")
        timeline.flush()

        ug = rec["user_get"] if isinstance(rec["user_get"], dict) else {}
        rsec = ug.get("20", "?")
        cur = flat(rec["score"])
        moved = cur != last_flat
        if moved:
            w("tick %2d %s RoomSecond=%-4s 计分变化: %s"
              % (tick, rec["wall"], rsec, cur))
            changes.append({"tick": tick, "wall": rec["wall"], "room_second": rsec,
                            "score": rec["score"], "flat": cur,
                            "cities": rec["cities"],
                            "alive": {k: v.get("blood") for k, v in rec["units"].items()
                                      if str(v.get("blood")) not in ("0", "")}})
            last_flat = cur

        running = bool(ug.get("3", "").strip())
        if not running:
            tick += 1
            time.sleep(max(0.2, args.tick - (time.time() - t0)))
            continue

        units, cities = rec["units"], [c for c in rec["cities"] if c.get("pos")]

        # ---- 阶段目标选择 ----
        if args.phase == "capture":
            if state["unit"] is None:
                picks = [c for c in cities if c.get("name") == args.city_name]
                cands = []
                for c in picks:
                    best = nearest(units, int(c["pos"]), "BLUE")
                    if best:
                        cands.append((best[1], best[0], c))
                if not cands:
                    w("- 找不到蓝方单位或目标点，退出")
                    break
                cands.sort(key=lambda x: x[0])
                dist, uid_, city = cands[0]
                state.update(unit=uid_, city=city, dest=int(city["pos"]))
                w("→ 目标：%s(%s) @%s；执行单位 %s (%s) 距离 %d 格"
                  % (city.get("name"), city.get("id"), GEO.hexid(int(city["pos"])),
                     uid_, units[uid_].get("ico"), dist))
        else:
            if state["unit"] is None:
                sh = pick_shooter(units)
                if not sh:
                    w("- 找不到蓝方可射手，退出")
                    break
                state["unit"], state["range"], state["wz"] = sh
                w("→ 射手 %s (%s) 武器 %s 射程 %d"
                  % (sh[0], units[sh[0]].get("ico"), sh[2], sh[1]))
            if state["target"] is None and state["unit"] in units:
                frm = int(units[state["unit"]].get("pos") or 0)
                tg = nearest(units, frm, args.color2)
                if tg:
                    state["target"] = tg[0]
                    w("→ 目标 %s (%s) @%s 距离 %d 格"
                      % (tg[0], units[tg[0]].get("ico"), GEO.hexid(tg[2]), tg[1]))

        uid_ = state["unit"]
        if uid_ not in units:
            tick += 1
            time.sleep(max(0.2, args.tick - (time.time() - t0)))
            continue
        frm = int(units[uid_].get("pos") or 0)

        if args.phase == "capture":
            city_pos = state["dest"]
            on_city = (frm == city_pos)
            if not on_city:
                if state["moves"] < 400:
                    to, step = step_toward(sessA, base7, uid_, frm, city_pos, rec, log_action)
                    if to:
                        state["moves"] += 1
                        w("  → 机动 %s %s→%s 耗时=%sms"
                          % (uid_, GEO.hexid(frm), GEO.hexid(to),
                             (step or {}).get("updatePos_ms")))
                    else:
                        w("  ! %s 无法朝 %s 机动（updatePos=0）"
                          % (uid_, GEO.hexid(city_pos)))
                        state["stuck"] += 1
                        if state["stuck"] > 6:
                            break
            else:
                res = P.act_take_city(sessA, base7, uid_, rec)
                log_action({"kind": "city_take", **res})
                gained = [c for c in cities if c.get("flag") and c.get("flag") != "GREEN"]
                w("  → 夺控 %s 返回=%r  带旗点=%s"
                  % (uid_, str(res.get("response"))[:40],
                     [(c.get("id"), c.get("flag")) for c in gained]))
                state["taken"] = state["taken"] or bool(gained)
                if state["taken"]:
                    state["hold"] += 1
                if state["hold"] >= args.hold_ticks:
                    w("  - 占住 %d tick 后收工（用于判断是否按时间重复加分）" % state["hold"])
                    break
        else:
            tgt = state["target"]
            if tgt not in units:
                w("- 目标不存在，收工")
                break
            tpos = int(units[tgt].get("pos") or 0)
            dist = GEO.distance(frm, tpos)
            in_los = C.los_ok(frm, tpos)
            rng = state.get("range") or 0
            if not in_los or dist > rng:
                if state["moves"] >= args.max_move:
                    w("- 机动步数用尽仍未进入射程/通视（距离 %d，通视 %s），收工" % (dist, in_los))
                    break
                to, step = step_toward(sessA, base7, uid_, frm, tpos, rec, log_action)
                if to:
                    state["moves"] += 1
                    w("  → 接近 %s %s→%s（距目标 %d 格，通视 %s）"
                      % (uid_, GEO.hexid(frm), GEO.hexid(to), dist, in_los))
                else:
                    w("  ! 无法接近（updatePos=0）")
                    state["stuck"] += 1
                    if state["stuck"] > 6:
                        break
            else:
                if state["shots"] >= args.max_shots:
                    w("- 达到最大开火次数 %d，收工" % args.max_shots)
                    break
                pick = C.best_weapon(units, uid_, tgt, dist)
                if not pick:
                    w("- 没有可用武器（距离 %d），收工" % dist)
                    break
                idx, wid, info, lvl = pick
                rdy = weapon_ready(sessA, base7, uid_)
                step = C.fire(sessA, base7, uid_, tgt, wid, units[uid_].get("color"), rec)
                state["shots"] += 1
                log_action({"kind": "fire", "weapon": wid, "weapon_name": info[0],
                            "expected_level": lvl, "weapon_ready": rdy, **step})
                w("  → 开火#%d %s→%s 武器 %s(射程%s) 距%d 预期攻级=%s 返回=%r"
                  % (state["shots"], uid_, tgt, info[0], info[2], dist, lvl,
                     str(step.get("attack_resp"))[:60]))

        tick += 1
        time.sleep(max(0.2, args.tick - (time.time() - t0)))

    # ---------- 5) 汇总 ----------
    io.open(os.path.join(d, "score_changes.json"), "w", encoding="utf-8").write(
        json.dumps(changes, ensure_ascii=False, indent=1))
    timeline.close()
    actions.close()
    w("")
    w("## 结果")
    w("- 采样 %d tick；动作 %d 个" % (tick, len(changes)))
    w("- 计分页一共变化 %d 次：" % len(changes))
    for ch in changes:
        s = ch["score"]
        def g(k, side):
            v = (s or {}).get(k)
            return "-" if not v else v[side]
        w("  - tick %-3d %s RoomSecond=%-5s 夺控 红%s/蓝%s 兵力 红%s/蓝%s 歼灭 红%s/蓝%s"
          % (ch["tick"], ch["wall"], ch["room_second"],
             g("captured", "red"), g("captured", "blue"),
             g("remaining", "red"), g("remaining", "blue"),
             g("killed", "red"), g("killed", "blue")))
    io.open(os.path.join(d, "report.md"), "w", encoding="utf-8").write("\n".join(log))
    print("ok ->", d)


if __name__ == "__main__":
    main()
