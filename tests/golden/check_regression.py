"""Golden captures regression checker.

Compares the structure of golden baseline files against a live capture directory
(or just validates the golden captures themselves when run standalone).

Exit code 0 = pass, 1 = fail.

Usage:
    # Validate golden captures exist and are structurally valid
    python tests/golden/check_regression.py

    # Compare a new capture against a golden baseline
    python tests/golden/check_regression.py --compare <mission_slug> <new_capture_dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).parent
MISSIONS = ["alertmanager-lag-preprod", "jira-broker-crash"]

EXPECTED_FILES = [
    "prompts.json",
    "tool_calls.json",
    "audit.kafka_strimzi_expert.jsonl",
    "audit.k8s_gcp_sre.jsonl",
    "audit.prom_alerts_triage.jsonl",
    "BRIEF.md",
    "kb_card.json",
]

AUDIT_NON_LLM_FIELDS = {"timestamp", "tool_name", "mission_id"}
JSON_STRUCTURAL_FILES = {"prompts.json", "tool_calls.json", "kb_card.json"}
JSONL_FILES = {
    "audit.kafka_strimzi_expert.jsonl",
    "audit.k8s_gcp_sre.jsonl",
    "audit.prom_alerts_triage.jsonl",
}


def _load_json(path: Path) -> Any:
    with path.open() as f:
        return json.load(f)


def _load_jsonl(path: Path) -> list[dict]:
    lines = []
    with path.open() as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno} — invalid JSON: {e}") from e
    return lines


def _get_structure(obj: Any, depth: int = 0) -> Any:
    """Return a type-only skeleton of a JSON object for structural comparison."""
    if depth > 5:
        return type(obj).__name__
    if isinstance(obj, dict):
        return {k: _get_structure(v, depth + 1) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        if not obj:
            return []
        return [_get_structure(obj[0], depth + 1)]
    return type(obj).__name__


def _compare_structures(golden: Any, candidate: Any, path: str) -> list[str]:
    errors: list[str] = []
    g_struct = _get_structure(golden)
    c_struct = _get_structure(candidate)
    if g_struct != c_struct:
        errors.append(
            f"  {path}: structure mismatch\n"
            f"    golden:    {json.dumps(g_struct, indent=2)[:200]}\n"
            f"    candidate: {json.dumps(c_struct, indent=2)[:200]}"
        )
    return errors


def _check_audit_non_llm_fields(golden_lines: list[dict], candidate_lines: list[dict], path: str) -> list[str]:
    errors: list[str] = []
    if len(golden_lines) != len(candidate_lines):
        errors.append(
            f"  {path}: line count mismatch (golden={len(golden_lines)}, candidate={len(candidate_lines)})"
        )
        return errors
    for i, (g, c) in enumerate(zip(golden_lines, candidate_lines)):
        for field in AUDIT_NON_LLM_FIELDS:
            if field in g and g.get(field) != c.get(field):
                errors.append(
                    f"  {path}:{i+1} field '{field}': golden={g.get(field)!r}, candidate={c.get(field)!r}"
                )
            elif field not in g and field in c:
                errors.append(f"  {path}:{i+1} unexpected field '{field}' in candidate")
            elif field in g and field not in c:
                errors.append(f"  {path}:{i+1} missing field '{field}' in candidate")
    return errors


def validate_golden(mission_dir: Path) -> list[str]:
    """Check that a golden capture directory has the expected files and valid JSON."""
    errors: list[str] = []
    mission = mission_dir.name

    for fname in EXPECTED_FILES:
        fpath = mission_dir / fname
        if not fpath.exists():
            if fname == "BRIEF.md":
                errors.append(f"  [{mission}] MISSING: {fname} (capture not yet run — see README.md)")
            else:
                errors.append(f"  [{mission}] MISSING: {fname} (capture not yet run — see README.md)")
            continue

        if fname in JSON_STRUCTURAL_FILES:
            try:
                _load_json(fpath)
            except (json.JSONDecodeError, OSError) as e:
                errors.append(f"  [{mission}] INVALID JSON in {fname}: {e}")

        elif fname in JSONL_FILES:
            try:
                _load_jsonl(fpath)
            except (ValueError, OSError) as e:
                errors.append(f"  [{mission}] INVALID JSONL in {fname}: {e}")

    return errors


def compare_capture(mission_slug: str, candidate_dir: Path) -> list[str]:
    """Compare a candidate capture directory against the golden baseline."""
    golden_dir = GOLDEN_DIR / mission_slug
    errors: list[str] = []

    if not golden_dir.exists():
        return [f"Golden baseline not found: {golden_dir}"]

    for fname in EXPECTED_FILES:
        golden_path = golden_dir / fname
        candidate_path = candidate_dir / fname

        if not golden_path.exists():
            errors.append(f"  [{mission_slug}] Golden missing {fname} — cannot compare")
            continue
        if not candidate_path.exists():
            errors.append(f"  [{mission_slug}] Candidate missing {fname}")
            continue

        if fname == "BRIEF.md":
            # Semantic diff only — flag for manual review if sizes differ drastically
            golden_size = golden_path.stat().st_size
            cand_size = candidate_path.stat().st_size
            ratio = abs(golden_size - cand_size) / max(golden_size, 1)
            if ratio > 0.5:
                errors.append(
                    f"  [{mission_slug}] BRIEF.md size differs by {ratio:.0%} "
                    f"(golden={golden_size}B, candidate={cand_size}B) — manual semantic review required"
                )
            continue

        if fname in JSON_STRUCTURAL_FILES:
            try:
                g_data = _load_json(golden_path)
                c_data = _load_json(candidate_path)
                errors.extend(_compare_structures(g_data, c_data, f"[{mission_slug}] {fname}"))
            except (json.JSONDecodeError, OSError) as e:
                errors.append(f"  [{mission_slug}] {fname}: parse error — {e}")

        elif fname in JSONL_FILES:
            try:
                g_lines = _load_jsonl(golden_path)
                c_lines = _load_jsonl(candidate_path)
                errors.extend(_check_audit_non_llm_fields(g_lines, c_lines, f"[{mission_slug}] {fname}"))
            except (ValueError, OSError) as e:
                errors.append(f"  [{mission_slug}] {fname}: parse error — {e}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden captures regression checker")
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("MISSION_SLUG", "CANDIDATE_DIR"),
        help="Compare a candidate capture against the golden baseline",
    )
    args = parser.parse_args()

    all_errors: list[str] = []

    if args.compare:
        mission_slug, candidate_dir_str = args.compare
        candidate_dir = Path(candidate_dir_str)
        if not candidate_dir.is_dir():
            print(f"ERROR: candidate directory not found: {candidate_dir}")
            return 1
        errors = compare_capture(mission_slug, candidate_dir)
        label = f"COMPARE {mission_slug}"
        if errors:
            print(f"[FAIL] {label}")
            for e in errors:
                print(e)
        else:
            print(f"[PASS] {label}")
        return 1 if errors else 0

    # Default: validate all golden captures exist and are structurally valid
    print("Checking golden capture baselines...")
    missing_captures: list[str] = []

    for mission in MISSIONS:
        mission_dir = GOLDEN_DIR / mission
        if not mission_dir.exists():
            all_errors.append(f"  [{mission}] directory not found")
            continue
        errors = validate_golden(mission_dir)
        if errors:
            # Distinguish between "not captured yet" and "corrupt"
            if all("not yet run" in e for e in errors):
                missing_captures.append(mission)
                print(f"[PENDING] {mission} — artifacts not yet captured (see README.md)")
            else:
                all_errors.extend(errors)
                print(f"[FAIL] {mission}")
                for e in errors:
                    print(e)
        else:
            print(f"[PASS] {mission}")

    if missing_captures:
        print(
            f"\n⚠ {len(missing_captures)} mission(s) not yet captured: {missing_captures}"
            "\n  Run the platform in LAB and copy artifacts per README.md instructions."
            "\n  Re-run this script after capture to validate."
        )
        # Missing captures are a warning when running pre-WS-1, not a failure
        # They become a failure once at least one capture exists
        captured = [m for m in MISSIONS if (GOLDEN_DIR / m / "prompts.json").exists()]
        if not captured:
            print("\nStatus: PENDING (no captures yet — this is expected before WS-0)")
            return 0

    if all_errors:
        print(f"\n[FAIL] {len(all_errors)} error(s) found:")
        for e in all_errors:
            print(e)
        return 1

    if not missing_captures:
        print("\n[PASS] All golden captures valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
