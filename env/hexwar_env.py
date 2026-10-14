# -*- coding: utf-8 -*-
"""Hexwar 兵推策略搜索环境。

面向对象：AI 智能体 / 强化学习 / LLM 规划器 / 手工脚本。

设计原则
--------
1. **观察是纯 JSON**：可序列化、字段自解释、坐标用「行列号 + mapid」双写，
   便于 LLM 直接读、也便于程序处理。
2. **动作是纯 JSON**：`{"type": "...", ...}`，可被 LLM 直接生成、可被校验。
3. **一次 step = 一个决策 + 时间前推**：把机动耗时算进时钟，
   避免实时调度，天然适合回合制的策略搜索。
4. **迷雾可选**：`fog=True` 时只能看到己方与「当前可观察到的」敌方，
   这才是真正的兵推——不然就是上帝视角。

用法
----
    from env import HexwarEnv
    env = HexwarEnv(side="BLUE")
    obs = env.reset(seed=1)
    while not env.done:
        acts = env.legal_actions()
        obs, r, done, info = env.step(acts[0])
    print(env.score())
"""
import os
import sys
import json
import copy
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import Game, geometry as G
from engine.equip import WEAPONS, EQUIPMENT, AMMO_FIELD
from engine import crt

# ---------------- 时间与代价常量（秒） ----------------
ATTACK_SEC = 10        # 一次直瞄射击占用时间
CAPTURE_SEC = 30       # 夺控判定耗时
HIDE_SEC = 10          # 隐蔽/解除隐蔽
WAIT_SEC = 10          # 主动等待的默认时长
LOAD_SEC = 30          # 上/下车
GRENADE_SEC = 10       # 投掷手雷
# 手册未给出单车载员数，此处按堆叠上限（手册 4.2）假定为 4
VEHICLE_SEATS = 4

MAX_BLOOD = {}         # 初始兵力缓存（按 data 记）


class HexwarEnv:
    """单方视角的兵推环境。"""

    def __init__(self, snapshot=None, side="BLUE", max_seconds=1800,
                 fog=True, dt=WAIT_SEC, victory="score"):
        self.snapshot = snapshot
        self.side = side
        self.max_seconds = max_seconds
        self.fog = fog
        self.dt = dt
        self.victory = victory
        self.game = None
        self.done = False
        self._history = []

    # ---------------- 生命周期 ----------------
    def reset(self, seed=None):
        self.game = Game(seed=seed, snapshot=self.snapshot)
        self.game.start()
        self.game.second = 0
        self.done = False
        self._history = []
        self._remember()
        return self.observe()

    def _remember(self):
        """记住当前可见的敌方（形成「已知但可能过期」的情报）。"""
        for u in self.game.units.values():
            if u.color == self.side or not u.alive():
                continue
            key = u.id
            if key not in MAX_BLOOD:
                MAX_BLOOD[key] = u.blood
            self._history.append({"t": self.game.second, "id": u.id,
                                  "pos": u.pos, "blood": u.blood})

    # ---------------- 观察 ----------------
    def _unit_view(self, u, known=False):
        d = {
            "id": u.id,
            "army": u.army or u.name,
            "name": u.name,
            "typeid": u.typeid,
            "pos": u.pos,
            "hexid": G.hexid(u.pos) if u.pos else "-",
            "blood": u.blood,
            "suppressed": 1 if u.stunned(self.game.second) else 0,
        }
        if not known:
            d.update({
                "color": u.color,
                "score": u.score,
                "armor": u.armor,
                "hidden": 1 if u.ste == 2 else 0,
                "ste": u.ste,
                "loaded_into": u.detail.get("carrier"),
                "carrying": list(u.detail.get("carried") or []),
                "weapons": [self._weapon_view(u, wid) for wid in u.wz],
                "can_observe_range": self._observe_range(u),
            })
        return d

    @staticmethod
    def _weapon_view(u, wid):
        w = WEAPONS.get(wid)
        if not w:
            return {"id": wid}
        fld = AMMO_FIELD.get(w[1])
        n = u.ammo.get(fld) if fld else None
        return {"id": wid, "name": w[0], "ammo_type": w[1], "range": w[2],
                "ammo": n if n is not None else -1}

    def _observe_range(self, u):
        eq = EQUIPMENT.get(u.data)
        return {"person": eq[4][0], "vehicle": eq[4][1], "air": eq[4][2]} if eq else {}

    def observe(self):
        g = self.game
        own, seen = [], []
        for u in g.units.values():
            if not u.alive():
                continue
            if u.color == self.side:
                own.append(self._unit_view(u))
            else:
                visible = (not self.fog) or any(
                    self.game.can_observe(o.id, u.id)
                    for o in g.units.values()
                    if o.alive() and o.color == self.side)
                if visible:
                    seen.append(self._unit_view(u))
        known = []
        if self.fog:
            latest = {}
            for h in self._history:
                if h["id"] in {v["id"] for v in seen}:
                    continue
                latest[h["id"]] = h
            for h in latest.values():
                known.append({"id": h["id"], "pos": h["pos"],
                              "hexid": G.hexid(h["pos"]), "blood": h["blood"],
                              "last_seen": h["t"], "stale": True})
        return {
            "time": g.second,
            "time_left": max(0, self.max_seconds - g.second),
            "side": self.side,
            "score": self.score(),
            "objectives": [{"id": c["id"], "name": c.get("name"), "pos": c["pos"],
                            "hexid": G.hexid(c["pos"]), "held_by": c.get("flag")}
                           for c in g.cities],
            "own": own,
            "enemy_visible": seen,
            "enemy_known": known,
            "done": self.done,
        }

    # ---------------- 计分（口径同线上） ----------------
    def score(self):
        g = self.game
        def side_score(color):
            survive = sum(u.score for u in g.units.values()
                          if u.color == color and u.alive())
            cap = sum(10 for c in g.cities if c.get("flag") == color)
            killed = sum(u.score for u in g.units.values()
                         if u.color and u.color != color and not u.alive())
            return {"remaining": survive, "captured": cap,
                    "killed": killed, "total": survive + cap + killed}
        me = side_score(self.side)
        opp = side_score("RED" if self.side == "BLUE" else "BLUE")
        return {"own": me, "enemy": opp, "diff": me["total"] - opp["total"]}

    # ---------------- 动作空间 ----------------
    def legal_actions(self, unit_id=None, move_radius=6):
        """列出当前合法动作。move_radius 控制枚举范围（太大会爆炸）。"""
        g = self.game
        acts = []
        units = [u for u in g.units.values()
                 if u.alive() and u.color == self.side
                 and not u.detail.get("carrier")      # 已上车的不再独立行动
                 and (unit_id is None or u.id == unit_id)]
        for u in units:
            if u.stunned(g.second):
                continue
            # 机动：邻格逐步扩展（BFS，受通行与堆叠约束）
            fronts = [(u.pos, [u.pos])]
            seenpos = {u.pos}
            for _ in range(move_radius):
                nxt = []
                for cur, path in fronts:
                    for nb in G.neighbors(cur):
                        if nb in seenpos:
                            continue
                        sec, _why = g.step_seconds(u, cur, nb)
                        if sec <= 0:
                            continue
                        seenpos.add(nb)
                        p2 = path + [nb]
                        nxt.append((nb, p2))
                        acts.append({"type": "move", "unit": u.id,
                                     "path": p2, "seconds": int(sec)})
                fronts = nxt
                if not fronts:
                    break
            # 射击：射程内 + 通视 + 可观察
            for t in g.units.values():
                if not t.alive() or t.color == u.color:
                    continue
                d = G.distance(u.pos, t.pos)
                for wid in u.wz:
                    w = WEAPONS.get(wid)
                    if not w or d > w[2]:
                        continue
                    if not g.can_observe(u.id, t.id):
                        continue
                    acts.append({"type": "attack", "unit": u.id, "target": t.id,
                                 "weapon": wid, "dist": d, "weapon_name": w[0]})
            # 夺控
            for c in g.cities:
                if c["pos"] == u.pos and c.get("flag") != self.side:
                    acts.append({"type": "capture", "unit": u.id})
            # 隐蔽切换（手册 4.5(2)：打击间隔期间不允许掩蔽）
            if not self._in_attack_gap(u):
                acts.append({"type": "hide", "unit": u.id,
                             "on": 0 if u.ste == 2 else 1})
            # 上车（手册 3.3）：人员与车辆同格
            if u.typeid == 1:
                for c in g.units.values():
                    if (c.alive() and c.typeid == 2 and c.color == u.color
                            and c.pos == u.pos and not c.stunned(g.second)
                            and not c.detail.get("carrier")
                            and self._seat_left(c) > 0):
                        acts.append({"type": "load", "unit": u.id, "carrier": c.id})
            # 下车（手册 3.3）：由车辆下达
            if u.typeid == 2 and u.detail.get("carried"):
                acts.append({"type": "unload", "unit": u.id})
            # 手雷（手册 3.15 / 4.7）：投掷范围通常为相邻格
            if u.typeid == 1 and 144 in u.wz and u.ammo.get("a5", 0) > 0:
                for nb in [u.pos] + list(G.neighbors(u.pos)):
                    if g.hex(nb):
                        acts.append({"type": "grenade", "unit": u.id,
                                     "target_hex": nb})
            # 停止机动（清空 pos2）
            if u.pos2 and u.pos2 != u.pos:
                acts.append({"type": "stop", "unit": u.id})
        acts.append({"type": "wait", "seconds": self.dt})
        return acts

    # ---------------- 执行 ----------------
    def step(self, action):
        """执行一个动作，推进时钟，返回 (obs, reward, done, info)。"""
        if self.done:
            return self.observe(), 0.0, True, {"msg": "已结束"}
        g = self.game
        before = self.score()
        info = {"msg": ""}
        cost = 0

        if isinstance(action, (list, tuple)):
            # 同时下达多条命令：逐条执行，时间取最大值
            costs = []
            for a in action:
                _o, _r, _d, i2 = self._apply(a)
                info["msg"] += i2.get("msg", "") + "; "
                costs.append(i2.get("seconds", 0))
            cost = max(costs) if costs else self.dt
        else:
            act = action
            if not act:
                act = {"type": "wait"}
            if act.get("type") == "wait":
                cost = int(act.get("seconds", self.dt))
            else:
                _o, _r, _d, info = self._apply(act)
                cost = int(info.get("seconds", self.dt))

        # 不允许越过推演总时长
        cost = min(int(cost), max(0, self.max_seconds - g.second))
        g.advance(cost)
        self._remember()
        self._check_done()
        after = self.score()
        reward = (after["own"]["total"] - after["enemy"]["total"]) - \
                 (before["own"]["total"] - before["enemy"]["total"])
        return self.observe(), float(reward), self.done, info

    def _apply(self, act):
        g = self.game
        t = act.get("type")
        u = g.units.get(act.get("unit"))
        if u is None and t != "wait":
            return None, 0.0, False, {"msg": "单位不存在", "seconds": 0}
        if t == "move":
            if u.detail.get("carrier"):
                return None, 0.0, False, {"msg": "已上车，随载具机动（手册 3.3）",
                                          "seconds": 0}
            path = list(act.get("path") or [])
            # 允许 path 带上起点（legal_actions 给出的就是含起点的完整路径），
            # 起点自身不产生机动耗时。
            if path and path[0] == u.pos:
                path = path[1:]
            total = 0
            cur = u.pos
            for step_to in path:
                sec, why = g.step_seconds(u, cur, step_to)
                if sec <= 0:
                    return None, 0.0, False, {"msg": "机动受阻：%s" % why, "seconds": total}
                u.pos2 = step_to
                u.pos = step_to
                u.rot = self._rot(cur, step_to)
                total += sec
                cur = step_to
            # 手册 3.3：已完成上车的步兵随车辆机动
            for pid in list(u.detail.get("carried") or []):
                p = g.units.get(pid)
                if p and p.alive():
                    p.pos = u.pos
                    p.pos2 = u.pos
            g.apply_city_capture(u)
            g.dirty = True
            return None, 0.0, False, {"msg": "机动 %d 格，耗时 %ds" % (len(path), total),
                                      "seconds": total}
        if t == "attack":
            r, err = g.attack(u.id, act.get("target"), weapon_id=int(act.get("weapon") or 0))
            if err:
                return None, 0.0, False, {"msg": "射击失败：%s" % err, "seconds": 0}
            u.detail["attacked_at"] = g.second
            return None, 0.0, False, {"msg": "射击 %s" % (r["result"],), "seconds": ATTACK_SEC}
        if t == "capture":
            c = g.apply_city_capture(u)
            return None, 0.0, False, {
                "msg": "夺控成功" if c else "夺控条件不满足",
                "seconds": CAPTURE_SEC}
        if t == "hide":
            if self._in_attack_gap(u):
                return None, 0.0, False, {
                    "msg": "打击间隔期间不允许掩蔽（手册 4.5(2)）", "seconds": 0}
            u.ste = 2 if act.get("on") else 0
            return None, 0.0, False, {"msg": "掩蔽切换", "seconds": HIDE_SEC}
        if t == "load":
            car = g.units.get(act.get("carrier"))
            if not car or not car.alive():
                return None, 0.0, False, {"msg": "载具不存在", "seconds": 0}
            if car.pos != u.pos:
                return None, 0.0, False, {"msg": "人与车必须同格（手册 3.3）", "seconds": 0}
            if u.stunned(g.second) or car.stunned(g.second):
                return None, 0.0, False, {
                    "msg": "被压制不能上/下车（手册 4.6.3(1)）", "seconds": 0}
            if self._seat_left(car) <= 0:
                return None, 0.0, False, {"msg": "载员已满", "seconds": 0}
            u.detail["carrier"] = car.id
            car.detail.setdefault("carried", []).append(u.id)
            return None, 0.0, False, {"msg": "上车完成", "seconds": LOAD_SEC}
        if t == "unload":
            if u.stunned(g.second):
                return None, 0.0, False, {
                    "msg": "车辆被压制时人员不能下车（手册 4.6.3(1)(4)）", "seconds": 0}
            out = []
            for pid in list(u.detail.get("carried") or []):
                p = g.units.get(pid)
                if not p or not p.alive():
                    continue
                p.pos = u.pos
                p.pos2 = u.pos
                p.detail.pop("carrier", None)
                out.append(p.id)
            u.detail["carried"] = []
            return None, 0.0, False, {"msg": "下车 %d 个" % len(out), "seconds": LOAD_SEC}
        if t == "grenade":
            res, err = g.grenade(u.id, int(act.get("target_hex") or u.pos))
            if err:
                return None, 0.0, False, {"msg": "手雷失败：%s" % err, "seconds": 0}
            return None, 0.0, False, {
                "msg": "手雷裁决 %d 个目标" % len(res), "seconds": GRENADE_SEC}
        if t == "stop":
            u.pos2 = u.pos
            return None, 0.0, False, {"msg": "停止", "seconds": 0}
        return None, 0.0, False, {"msg": "未知动作", "seconds": 0}

    # ---------------- 规则辅助 ----------------
    def _in_attack_gap(self, u):
        """手册 4.5(2)：棋子在打击间隔期间不允许掩蔽。"""
        return (self.game.second - u.detail.get("attacked_at", -10 ** 9)) < ATTACK_SEC

    @staticmethod
    def _seat_left(car):
        """车辆剩余载员位（手册未给载员数，按 VEHICLE_SEATS 假定）。"""
        return VEHICLE_SEATS - len(car.detail.get("carried") or [])

    @staticmethod
    def _rot(a, b):
        ax, ay = G.pos_of(a)
        bx, by = G.pos_of(b)
        import math
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return 0
        return int(round(math.degrees(math.atan2(dy, dx)) / 60.0) * 60) % 360

    def _check_done(self):
        g = self.game
        if g.second >= self.max_seconds:
            self.done = True
        if not any(u.alive() and u.color == self.side for u in g.units.values()):
            self.done = True
        other = "RED" if self.side == "BLUE" else "BLUE"
        if not any(u.alive() and u.color == other for u in g.units.values()):
            self.done = True
        if self.victory == "capture" and g.cities and \
                all(c.get("flag") == self.side for c in g.cities):
            self.done = True

    # ---------------- 文本渲染（给 LLM / 调试用） ----------------
    def render(self, width=48, height=16):
        g = self.game
        if not g.hexes:
            return "(空地图)"
        rows = sorted({G.split_mapid(m)[0] for m in g.hexes})
        cols = sorted({G.split_mapid(m)[1] for m in g.hexes})
        r0, r1 = rows[0], min(rows[0] + height - 1, rows[-1])
        c0, c1 = cols[0], min(cols[0] + width - 1, cols[-1])
        grid = {}
        for u in g.units.values():
            if u.alive() and u.pos:
                grid[u.pos] = ("A" if u.color == self.side else "E") + str(u.blood)
        for c in g.cities:
            grid.setdefault(c["pos"], "**")
        out = ["    " + "".join("%2d" % (c % 100) for c in range(c0, c1 + 1))]
        for r in range(r0, r1 + 1):
            line = "%3d " % r
            for c in range(c0, c1 + 1):
                mid = G.make_mapid(r, c)
                h = g.hex(mid)
                if mid in grid:
                    line += "%2s" % grid[mid]
                elif h is None:
                    line += " ."
                else:
                    cond = int(h.get("cond") or 0)
                    line += {0: "  ", 6: "~~", 7: "##", 8: "TT", 9: "TT"}.get(cond, "  ")
            out.append(line)
        out.append("")
        out.append("图例: A#=己方算子 E#=敌方算子 **=夺控点 ~~=过河 ##=居民地 TT=丛林地 .=界外")
        out.append("时间 %ds / 剩余 %ds" % (g.second, self.max_seconds - g.second))
        return "\n".join(out)

    def state_json(self):
        return json.dumps(self.observe(), ensure_ascii=False, indent=1)
