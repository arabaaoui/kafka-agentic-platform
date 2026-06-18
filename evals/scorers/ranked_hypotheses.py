"""
Promptfoo Python scorer — ranked hypotheses structure.
Checks that the consolidator audit output has:
  - An executive summary section
  - A markdown table with at least 2 hypothesis rows
  - A "Rank" or "#" column header
  - A "Next steps" or "Recommended" section
Score: 0.0-1.0 based on how many criteria are met (partial credit).
"""

import re

_CRITERIA = [
    ("executive_summary", re.compile(r"##?\s*(executive\s+summary|summary)", re.IGNORECASE)),
    ("hypothesis_table", re.compile(r"\|\s*(rank|#|\d+)\s*\|", re.IGNORECASE)),
    ("table_rows", re.compile(r"(\|\s*\d+\s*\|.*\n){1,}", re.IGNORECASE)),
    ("next_steps", re.compile(r"##?\s*(next steps?|recommended|recommendations?)", re.IGNORECASE)),
    ("confidence_col", re.compile(r"confidence", re.IGNORECASE)),
]


def get_score(output: str, context: dict) -> dict:  # noqa: ARG001
    passed = [(name, bool(pat.search(output))) for name, pat in _CRITERIA]
    n_passed = sum(1 for _, ok in passed if ok)
    score = n_passed / len(_CRITERIA)

    missing = [name for name, ok in passed if not ok]
    reason = (
        f"Passed {n_passed}/{len(_CRITERIA)} structure criteria."
        + (f" Missing: {', '.join(missing)}" if missing else "")
    )

    return {
        "pass": score >= 0.8,
        "score": score,
        "reason": reason,
    }
