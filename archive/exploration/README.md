# archive/exploration —— 已封存的探索记录（只读留档）

这里存放**逆向与实测探索**过程的一手材料。2026-10-15 起，主仓库只保留"规则 + 训练 +
验证"的核心，探索物整体搬到这里；**代码不再依赖本文档目录**（唯一例外：规则验证工具会
从 `capture/` 读实测样本，见下）。

## 怎么搬的

* 搬家清单与结果：`_moves.txt`（逐条"来源 → ok/缺"）。
* 判定原则：**规则重建与验证**（`build_crt` / `verify_*` / `derive_table4_columns`）、
  **线上协议客户端与裁决页解析**（`hex_transport_capture` / `hex_combat_round`）、
  **训练与评测**（`evaluate_*` / `export_policy_replay` / `hex_env_diff`）、
  **计分对账**（`hex_score_audit`）留在主仓库 `tools/`；其余一次性探测/抓包/解包/下载脚本
  与过程文档全部封存。
* 路径引用改动记录：`_path_patch.txt`（核心工具里"采集数据路径"改成
  「本地优先、封存区兜底」，并去掉硬编码 `d:\兵推`）。

## 目录

| 目录 | 内容 | 入库 |
|---|---|---|
| `tools/` | 一次性探测/抓包/逆向/解包脚本（`probe_*`、`hex_*` 探针、`extract_*`、`analyze_*`、`download_*`、`fetch_*`、镜像构建…） | ✅ 入库（是代码，也是过程证据） |
| `docs/` | 逆向过程文档：`裁决明细解码.md`、`手册逐页核对.md`、`运输机制实测*.md`、`战斗采集方法.md`、`战斗链路实测.md`、`站点探测.md`、`dot-assist-*.md`、`experiments/`、`replays/`、`research/` | ✅ 入库 |
| `capture/` | 实测采集产物（裁决页、房间页、计分区、探测时间线） | ⛔ 不入库（服务端数据） |
| `analysis/` | 分析中间产物与日志 | ⛔ 不入库 |
| `har/` | `www.hexwar.cn.har`（★ 含会话 Cookie 与认证头） | ⛔ 不入库 |
| `artifacts/` | 早期交付产物 | ⛔ 不入库 |
| `tests/` | 探索期的一次性测试（依赖已封存脚本） | ✅ 入库 |

## ⚠ 安全与版权

* `har/`、`analysis/`、`capture/` 里有**会话 Cookie、账号名、`Set-Cookie` 响应头**。
  公开发布前的扫描见 `tools/scan_secrets_before_publish.py`（报告
  `analysis/publish_scan.md`）；**这几个目录一律不得公开**。
* `docs/` 里的过程文档是自研记录，可公开；但其中引用的官方前端代码/手册内容，
  权利仍属原厂商与原出版方。

## 规则验证仍会用到封存区

`review` 类工具需要**实测样本**来反解/对账表格，所以它们会去
`archive/exploration/capture/7527_transport_capture/` 找数据（找不到就跳过该段）：

```bash
py -3.13 tools/verify_live_crttables.py    # 86 条实测裁决 × 引擎，三链路零残差
py -3.13 tools/derive_table4_columns.py    # 反解表4/表6 列号（PDF 网格不可信）
py -3.13 tools/verify_unfavorable.py       # 31/31（含把上面这两件作为断言）
```

## 如果要恢复成主目录

搬回去就是把 `tools/`、`docs/` 里的文件挪回上层同名目录，并把工具里的
`archive/exploration/capture/...` 兜底路径去掉。**不建议**：探索物会让核心目录难以阅读，
而它的证据价值靠本文档 + git 历史就能保留。
