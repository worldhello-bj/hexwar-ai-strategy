# -*- coding: utf-8 -*-
"""7527 计分口径（**唯一的定义处**）。

## 已确证 / 未确证

**只有一项是已反推、并用平台实测数据对账过的**（证据 `docs/计分对账.md`，
复现 `tools/hex_score_audit.py`）：

    剩余兵力分 = Σ_上阵(score × blood) + Σ_车内载员(score × 编制兵力)

对 7527 开局同时精确命中平台计分页的两个数（**红 354 / 蓝 234**，误差 0）。

其余两项官方未给、实测也无法反推（全部采集里恒为 0）：

- **歼灭分**：按歼灭掉的兵力计（`score × (编制 − 现存)`）。⚠️ **这是假设** ——
  官方是「整单位被歼」还是「按损失兵力」、载员是否与载具重复计算，都没有依据。
- **夺控分**：`CAPTURE_POINT_SCORE_PLACEHOLDER`，**毫无依据**（手册没写、实测恒为 0）。

所以每个阵营同时给出三个数，调用方必须自己选：

| 键 | 含义 | 用途 |
|---|---|---|
| `total` | 三个分项**全算**（平台式，含未确证项） | 只用于对账 / 展示 |
| `verified` | **只算已确证分项**（当前 = `remaining`） | **默认奖励口径**：未确证分值不进训练 |
| `unverified` | 本次实际涉及的未确证项清单（含"编制取自载入时 blood"这类前提） | 显式告警 |

## 载员归属：必须用稳定 ID，不能用格号现场匹配

快照里的载员记录只有 `pos2`（当时的载具格），而 `pos2` 是"目标格/旧格"：
**载具一机动就不再指向它**。若现场按格匹配，载具离开原格后载员分值会凭空消失，
等价于"惩罚机动"。所以归属由 `Game.link_carried()` 在载入时固化到
`carried.detail["carrier"]`（载具 ID），装卸动作写的是同一字段。

无法唯一确定归属的载员**不静默处理**：记入 `issues`
（`carried_unlinked` / `carried_ambiguous`），并进入 `unverified` 清单。
未知型号的载员编制（不在 `CARRIED_ESTABLISHMENT` 里）同样返回 **None 而不是 0**。
"""
from . import equip

# 口径版本。任何改变分值语义的改动都必须 +1：检查点/续跑靠它绑定，
# 以免旧模型与新公式混用（同一快照下两套奖励会污染训练）。
SCORING_VERSION = 2

# ---------------- 载员编制兵力 ----------------
# 表本身在**装备层**（`engine/equip.py`）：引擎自己（下车、发射巡飞弹）也要用它，
# 这里只是 re-export，保持 `scoring.carried_establishment` 这个稳定入口。
CARRIED_ESTABLISHMENT = equip.CARRIED_ESTABLISHMENT
carried_establishment = equip.carried_establishment

# ---------------- 未确证的占位 ----------------
CAPTURE_POINT_SCORE_PLACEHOLDER = 10
PENDING_RULES = ("captured_per_point", "killed_formula")
# 已确证分项（只有这些进 `verified`）。`remaining` 已由平台两个数同时验证；
# `captured` / `killed` 都不是。
VERIFIED_COMPONENTS = ("remaining",)
SIDES = ("BLUE", "RED")


def breakdown(game):
    """把棋子拆成「上阵单位」与「车内载员+其载具」，并回报无法归类的问题。

    返回 `(parts, issues)`：

    - `parts[side] = {"deployed": [...], "carried": [(载员, 载具), ...]}`
    - `issues = {"carried_unlinked": [id...], "carried_ambiguous": [(id, [载具id...])],
      "carried_establishment_unknown": [(id, data)...]}`

    归属优先用 `detail["carrier"]`（载入时由 `Game.link_carried` 固化，
    装卸动作写同一字段，**载具移动后依然有效**）；只有缺少该字段的老数据才回退到
    "该格唯一载具"，并且回退事实仍会被记进 `issues`。
    """
    parts = {s: {"deployed": [], "carried": []} for s in SIDES}
    issues = {"carried_unlinked": [], "carried_ambiguous": [],
              "carried_establishment_unknown": []}
    for u in game.units.values():
        if u.color in SIDES:
            parts[u.color]["deployed"].append(u)
    for u in sorted(game.units.values(), key=lambda x: str(x.id)):
        if u.color or not u.pos2 and not u.detail.get("carrier"):
            continue
        host = None
        carrier_id = u.detail.get("carrier")
        if carrier_id:
            candidate = game.units.get(carrier_id)
            if candidate is not None and candidate.color in SIDES:
                host = candidate
            else:
                issues["carried_unlinked"].append(u.id)      # 关联指向已消失/无阵营的载具
        if host is None:
            # 回退：老数据没有稳定关联，只在该格能唯一确定归属时使用。
            group = [m for m in game.units.values()
                     if m.color in SIDES and m.pos and m.pos == u.pos2]
            vehicles = [m for m in group if m.typeid in (2, 3)]
            pool = vehicles or group
            if len(pool) != 1:
                if pool:
                    issues["carried_ambiguous"].append((u.id, sorted(str(m.id) for m in pool)))
                elif u.id not in issues["carried_unlinked"]:
                    issues["carried_unlinked"].append(u.id)
                if not pool:
                    continue
            host = sorted(pool, key=lambda x: str(x.id))[0]
        if carried_establishment(u.data) is None:
            issues["carried_establishment_unknown"].append((u.id, u.data))
        parts[host.color]["carried"].append((u, host))
    return parts, issues


def _from_parts(parts, issues, side, cities=()):
    mine = parts[side]
    other = parts["RED" if side == "BLUE" else "BLUE"]

    # ---- 剩余兵力分（★ 已反推并精确验证）----
    remaining = sum(u.score * u.blood for u in mine["deployed"])
    for carried, host in mine["carried"]:
        establishment = carried_establishment(carried.data)
        if establishment is None or not host.alive():
            continue                       # 未知型号 / 载具已毁：不计入，并在下面报出
        remaining += carried.score * establishment

    # ---- 歼灭分（⚠️ 假设：按歼灭的兵力计；载具被歼时其载员一并计入）----
    killed = sum(u.score * max(0, u.establishment - u.blood)
                 for u in other["deployed"])
    for carried, host in other["carried"]:
        establishment = carried_establishment(carried.data)
        if establishment is not None and not host.alive():
            killed += carried.score * establishment

    # ---- 夺控分（⚠️ 占位，无依据）----
    captured = CAPTURE_POINT_SCORE_PLACEHOLDER * sum(
        1 for city in cities if city.get("flag") == side)

    unverified = list(PENDING_RULES) + ["establishment_from_load_blood"]
    own_ids = {u.id for u in mine["deployed"]} | {c.id for c, _h in mine["carried"]}
    if any(cid in own_ids for cid, _d in issues["carried_establishment_unknown"]):
        unverified.append("carried_establishment_unknown")
    if any(cid in own_ids for cid in issues["carried_unlinked"]):
        unverified.append("carried_unlinked")
    if any(cid in own_ids for cid, _h in issues["carried_ambiguous"]):
        unverified.append("carried_ambiguous")
    if any(u.detail.get("establishment_unverified") for u in mine["deployed"]):
        unverified.append("establishment_unverified")
    if any(u.detail.get("carrier") for u in mine["deployed"]):
        # 引擎的 `load` 不把载员的 blood 置 0（仍按上阵单位的 score×blood 计），
        # 而平台的车内记录 blood=0、按编制计入。两者在中途装载时可能不一致，
        # 所以显式报出，而不是静默按其中一套算。
        unverified.append("aboard_counted_as_deployed")
    return {"remaining": remaining, "captured": captured, "killed": killed,
            "total": remaining + captured + killed, "verified": remaining,
            "unverified": unverified}


def _global_unverified(issues):
    """无法归属到某一方的未确证项（例如"载员根本没关联上"）—— 两边都要报出。"""
    out = []
    if issues["carried_unlinked"]:
        out.append("carried_unlinked")
    if issues["carried_ambiguous"]:
        out.append("carried_ambiguous")
    if issues["carried_establishment_unknown"]:
        out.append("carried_establishment_unknown")
    return out


def side_score(game, side):
    """一方三个分项 + `total`/`verified`/`unverified`。"""
    parts, issues = breakdown(game)
    return _from_parts(parts, issues, side, getattr(game, "cities", ()))


def both_scores(game):
    """一次算出两方（避免重复遍历）。返回 `({"BLUE":..,"RED":..}, issues)`。"""
    parts, issues = breakdown(game)
    cities = getattr(game, "cities", ())
    global_reasons = _global_unverified(issues)
    scores = {}
    for side in SIDES:
        party = _from_parts(parts, issues, side, cities)
        party["unverified"] = sorted(set(party["unverified"]) | set(global_reasons))
        scores[side] = party
    return scores, issues


def reward_value(party, mode="verified"):
    """按奖励口径取总分：`verified`（默认，只用已确证分项）或 `platform`（含未确证项）。"""
    if mode == "verified":
        return party["verified"]
    if mode == "platform":
        return party["total"]
    raise ValueError("scoring mode must be 'verified' or 'platform'")
