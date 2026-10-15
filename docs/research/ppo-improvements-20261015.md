# PPO 后续改进：证据与受控实验（2026-10-15）

检索日期：2026-10-14 UTC。依据任务提供的现状，未检查代码、未运行新实验。下面的优先级和参数是针对 CPU/NumPy 条件的工程判断，不是论文证明在本游戏必然有效。

## 结论

保留 masked PPO，现有 mask、有限差分梯度、old-prob 和配对评测已完成验证；下一优先级是历史对手池与3个训练种子的复验，之后再考虑额外时序输入、GRU 和结构化编码。暂不整体迁移到 AlphaStar 规模联赛、完整 PSRO 或 NFSP。

当前单训练种子、100 episodes 后，对随机 128 局由 45胜36平47负变为83胜22平23负：胜率由35.16%变为64.84%；按胜1平0.5计的比赛得分率由49.22%变为73.44%。这是该评测的积极信号；不能说明跨训练种子稳定、对更强对手更好、找到均衡。两批已使用相同64个环境种子2700000–2700063，每个种子互换双方座位，共128局，评测协议相同。因此已控制这部分评测差异；尚需增加独立训练种子与非随机对手。

## 推荐顺序与成本

### 0. 扩展现有配对评测（低成本，与对手池并列最高优先级）

- 分离训练、调参验证和最终测试的地图/环境随机种子；每个测试配置换边，固定随机数和动作选择协议。
- 训练种子至少3个作筛选，预算允许再增加；评测对手不只随机，还包括初始化模型、当前冻结模型、独立训练的冻结模型。若已有合法规则基线也纳入。
- 同时记录原始终局 own-score、胜平负、比赛得分率、平均回合数、截断率和运行时间。按训练种子报告结果，不能把大量对局当成大量独立训练重复。
- 各方法比较同样 learner environment steps，同时报告 CPU wall time。episodes 长短可能不同，不能只以同样100局认为预算相同。
- 实验约束为仅使用己方终局原始分数作为奖励，应保留；胜平负只是辅助评测，不能据此擅自改成胜负奖励、分差或塑形。

### 1. PPO 已有验证与后续数值诊断（低至中成本，次优先级）

支持文献：Engstrom 等发现代码层面的实现选择可以显著影响 PPO/TRPO 结果；Andrychowicz 等通过大规模连续控制实验进一步说明训练、网络、归一化等选择的重要性。这支持“先审计再换算法”，不支持直接照搬连续控制的最佳超参数。

已确认的现状（不作为待实施功能）：
- batch=4 是4个已完成 episode，轨迹长度可变，不是4条 transition。
- actor 梯度对每条轨迹求和，再除以轨迹数；critic 按决策数取均值。二者归一化单位不同，后续应记录轨迹长度、actor/critic 梯度量级；轨迹长度变化会影响相对损失尺度，但不能直接认定现有实现错误。
- NumPy 梯度已通过有限差分检查；old probabilities 在更新 epoch 中固定；动作 mask 一致性已有测试。

后续数值诊断为次优先级：记录每次更新总决策数、策略熵、approx-KL、clip fraction、梯度范数和轨迹长度。若要比较 batch=4 与更大的 episode batch，应固定总 learner environment steps 并报告总更新次数；不能把“batch=4”本身当作训练不稳定证据。归一化方式若改变，独立消融，避免与对手池同时变化。是否采用 GAE、终止/截断处理等未在本备忘核查，不能宣称缺失。

### 2. 小型冻结历史对手池（低至中成本，最高优先级策略改进）

PSRO 的直接相关点是：对单一训练对手会过拟合；可以训练对策略混合的近似最佳响应。完整 PSRO 还需要经验收益矩阵、元策略求解和迭代响应，当前阶段过重。

轻量方案：对手每局从“随机＋若干冻结历史快照”抽样，局内保持不变；历史快照均匀抽样是起点。保留少量随机对手，避免基本能力遗忘。池上限可先设4–8；比例、容量、保存间隔都是待测超参，不能冠以 PSRO/Nash 收敛保证。不要双方同时逐步更新同一权重导致对手非平稳且难归因。评测保留不参与训练的冻结对手。

NFSP 适合作为理论路线阅读：它结合最佳响应学习与平均策略的监督学习，在不完全信息扑克中展示了价值。但需要双学习过程和合适的回放/蓄水池采样，实现和调参成本高，当前不优先。

### 3. 历史输入 → recurrent PPO（中到高成本）

fog 下单帧相同可能对应不同历史。Ni 等的原论文支持“认真实现的 recurrent model-free RL 可以是强 POMDP 基线”，但主要不是证明 GRU-PPO 在本任务更好。

当前已经输入 last-seen 信息，因此不能把 last-seen 当作新功能。额外廉价诊断可比较现有输入与最近2–4次本人可见观测、上一动作及合法可得反馈的序列拼接。先与同参数量较宽的单帧 MLP 比较，以免把容量增长误判为记忆收益。任何历史输入都不能调用隐藏真实状态；public score 是允许输入不等于允许把隐藏分数接入。

若确有长时记忆需求，再上小 GRU（如32/64维），以连续序列训练和 truncated BPTT。episode 边界重置隐状态；保存序列初始状态；padding 不计损失；不能把 transition 随机打散当作 recurrent minibatch。NumPy 手写 BPTT 的实现风险和验证成本明显高于前两项。作者维护的 recurrent PPO 实现可以参考序列批处理，但无需立即引入其整套依赖。

### 4. 从哈希编码升级到结构化公开特征（中成本；完整图网络更高）

哈希桶碰撞和缺乏几何关系可能造成信息瓶颈，需通过碰撞统计和消融验证，不能仅凭“哈希”断言已经失效。先增加稳定、可解释的公开数值特征和归一化坐标；考虑共享的小型候选动作打分器：结合状态编码与每个合法动作特征，避免依赖任意 action ID。

规则图/格子信息若很重要，下一步使用可见实体集合聚合或1–2层图消息传递，再对合法动作打分。隐藏实体不应出现在图节点或边中；unknown/不可见与真实空格要区分。Relational Deep RL 的实体关系推理在 Box-World 和 SC2 mini-games 中有实证，是结构化归纳偏置的依据，不是本游戏 GNN 优于 MLP 的证据。

## 第一轮最值得做的受控实验

mask 一致性、有限差分梯度和 old-prob 固定已确认，无须将这些现有功能包装为新进展。下一轮直接优先做历史对手池 A/B，并把独立训练种子增加到3个：

A：现有 masked feedforward PPO，仅随机对手。
B：同一模型、损失、奖励、采样预算，训练对手改为随机＋冻结历史池。

3个配对训练种子起步；所有版本用相同预先固定的验证种子、换边以及冻结对手集。每对手可先128局（64个种子各换边）；不要用该验证集反复挑选后再作为最终测试宣称提升。主指标采用事先指定的原始 own-score；同时报告比赛得分率及最差对手表现。保持终局 own-score 奖励约束；胜率仅为辅助指标。只有跨种子、对冻结强于随机的对手也改善，才称训练方案更好；如果只随机胜率下降但历史对手表现提高，完整呈现权衡。

已确认 batch=4 为完整 episodes，不建议仅因该数值先改变批量。历史对手池与3训练种子复验是当前明确的首选；后续若日志显示尺度或方差问题，再单独测试 episode batch 或归一化。

## 原始论文及其确切支持范围

1. Schulman et al., Proximal Policy Optimization Algorithms (2017)：PPO 的 clipped surrogate、多 epoch minibatch 更新框架。https://arxiv.org/abs/1707.06347
2. Engstrom et al., Implementation Matters in Deep Policy Gradients: A Case Study on PPO and TRPO (ICLR 2020)：实现细节会实质改变结果和算法行为。https://arxiv.org/abs/2005.12729
3. Andrychowicz et al., What Matters In On-Policy Reinforcement Learning? A Large-Scale Empirical Study (2020/ICLR 2021)：大规模评估 on-policy 实现选择；测试任务是连续控制，外推要验证。https://arxiv.org/abs/2006.05990
4. Huang & Ontañón, A Closer Look at Invalid Action Masking in Policy Gradient Algorithms (2020)：masking 的策略梯度依据和大量非法动作下的实证。当前已有 mask，应保留并验证采样/更新一致；不要当作尚未采用的新改进。https://arxiv.org/abs/2006.14171
5. Schulman et al., High-Dimensional Continuous Control Using Generalized Advantage Estimation (2015/ICLR 2016)：GAE 的偏差/方差权衡。https://arxiv.org/abs/1506.02438
6. Lanctot et al., A Unified Game-Theoretic Approach to Multiagent Reinforcement Learning (NeurIPS 2017)：对策略混合学习响应、对手过拟合、PSRO。https://arxiv.org/abs/1711.00832
7. Heinrich & Silver, Deep Reinforcement Learning from Self-Play in Imperfect-Information Games (2016)：NFSP，在不完全信息扑克中的近似均衡学习结果。https://arxiv.org/abs/1603.01121
8. Ni et al., Recurrent Model-Free RL Can Be a Strong Baseline for Many POMDPs (ICML 2022)：在多种 POMDP 中，架构/超参经过仔细选择的 recurrent model-free 基线具有竞争力。https://proceedings.mlr.press/v162/ni22a.html
9. Zambaldi et al., Relational Deep Reinforcement Learning (2018/ICLR 2019)：实体关系/注意力归纳偏置在 Box-World、SC2 mini-games 的表现。https://arxiv.org/abs/1806.01830
10. 作者维护的实现参考（不是新增理论证据）：Recurrent PPO using truncated BPTT。https://github.com/MarcoMeter/recurrent-ppo-truncated-bptt


本文提出待验证的实验，不宣称历史对手池、GRU 或结构化编码已在此游戏取得提升。当前合成地图的后续500局结果见 [实验记录](../experiments/README.md)。
