"""Read-only capture regressions plus two explicit expected DS wire failures."""
from pathlib import Path
import unittest

import argparse
import importlib.util
import sys

HERE = Path(__file__).resolve().parent
HELPER = HERE / "dot_assist_contracts_20261015_1452.py"
if not HELPER.exists():
    HELPER = HERE.parent / "tools" / "dot_assist_contracts_20261015_1452.py"
SPEC = importlib.util.spec_from_file_location("dot_assist_contracts_1452", HELPER)
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)
audit, normalized_units = CONTRACT.audit, CONTRACT.normalized_units
new_command_id = CONTRACT.new_command_id
PROJECT = HERE.parent
MODE = "baseline"


class DSContractChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = audit(PROJECT, proposed=MODE == "proposed")

    def test_three_isolated_transport_cycles(self):
        self.assertEqual(len(self.result["transport_cycles"]), 3)
        for cycle in self.result["transport_cycles"]:
            self.assertTrue(all(cycle["checks"].values()))

    def test_parked_predicate_is_not_current_passenger_membership(self):
        for cycle in self.result["transport_cycles"]:
            self.assertEqual(cycle["reported_counts"][-1], 0)
            self.assertGreater(cycle["parked_candidates_at_same_pos2"][-1], 0)

    def test_fresh_initial_is_36_live_records_without_cargo(self):
        initial = self.result["fresh_initial"]
        self.assertEqual((initial["records"], initial["alive"], initial["captured_cargo_count"]),
                         (36, 36, 0))
        self.assertEqual(initial["sides"], {"BLUE": 18, "RED": 18})

    def test_ids_are_added_from_source_keys_without_reviving_records(self):
        source = {"original": {"id2": "Obj_0", "pos": "0", "blood": "0", "color": ""},
                  "new": {"id2": "original", "pos": "10004", "blood": "3", "color": "BLUE"}}
        normalized = normalized_units(source)
        self.assertEqual({record["id"] for record in normalized}, set(source))
        self.assertEqual(normalized[0]["blood"], "0")
        self.assertNotIn("id", source["original"])
        with self.assertRaises(ValueError):
            normalized_units({"key": {"id": "different"}})

    def test_new_entity_pos2_is_not_assumed_equal_to_current_cell(self):
        self.assertTrue(all(cycle["new_entity_pos2"] == "0"
                            for cycle in self.result["transport_cycles"]))

    def test_command_and_update_fields_already_match_client_contract(self):
        checks = self.result["mocked_motion"]["checks"]
        self.assertTrue(checks["command_path_is_mapids"])
        self.assertTrue(checks["ComPost_labels_are_display_hexids"])
        self.assertTrue(checks["updatePos_MapID_is_mapid"])
        self.assertTrue(checks["updatePos_tile_fields_are_tiles"])

    def test_move_end_positions_use_authoritative_mapids(self):
        # 2026-10-15：`tools/hex_combat_round.move_step` 已修正为传 mapid
        #（受控实验 tools/hex_move_probe.py 证实 MoveEnd 的 ObjPos/ObjNewPos 是新位置来源），
        # 故此前的 expectedFailure 不再成立 → 改为正常断言。
        checks = self.result["mocked_motion"]["checks"]
        self.assertTrue(checks["MoveEnd_ObjPos_is_mapid"])
        self.assertTrue(checks["MoveEnd_ObjNewPos_is_mapid"])

    @unittest.expectedFailure
    def test_queue_selects_latest_matching_target_command(self):
        self.assertTrue(self.result["mocked_motion"]["checks"]["ComID_matches_latest_target_command"])


    def test_queue_does_not_reuse_old_identical_command(self):
        before = '5|U|{"probe":{"off":1}}||task'
        after = before + '&6|U|{"probe":{"off":1}}||task&99|U|{"other":{"off":1}}||task'
        self.assertEqual(new_command_id(before, after, "probe", {"probe": {"off": 1}}), "6")

    def test_queue_checks_actor_when_available(self):
        after = '1|U|{"probe":{"off":1}}||task&2|V|{"probe":{"off":1}}||task'
        self.assertEqual(new_command_id("", after, "probe", {"probe": {"off": 1}}, "V"), "2")

    def test_queue_different_action_on_same_unit_does_not_match(self):
        with self.assertRaises(ValueError):
            new_command_id("", '1|U|{"probe":{"off":2}}||task', "probe", {"probe": {"off": 1}})

    def test_queue_ambiguous_new_commands_stop(self):
        after = '1|U|{"probe":{"off":1}}||task&2|U|{"probe":{"off":1}}||task'
        with self.assertRaises(ValueError):
            new_command_id("", after, "probe", {"probe": {"off": 1}})

    def test_queue_no_new_id_stops(self):
        queue = '1|U|{"probe":{"off":1}}||task'
        with self.assertRaises(ValueError):
            new_command_id(queue, queue, "probe", {"probe": {"off": 1}})

    def test_queue_delimiters_inside_json_are_not_headers(self):
        command = {"probe": {"note": "value&7|BOGUS|inside"}}
        import json
        after = '1|U|' + json.dumps(command) + '||task'
        self.assertEqual(new_command_id("", after, "probe", command), "1")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--mode", choices=("baseline", "proposed"), default="baseline")
    args = parser.parse_args()
    PROJECT, MODE = args.project, args.mode
    if MODE == "proposed":
        for name in ("test_move_end_positions_use_authoritative_mapids",
                     "test_queue_selects_latest_matching_target_command"):
            getattr(DSContractChecks, name).__unittest_expecting_failure__ = False
    unittest.main(argv=[sys.argv[0]], verbosity=2)
