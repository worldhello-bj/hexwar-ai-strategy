# -*- coding: utf-8 -*-
"""从 war.min.js 中按名字抽取函数源码（花括号配对），输出到 UTF-8 文件。"""
import re
import os
import sys

SRC = r"d:\兵推\analysis\bodies\www.hexwar.cn_WARGAMEAI7_war.min.js.js"
OUTDIR = r"d:\兵推\analysis\funcs"
os.makedirs(OUTDIR, exist_ok=True)

js = open(SRC, "r", encoding="utf-8", errors="replace").read()

def extract(name):
    """找到 function name(...) 或 name=function(...)，返回其源码。"""
    pats = [r"function\s+%s\s*\(" % re.escape(name), r"\b%s\s*=\s*function\s*\(" % re.escape(name)]
    for p in pats:
        m = re.search(p, js)
        if not m:
            continue
        i = js.find("(", m.start())
        # 找到参数表结束
        depth = 0
        j = i
        while j < len(js):
            if js[j] == "(":
                depth += 1
            elif js[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        k = js.find("{", j)
        if k < 0:
            continue
        d = 0
        e = k
        while e < len(js):
            c = js[e]
            if c == "{":
                d += 1
            elif c == "}":
                d -= 1
                if d == 0:
                    break
            e += 1
        return js[m.start(): e + 1]
    return None

names = sys.argv[1:]
if not names:
    names = ["UserGet", "loadMapData", "ObjUpdate", "loadMap", "loadMap2", "ObjShow",
             "ComPost", "CommandMove", "CommandAttack", "timer", "ObjFire"]

out = []
for n in names:
    src = extract(n)
    out.append("## `%s`" % n)
    out.append("")
    if not src:
        out.append("（未找到）")
        out.append("")
        continue
    out.append("长度 %d" % len(src))
    out.append("")
    out.append("```javascript")
    out.append(src)
    out.append("```")
    out.append("")

p = os.path.join(OUTDIR, "extracted.md")
with open(p, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("ok", p, [n for n in names if extract(n)])
