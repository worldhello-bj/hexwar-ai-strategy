# -*- coding: utf-8 -*-
"""在压缩后的 war.min.js 中提取所有与后端交互的调用点，输出上下文到 UTF-8 文件。"""
import re
import os

SRC = r"d:\兵推\analysis\bodies\www.hexwar.cn_WARGAMEAI7_war.min.js.js"
OUT = r"d:\兵推\analysis\warjs_endpoints.md"

with open(SRC, "r", encoding="utf-8", errors="replace") as f:
    js = f.read()

out = []
def w(s=""):
    out.append(s)

w("# war.min.js 后端交互点分析")
w()
w("文件长度: %d 字符" % len(js))
w()

# 1. 所有出现的 .asp 字符串
w("## 1. 脚本中出现的全部 .asp 引用（按出现次数）")
w()
asp = re.findall(r"[\"'`]?([A-Za-z0-9_/\.\-]*\.asp)", js)
from collections import Counter
cnt = Counter(asp)
w("| 次数 | 路径 |")
w("|---|---|")
for k, v in cnt.most_common():
    w("| %d | `%s` |" % (v, k))
w()

# 2. 每个 .asp 出现的上下文（前后 160 字符）
w("## 2. 各 .asp 引用上下文")
w()
seen_ctx = set()
for m in re.finditer(r"([A-Za-z0-9_/\.\-]*\.asp)", js):
    a, b = max(0, m.start() - 160), min(len(js), m.end() + 160)
    ctx = js[a:b]
    key = ctx[:0]  # keep all
    w("### `%s` @ offset %d" % (m.group(1), m.start()))
    w()
    w("```javascript")
    w(ctx)
    w("```")
    w()

# 3. Ajax / get / post / load 调用点
w("## 3. Ajax/get/post/load 调用点（去重上下文）")
w()
pat = re.compile(r"(\.ajax\s*\(|\$\.get\s*\(|\$\.post\s*\(|\.load\s*\(|XMLHttpRequest|ActiveXObject|\.open\s*\(\s*[\"'](?:GET|POST)|new\s+Ajax|ObjAjax\s*\()", re.I)
ctxs = []
for m in pat.finditer(js):
    a, b = max(0, m.start() - 120), min(len(js), m.end() + 260)
    ctxs.append((m.group(1), m.start(), js[a:b]))

w("共 %d 处。" % len(ctxs))
w()
for g, off, ctx in ctxs:
    w("#### `%s` @ %d" % (g, off))
    w()
    w("```javascript")
    w(ctx)
    w("```")
    w()

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("written", OUT, len(out), "lines")
