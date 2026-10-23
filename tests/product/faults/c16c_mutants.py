"""Reproducible C16c fault injection; run under heavy-lock, from a clean worktree.

Only one product file is changed at a time, restored byte-for-byte in finally.
Assertions come from the ordinary green controls, so expectedFailure cannot mask a
mutation. Known-red cases are separately documented and never counted as kills.
"""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
CASES = [
    ("4.1", "ai_caddie/courses/course_search.py",
     'records.setdefault(int(row["global_id"]), row)', 'records[len(records)] = row',
     'tests.product.test_j4_course.CourseHTTPTests.test_j4_1_discovery_deduplicates_and_names_venues'),
    ("4.2", "ai_caddie/caddie/round_loops.py",
     'if loops[0][0] != int(path_global_id):', 'if False:',
     'tests.product.test_j4_course.CourseHTTPTests.test_j4_2_illegal_course_parameters_are_rejected'),
    ("4.3", "ai_caddie/caddie/mobile_live.py",
     'int(hole["sourceLocalHole"]) if loop["half"] in ("front", "back") else number',
     'int(hole["sourceLocalHole"]) + 1 if loop["half"] in ("front", "back") else number',
     'tests.product.test_j4_course.CourseHTTPTests.test_j4_3_packages_equal_hand_physical_hole_table'),
    ("4.3/no-shift", "ai_caddie/caddie/mobile_live.py",
     'offset = len(front.get("holes") or [])', 'offset = 0',
     'tests.product.test_j4_course.CourseHTTPTests.test_j4_3_packages_equal_hand_physical_hole_table'),
    ("4.3/forced-back", "ai_caddie/caddie/mobile_live.py",
     '_filter_package_to_nine(base, half)', '_filter_package_to_nine(base, "back" if loop_packages else half)',
     'tests.product.test_j4_course.CourseHTTPTests.test_j4_3_packages_equal_hand_physical_hole_table'),
    ("4.1/coverage", "ai_caddie/caddie/mobile_live.py",
     '"segmentHoles": int(segment_holes) if segment_holes else played_holes,',
     '"segmentHoles": played_holes,',
     'tests.product.test_j4_course.CourseHTTPTests.test_j4_1_discovery_deduplicates_and_names_venues'),
    ("4.4", "ai_caddie/courses/course_prep.py",
     'front_pt = min(boundary_points, key=_from_tee)', 'front_pt = max(boundary_points, key=_from_tee)',
     'tests.product.test_j4_course.GeometryTests.test_j4_4_geometry_equals_polygon_arithmetic'),
    ("5.7", "ai_caddie/rounds/round_ingest.py",
     'if strokes is None or strokes < 1:', 'if strokes is None or strokes < 6:',
     'tests.product.test_j5_play.PlayTests.test_j5_7_legal_writes'),
    ("5.8", "ai_caddie/courses/tee_result.py", 'return "left"', 'return "right"',
     'tests.product.test_j5_play.PlayTests.test_j5_8_tee_result_shared_golden'),
    ("5.9", "ai_caddie/caddie/mobile_event_store.py",
     'existing = positions.get(item.identity) if item.identity[2] else None', 'existing = None',
     'tests.product.test_j5_play.PlayTests.test_j5_9_event_retry_order_and_materialization'),
    ("5.11", "ai_caddie/caddie/decision.py",
     '"clubName": row.get("clubName"),\n        "role": role,',
     '"clubName": "9I",\n        "role": role,',
     'tests.product.test_j5_play.DecisionGoldenTests.test_j5_11_decisions_equal_hand_routes'),
    ("5.11/hazards", "ai_caddie/caddie/decision.py",
     'forbidden = _forbidden_zones_from_route(route)', 'forbidden = []',
     'tests.product.test_j5_play.DecisionGoldenTests.test_j5_11_decisions_equal_hand_routes'),
    ("5.11/strokes", "ai_caddie/caddie/decision.py",
     '"expectedStrokes": round(1.0 + expected_delta, 2),', '"expectedStrokes": 99,',
     'tests.product.test_j5_play.DecisionGoldenTests.test_j5_11_decisions_equal_hand_routes'),
    ("5.15", "ai_caddie/rounds/swing_candidates.py",
     'merged = {c["id"]: c for c in load_candidates(player_id, round_id, root)}', 'merged = {}',
     'tests.product.test_j5_play.PlayTests.test_j5_15_candidate_retry_never_changes_scores'),
    ("8.1", "ai_caddie/history/history_stats.py",
     '"topWeakness": weaknesses[0] if weaknesses else None',
     '"topWeakness": weaknesses[0] if weaknesses else {"issue":"putting"}',
     'tests.product.test_j8_degrade.DegradeTests.test_j8_1_no_baseline_no_prescription'),
    ("8.2", "ai_caddie/caddie/decision.py",
     '"selected": selected,\n        "selectedOptionId":',
     '"selected": selected or {"carry_m":99},\n        "selectedOptionId":',
     'tests.product.test_j8_degrade.DegradeTests.test_j8_2_missing_geometry_and_bag_give_no_distances'),
    ("8.3", "ai_caddie/rounds/round_corrections.py",
     'return [path for path in (legacy, current) if path.exists()]',
     'return [path for path in (current,) if path.exists()]',
     'tests.product.test_j8_degrade.DegradeTests.test_j8_3_legacy_and_current_corrections_merge_stably'),
]


def clear_bytecode(path):
    for cached in (path.parent / "__pycache__").glob(path.stem + ".*.pyc"):
        cached.unlink()


def main():
    killed = 0
    for promise, relative, old, new, test in CASES:
        path = ROOT / relative
        original = path.read_bytes()
        source = original.decode()
        if old not in source:
            raise RuntimeError(f"{promise}: mutation location changed")
        # Positive control first. An already-red test is never evidence of a killed mutant.
        env = {**os.environ, "AI_CADDIE_DATA_MODE":"fixture", "PYTHONDONTWRITEBYTECODE":"1"}
        command = [sys.executable,"-m","unittest",test]
        baseline = subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=60)
        if baseline.returncode:
            raise RuntimeError(f"{promise}: baseline is not green\n{baseline.stderr}")
        line = source[:source.index(old)].count("\n") + 1
        try:
            path.write_text(source.replace(old,new))
            clear_bytecode(path)
            result = subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=60)
            # Require an actual assertion failure in the target test, not an import/syntax error.
            dead = result.returncode != 0 and "\nFAIL: " in result.stderr and "ERROR:" not in result.stderr
            if not dead:
                print(result.stderr)
                raise RuntimeError(f"{promise}: survived or failed for the wrong reason")
            if promise.startswith("4.3/") and "physical-hole golden with identity validation disabled" not in result.stderr:
                raise RuntimeError(f"{promise}: failed before the physical-hole comparison\n{result.stderr}")
            killed += 1
            print(f"{promise}: KILLED {relative}:{line} ({test.rsplit('.',1)[1]})",flush=True)
        finally:
            path.write_bytes(original)
            clear_bytecode(path)
    print(f"{killed}/{len(CASES)} killed; product sources restored",flush=True)


if __name__ == "__main__":
    main()
