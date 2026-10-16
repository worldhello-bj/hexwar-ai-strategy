# -*- coding: utf-8 -*-
"""比较私有仓工作区与公开仓克隆，列出需要发布/删除的文件（只读，不改任何东西）。

用法::

    py -3.13 archive/exploration/analysis/_publish_diff.py
    py -3.13 archive/exploration/analysis/_publish_diff.py --json out.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

PRIV = r"d:\兵推"
PUB = r"d:\兵推-public"
# 不随公开仓分发的路径前缀（与上一次发布一致）：探索封存区 + 依赖采集数据/凭据的脚本
EXCLUDE_PREFIX = ("archive/",)
EXCLUDE_FILES = ("tests/test_crt_live.py",)


def git(*args, cwd):
    # core.quotepath=false：否则非 ASCII 路径会被 git 加引号并转义（与磁盘路径对不上）
    out = subprocess.run(["git", "-c", "core.quotepath=false", "-C", cwd] + list(args),
                         capture_output=True)
    return out.stdout.decode("utf-8", "replace")


def tracked(cwd):
    return [p for p in git("ls-files", cwd=cwd).split("\n") if p]


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha1(fh.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="把结果写入该 JSON 文件")
    args = ap.parse_args()
    priv = tracked(PRIV)
    pub = tracked(PUB)
    candidates = [p for p in priv
                  if not p.startswith(EXCLUDE_PREFIX) and p not in EXCLUDE_FILES]
    result = {"excluded_private": sorted(set(priv) - set(candidates)),
              "new": [], "changed": [], "public_only": [], "identical": 0}
    for rel in candidates:
        src = os.path.join(PRIV, rel.replace("/", os.sep))
        dst = os.path.join(PUB, rel.replace("/", os.sep))
        if not os.path.exists(dst):
            result["new"].append(rel)
        elif sha(src) != sha(dst):
            result["changed"].append(rel)
        else:
            result["identical"] += 1
    for rel in pub:
        if rel not in set(candidates):
            result["public_only"].append(rel)
    print("私有已跟踪 %d 个；公开候选 %d 个（排除 %d 个）"
          % (len(priv), len(candidates), len(result["excluded_private"])))
    print("被排除：")
    for p in result["excluded_private"]:
        print("  -", p)
    for key, title in (("new", "需要新增"), ("changed", "内容不同"),
                       ("public_only", "只在公开仓（待删）")):
        print("%s：%d" % (title, len(result[key])))
        for p in result[key]:
            print("  *", p)
    print("逐字节相同：%d" % result["identical"])
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=1)
        print("已写入", args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
