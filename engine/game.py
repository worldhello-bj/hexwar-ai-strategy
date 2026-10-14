# -*- coding: utf-8 -*-
"""离线裁决引擎：状态、规则与指令处理。

设计要点（来自对官方客户端的实测与手册第 4 章）：
- 引擎是唯一权威；客户端每秒通过 ObjAjax.asp 覆盖式同步。
- 机动指令由客户端本地播放动画，服务端在 com/updatePos.asp 返回本格耗时(ms)。
- 直瞄射击由 com/Attack.asp 裁决，结果通过下一帧 ObjAjax 下发（血量/压制变化）。
"""
import os
import json
import math
import time
import random

from . import geometry as G
from . import crt
from .equip import EQUIPMENT, WEAPONS, AMMO_FIELD, ANTI_AIR_CLASS, CRT_AIR_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.environ.get("HEXWAR_SNAP", os.path.join(os.path.dirname(HERE), "snapshot", "parsed"))

# 压制持续（手册 4.6.3：150 秒）
SUPPRESS_SEC = 150
# 疲劳移除时长（想定参数，取 SetUp.js 默认口径）
FATIGUE_SEC = 60
# 夺控判定所需兵力
CAPTURE_MIN_BLOOD = 1


class Unit:
    __slots__ = ("id", "data", "name", "army", "group", "typeid", "color", "pos",
                 "pos2", "rot", "blood", "space", "score", "armor", "units",
                 "wz", "ammo", "stunned_until", "fatigued_until", "missile_ids",
                 "uid", "ste", "keep", "pass_", "att", "ai", "c0", "c3", "detail",
                 "radar", "see", "task")

    def __init__(self, d):
        self.id = d["id"]
        self.data = int(d.get("data") or 0)
        eq = EQUIPMENT.get(self.data, ("未知", 1, "无装甲", 0, (0, 0, 0), []))
        self.name = d.get("name") or eq[0]
        self.army = d.get("army") or ""
        self.group = d.get("group") or ""
        self.typeid = int(d.get("typeid") or eq[1])
        self.color = d.get("color") or ""
        self.pos = int(d.get("pos") or 0)
        self.pos2 = int(d.get("pos2") or 0)
        self.rot = int(d.get("rot") or 0)
        self.blood = int(d.get("blood") or 0)
        self.space = int(d.get("space") or 0)
        self.score = int(d.get("score") or eq[3])
        self.armor = eq[2]
        self.units = max(1, int(d.get("blood") or 1)) if self.typeid in (1, 2) else 1
        self.wz = [int(x) for x in (d.get("wz") or "").replace(" ", "").split(",") if x.strip().isdigit()]
        if not self.wz:
            self.wz = list(eq[5])
        self.ammo = {"a3": int(d.get("a3") or 0), "a4": int(d.get("a4") or 0),
                     "a5": int(d.get("a5") or 0)}
        self.stunned_until = 0.0
        self.fatigued_until = 0.0
        self.missile_ids = []
        self.uid = int(d.get("uid") or 0)
        self.ste = int(d.get("ste") or 0)
        self.keep = int(d.get("keep") or 0)
        self.pass_ = int(d.get("pass") or 0)
        self.att = int(d.get("att") or 0)
        self.ai = int(d.get("ai") or 0)
        self.c0 = int(d.get("c0") or 0)
        self.c3 = int(d.get("c3") or 0)
        self.radar = d.get("radar") or ""
        self.see = int(d.get("see") or 0)
        self.task = int(d.get("task") or 0)
        self.detail = {}

    # --- 便于裁决的派生属性 ---
    def moving(self, now):
        return self.detail.get("move_until", 0) > now

    def stunned(self, now):
        return self.stunned_until > now

    def fatigued(self, now):
        return self.fatigued_until > now

    def alive(self):
        return self.blood > 0

    def weapon_name(self, idx=0):
        if not self.wz:
            return None
        wid = self.c3 if self.c3 in self.wz else self.wz[min(idx, len(self.wz) - 1)]
        w = WEAPONS.get(wid)
        return w[0] if w else None

    def is_anti_air_capable(self):
        for wid in self.wz:
            w = WEAPONS.get(wid)
            if w and w[0] in ANTI_AIR_CLASS:
                return True
        return False


class Game:
    """一局推演。完全本地，无外部依赖。"""

    def __init__(self, seed=None, snapshot=None):
        if seed is not None:
            random.seed(seed)
        snap = snapshot or SNAP
        self.snap_dir = snap
        self.hexes = {}
        p = os.path.join(snap, "map_hexes.json")
        raw = json.load(open(p, encoding="utf-8"))
        for k, v in raw.items():
            self.hexes[int(k)] = v
        self.cities = json.load(open(os.path.join(snap, "cities.json"), encoding="utf-8"))
        for c in self.cities:
            c["pos"] = int(c.get("pos") or 0)
        self.units = {}
        for u in json.load(open(os.path.join(snap, "units.json"), encoding="utf-8")):
            uu = Unit(u)
            self.units[uu.id] = uu

        self.started = False
        self.t0 = 0.0          # 推演开始时刻
        self.second = 0        # 已推演秒数
        self.round = 0
        self.log = []
        self.orders = {}       # ComID -> 指令
        self.com_seq = 0
        self.fires = {}        # ObjID -> 射击特效
        self.dirty = True
        self.obj_fire_seq = {}
        self.start_str = ""    # 开始时刻的日期串（客户端时钟用）

    # ---------------- 时钟 ----------------
    def start(self):
        self.started = True
        self.t0 = time.time() - self.second
        self.start_str = self.now_str()
        return True

    def tick(self):
        if not self.started:
            return
        self.second = int(time.time() - self.t0)
        self._expire_states()

    def advance(self, seconds):
        """把推演时钟向前推进若干秒（供无头模拟/策略搜索使用，与真实时钟无关）。"""
        if seconds <= 0:
            return self.second
        self.second += seconds
        self.t0 = time.time() - self.second
        self._expire_states()
        return self.second

    def _expire_states(self):
        now = self.second
        for u in self.units.values():
            if u.stunned_until and u.stunned_until <= now:
                u.stunned_until = 0.0
                u.keep = 0
            if u.fatigued_until and u.fatigued_until <= now:
                u.fatigued_until = 0.0

    @property
    def time1(self):
        return 1 if self.started else ""

    # ---------------- 地形 / 通行 ----------------
    def hex(self, mapid):
        return self.hexes.get(int(mapid))

    def elevation(self, mapid):
        h = self.hex(mapid)
        return int(h["elevation"]) if h else 0

    def terrain_kind(self, mapid):
        """粗略地形类别（由 cond / note 推断）。"""
        h = self.hex(mapid)
        if not h:
            return None
        cond = int(h.get("cond") or 0)
        note = h.get("note") or ""
        if cond == 7:
            return "居民地"
        if cond == 6:
            return "过河"
        if cond in (8, 9):
            return "丛林地"
        return None

    def passable(self, mapid, unit):
        h = self.hex(mapid)
        if not h:
            return False, "地图外"
        step = int(h.get("step") or 0)
        if step == 0:
            return False, "禁行区"
        terr = self.terrain_kind(mapid)
        if unit.typeid == 2:
            if terr == "过河":
                return False, "车辆不可跨越水系"
            if step == -1 and unit.c0 != 2:
                return False, "车辆禁行"
        return True, ""

    def step_seconds(self, unit, from_id, to_id):
        """返回进入 to_id 一格所需秒数（客户端会 ×1000 作为动画时长）。"""
        ok, why = self.passable(to_id, unit)
        if not ok:
            return 0, why
        base = {1: 60.0, 2: 12.0, 3: 6.0, 4: 999.0}.get(unit.typeid, 60.0)
        terr = self.terrain_kind(to_id)
        if unit.typeid == 1:
            if terr == "过河":
                base *= 2.0            # 步兵过河 1/2 速
            dh = abs(self.elevation(to_id) - self.elevation(from_id))
            if dh // 20 >= 4:
                base *= 2.0
            if unit.ste == 4:          # 冲锋
                base /= 4.0
                if random.random() < 0.5:
                    unit.fatigued_until = self.second + FATIGUE_SEC
        elif unit.typeid == 2:
            if terr == "丛林地":
                base *= 2.0
            elif terr == "居民地":
                base *= 3.0
            dh = abs(self.elevation(to_id) - self.elevation(from_id))
            lvl = dh // 20
            if lvl >= 6:
                return 0, "高差过大无法通过"
            if lvl >= 1:
                base *= (lvl + 1)
        # 堆叠限制：同格本方地面单位不超过 4
        n = sum(1 for u in self.units.values()
                if u.alive() and u.color == unit.color and u.pos == to_id
                and u.typeid in (1, 2) and u.id != unit.id)
        if n >= 4:
            return 0, "违反堆叠规则"
        return base, ""

    # ---------------- 通视 / 观察 ----------------
    def _los_blocks(self, mapid, endpoint_ids):
        """连线经过该格时，其用于阻挡的等效高程。"""
        e = self.elevation(mapid)
        if mapid in endpoint_ids:
            return e          # 端点所在格的居民地/丛林地不修正
        terr = self.terrain_kind(mapid)
        if terr in ("居民地", "丛林地"):
            e += 1
        return e

    def line_hexes(self, a, b):
        """a→b 的格序列（线性插值取整）。"""
        ax, ay = G.pos_of(a)
        bx, by = G.pos_of(b)
        n = max(abs(ax - bx), abs(ay - by))
        steps = max(1, int(n / (G.HEX_W / 2)))
        # 用立方坐标插值更稳
        aq, ar, as_ = G.to_cube(a)
        bq, br, bs = G.to_cube(b)
        d = max(abs(aq - bq), abs(ar - br), abs(as_ - bs))
        out = []
        for i in range(d + 1):
            t = i / d if d else 0
            q = aq + (bq - aq) * t
            r = ar + (br - ar) * t
            out.append(self._cube_round(q, r))
        return out

    @staticmethod
    def _cube_round(q, r):
        s = -q - r
        rq, rr, rs = round(q), round(r), round(s)
        dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
        if dq > dr and dq > ds:
            rq = -rr - rs
        elif dr > ds:
            rr = -rq - rs
        row = rr
        col = rq + (rr - (rr & 1)) // 2
        return G.make_mapid(row, col)

    def los(self, a, b, h_obs=None, h_tar=None):
        """通视判定（手册 4.4：高看低，高者所在格高程 +1 个等级）。"""
        if a == b:
            return True, []
        pa = G.distance(a, b)
        if pa <= 1:
            return True, []          # 相邻格总是通视
        ea = self.elevation(a)
        eb = self.elevation(b)
        if h_obs is None:
            h_obs, h_tar = (ea, eb) if ea >= eb else (eb, ea)
        else:
            if h_obs >= h_tar:
                ea, eb = h_obs, h_tar
                obs_is_a = True
            else:
                ea, eb = h_tar, h_obs
                obs_is_a = False
        # 观察点所在格高程 +1 个等级（20m）
        ea += 20
        path = self.line_hexes(a, b)
        blockers = []
        for i, hid in enumerate(path):
            if hid in (a, b):
                continue
            t = i / (len(path) - 1) if len(path) > 1 else 0
            line_e = ea + (eb - ea) * t
            be = self._los_blocks(hid, {a, b})
            if be > line_e:
                blockers.append(hid)
        return (len(blockers) == 0), blockers

    def observe_range(self, obs, tgt):
        """观察者对被观察者的有效观测距离（格）。"""
        eq = EQUIPMENT.get(obs.data, None)
        if obs.typeid == 3:
            base = 2 if obs.name in ("旋翼无人机", "自爆无人机", "巡飞弹") else 2
            rng = base
        else:
            rng = (eq[4][1] if eq else 25) if tgt.typeid == 2 else (eq[4][0] if eq else 10)
            if tgt.typeid == 3:
                rng = (eq[4][2] if eq else 1)
        if obs.typeid == 3:
            rng = 2 if tgt.typeid != 3 else 0
        terr = self.terrain_kind(tgt.pos)
        if terr in ("居民地", "丛林地"):
            rng *= 0.5
        if tgt.ste == 2 or tgt.detail.get("hidden"):
            rng *= 0.5
        return rng

    def can_observe(self, obs_id, tgt_id):
        o = self.units.get(obs_id)
        t = self.units.get(tgt_id)
        if not o or not t or not o.alive() or not t.alive():
            return False
        d = G.distance(o.pos, t.pos)
        if d > self.observe_range(o, t):
            return False
        ok, _ = self.los(o.pos, t.pos)
        return ok

    # ---------------- 指令 ----------------
    def new_command(self, data):
        self.com_seq += 1
        cid = self.com_seq
        self.orders[cid] = {"data": data, "ts": self.now_str(), "done": False}
        return cid

    def now_str(self):
        return time.strftime("%Y/%m/%d %H:%M:%S")

    def apply_city_capture(self, unit):
        """夺控：到达夺控点格且该格及相邻 6 格无敌方地面单位。"""
        if unit.typeid == 3:
            return None
        for c in self.cities:
            if c["pos"] != unit.pos:
                continue
            zone = [c["pos"]] + G.neighbors(c["pos"])
            enemy = [u for u in self.units.values()
                     if u.alive() and u.color and unit.color and u.color != unit.color
                     and u.typeid in (1, 2) and u.pos in zone]
            if enemy:
                return None
            c["flag"] = unit.color or c.get("flag")
            c["ico"] = unit.color or c.get("ico")
            self.record("%s 夺占 %s" % (unit.army or unit.name, c.get("name")))
            return c
        return None

    def record(self, text):
        self.log.append("[%s] %s" % (self._fmt_sec(self.second), text))
        if len(self.log) > 400:
            self.log = self.log[-400:]

    @staticmethod
    def _fmt_sec(s):
        return "%02d:%02d" % (s // 60, s % 60)

    # ---------------- 直瞄射击 ----------------
    def attack(self, obj_id, tar_id, weapon_id=0, com_id=0, dist=None):
        a = self.units.get(obj_id)
        t = self.units.get(tar_id)
        if not a or not t:
            return None, "棋子不存在"
        if not a.alive():
            return None, "射击单位已被消灭"
        if not t.alive():
            return None, "目标已被消灭"
        if a.stunned(self.second):
            a.keep = 1
            return None, "压制状态下不能射击"
        # 同格交战
        if a.pos == t.pos and a.color == t.color:
            return None, "不能攻击己方"

        units = max(1, a.blood if a.typeid in (1, 2) else 1)
        wid = weapon_id if weapon_id in a.wz else (a.wz[0] if a.wz else 0)
        w = WEAPONS.get(wid)
        if not w:
            return None, "无可用武器"
        wname, ammo_type, wrange = w

        if dist is None:
            dist = G.distance(a.pos, t.pos)
        if dist > wrange:
            return None, "超出射程(%d格>%d格)" % (dist, wrange)

        # 通视与观察
        ok, blk = self.los(a.pos, t.pos)
        if not ok:
            return None, "不通视(%s-%s)" % (G.hexid(a.pos), G.hexid(t.pos))
        if not self.can_observe(obj_id, tar_id):
            return None, "不可观察(%s-%s)" % (G.hexid(a.pos), G.hexid(t.pos))

        # 弹药
        fld = AMMO_FIELD.get(ammo_type)
        avail = a.ammo.get(fld, 0) if fld else None
        if fld and avail is not None and avail <= 0:
            return None, "%s 弹药不足" % ammo_type

        dh = self.elevation(a.pos) - self.elevation(t.pos)
        terr = self.terrain_kind(t.pos)
        # 叠加状态
        stacked = sum(1 for u in self.units.values()
                      if u.alive() and u.color == t.color and u.pos == t.pos
                      and u.typeid in (1, 2) and u.id != t.id) > 0
        r = crt.direct_fire(
            shooter=dict(typeid=a.typeid, units=units, moving=a.moving(self.second),
                         stunned=a.stunned(self.second)),
            target=dict(typeid=t.typeid, armor=t.armor, hidden=(t.ste == 2),
                        moving=t.moving(self.second), stacked=stacked),
            weapon_name=wname, dist=dist, dh_m=dh, terrain=terr,
        )
        if r["result"] == "NO_WEAPON":
            return None, "；".join(r["detail"])

        if fld:
            a.ammo[fld] = max(0, a.ammo.get(fld, 0) - 1)

        # 应用战果
        msg = []
        kills = r["kills"]
        if kills > 0:
            t.blood -= kills
            if t.blood < 0:
                t.blood = 0
            msg.append("消灭 %d" % kills)
            # 车辆被消灭，车内人员同损（手册 4.6.3）
            if t.typeid == 2:
                for s in self.units.values():
                    if s.alive() and s.id != t.id and s.pos == t.pos and s.typeid == 1 \
                            and s.color == t.color and s.blood > 0 and s.detail.get("carrier") == t.id:
                        s.blood = max(0, s.blood - kills)
        if r["suppressed"]:
            t.keep = 1
            t.stunned_until = self.second + SUPPRESS_SEC
            msg.append("压制")
        if t.typeid == 2 and kills > 0:
            pass  # 表4 有效战果对车辆同时造成压制
        if t.blood <= 0:
            msg.append("已被消灭")
        a.att = 1
        self.fires[a.id] = {"x": 0, "y": 0, "type": 1, "sec": 2}
        self.record("直瞄：%s → %s（%s）%s" % (a.army or a.name, t.army or t.name,
                                              "；".join(r["detail"]), "，".join(msg) or "无效"))
        self.dirty = True
        return r, None

    # ---------------- ObjAjax 快照 ----------------
    def obj_state(self, u):
        """客户端 ObjAjax 所需字段（键名与线上一致）。"""
        now = self.second
        st = {
            "uid": str(u.uid), "color": u.color, "pos": str(u.pos), "pos2": str(u.pos2),
            "rot": str(u.rot), "son": "0", "sonarr": "", "blood": str(u.blood),
            "keep": str(1 if u.stunned(now) else 0), "see": str(u.see),
            "ste": 4 if u.ste == 4 else 0, "pass": str(u.pass_),
            "score": u.score, "runed": 0, "att": u.att, "datetime": "",
            "radar": u.radar or "", "aim": 0,
            "a0": 0, "a2": 0, "c0": u.c0, "c3": u.c3, "d0": 0,
            "f1": 0, "f2": 0, "e2": u.detail.get("e2", 0),
            "f3": 0, "r3": 0, "r4": 0, "ai": u.ai, "user": str(u.uid or ""),
        }
        return st
