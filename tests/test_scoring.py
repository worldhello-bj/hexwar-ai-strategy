"""计分口径回归测试（`engine/scoring.py`）。

用**原创合成 fixture**（不依赖真实想定数据，`snapshot/parsed` 不入库）锁定三件事：

1. `remaining`：`Σ上阵(score×blood)` + `Σ车内载员(score×编制)` —— 已反推并实测对账的口径；
2. `killed`：**假设**按歼灭的兵力计（载具被歼时其载员一并计入），是未确证项；
3. `captured`：**占位**每点 10 分，无依据；未确证项必须随 `score()['pending_rules']` 下发。

另外锁定两条不变式：
- `total(BLUE) + total(RED)` 恒定（= 全部单位 `score×编制` 之和），与交火无关；
- 载员按 `pos2` 归属该格的**载具/飞行器**，即使该格还站着步兵。
"""
import json
import tempfile
import unittest
from pathlib import Path

from engine import Game, Unit, geometry as G
from engine import scoring
from env.hexwar_env import HexwarEnv

CARRIER_HEX = G.make_mapid(10, 10)      # 载具与载员所在格
BLUE_HEX = G.make_mapid(12, 12)
RED_HEX = G.make_mapid(9, 9)


def build(snapshot):
    """合成想定：蓝 1 个上阵单位 / 红 1 个上阵单位 + 1 辆载具 + 1 个车内载员。"""
    hexes = {str(G.make_mapid(r, c)): {"cond": 0, "elevation": 0, "step": 1}
             for r in range(6, 15) for c in range(6, 15)}
    units = [
        dict(id="blue", data=0, typeid=1, color="BLUE", blood=4, score=3, pos=BLUE_HEX),
        dict(id="red", data=0, typeid=1, color="RED", blood=2, score=5, pos=RED_HEX),
        # 载具：typeid=2（车辆），编制 3
        dict(id="truck", data=0, typeid=2, color="RED", blood=3, score=10, pos=CARRIER_HEX),
        # 车内载员：无阵营、pos=0、blood=0，只有 pos2 指向载具格；data=382 查编制表得 3
        dict(id="squad", data=382, typeid=1, color="", blood=0, score=3, pos=0,
             pos2=CARRIER_HEX),
    ]
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

    def sides(self):
        return scoring.both_scores(self.game)

    def unit(self, uid):
        return self.game.units[uid]

    # ---------- remaining ----------

    def test_remaining_is_score_times_blood_plus_carried_establishment(self):
        sides = self.sides()
        # 蓝：3×4 = 12（无载员）
        self.assertEqual(sides["BLUE"]["remaining"], 12)
        # 红：5×2 + 载具 10×3 + 载员 3×编制3 = 10 + 30 + 9 = 49
        self.assertEqual(sides["RED"]["remaining"], 49)

    def test_blood_attrition_moves_remaining_by_score_times_loss(self):
        self.unit("red").blood = 1
        sides = self.sides()
        self.assertEqual(sides["RED"]["remaining"], 44)      # 49 − 5
        self.assertEqual(sides["BLUE"]["killed"], 5)         # 敌方损失 1 兵力 × score 5

    def test_total_is_invariant_under_attrition(self):
        before = self.sides()
        total = before["BLUE"]["total"] + before["RED"]["total"]
        self.unit("red").blood = 1
        sides = self.sides()
        self.assertEqual(sides["BLUE"]["total"] + sides["RED"]["total"], total)
        self.assertEqual(total, 61)                          # 12 + 49

    # ---------- carried ----------

    def test_carried_unit_leaves_remaining_when_its_carrier_dies(self):
        self.unit("truck").blood = 0
        sides = self.sides()
        # 红方只剩上阵步兵 5×2 = 10；被歼载具与车内载员都不再计入剩余兵力
        self.assertEqual(sides["RED"]["remaining"], 10)
        self.assertEqual(sides["BLUE"]["killed"], 30 + 9)    # 载具 10×3 + 载员 3×编制3
        self.assertEqual(sides["BLUE"]["total"] + sides["RED"]["total"], 61)

    def test_carried_unit_prefers_a_vehicle_over_a_stacked_infantry_squad(self):
        """同格里还站着一名蓝方步兵时，载员仍应归属红方载具。"""
        self.game.units["stacker"] = Unit(
            dict(id="stacker", data=0, typeid=1, color="BLUE", blood=1, score=1,
                 pos=CARRIER_HEX))
        sides = self.sides()
        self.assertEqual(sides["RED"]["remaining"], 49)      # 载员仍算红方（不被蓝方步兵"抢走"）
        self.assertEqual(sides["BLUE"]["remaining"], 13)     # 蓝方多了一个 1×1 的上阵单位

    def test_unknown_carried_equipment_contributes_nothing(self):
        self.unit("squad").data = 99999                      # 编制表里没有的装备
        self.assertEqual(scoring.carried_establishment(99999), 0)
        self.assertEqual(self.sides()["RED"]["remaining"], 40)

    # ---------- captured（占位） ----------

    def test_captured_is_a_documented_placeholder_not_a_rule(self):
        self.assertEqual(scoring.CAPTURE_POINT_SCORE_PLACEHOLDER, 10)
        self.game.cities[0]["flag"] = "BLUE"
        # 占领 1 个点 = 1 × 占位值（**不是** 10×10）
        self.assertEqual(self.sides()["BLUE"]["captured"],
                         scoring.CAPTURE_POINT_SCORE_PLACEHOLDER)
        self.assertEqual(self.sides()["RED"]["captured"], 0)

    # ---------- 未确证项必须显式下发 ----------

    def test_env_score_delegates_and_reports_pending_rules(self):
        env = HexwarEnv(snapshot=str(self.root), side="BLUE")
        env.reset(seed=1)
        report = env.score()
        self.assertEqual(report["own"], scoring.side_score(env.game, "BLUE"))
        self.assertEqual(report["enemy"], scoring.side_score(env.game, "RED"))
        self.assertEqual(report["diff"], report["own"]["total"] - report["enemy"]["total"])
        self.assertEqual(report["pending_rules"], ["captured_per_point", "killed_formula"])
        self.assertNotIn("remaining_includes_carried", report["pending_rules"])
        self.assertEqual(HexwarEnv.CAPTURE_POINT_SCORE_PLACEHOLDER, 10)

    def test_settlement_uses_the_same_pipeline_for_both_seats(self):
        env = HexwarEnv(snapshot=str(self.root), side="RED")
        env.reset(seed=1)
        self.assertEqual(env.score()["own"], scoring.side_score(env.game, "RED"))
        self.assertEqual(env.score()["enemy"], scoring.side_score(env.game, "BLUE"))


if __name__ == "__main__":
    unittest.main()
