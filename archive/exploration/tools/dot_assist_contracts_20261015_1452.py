"""Read-only DS assistance: captured transport transitions and mocked wire calls.

No DS modules/top-level code are imported. Only reviewed function definitions
are extracted; every HTTP helper they call is replaced by an in-memory recorder.
Session objects, credentials and response headers are never exported.
"""
import ast
import collections
import copy
import hashlib
import json
from pathlib import Path
import re
import types


def snapshot(path):
    data = path.read_bytes()
    value = json.loads(data.decode("utf-8-sig"))
    return {key: value[key] for key in ("static_units", "dynamic_units", "report_all")
            if key in value}, {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}


def parked(unit, position):
    return (int(unit.get("pos") or 0) == 0 and int(unit.get("blood") or 0) == 0
            and not unit.get("color") and str(unit.get("pos2")) == str(position))


def normalized_units(keyed):
    """Use the authoritative dictionary key as ID; retain every source record."""
    result = []
    for identity, original in keyed.items():
        record = copy.deepcopy(original)
        if record.get("id") not in (None, identity):
            raise ValueError("record ID conflicts with its dictionary key")
        record["id"] = identity
        result.append(record)
    return result


def check_cycle(directory):
    stages, sources = {}, []
    for name in ("before", "after_load", "after_unload"):
        stages[name], info = snapshot(directory / (name + ".json"))
        sources.append(info)
    before, loaded, unloaded = [stages[name]["static_units"] for name in stages]
    passengers = [key for key, unit in before.items()
                  if int(unit.get("blood") or 0) > 0 and unit.get("color")
                  and int(unit.get("pos") or 0) > 0
                  and parked(loaded[key], unit["pos"])]
    carriers = [key for key, unit in before.items()
                if int(loaded[key].get("sons") or 0) - int(unit.get("sons") or 0) == 1]
    created = sorted(set(unloaded) - set(loaded))
    if not (len(passengers) == len(carriers) == len(created) == 1):
        raise AssertionError("capture is not one isolated load/unload transition")
    passenger, carrier, entity = passengers[0], carriers[0], created[0]
    new = unloaded[entity]
    checks = {
        "static_dynamic_id_sets_match": all(set(data["static_units"]) == set(data["dynamic_units"])
                                            for data in stages.values()),
        "normalization_preserves_every_record": all(len(normalized_units(data)) == len(data)
                                                   for data in (before, loaded, unloaded)),
        "no_id_created_by_load": set(before) == set(loaded),
        "new_entity_has_original_id2": new.get("id2") == passenger,
        "new_entity_has_carrier_reference": new.get("car") == carrier,
        "new_entity_at_carrier": str(new["pos"]) == str(unloaded[carrier]["pos"]),
        "observed_hp_retained": new["blood"] == before[passenger]["blood"],
        "observed_side_retained": new["color"] == before[passenger]["color"],
        "observed_type_retained": new["typeid"] == before[passenger]["typeid"],
        "original_record_still_parked_after_unload": parked(unloaded[passenger], unloaded[carrier]["pos"]),
        "carrier_count_round_trip": int(before[carrier]["sons"]) == int(unloaded[carrier]["sons"]),
        "icon_string_unchanged": len({data[carrier]["son"] for data in (before, loaded, unloaded)}) == 1,
        "static_dynamic_carrier_counts_match": all(
            int(data["static_units"][carrier]["sons"]) == int(data["dynamic_units"][carrier]["son"])
            for data in stages.values()),
        "report_all_bytes_identical_only": len({data.get("report_all") for data in stages.values()}) == 1,
    }
    if not all(checks.values()):
        raise AssertionError({key: value for key, value in checks.items() if not value})
    return {"group": directory.name, "sources": sources, "checks": checks,
            "carrier": carrier, "original": passenger, "new_entity": entity,
            "observed_type": int(new["typeid"]), "observed_hp": int(new["blood"]),
            "new_entity_pos2": new.get("pos2"),
            "record_counts": [len(data) for data in (before, loaded, unloaded)],
            "reported_counts": [int(data[carrier]["sons"]) for data in (before, loaded, unloaded)],
            "parked_candidates_at_same_pos2": [sum(parked(unit, data[carrier]["pos"])
                                                    for unit in data.values())
                                                for data in (before, loaded, unloaded)],
            "predicate_is_not_a_current_manifest": parked(unloaded[passenger], unloaded[carrier]["pos"])}


def queue_rows(text):
    """Decode JSON before scanning the next queue header; no eval or auth I/O."""
    result, position, decoder = [], 0, json.JSONDecoder()
    header = re.compile(r"(\d+)\|([^|]*)\|")
    next_header = re.compile(r"&(?=\d+\|[^|]*\|)")
    while position < len(text):
        while position < len(text) and text[position] in "& \r\n\t":
            position += 1
        if position == len(text):
            break
        match = header.match(text, position)
        if not match:
            raise ValueError("unsupported queue header; do not guess ComID")
        start = match.end()
        while start < len(text) and text[start].isspace():
            start += 1
        payload, end = decoder.raw_decode(text, start)
        if not isinstance(payload, dict):
            raise ValueError("queue command must be an object")
        result.append({"id": match.group(1), "user": match.group(2), "command": payload})
        following = next_header.search(text, end)
        position = following.end() if following else len(text)
    return result


def new_command_id(before, after, unit, command, expected_user=None):
    """Require a unique fresh row for this exact unit/action, not queue order."""
    if unit not in command:
        raise ValueError("requested unit is absent from command")
    old = {row["id"] for row in queue_rows(before)}
    matches = {row["id"] for row in queue_rows(after)
               if row["id"] not in old
               and (expected_user is None or row["user"] == str(expected_user))
               and row["command"].get(unit) == command[unit]}
    if len(matches) != 1:
        raise ValueError("no unique new matching ComID; do not send MoveEnd or retry the action")
    return matches.pop()


def fixed_move_ast(node):
    if node.name != "move_step":
        return node
    for call in ast.walk(node):
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == "jget" and len(call.args) >= 3
                and isinstance(call.args[2], ast.Constant)
                and call.args[2].value == "com/MoveEnd.asp"):
            for keyword in call.keywords:
                if keyword.arg in ("ObjPos", "ObjNewPos"):
                    keyword.value = ast.Name(id="frm" if keyword.arg == "ObjPos" else "to", ctx=ast.Load())
                elif keyword.arg == "ComID":
                    keyword.value = ast.Subscript(value=ast.Name(id="c", ctx=ast.Load()),
                                                  slice=ast.Constant(value="com_id"), ctx=ast.Load())
    return ast.fix_missing_locations(node)


def extract(path, names, namespace, transform=None):
    original_bytes = path.read_bytes()
    text = original_bytes.decode("utf-8-sig")
    tree = ast.parse(text)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in nodes} != set(names):
        raise AssertionError("expected reviewed functions not found")
    if any(isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal))
           for function in nodes for node in ast.walk(function)):
        raise AssertionError("unexpected side-effectful code inside extracted function")
    if transform:
        nodes = [transform(node) for node in nodes]
    namespace["__builtins__"] = {"int": int, "str": str}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    if path.read_bytes() != original_bytes:
        raise RuntimeError("DS changed this source during inspection; reobserve before judging it")
    return {"path": str(path), "sha256": hashlib.sha256(original_bytes).hexdigest(),
            "extracted_functions": [node.name for node in nodes]}


def probe_motion(root, proposed=False):
    maps = json.loads((root / "snapshot/parsed/map_hexes.json").read_text(encoding="utf-8"))
    frm, to = 170068, 170070
    assert str(frm) in maps and str(to) in maps
    geo = types.SimpleNamespace(hexid=lambda mid: maps[str(mid)]["hexid"])
    calls = []
    before_queue = '41|USER|{"old":{"off":1}}||下车'
    after_queue = before_queue + '&42|USER|{"probe":{"move":"170068,170070","speed":0}}||机动&99|OTHER|{"other":{"off":2}}||卸载'
    posted = False

    def fake_get(session, base, endpoint, **params):
        nonlocal posted
        calls.append({"endpoint": endpoint, "params": params})
        if endpoint.endswith("ComPost.asp"):
            posted = True
        return (after_queue if posted else before_queue) if endpoint.endswith("ComAjax.asp") else "120" if endpoint.endswith("updatePos.asp") else ""

    namespace = {"json": json, "re": re, "GEO": geo, "MAPINFO": maps, "jget": fake_get}
    source = extract(root / "tools/hex_combat_round.py", ["cmd", "cell", "move_step"], namespace,
                     fixed_move_ast if proposed else None)
    if proposed:
        def fixed_cmd(sess, base7, objid, color, command, task, pos_hex, map_hex=""):
            before = fake_get(sess, base7, "com/ComAjax.asp")
            params = {"ObjID": objid, "Command": json.dumps(command, ensure_ascii=False),
                      "ObjColor": color, "TaskName": task, "ObjPos": pos_hex, "MapID": map_hex}
            body = fake_get(sess, base7, "com/ComPost.asp", **params)
            echo = fake_get(sess, base7, "com/ComAjax.asp")
            return {"params": params, "com_post": body, "com_ajax": echo[:300],
                    "com_id": new_command_id(before, echo, objid, command)}
        namespace["cmd"] = fixed_cmd
    namespace["move_step"](None, "offline-only/", "probe", frm, to, "BLUE")
    update = next(call["params"] for call in calls if call["endpoint"].endswith("updatePos.asp"))
    end = next(call["params"] for call in calls if call["endpoint"].endswith("MoveEnd.asp"))
    post = next(call["params"] for call in calls if call["endpoint"].endswith("ComPost.asp"))
    return {"source": source, "proposed_in_memory_copy": proposed,
            "all_http_calls_mocked": True, "network_requests": 0,
            "sample_mapids": [frm, to], "display_hexids": [geo.hexid(frm), geo.hexid(to)],
            "captured_calls": calls,
            "checks": {"command_path_is_mapids": json.loads(post["Command"])["probe"]["move"] == f"{frm},{to}",
                       "ComPost_labels_are_display_hexids": post["ObjPos"] == geo.hexid(frm) and post["MapID"] == geo.hexid(to),
                       "updatePos_MapID_is_mapid": update["MapID"] == to,
                       "updatePos_tile_fields_are_tiles": update["preIDhex"] == maps[str(frm)]["hex"] and update["posIDhex"] == maps[str(to)]["hex"],
                       "MoveEnd_ObjPos_is_mapid": str(end["ObjPos"]) == str(frm),
                       "MoveEnd_ObjNewPos_is_mapid": str(end["ObjNewPos"]) == str(to),
                       "ComID_matches_latest_target_command": str(end["ComID"]) == "42"}}


def audit(root, proposed=False):
    capture = root / "7527_transport_capture"
    cycles = [check_cycle(capture / group) for group in
              ("load_unload_blue_armored", "load_unload_red_support", "load_unload_red_support_ugvs")]
    initial, source = snapshot(capture / "2p_before_start.json")
    units = initial["static_units"]
    return {"scope": "read-only existing project captures and isolated mocked request functions",
            "fresh_initial": {"source": source, "records": len(units),
                              "alive": sum(int(unit["blood"]) > 0 for unit in units.values()),
                              "sides": dict(collections.Counter(unit["color"] for unit in units.values())),
                              "captured_cargo_count": sum(int(unit["sons"]) for unit in units.values())},
            "transport_cycles": cycles, "mocked_motion": probe_motion(root, proposed),
            "limits": ["Parked records are history candidates, not an authoritative current passenger manifest.",
                       "HP equality is observed only for the three captured undamaged examples; damaged reload behavior remains untested.",
                       "No off=3 cycle or capacity/cost rule is inferred.",
                       "Identical Report_All strings do not prove zero time or resource cost.",
                       "No DS source edits, sessions, credentials, network actions, games or training."]}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proposed", action="store_true")
    args = parser.parse_args()
    result = audit(args.project, args.proposed)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "transport_cycles_verified": len(result["transport_cycles"]),
                      "motion_checks": result["mocked_motion"]["checks"]}, ensure_ascii=False))
