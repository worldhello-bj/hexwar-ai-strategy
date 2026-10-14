# -*- coding: utf-8 -*-
"""战斗裁决表（CRT）实现。

数据来源：比赛手册第 5 章「裁决表」（第 27-31 页），
按页渲染核对后编码；表4/表5 存在网格歧义，见 tables.json 的 note。
"""
import json
import os
import random

try:
    from .equip import ANTI_AIR_CLASS, CRT_AIR_NAME
except ImportError:  # 允许直接以脚本方式运行
    from equip import ANTI_AIR_CLASS, CRT_AIR_NAME

_HERE = os.path.dirname(os.path.abspath(__file__))
T = json.load(open(os.path.join(_HERE, "tables.json"), encoding="utf-8"))

PUSH = "P"          # 压制
INVALID = ""        # 无效


def d6():
    return random.randint(1, 6)


def roll2d6():
    return d6() + d6()


# ---------------- 攻击等级 ----------------

def atk_level_person(weapon_name, units, dist):
    """表1：直瞄武器对人员单位攻击等级。units = 车/班数(1-4)，dist = 距离格。
    超出表列范围（即超出该武器对人员的有效射程）返回 None。"""
    row = T["atk_person"].get(weapon_name)
    if not row:
        return None
    arr = row.get(str(min(max(int(units), 1), 4)))
    if not arr or dist >= len(arr):
        return None
    return arr[dist]


def atk_level_vehicle(weapon_name, dist):
    """表2：直瞄武器对车辆单位攻击等级；超出射程返回 None。"""
    arr = T["atk_vehicle"].get(weapon_name)
    if not arr or dist >= len(arr):
        return None
    return arr[dist]


def atk_level_elev_fix(dh, dist):
    """表3：高度差对攻击等级的修正（dh 为米，dist 为格）。"""
    bands = sorted(int(k) for k in T["atk_elev_fix"].keys())
    band = None
    for b in bands:
        if dh >= b:
            band = b
    if band is None:
        return 0
    row = T["atk_elev_fix"][str(band)]
    if dist < 1:
        dist = 1
    return row.get(str(dist), 0)


def atk_level_air(weapon_name, dist):
    """表9：反无人机武器攻击等级。"""
    arr = T["atk_air"].get(weapon_name)
    if not arr:
        return None
    if dist >= len(arr):
        return None
    return arr[dist]


# ---------------- 状态/地形修正（作用于随机数） ----------------

def situational_mod(shooter_stunned=False, shooter_moving=False,
                    terrain=None, target_hidden=False, target_moving=False,
                    target_stacked=False):
    """手册 4.6.2 / 表5 / 表7 共同的射击/目标状态修正。"""
    m = T["state_mods"]
    v = 0
    if shooter_stunned:
        v += m["shooter_stunned"]
    if shooter_moving:
        v += m["shooter_moving"]
    if terrain == "居民地":
        v += m["terrain_town"]
    elif terrain == "丛林地":
        v += m["terrain_jungle"]
    elif terrain in ("工事", "掩体", "建筑物"):
        v += m["terrain_fort"]
    if target_hidden:
        v += m["target_hidden"]
    if target_moving:
        v += m["target_moving"]
    if target_stacked:
        v += m["target_stacked"]
    return v


def fix_person_result(corrected_roll):
    """表7：人员伤亡结果修正。"""
    for lo, hi, v in T["person_result_fix"]:
        if lo <= corrected_roll <= hi:
            return v
    return 0


# ---------------- 战斗结果 ----------------

def result_person(attack_level, roll):
    """表6：直瞄武器对人员单位结果。返回 'P'(压制) / 0 / 1 / 2。"""
    a = min(max(int(attack_level), 1), 10)
    row = T["person_result"].get(str(min(max(int(roll), 2), 12)))
    if not row:
        return INVALID
    v = row[a - 1]
    return v


def result_grenade(roll):
    """表8：手雷结果。返回 0 或 1。"""
    return T["grenade_result"].get(str(min(max(int(roll), 2), 12)), 0)


def armor_mod(corrected_roll, armor):
    """表5：按防护力对（车辆）战损随机数再做修正。"""
    tbl = T["table5"]["by_armor"].get(armor)
    if not tbl:
        return 0
    key = str(min(max(int(corrected_roll), -3), 11))
    return tbl.get(key, 0)


def result_vehicle(attack_level, units, corrected_roll):
    """表4：直瞄武器对车辆单位战斗结果 → 消灭车数（0-4）。"""
    n = min(max(int(units), 1), 4)
    cols = T["table4_columns"].get(str(n))
    if not cols:
        return 0
    a = min(max(int(attack_level), 1), 10)
    col = cols.get(str(a))
    if not col:
        return 0
    row = T["table4"].get(str(min(max(int(corrected_roll), 2), 12)))
    if not row:
        return 0
    if col - 1 >= len(row):
        return 0
    return row[col - 1]


def result_air(attack_level, roll):
    """表10：反无人机战斗结果。返回 1=歼灭，0=无效。"""
    a = min(max(int(attack_level), 1), 11)
    row = T["air_result"].get(str(min(max(int(roll), 2), 12)))
    if not row:
        return 0
    return row[a - 1] if a - 1 < len(row) else 0


# ---------------- 高层裁决入口 ----------------

def direct_fire(shooter, target, weapon_name, dist, dh_m=0, roll=None,
                terrain=None, log=None):
    """一次直瞄射击裁决。

    返回 dict(result=..., kills=..., suppressed=..., roll=..., level=..., detail=...)
    shooter/target 需要有 typeid / armor / units / moving / stunned / hidden / stacked
    """
    detail = []
    is_air_target = target.get("typeid") == 3
    is_person_target = target.get("typeid") in (1, 4) and target.get("typeid") != 3

    # 1) 攻击等级
    if is_air_target:
        # 手册 4.10：巡飞弹速度极快，不可被任何武器打击
        if target.get("name") == "巡飞弹":
            return dict(result="IMMUNE", kills=0, suppressed=False,
                        detail=["巡飞弹不可被任何武器打击"])
        air_name = CRT_AIR_NAME.get(weapon_name, weapon_name)
        lvl = atk_level_air(air_name, dist)
        if lvl is None:
            return dict(result="NO_WEAPON", kills=0, suppressed=False,
                        detail=["该武器不能打击空中单位"])
        table_used = "表9+表10"
    elif target.get("typeid") == 2:
        lvl = atk_level_vehicle(weapon_name, dist)
        if weapon_name == "步兵轻武器":
            lvl = atk_level_person("步兵轻武器", shooter.get("units", 1), dist)
        if lvl is None:
            return dict(result="NO_WEAPON", kills=0, suppressed=False,
                        detail=["该武器不能打击车辆"])
        table_used = "表2+表4"
    else:
        lvl = atk_level_person(weapon_name, shooter.get("units", 1), dist)
        if lvl is None:
            return dict(result="NO_WEAPON", kills=0, suppressed=False,
                        detail=["超出该武器对人员的有效射程或不能打击人员"])
        table_used = "表1+表6"

    if lvl is not None and lvl <= 0 and not is_air_target:
        return dict(result=INVALID, kills=0, suppressed=False, roll=roll,
                    level=0, detail=["攻击等级为 0，无法造成战果"], table=table_used)

    detail.append("攻击等级(表)=%s" % lvl)

    # 2) 高度差修正
    if not is_air_target:
        fix = atk_level_elev_fix(abs(dh_m), dist)
        if fix:
            lvl = max(0, lvl + fix)
            detail.append("高度差修正 %+d → %d" % (fix, lvl))

    # 3) 掷骰 + 状态修正
    if roll is None:
        roll = roll2d6()
    smod = situational_mod(
        shooter_stunned=shooter.get("stunned", False),
        shooter_moving=shooter.get("moving", False),
        terrain=terrain,
        target_hidden=target.get("hidden", False),
        target_moving=target.get("moving", False),
        target_stacked=target.get("stacked", False),
    )
    corrected = roll + smod
    detail.append("随机数 %d，状态修正 %+d → %d" % (roll, smod, corrected))

    # 4) 装甲修正（表5，仅对车辆战损）
    corrected_raw = corrected        # 手册 4.6.2(5) 需保留"修正前"的战果
    if target.get("typeid") == 2 and not is_air_target:
        am = armor_mod(corrected, target.get("armor", "无装甲"))
        if am:
            corrected += am
            detail.append("防护力(%s)修正 %+d → %d" % (target.get("armor"), am, corrected))

    # 5) 查结果
    if is_air_target:
        if lvl is None or lvl <= 0:
            return dict(result=INVALID, kills=0, suppressed=False, roll=roll,
                        level=lvl, detail=detail + ["攻击等级为 0，无法造成战果"],
                        table=table_used)
        r = result_air(lvl, corrected)
        return dict(result=("歼灭" if r else INVALID), kills=1 if r else 0,
                    suppressed=False, roll=roll, level=lvl,
                    detail=detail, table=table_used)

    if target.get("typeid") == 2 or weapon_name == "步兵轻武器":
        kills_raw = max(0, result_vehicle(lvl, shooter.get("units", 1), corrected_raw))
        kills = max(0, result_vehicle(lvl, shooter.get("units", 1), corrected))
        # 手册 4.6.2(4)(5)：对车辆只要产生过有效战果（含被防护力修正为 0），
        # 就同时造成压制；这是车辆与人员不同的地方。
        suppressed = kills_raw > 0 or kills > 0
        if kills_raw > 0 and kills == 0:
            detail.append("战果被防护力修正为 0 → 仅压制（手册 4.6.2(5)）")
        detail.append("表4 → 消灭 %d 车" % kills)
        return dict(result=(kills or INVALID), kills=kills, suppressed=suppressed,
                    kills_raw=kills_raw, roll=roll, level=lvl, detail=detail,
                    table=table_used)

    # 人员：表6 + 表7
    rf = fix_person_result(corrected)
    if rf:
        corrected += rf
        detail.append("表7 结果修正 %+d → %d" % (rf, corrected))
    v = result_person(lvl, corrected)
    if v == PUSH:
        detail.append("表6 → 压制")
        return dict(result=PUSH, kills=0, suppressed=True, roll=roll, level=lvl,
                    detail=detail, table=table_used)
    kills = int(v) if v else 0
    detail.append("表6 → 消灭 %d 班" % kills)
    # 手册 4.6.1：人员战果为"消灭 n 个班 / 无效 / 压制"三者之一，消灭与压制**互斥**。
    # （车辆才规定"产生有效战果同时造成压制"，见 4.6.2(4)。）
    return dict(result=(kills or INVALID), kills=kills,
                suppressed=False, roll=roll, level=lvl,
                detail=detail, table=table_used)
