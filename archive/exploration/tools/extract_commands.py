"""从官方客户端脚本中提取「指令词汇表」。

背景
----
客户端下达指令统一走 `ComPost()`，body 形如：

    {"<ObjID>":{"<cmd>":<value>, ...}}

被点号的键集合就是**客户端能下达的全部指令词汇**，也就是复刻服务端时
必须实现的完整动作空间。本脚本把它连同端点清单、状态码、任务名一起抽出来。

用法
----
    py -3.13 tools/extract_commands.py offline/assets/war.min.js [-o out.md]

脚本只做静态文本抽取，不访问网络。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------- 读取

RE_ESC = re.compile(r"\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})")


def _unescape(s: str) -> str:
    """还原 JS 源码里的 \\uXXXX / \\xNN 转义，否则中文任务名读不出来。"""
    def rep(m: re.Match) -> str:
        return chr(int(m.group(1) or m.group(2), 16))
    return RE_ESC.sub(rep, s)


def load_text(path: Path) -> str:
    """官方脚本是 GBK/UTF-8/纯 ASCII 混杂，逐个试；再还原转义。"""
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", "replace")
    return _unescape(text)


# ---------------------------------------------------------------- 抽取器

# ComPost 的 body 写作  '"on":"' + objid + '"'，内层双引号才是真正的键
CMD_KEY = re.compile(r'"(\w{1,16})"\s*:')

# 端点
RE_ASP = re.compile(r"[A-Za-z0-9_/.\-]+\.asp\b", re.I)

# TaskName="xxx"（中文任务名）
RE_TASK = re.compile(r"""TaskName\s*=\s*["']([^"']{1,12})["']""")

# 状态码来源 1：jQuery 选择器 [f2=6] / [f2!=9]
RE_SEL_F2 = re.compile(r"\[\s*f2\s*!?=\s*(\d+)\s*\]")

# 状态码来源 2：attr("f2")==6
RE_ATTR_F2 = re.compile(r"""attr\(\s*["']f2["']\s*\)\s*[!=]=\s*(\d+)""")

# 状态码来源 3：下拉选项 <option value="101">机动</option>
RE_OPTION = re.compile(r"""<option[^>]*value=["']?(\d{2,3})["']?[^>]*>([^<]{1,12})<""", re.I)

# 常见的「从 POST body 构造命令」的调用
RE_COMPOST = re.compile(r"""ComPost\s*\(""")

# 已知的非指令键（jQuery/内部对象字段），用于过滤噪声
NOISE = {
    "async", "type", "url", "data", "datatype", "complete", "success", "error",
    "cache", "timeout", "context", "obj", "id", "name", "class", "style", "key",
    "value", "text", "html", "left", "top", "width", "height", "pos", "color",
    "size", "pos1", "pos2", "attr", "prop", "css", "each", "length", "push",
    "split", "join", "indexOf", "substring", "charAt", "replace", "match",
    "toLowerCase", "toUpperCase", "toString", "parseInt", "parseFloat",
    "datetime", "datatype", "ifModified", "processData", "contentType",
    "beforeSend", "dataType", "jsonp", "username", "password", "xhrFields",
}


def extract(path: Path) -> dict:
    text = load_text(path)

    endpoints = sorted({m.group(0) for m in RE_ASP.finditer(text)},
                       key=lambda s: s.lower())

    keys = Counter(m.group(1) for m in CMD_KEY.finditer(text))

    tasks = sorted({m.group(1) for m in RE_TASK.finditer(text)})

    options: dict[str, str] = {}
    for m in RE_OPTION.finditer(text):
        options.setdefault(m.group(1), m.group(2).strip())

    f2_codes = Counter()
    for m in RE_SEL_F2.finditer(text):
        f2_codes[m.group(1)] += 1
    for m in RE_ATTR_F2.finditer(text):
        f2_codes[m.group(1)] += 1

    return {
        "endpoints": endpoints,
        "keys": keys,
        "tasks": tasks,
        "options": options,
        "f2": f2_codes,
        "compost_calls": len(RE_COMPOST.findall(text)),
        "size": len(text),
    }


def classify(key: str, count: int) -> bool:
    """粗略判断这个键是否像指令键。"""
    if key in NOISE:
        return False
    if len(key) > 16:
        return False
    return count >= 1


# ---------------------------------------------------------------- 输出

def render_md(src: Path, info: dict) -> str:
    out: list[str] = []
    w = out.append

    w(f"# 客户端指令词汇表（静态抽取）\n")
    w(f"- 来源：`{src.as_posix()}`（{info['size']:,} 字符）")
    w(f"- `ComPost()` 调用点：{info['compost_calls']} 处")
    w(f"- 端点：{len(info['endpoints'])} 个")
    w("")
    w("> 本文件由 `tools/extract_commands.py` 自动生成，仅做静态文本抽取。\n")

    w("## 指令键候选\n")
    w("`ComPost()` 的 body 形如 `{\"<ObjID>\":{\"<key>\":<value>}}`。")
    w("以下键出现在 JSON 字面量上下文里，即客户端可下达的指令集合：\n")
    w("| 键 | 出现次数 |")
    w("|---|---|")
    for k, c in sorted(info["keys"].items(), key=lambda kv: (-kv[1], kv[0])):
        if classify(k, c):
            w(f"| `{k}` | {c} |")
    w("")

    w("## 中文任务名（TaskName）\n")
    if info["tasks"]:
        for t in info["tasks"]:
            w(f"- {t}")
    else:
        w("（未抽到）")
    w("")

    w("## 状态码（下拉/选项）\n")
    if info["options"]:
        w("| 码 | 含义 |")
        w("|---|---|")
        for k, v in sorted(info["options"].items(), key=lambda kv: int(kv[0])):
            w(f"| {k} | {v} |")
    else:
        w("（未抽到）")
    w("")

    w("## `f2` 状态比较出现的取值\n")
    if info["f2"]:
        for k, c in sorted(info["f2"].items(), key=lambda kv: int(kv[0])):
            w(f"- `f2 == {k}`：{c} 处")
    else:
        w("（未抽到）")
    w("")

    w("## 端点全清单\n")
    w("```")
    for e in info["endpoints"]:
        w(e)
    w("```")
    w("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="抽取客户端指令词汇表")
    ap.add_argument("script", type=Path, help="官方客户端脚本（war.min.js 等）")
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="输出 Markdown 路径")
    ap.add_argument("--json", action="store_true", help="同时打印 JSON 摘要")
    ns = ap.parse_args(argv)

    if not ns.script.exists():
        print(f"找不到文件：{ns.script}", file=sys.stderr)
        return 2

    info = extract(ns.script)
    md = render_md(ns.script, info)

    if ns.out:
        ns.out.parent.mkdir(parents=True, exist_ok=True)
        ns.out.write_text(md, encoding="utf-8")
        print(f"已写入 {ns.out}")
    else:
        print(md)

    if ns.json:
        print(json.dumps({k: (v if not isinstance(v, Counter) else dict(v))
                          for k, v in info.items()
                          if k != "endpoints"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
