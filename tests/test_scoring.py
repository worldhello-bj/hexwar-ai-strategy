"""计分口径回归测试（`engine/scoring.py`）。

用**原创合成 fixture**（不依赖真实想定数据，`snapshot/parsed` 不入库）。覆盖：

1. `remaining` = `Σ上阵(score×blood)` + `Σ车内载员(score×编制)`（已反推口径）；
2. **载员归属用稳定载具 ID**：载具机动后载员分值**守恒**（不能凭空消失）；
3. 同格多辆载具时按 `son` 图标配对，不"取第一辆"；定不下来要显式报出；
4. 未知型号载员编制 = `None`（不按 0 静默计分），并在 `unverified` 里报出；
5. 下车后恢复阵营与兵力，分值不消失；
6. 未确证分值（占位夺控分、假设歼灭分）**默认不进奖励**（`verified`），
   `platform` 口径才包含它们；
7. `total(BLUE) + total(RED)` 恒定（= 全部单位 `score×编制` 之和）。
"""
import json
import tempfile
import unittest
from pathlib import Path

from engine import Game, Unit, geometry as G
from engine import scoring
from env.hexwar_env import HexwarEnv

CARRIER_HEX = G.make_mapid(10, 10)
BLUE_HEX = G.make_mapid(12, 12)
RED_HEX = G.make_mapid(9, 9)
FAR_HEX = G.make_mapid(11, 13)


def build(snapshot, *, extra_carrier=False, unknown_data=False):
    """合成想定：蓝 1 个上阵单位 / 红 1 个上阵单位 + 1 辆载具 + 1 个车内载员。

    载具带 `son` 图标串、载员带 `ico`（与真实快照同形状），用于验证图标配对。
    """
    hexes = {str(G.make_mapid(r, c)): {"cond": 0, "elevation": 0, "step": 1}
             for r in range(6, 16) for c in range(6, 16)}
    units = [
        dict(id="blue", data=0, typeid=1, color="BLUE", blood=4, score=3, pos=BLUE_HEX),
        dict(id="red", data=0, typeid=1, color="RED", blood=2, score=5, pos=RED_HEX),
        dict(id="truck", data=0, typeid=2, color="RED", blood=3, score=10,
             pos=CARRIER_HEX, ico="ZBD100", son="PLA2-191,VUT5,UGVS"),
        # 载员：无阵营、pos=0、blood=0，只有 pos2 指向载具格；ico 命中载具 son
        dict(id="squad", data=382, typeid=1, color="", blood=0, score=3, pos=0,
             pos2=CARRIER_HEX, ico="PLA2-191"),
    ]
    if extra_carrier:
        # 同格第二辆载具，图标串里**没有**该载员的 ico → 必须能区分开
        units.append(dict(id="truck2", data=0, typeid=2, color="RED", blood=3,
                          score=10, pos=CARRIER_HEX, ico="M113TW",
                          son="COD-M4,COD-FK"))
    if unknown_data:
        units[3]["data"] = 99999
    (snapshot / "map_hexes.json").write_text(json.dumps(hexes))
    (snapshot / "cities.json").write_text(json.dumps(
        [{"id": "obj", "pos": G.make_mapid(13, 13), "name": "Synthetic", "flag": None}]))
    (snapshot / "units.json").write_text(json.dumps(units))


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        build(self.root)
        self.game = Game(seed=1, snapshot=str(self.root))

    def make(self, **kwargs):
        kwargs.setdefault("scoring_mode", "verified")
        env = HexwarEnv(snapshot=str(self.root), **kwargs)
        env.reset(seed=1)
        return env

    def sides(self, game=None):
        both, issues = scoring.both_scores(game or self.game)
        return both, issues

    def unit(self, uid):
        return self.game.units[uid]

    # ---------- remaining ----------

    def test_remaining_is_score_times_blood_plus_carried_establishment(self):
        both, _ = self.sides()
        self.assertEqual(both["BLUE"]["remaining"], 12)      # 3×4
        self.assertEqual(both["RED"]["remaining"], 49)       # 5×2 + 10×3 + 3×3

    def test_blood_attrition_moves_remaining_by_score_times_loss(self):
        self.unit("red").blood = 1
        both, _ = self.sides()
        self.assertEqual(both["RED"]["remaining"], 44)       # 49 − 5
        self.assertEqual(both["BLUE"]["killed"], 5)

    def test_total_is_invariant_under_attrition(self):
        both, _ = self.sides()
        total = both["BLUE"]["total"] + both["RED"]["total"]
        self.assertEqual(total, 61)
        self.unit("red").blood = 1
        both, _ = self.sides()
        self.assertEqual(both["BLUE"]["total"] + both["RED"]["total"], total)

    # ---------- 载员-载具关联（评审点名的关键场景）----------

    def test_snapshot_carried_unit_is_linked_to_a_stable_carrier_id(self):
        self.assertEqual(self.unit("squad").detail["carrier"], "truck")
        self.assertEqual(self.unit("truck").detail["carried"], ["squad"])

    def test_carried_points_survive_carrier_movement(self):
        """载具开走（离开原格）后，载员分值**必须守恒**。"""
        both, _ = self.sides()
        before_red = both["RED"]["remaining"]
        before_total = both["BLUE"]["total"] + both["RED"]["total"]
        self.unit("truck").pos = FAR_HEX                 # 载具机动到别处
        after, issues = self.sides()
        self.assertEqual(after["RED"]["remaining"], before_red)
        self.assertEqual(after["BLUE"]["total"] + after["RED"]["total"], before_total)
        self.assertEqual(issues["carried_unlinked"], [])
        self.assertEqual(self.unit("squad").pos2, CARRIER_HEX)   # pos2 保持旧格，但已不参与计分

    def test_carrier_movement_through_env_action_conserves_score(self):
        env = self.make()
        before = env.score()
        env.game.units["truck"].pos = FAR_HEX
        after = env.score()
        self.assertEqual(after["own"]["remaining"], before["own"]["remaining"])
        self.assertEqual(after["enemy"]["remaining"], before["enemy"]["remaining"])
        self.assertEqual(after["enemy"]["unverified"].count("carried_unlinked"), 0)

    def test_two_carriers_in_one_hex_are_disambiguated_by_icon(self):
        build(self.root, extra_carrier=True)
        game = Game(seed=1, snapshot=str(self.root))
        self.assertEqual(game.units["squad"].detail["carrier"], "truck")
        self.assertEqual(game.carried_ambiguous, [])
        both, issues = scoring.both_scores(game)
        # 载员算红方 3×3；两辆载具各自 10×3
        self.assertEqual(both["RED"]["remaining"], 5 * 2 + 10 * 3 * 2 + 9)
        self.assertEqual(issues["carried_linked"] if "carried_linked" in issues else [], [])

    def test_unlinkable_carried_unit_is_reported_not_silently_dropped(self):
        build(self.root)
        units = json.loads((self.root / "units.json").read_text())
        for entry in units:
            if entry["id"] == "truck":
                entry["pos"] = FAR_HEX          # 载具不在 pos2 指的那一格，且图标也不匹配
        self.root.joinpath("units.json").write_text(json.dumps(units))
        game = Game(seed=1, snapshot=str(self.root))
        both, issues = scoring.both_scores(game)
        self.assertEqual(game.carried_unlinked, ["squad"])
        self.assertEqual(issues["carried_unlinked"], ["squad"])
        self.assertIn("carried_unlinked", both["BLUE"]["unverified"] +
                      both["RED"]["unverified"])
        self.assertEqual(both["RED"]["remaining"], 40)      # 只剩 5×2 + 10×3

    # ---------- 未知型号 / 编制来源 ----------

    def test_unknown_carried_establishment_is_none_and_reported(self):
        build(self.root, unknown_data=True)
        game = Game(seed=1, snapshot=str(self.root))
        self.assertIsNone(scoring.carried_establishment(99999))
        both, issues = scoring.both_scores(game)
        self.assertEqual(issues["carried_establishment_unknown"], [("squad", 99999)])
        self.assertEqual(both["RED"]["remaining"], 40)      # 未知型号**不按 0 计入**
        self.assertIn("carried_establishment_unknown", both["RED"]["unverified"])

    def test_establishment_provenance_is_always_flagged(self):
        both, _ = self.sides()
        self.assertIn("establishment_from_load_blood", both["RED"]["unverified"])

    def test_aboard_unit_counted_as_deployed_is_flagged(self):
        """引擎的中途装载不把载员 blood 置 0；这种口径差异必须报出来。"""
        both, _ = self.sides()
        self.assertNotIn("aboard_counted_as_deployed", both["BLUE"]["unverified"])
        self.unit("blue").detail["carrier"] = "truck"       # 假装蓝方步兵上了车
        both, _ = self.sides()
        self.assertIn("aboard_counted_as_deployed", both["BLUE"]["unverified"])

    # ---------- 下车恢复身份 ----------

    def test_unload_restores_color_and_strength_so_points_do_not_vanish(self):
        env = self.make(side="RED")
        before = env.score()["own"]["remaining"]
        _, _, _, info = env.step({"type": "unload", "unit": "truck"})
        self.assertFalse(info.get("invalid_action"), info)
        squad = env.game.units["squad"]
        self.assertEqual(squad.color, "RED")
        self.assertEqual(squad.blood, 3)                    # 编制表补回
        self.assertNotIn("carrier", squad.detail)
        after = env.score()["own"]["remaining"]
        self.assertEqual(after, before)                     # 3×3 仍在（换了个身份）

    # ---------- 未确证分值不进奖励 ----------

    def test_verified_mode_excludes_placeholder_capture_points(self):
        env = self.make()
        self.assertEqual(env.score()["mode"], "verified")
        self.assertEqual(env.score()["own"]["total"], 12)
        env.game.cities[0]["flag"] = "BLUE"
        self.assertEqual(env.score()["own"]["captured"],
                         scoring.CAPTURE_POINT_SCORE_PLACEHOLDER)
        self.assertEqual(env.score()["own"]["verified"], 12)
        self.assertEqual(env.score()["diff"], -37)          # 只用 remaining
        platform = self.make(scoring_mode="platform")
        platform.game.cities[0]["flag"] = "BLUE"
        self.assertEqual(platform.score()["diff"], -37 + 10)
        self.assertIn("captured_per_point", platform.score()["unverified"])

    def test_verified_mode_excludes_assumed_kill_points(self):
        env = self.make()
        before = env.score()["diff"]
        env.game.units["red"].blood = 1                     # 敌方受损
        after = env.score()
        # 歼灭分（**假设**）确实被算出来了，并如实报出
        self.assertEqual(after["own"]["killed"], 5)
        self.assertIn("killed_formula", after["unverified"])
        # 但奖励只动"敌方剩余兵力下降"这一份（-5 → diff +5），
        # **不**叠加"己方歼灭分 +5"；否则同一个损失会在 diff 里被算两遍。
        self.assertEqual(after["diff"] - before, 5)
        self.assertEqual(after["own"]["verified"], 12)

    def test_reward_follows_the_selected_mode(self):
        # verified：损失只算敌方剩余下降 1 份（+5）；
        # platform：再加上假设的歼灭分（+5），于是同一损失在 diff 里加倍（+10）。
        # 这正是"口径不同不能混用"的最直接理由。
        for mode, expected in (("verified", 5), ("platform", 10)):
            env = self.make(scoring_mode=mode)
            before = env.score()["diff"]
            env.game.units["red"].blood = 1
            self.assertEqual(env.score()["diff"] - before, expected, mode)

    # ---------- 占位与版本 ----------

    def test_placeholder_and_version_are_explicit(self):
        self.assertEqual(scoring.CAPTURE_POINT_SCORE_PLACEHOLDER, 10)
        self.assertEqual(scoring.PENDING_RULES, ("captured_per_point", "killed_formula"))
        self.assertEqual(scoring.VERIFIED_COMPONENTS, ("remaining",))
        self.assertIsInstance(scoring.SCORING_VERSION, int)
        self.assertEqual(HexwarEnv.CAPTURE_POINT_SCORE_PLACEHOLDER, 10)

    def test_score_reports_version_mode_and_rules(self):
        report = self.make().score()
        self.assertEqual(report["scoring_version"], scoring.SCORING_VERSION)
        self.assertEqual(report["mode"], "verified")
        self.assertEqual(report["pending_rules"], list(scoring.PENDING_RULES))
        self.assertIn("issues", report)


if __name__ == "__main__":
    unittest.main()
