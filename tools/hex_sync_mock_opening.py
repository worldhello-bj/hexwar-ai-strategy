# -*- coding: utf-8 -*-
"""把桩服务的静态快照（`offline/mock/Obj_Get.asp`、`ObjAjax.asp`）与 `snapshot/parsed` 对齐。

为什么要它：桩服务的**静态**端点（`Obj_Get` / `ObjAjax`）是从 `snapshot/raw/`（HAR 原始字节）
生成的，而**动态**端点（`com/*`）走 `offline/engine_bridge.py` → `engine.Game()`，
而 `Game()` 读的是 `snapshot/parsed/`。一旦改了 `parsed/units.json`（例如用
`tools/hex_sync_snapshot_opening.py` 把快照对齐到平台开局），两边就会不一致：
`Obj_Get` 还显示旧位置，而引擎世界已经变了 ⇒ `tools/verify_e2e.py` 会表现为
“战线两边距离对不上、攻击被拒 ⇒ 战果不生效”。

本工具按 `snapshot/parsed/units.json` 改写两个静态文件里的 pos/pos2/blood/color/step
（`Obj_Get` 是 `<div id="Obj_x" 属性...>`；`ObjAjax` 是 JSON）。

用法：
    py -3.13 tools/hex_sync_mock_opening.py            # dry-run
    py -3.13 tools/hex_sync_mock_opening.py --apply
"""
import argparse
import io
import json
import os
import re

ROOT = r"d:\兵推"
PARSED = os.path.join(ROOT, "snapshot", "parsed", "units.json")
MOCK = os.path.join(ROOT, "offline", "mock")
FIELDS = ("pos", "pos2", "blood", "color", "step")


def load_parsed():
    with io.open(PARSED, encoding="utf-8") as fh:
        return {u["id"]: u for u in json.load(fh)}


def patch_obj_get(text, parsed):
    out, changed = [], []
    for m in re.finditer(r'<div id="(Obj_\d+)"([^>]*)>', text):
        uid, attrs = m.group(1), m.group(2)
        pu = parsed.get(uid)
        if pu is None:
            continue
        new_attrs = attrs
        for f in FIELDS:
            if f not in pu:
                continue
            val = str(pu[f])
            new_attrs, n = re.subn(r'(?<=\s)%s="[^"]*"' % f,
                                   '%s="%s"' % (f, val), new_attrs, count=1)
            old = re.search(r'(?<=\s)%s="([^"]*)"' % f, attrs)
            if n and old and old.group(1) != val:
                changed.append((uid, f, old.group(1), val))
        out.append((m.start(2), m.end(2), new_attrs))
    for s, e, rep in reversed(out):
        text = text[:s] + rep + text[e:]
    return text, changed


def patch_obj_ajax(text, parsed):
    try:
        data = json.loads(text)
    except ValueError:
        return text, []
    if not isinstance(data, dict):
        return text, []
    changed = []
    for uid, dyn in data.items():
        pu = parsed.get(uid)
        if pu is None or not isinstance(dyn, dict):
            continue
        for f in FIELDS:
            if f in pu and f in dyn and str(dyn[f]) != str(pu[f]):
                changed.append((uid, f, dyn[f], pu[f]))
                dyn[f] = pu[f]
    return json.dumps(data, ensure_ascii=False), changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    parsed = load_parsed()
    total = []
    for name, fn in (("Obj_Get.asp", patch_obj_get), ("ObjAjax.asp", patch_obj_ajax)):
        p = os.path.join(MOCK, name)
        if not os.path.exists(p):
            print("跳过（不存在）:", name)
            continue
        with io.open(p, "rb") as fh:
            raw = fh.read()
        enc_used = None
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                text = raw.decode(enc)
                enc_used = enc
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", "replace")
            enc_used = "utf-8"
        new, changed = fn(text, parsed)
        print("%s：需要改 %d 处（读编码 %s；按官方约定以 GB18030 写回）"
              % (name, len(changed), enc_used))
        for uid, f, old, val in changed[:40]:
            print("   %-14s %-6s %s -> %s" % (uid, f, old, val))
        total += changed
        if args.apply:
            # ★ 桩的 `.asp` 一律是 GB18030 字节（见 `tools/build_offline_site.py::put`），
            #   不能按读到的编码写回（曾写成 UTF-8 ⇒ 与其它桩文件编码不一致）。
            #   即使这次没有字段变化也重写一遍，用于把编码归一。
            with io.open(p, "wb") as fh:
                fh.write(new.encode("gb18030", errors="replace"))
    print("共 %d 处；%s" % (len(total), "已写入" if args.apply else "(dry-run)"))
    if not total:
        print("两边已经一致。")


if __name__ == "__main__":
    main()
