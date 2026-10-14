# Hexwar 兵推 AI 策略环境

让 AI **指挥算子、搜索好策略**的离线兵棋推演环境。

面向：AI 智能体 / 强化学习 / LLM 规划器 / 想认真练战术的人。
特点：**Python 核心引擎、可复现、自带示例想定**。核心引擎和表格基线只使用标准库；可选神经网络基线使用 NumPy。

---

## 这个仓库解决什么问题

在线兵棋平台（B/S 架构，Classic ASP 后端）把规则与裁决全部放在服务端，
客户端只是个渲染器。这带来三个麻烦：

1. 想练战术必须连服务器、必须有人在对面、没法批量试错
2. 规则散在客户端脚本与手册 PDF 里，不成体系
3. AI 无法与它对弈——没有可编程接口

本仓库把它变成一个**可编程的推演环境**：

- **裁决引擎**（`engine/`）—— 从规则与裁决表实现机动、通视、观察、堆叠、
  直瞄/间瞄射击、压制、夺控、计分
- **策略环境**（`env/`）—— 标准 `reset / observe / legal_actions / step` 接口，
  观察与动作都是纯 JSON，可直接喂给 LLM
- **操控 skill**（`skill/`）—— 教 AI 怎么读态势、怎么算子、有哪些战术原语
- **离线客户端**（`offline/`）—— 用官方前端 + 本地裁决引擎，可鼠标实操对打

```
┌──────────────┐   observe()   ┌─────────────────┐
│  AI 规划器    │ ◄──────────── │                 │
│  (LLM / RL / │               │   HexwarEnv     │
│   脚本策略)   │ ────────────► │  (env/)         │
└──────────────┘  step(action) └────────┬────────┘
                                        │ 调用
                                        ▼
                              ┌─────────────────┐
                              │  裁决引擎 engine/ │
                              │ 机动/通视/射击/夺控 │
                              └────────┬────────┘
                                       │ 同一套接口
                                       ▼
                              ┌─────────────────┐
                              │ 官方前端 + 桩服务  │  ← 鼠标实操
                              │  offline/        │
                              └─────────────────┘
```

## 快速开始

```bash
# 1) 生成自带示例想定（原创合成数据，非任何真实站点的数据）
py -3.13 tools/make_sample.py

# 2) 跑一局看效果
py -3.13 env/run_episode.py --agent greedy-multi --episodes 3 --render

# 3) 跑 50 局做基线对比
py -3.13 env/run_episode.py --agent random       --episodes 50 --json random.json
py -3.13 env/run_episode.py --agent greedy-multi --episodes 50 --json greedy.json

# 4) 自检裁决引擎
py -3.13 tools/selftest_engine.py

# 5) 按手册逐条验证规则实现（当前 29/29 通过）
py -3.13 tools/verify_rules.py

# 6) 校验裁决表数值与手册一致（当前 26/26 通过）
py -3.13 tools/verify_tables.py
```

最小代码闭环：

```python
from env import HexwarEnv

env = HexwarEnv(side="BLUE", fog=True)
obs = env.reset(seed=1)
while not env.done:
    acts = env.legal_actions()          # 已含通行/射程/通视/堆叠/弹药校验
    obs, reward, done, info = env.step(acts[0])
print(env.score())
```

## 双边自博弈：仅终局给分

新增 `TwoPlayerEpisode` 与 `env.selfplay`，提供双方独立迷雾视角、公开总分观察、合法意图菜单、终局原始分数奖励及检查点续跑。训练算法为表格蒙特卡洛基线，不使用下面的手写 greedy 策略，也不添加动作奖励。

```bash
python -m env.selfplay --snapshot samples/demo --episodes 20 --max-seconds 1800 --max-steps 1000 --checkpoint /tmp/hexwar-20.json --report /tmp/hexwar-20-report.json
```

详细规则、复现与续跑方法见 [双边训练说明](docs/selfplay.md)。下方旧 `HexwarEnv` 接口仍返回分差增量；只需要终局奖励的调用方应使用新接口。

## 共享特征的神经网络基线

`env.neural_train` 使用小型 NumPy 网络与 REINFORCE，从玩家可见的 JSON 观察和候选动作学习共享特征。保留原始终局总分，不添加动作奖励。先对阵固定随机对手，再用保留种子比较训练前后模型。安装、续跑及实验口径见 [神经网络训练说明](docs/neural-learning.md)。

## 环境接口

| 方法 | 作用 |
|---|---|
| `reset(seed)` | 开新局，返回观察 |
| `observe()` | 当前态势（纯 JSON：己方全量、敌方可观察/已知过期、夺控点、计分、剩余时间） |
| `legal_actions(unit_id=None, move_radius=6)` | 枚举合法动作 |
| `step(action)` | 执行动作（单个或数组=同时下令），推进时钟，返回 `(obs, reward, done, info)` |
| `render(width, height)` | 文本态势图，调试用 |
| `score()` | `own/enemy/diff`，口径为 `剩余兵力 + 夺控点×10 + 歼敌分值` |

**动作类型**：`move` / `attack`(可 `track` 持续打击) / `area_fire`(集火) / `stop_attack` / `grenade` / `capture` / `load` / `unload` / `hide` / `stop` / `wait`
**奖励**：`diff` 的增量，可直接当 RL 的稠密奖励。

字段字典见 [`skill/hexwar-operator/references/action-schema.md`](skill/hexwar-operator/references/action-schema.md)。

## 用真实数据（可选）

自带的是合成想定。若你**用自己的账号**从官方站点获取了真实想定数据快照，
把 `map_hexes.json` / `units.json` / `cities.json` 放到一个目录，然后：

```bash
py -3.13 env/run_episode.py --snapshot D:\你的快照目录 --agent greedy-multi
# 或
$env:HEXWAR_SNAP="D:\你的快照目录"
```

抓取与解析脚本在 `tools/`（凭据走环境变量 `HEXWAR_USER` / `HEXWAR_PASS`）。

> ⚠️ 真实数据、官方前端资源与比赛手册**均不随本仓库分发**（见 `.gitignore` 与 `NOTICE`）。
> 请只使用本人的账号与正常登录操作。

## 备赛要点：两台服务器

官方 `readme.txt` 公告了**两台**服务器：

| 名称 | 地址 | 模式 |
|---|---|---|
| 练习服务器 1 | `http://www.hexwar.cn/WARGAMEAI` | 练习模式 |
| 练习服务器 2 | `http://43.143.209.228/WARGAMEAI` | **比赛模式** |

实测两台客户端**是同一份**（`main.html` 均为 7,759 字节 / GBK / 同标题）。
`tools/compare_servers.py` 逐字节比对 17 项公开资源：**16 项 sha1 完全相同**，
唯一不同的是 `GetServerTime.asp`（本就只是当前时间）。
所以本仓库的离线客户端对两台都适用。但**比赛模式**有额外限制：
禁用 Ctrl 批量机动、仅无人装备可使用 AI。

⇒ **每次备赛前先拉一次 `readme.txt`**（两台同步），与本仓库 `engine/` 里的常量
逐条对照。详见 [`docs/站点探测.md`](docs/站点探测.md)。

> ⚠️ 比赛服是真实比赛环境。本仓库**不**对其做任何写入（不建房、不下令、不登录）。

## Skill

本仓库附带两个可安装到 AI 助手的 skill（`skill/` 目录）：

| skill | 用途 |
|---|---|
| **`hexwar-operator`** | **操控算子**：读态势、下命令、枚举合法动作、战术原语、策略搜索工作流 |
| `web-wargame-offline` | 逆向方法论：如何把这类 B/S 兵棋平台复现成离线环境（本仓库的"施工记录"） |

安装：把 `skill/<名称>/` 整个目录复制到 `~/.agents/skills/` 下即可。

## 目录结构

| 路径 | 内容 |
|---|---|
| `engine/` | 裁决引擎：几何、装备库、裁决表、对局状态机 |
| `env/` | 策略搜索环境、参考智能体、跑分台 |
| `offline/` | 官方前端离线运行所需的桩服务器（需自备前端资源） |
| `tools/` | 采集、解析、构建、自检脚本（含站点探测 `probe_site.py`、端点勘察 `probe_endpoints.py`、双服比对 `compare_servers.py`、指令词汇 `extract_commands.py`、规则验证 `verify_rules.py`、裁决表校验 `verify_tables.py`） |
| `samples/demo/` | 自带合成想定（原创数据） |
| `skill/` | AI 助手用的 skill 包 |
| `docs/` | 接口对照表、裁决引擎说明、离线客户端说明、[站点探测记录](docs/站点探测.md)、[规则符合性对照](docs/规则符合性.md) |

## 已验证 / 未验证

**已验证**

- 几何往返一致、邻接距离为 1、通视与机动耗时符合规则
- 直瞄裁决链路端到端跑通（攻击等级 → 修正 → 战果 → 状态变化）
- 离线客户端可被鼠标实操，指令经引擎裁决并回写态势
- 装备映射（武器 ID ↔ 名称/射程/弹药类型/装甲）与官方接口交叉校验一致

**未验证 / 已知不足**

- 与官方裁决**只有概率分布一致**，随机源不同，单次结果不会相同
- 战果表（对车辆）在手册 PDF 中存在网格歧义，列对齐按单调性择优重建，
  见 `engine/tables.json` 的 `note`
- 未实现：AI 对局调度、间瞄/面杀伤全流程、装载卸载时序、同格交战自动触发
- `samples/demo` 是合成数据，**不代表任何真实想定**

## 免责声明

- 本项目为**个人学习与赛前自主训练**用途的技术研究。
- 只应使用**使用者本人的账号**，且只进行正常登录与观察，不绕过任何安全机制。
- 复刻引擎**不声称**能复现官方比赛裁决结果，**不得**用于作弊、代打或冒名参赛。
- 第三方资源（客户端脚本、美术、手册）版权归原厂商，本仓库不包含、不授权。
  详见 [`NOTICE`](NOTICE)。

## 许可

原创代码与文档采用 MIT（见 [`LICENSE`](LICENSE)）。
