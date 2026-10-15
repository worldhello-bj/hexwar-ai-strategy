# 动作与观察字段字典

## 动作 schema

所有动作都是 JSON 对象。`env.step()` 接受**单个动作**或**动作数组**（数组=同时下令）。

### move — 机动

```json
{"type": "move", "unit": "Obj_9101", "path": [140012, 140014, 140016]}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `unit` | str | 算子 ID |
| `path` | int[] | 目标格序列。**含起点时起点不产生耗时**；含起点或不含都可以 |

- 返回 `info.seconds` = 本次机动总耗时（秒），时钟按此推进。
- 中途任一格不满足通行条件 → **整条动作被拒**，`info.msg` 给出原因，时间不推进。
- 到达后会自动尝试夺控判定。

### attack — 直瞄射击

```json
{"type": "attack", "unit": "Obj_9101", "target": "Obj_9001", "weapon": 36}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `weapon` | int | 武器 data ID。省略或填不在装备表里的 ID 时用**默认武器**（第一件） |

失败原因（`info.msg`）：射程外、不通视、不可观察、无弹药、射击方被压制、目标已消灭。

### capture — 夺控

```json
{"type": "capture", "unit": "Obj_9104"}
```

仅在算子**站在夺控点上**且该格与相邻 6 格**无敌方地面单位**时成功。

### hide — 隐蔽切换

```json
{"type": "hide", "unit": "Obj_9101", "on": 1}
```

`on=1` 进入隐蔽（被观察距离减半），`on=0` 解除。

### stop — 停止机动

```json
{"type": "stop", "unit": "Obj_9101"}
```

清空 `pos2`（正在前往的目标格）。

### wait — 等待

```json
{"type": "wait", "seconds": 30}
```

主动推进时钟，用于"等压制解除""等敌方进入射程"。

## 观察 schema

```json
{
  "time": 120,
  "time_left": 1680,
  "side": "BLUE",
  "score": {
    "own":   {"remaining": 40, "captured": 10, "killed": 10, "total": 60},
    "enemy": {"remaining": 20, "captured": 0,  "killed": 0,  "total": 20},
    "diff": 40
  },
  "objectives": [{"id": "C_9001", "name": "主要", "pos": 24010, "hexid": "2410", "held_by": "GREEN"}],
  "own": [{
    "id": "Obj_9101", "army": "蓝1排", "name": "坦克", "typeid": 2,
    "pos": 28006, "hexid": "2806", "blood": 3, "suppressed": 0,
    "color": "BLUE", "score": 10, "armor": "复合装甲",
    "hidden": 0, "ste": 0,
    "weapons": [{"id": 43, "name": "车载机枪", "ammo_type": "普通弹药", "range": 10, "ammo": -1}],
    "can_observe_range": {"person": 10, "vehicle": 25, "air": 1}
  }],
  "enemy_visible": [{"id": "Obj_9001", "...": "同上，字段完整"}],
  "enemy_known":   [{"id": "Obj_9002", "pos": 20010, "hexid": "2010", "blood": 3, "last_seen": 60, "stale": true}],
  "done": false
}
```

### 字段逐个说

| 字段 | 含义 | 注意 |
|---|---|---|
| `typeid` | `1` 步兵 / `2` 地面车辆 / `3` 飞行器 / `4` 工事 | 决定用哪张裁决表、能否夺控、能否被对空武器打 |
| `blood` | 剩余兵力（班数/车数） | 归零即消灭 |
| `suppressed` | `1` = 被压制 | 被压制时**不能机动、不能射击** |
| `ste` | 机动方式标记，`2` 表示隐蔽 | 与 `hidden` 同义 |
| `armor` | 装甲防护等级 | 影响车辆战损修正：复合 > 重型 > 中型 > 轻型 > 无 |
| `weapons[].ammo` | 弹药数，`-1` 表示不限 | 有限弹药的武器要省着用 |
| `weapons[].range` | 射程（格） | 不同武器射程差别很大，别用短射程武器硬够远目标 |
| `can_observe_range` | 对人员/车辆/空中的侦察距离（格） | **看得见才打得着**；这个值常大于武器射程 |
| `enemy_known[].stale` | 位置已过期 | 不可据此射击 |

### 计分口径（⚠️ 三项中只有一项已确证，其余分别是**假设**与**占位**）

`total = remaining + captured + killed`；`env.score()` 还会下发 `pending_rules`（未确证项清单）。

- `remaining`：剩余兵力分。✅ **已反推、已实现、已对账**——
  **`Σ上阵(score×blood) + Σ车内载员(score×编制)`**，对 7527 开局精确命中平台计分页的
  **红 354 / 蓝 234**（`tools/hex_score_audit.py` 会断言这一点，不一致即失败）。
  载员编制表在 `engine/scoring.py::CARRIED_ESTABLISHMENT`（3 项有下车实测，旋翼无人机=1 是反解）。
- `captured`：夺控分。**每点分值无任何依据**（手册未给、实测里恒为 0 ⇒ 无法反推）；
  代码里 `CAPTURE_POINT_SCORE_PLACEHOLDER = 10` 只是**占位**，
  **不得当作规则、不得据此比较胜率或净胜分**。
- `killed`：歼灭分。⚠️ **代码里是假设**：按歼灭的**兵力**计（`score × (编制 − 现存)`，
  载具被歼时其载员一并计入）；官方究竟是"整单位被歼计其分值"还是"按损失兵力"计、载员是否重复计算，均未确证。

`diff = own.total - enemy.total`。`step()` 的 `reward` 是 `diff` 的**增量**。
⚠️ 由于 `captured` / `killed` 未确证，`reward` 的**绝对值仍不可信**（可当方向性信号用，
但不要拿它当官方分）。

> ⇒ 待向主办方确认的清单：`docs/计分规则待确认.md`（可直接转发）；
> 证据与逐项对账：`docs/计分对账.md`（复现 `py -3.13 tools/hex_score_audit.py`）。
