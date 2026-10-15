# -*- coding: utf-8 -*-
"""7527 计分口径。

**只有一项已反推并精确验证**（证据见 `docs/计分对账.md`，复现 `tools/hex_score_audit.py`）：

    剩余兵力分 = Σ_上阵(score × blood) + Σ_车内载员(score × 编制兵力)

对 7527 开局**同时精确命中**平台计分页的两个数（红 354 / 蓝 234，误差 0）。

其余两项官方未给、实测也**无法反推**（全部采集里恒为 0），因此这里是显式占位或假设：

- **歼灭分**：按"歼灭掉的兵力 × 分值"（与剩余兵力分互补）。⚠️ **这是假设**——
  官方页面只写"歼灭对手兵力得分"，究竟是**整单位被歼**才计分还是**按损失兵力**计分、
  载员被歼是否与载具重复计算，都还没有依据。
- **夺控分**：占位 `CAPTURE_POINT_SCORE_PLACEHOLDER`，**毫无依据**
  （手册没写；实测里夺控分恒为 0，从未观察到非零值）。

未确证的项都列在 `PENDING_RULES`，并随 `env.score()` 一起下发，
以免下游（含 `skill/hexwar-operator`）把它当权威值。

⇒ 待确认清单：**`docs/计分规则待确认.md`**（可直接转发主办方）。
"""

# ---------------- 载员编制兵力 ----------------
# 想定里 15 条载员条目 `blood=0`（人在车内），编制兵力不可读。
# 下面的值来自证据：**下车会在服务端新建实体，其 `blood` 就是编制兵力**
# （见 `docs/运输机制实测.md`）。
CARRIED_ESTABLISHMENT = {
    382: 3,   # 步兵班（蓝方装甲车载）      —— 观测：blue_armored_unload_01
    392: 4,   # 步兵班（红方火力支援车载）  —— 观测：red_support_unload_01
    397: 4,   # 无人察打车                  —— 观测：red_support_unload_02_off2
    394: 1,   # 旋翼无人机                  —— **反解**：由平台分项 354 反推，未直接观测
    389: 0,   # 巡飞弹（score=0，恒不影响分值）
}

# ---------------- 未确证的占位 ----------------
CAPTURE_POINT_SCORE_PLACEHOLDER = 10
PENDING_RULES = ("captured_per_point", "killed_formula")


def carried_establishment(data):
    """该装备的载员编制兵力；未知返回 0（未知项应由调用方显式报出）。"""
    return CARRIED_ESTABLISHMENT.get(int(data or 0), 0)


def breakdown(game):
    """按阵营拆出「上阵单位」与「车内载员+其载具」。

    载员在记录里没有阵营（`color` 为空、`pos=0`、`blood=0`），
    只有 `pos2` 指向载具所在格。想定 7527 里每辆载具各占一格，故 `pos2` 可唯一归属；
    若该格被堆叠（例如载具上还站着步兵），优先取**载具/飞行器**（`typeid` 2/3）
    当载具，避免把载员误挂到步兵上而被算成另一方的分。
    """
    sides = ("BLUE", "RED")
    out = {s: {"deployed": [], "carried": []} for s in sides}
    for u in game.units.values():
        if u.color in sides:
            out[u.color]["deployed"].append(u)
    for u in game.units.values():
        if u.color or not u.pos2:
            continue
        same_hex = [m for m in game.units.values()
                    if m.color in sides and m.pos and m.pos == u.pos2]
        carriers = [m for m in same_hex if m.typeid in (2, 3)]
        host = carriers[0] if carriers else (same_hex[0] if same_hex else None)
        if host is not None:
            out[host.color]["carried"].append((u, host))
    return out


def both_scores(game):
    """一次算出两方分项（避免重复遍历；`env.score()` 用这个）。"""
    parts = breakdown(game)
    return {side: _from_parts(game, side, parts) for side in ("BLUE", "RED")}


def side_score(game, side):
    """一方三个分项与总计。口径见模块 docstring（只有 `remaining` 是已验证的）。"""
    return _from_parts(game, side, breakdown(game))


def _from_parts(game, side, parts):
    mine = parts[side]
    other = "RED" if side == "BLUE" else "BLUE"

    # 剩余兵力分（★ 已反推并精确验证）
    remaining = sum(u.score * u.blood for u in mine["deployed"])
    remaining += sum(u.score * carried_establishment(u.data)
                     for u, host in mine["carried"] if host.alive())

    # 歼灭分（⚠️ 假设：按歼灭的兵力计；载具被歼时其载员一并计入）
    killed = sum(u.score * max(0, u.establishment - u.blood)
                 for u in parts[other]["deployed"])
    killed += sum(u.score * carried_establishment(u.data)
                  for u, host in parts[other]["carried"] if not host.alive())

    # 夺控分（⚠️ 占位，无依据）
    captured = CAPTURE_POINT_SCORE_PLACEHOLDER * sum(
        1 for city in game.cities if city.get("flag") == side)

    return {"remaining": remaining, "captured": captured, "killed": killed,
            "total": remaining + captured + killed}
