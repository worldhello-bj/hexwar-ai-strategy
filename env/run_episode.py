# -*- coding: utf-8 -*-
"""跑一局或多局并输出统计——策略搜索的「跑分台」。

用法
----
    py -3.13 env\run_episode.py --agent greedy-multi --episodes 20
    py -3.13 env\run_episode.py --agent random --episodes 50 --side RED --json out.json
    py -3.13 env\run_episode.py --agent greedy --render      # 打印一局的文本态势
"""
import os
import sys
import json
import argparse
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hexwar_env import HexwarEnv
from agents import AGENTS

DEFAULT_SNAP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "samples", "demo")


def run_one(agent, side, seed, snapshot, max_seconds, fog, render=False, verbose=False):
    env = HexwarEnv(snapshot=snapshot, side=side, max_seconds=max_seconds, fog=fog)
    obs = env.reset(seed=seed)
    steps = 0
    if render:
        print(env.render())
    while not env.done:
        act = agent.act(env, obs)
        obs, reward, done, info = env.step(act)
        if env.game.second == 0 and steps == 0 and verbose:
            print("首步信息:", info)
        steps += 1
        if verbose and steps % 20 == 0:
            print("t=%4d  己方总分=%4d  敌方总分=%4d" %
                  (obs["time"], obs["score"]["own"]["total"],
                   obs["score"]["enemy"]["total"]))
        if steps > 5000:      # 安全阀
            break
    if render:
        print(env.render())
    return {"side": side, "seed": seed, "steps": steps,
            "score": env.score(), "log_tail": env.game.log[-5:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="greedy-multi", choices=sorted(AGENTS))
    ap.add_argument("--episodes", type=int, default=1)
    ap.add_argument("--side", default="BLUE", choices=["BLUE", "RED"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--snapshot", default=DEFAULT_SNAP,
                    help="快照目录（默认用自带样例；真实数据用 snapshot/parsed）")
    ap.add_argument("--max-seconds", type=int, default=1800)
    ap.add_argument("--no-fog", action="store_true", help="关闭战争迷雾（上帝视角）")
    ap.add_argument("--render", action="store_true", help="打印文本态势")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json", help="把结果写入 JSON")
    args = ap.parse_args()

    if not os.path.isfile(os.path.join(args.snapshot, "map_hexes.json")):
        sys.exit("快照目录无效（缺 map_hexes.json）：%s\n"
                 "先跑：py -3.13 tools/make_sample.py" % args.snapshot)

    results = []
    for i in range(args.episodes):
        agent = AGENTS[args.agent]() if args.agent != "greedy" else AGENTS[args.agent]()
        if hasattr(agent, "rng"):
            agent.rng.seed(args.seed + i)
        r = run_one(agent, args.side, args.seed + i, args.snapshot,
                    args.max_seconds, not args.no_fog,
                    render=args.render and i == 0, verbose=args.verbose)
        results.append(r)
        print("第 %2d 局  seed=%-4d  步数=%-5d  己方=%4d 敌方=%4d 净胜=%+4d" %
              (i + 1, r["seed"], r["steps"], r["score"]["own"]["total"],
               r["score"]["enemy"]["total"], r["score"]["diff"]))

    diffs = [r["score"]["diff"] for r in results]
    wins = sum(1 for d in diffs if d > 0)
    print()
    print("=" * 60)
    print("智能体: %s   阵营: %s   局数: %d   迷雾: %s" %
          (args.agent, args.side, len(results), "关" if args.no_fog else "开"))
    print("净胜分  平均 %+7.1f   中位 %+7.1f   最好 %+5d   最差 %+5d" %
          (statistics.mean(diffs), statistics.median(diffs), max(diffs), min(diffs)))
    print("胜率    %.1f%%  (%d/%d)" % (100.0 * wins / len(results), wins, len(results)))
    print("=" * 60)

    if args.json:
        json.dump({"agent": args.agent, "side": args.side, "fog": not args.no_fog,
                   "episodes": results,
                   "summary": {"mean_diff": statistics.mean(diffs),
                               "win_rate": wins / len(results)}},
                  open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("结果已写入", args.json)


if __name__ == "__main__":
    main()
