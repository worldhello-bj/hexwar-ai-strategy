# -*- coding: utf-8 -*-
"""解析 www.hexwar.cn.har，输出接口清单与资源清单到 UTF-8 报告。"""
import json
import os
import re
import collections
import sys

HAR = r"d:\兵推\www.hexwar.cn.har"
OUTDIR = r"d:\兵推\analysis"
os.makedirs(OUTDIR, exist_ok=True)

with open(HAR, "r", encoding="utf-8", errors="replace") as f:
    har = json.load(f)

entries = har["log"]["entries"]
log = har["log"]

lines = []
def w(s=""):
    lines.append(s)

w("# HAR 解析报告")
w()
w("- 文件: %s" % HAR)
w("- 记录条数: %d" % len(entries))
creator = log.get("creator", {})
w("- creator: %s %s" % (creator.get("name"), creator.get("version")))
browser = log.get("browser", {})
w("- browser: %s %s" % (browser.get("name"), browser.get("version")))
w()

# ---- 1. 按主机/路径聚合 ----
def strip_query(u):
    return u.split("?")[0]

counter = collections.Counter()
methods = collections.Counter()
by_path_entries = collections.defaultdict(list)
for i, e in enumerate(entries):
    req = e["request"]
    url = req["url"]
    p = strip_query(url)
    # 只保留 host+path
    m = re.match(r"^(https?://[^/]+)(/.*)?$", url)
    key = (m.group(1) if m else url) + (m.group(2) if m and m.group(2) else "/")
    key = strip_query(key)
    counter[key] += 1
    methods[(req["method"], key)] += 1
    by_path_entries[key].append(i)

w("## 1. 请求聚合（按 host+path，忽略查询串）")
w()
w("| 次数 | Method | 路径 |")
w("|---|---|---|")
for path, c in counter.most_common():
    ms = sorted({m for (m, k) in methods if k == path})
    w("| %d | %s | %s |" % (c, "/".join(ms), path))
w()

# ---- 2. 全部记录明细 ----
w("## 2. 全部记录明细")
w()
w("| # | Method | Status | MIME | 大小 | URL |")
w("|---|---|---|---|---|---|")
for i, e in enumerate(entries):
    req = e["request"]
    resp = e["response"]
    content = resp.get("content", {})
    size = content.get("size", 0)
    url = req["url"]
    w("| %d | %s | %s | %s | %s | %s |" % (
        i, req["method"], resp.get("status"), content.get("mimeType", ""),
        size, url.replace("|", "%7C")))
w()

# ---- 3. 分类：文档 / 脚本 / 样式 / 图片 / 接口 ----
cats = collections.defaultdict(list)
for i, e in enumerate(entries):
    c = e["response"].get("content", {})
    mt = (c.get("mimeType") or "").lower()
    url = e["request"]["url"].lower()
    upath = url.split("?")[0]
    if re.search(r"\.asp$", upath) or upath.endswith("/"):
        cats["api"].append(i)
    elif upath.endswith(".js") or "javascript" in mt:
        cats["js"].append(i)
    elif upath.endswith(".css") or "css" in mt:
        cats["css"].append(i)
    elif "image" in mt or re.search(r"\.(png|jpg|jpeg|gif|bmp|ico|svg|webp)$", upath):
        cats["image"].append(i)
    elif "html" in mt:
        cats["html"].append(i)
    else:
        cats["other"].append(i)

w("## 3. 分类统计")
w()
for k in ("html", "js", "css", "api", "image", "other"):
    w("- %s: %d" % (k, len(cats[k])))
w()

w("### 3.1 脚本文件")
w()
seen = {}
for i in cats["js"]:
    e = entries[i]
    u = strip_query(e["request"]["url"])
    if u not in seen:
        seen[u] = (i, e["response"].get("content", {}).get("size", 0))
for u, (i, sz) in sorted(seen.items(), key=lambda kv: -kv[1][1]):
    w("- `%s` (%d bytes, entry #%d)" % (u, sz, i))
w()

w("### 3.2 图片资源")
w()
seen = {}
for i in cats["image"]:
    e = entries[i]
    u = strip_query(e["request"]["url"])
    if u not in seen:
        seen[u] = (i, e["response"].get("content", {}).get("size", 0), e["response"].get("status"))
for u, (i, sz, st) in sorted(seen.items()):
    w("- `%s` (%d bytes, status=%s)" % (u, sz, st))
w()

# ---- 4. 接口（ASP）请求/响应详情 ----
w("## 4. 接口调用（.asp / 动态）")
w()
seen = collections.OrderedDict()
for i in cats["api"]:
    e = entries[i]
    u = strip_query(e["request"]["url"])
    key = (e["request"]["method"], u)
    seen.setdefault(key, []).append(i)

for (meth, u), idxs in seen.items():
    w("### `%s %s`  —— %d 次" % (meth, u, len(idxs)))
    w()
    # 取第一次有请求体的做样例
    for i in idxs[:1]:
        e = entries[i]
        req = e["request"]
        pd = req.get("postData", {})
        if pd:
            w("请求 MIME: `%s`" % pd.get("mimeType", ""))
            w()
            txt = pd.get("text", "")
            w("```")
            w(txt[:4000])
            w("```")
            w()
        qs = req.get("queryString", [])
        if qs:
            w("查询参数: " + ", ".join("%s=%s" % (q["name"], q["value"][:120]) for q in qs))
            w()
        resp = e["response"]
        c = resp.get("content", {})
        w("响应: status=%s mime=%s size=%s" % (resp.get("status"), c.get("mimeType"), c.get("size")))
        w()
        rt = c.get("text", "")
        if rt:
            w("```")
            w(rt[:3000])
            w("```")
            w()
    # 统计响应长度分布
    sizes = [entries[i]["response"].get("content", {}).get("size", 0) for i in idxs]
    w("响应大小: min=%s max=%s 平均=%.0f" % (min(sizes), max(sizes), sum(sizes)/len(sizes)))
    w()

with open(os.path.join(OUTDIR, "har_report.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

# ---- 5. 导出关键响应体到文件 ----
BODIES = os.path.join(OUTDIR, "bodies")
os.makedirs(BODIES, exist_ok=True)

def safe_name(u):
    m = re.match(r"^https?://([^/]+)(/.*)?$", u)
    host = m.group(1) if m else "host"
    path = (m.group(2) if m and m.group(2) else "/")
    path = path.split("?")[0]
    n = host + path.replace("/", "_")
    return re.sub(r"[^A-Za-z0-9_.\-]", "_", n)[:150]

exported = []
for i, e in enumerate(entries):
    c = e["response"].get("content", {})
    txt = c.get("text")
    if not txt:
        continue
    mt = (c.get("mimeType") or "").lower()
    url = e["request"]["url"].split("?")[0]
    if "image" in mt:
        continue
    if url.endswith(".png") or url.endswith(".css"):
        continue
    ext = ".js" if url.endswith(".js") else (".html" if "html" in mt else ".txt")
    name = safe_name(url) + ext
    p = os.path.join(BODIES, name)
    if os.path.exists(p):
        continue
    with open(p, "w", encoding="utf-8", errors="replace") as f:
        f.write(txt)
    exported.append((name, len(txt), url))

with open(os.path.join(OUTDIR, "exported_bodies.md"), "w", encoding="utf-8") as f:
    f.write("# 导出的响应体（去重后第一次出现）\n\n")
    f.write("| 文件 | 字符数 | URL |\n|---|---|---|\n")
    for name, ln, url in sorted(exported, key=lambda x: -x[1]):
        f.write("| `%s` | %d | %s |\n" % (name, ln, url))

print("written report +", len(exported), "bodies")

