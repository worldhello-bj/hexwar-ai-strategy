# 完整公开地图与结构化坐标

旧观察接口只包含单位、目标点、比分和时间，没有完整地图。合法动作能透露一部分局部道路与耗时，但不能代替整张棋盘。

`PublicObservationAdapter` 是独立的、可选的第2版观察接口。它补充模拟场景的完整公开静态地图，同时保持原来的战争迷雾、合法动作和奖励规则。

## 提供什么

- 每个静态格子的字符串ID、数值行列坐标、高程、地形类别码、静态通行类别码及地图范围。
- 本方、当前可见对手、最后目击对手和目标点，按稳定ID组织为字典。
- 单位和目标点的结构化坐标；类别与标识符使用字符串，避免把它们误当成连续数值。
- 每个候选动作的原始JSON，以及独立的公开空间上下文。路径仍按实际顺序排列。

完整静态地图是这个离线模拟的公开规则。输出只包含白名单字段，不复制原始快照、后台单位、隐藏敌方位置、弹药或目标信息。通行类别码不表示任何单位此刻必然能够进入；真正的动作规则仍由环境裁决。

## 使用

```python
from env.episode_api import TwoPlayerEpisode
from env.public_observation import PublicObservationAdapter

episode = TwoPlayerEpisode("samples/demo", max_seconds=1800, max_steps=1000)
view = PublicObservationAdapter(episode)
status = view.reset(seed=7)
side = view.current_actor
observation = view.observe(side)
candidates = view.candidate_views(side)

# 策略读取 observation 与候选项的 public_context。
# 提交的是原始 action，不提交上下文，也不改写动作。
status = view.step(candidates[0]["action"], side=side)
```

`schema_version` 为2。返回的数据可以安全修改而不会改变游戏状态。实体排序变化不会改写它们的身份，路径顺序仍有意义。

## 与已有模型的关系

已有表格和神经网络检查点保持原观察格式，尚未使用这个新适配器。本次没有用新地图输入重新训练，也没有声称补齐地图就提高了胜率。下一版策略需要分别编码静态地图、动态实体和候选动作，避免把320格地图简单拼入同一个哈希向量而稀释动态信息。

## 已覆盖的回归

全图白名单覆盖、奇偶行坐标与邻接、返回值隔离、远端公开地形变化、固定公开比分下的隐藏状态不干扰、最后目击信息保持陈旧、实体顺序不变性、路径顺序敏感性、原始动作身份和可执行性，以及零中间奖励和原始终局计分。
