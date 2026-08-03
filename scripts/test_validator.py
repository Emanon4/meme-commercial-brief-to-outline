#!/usr/bin/env python3
"""Run fixed positive and negative tests for validate_dossier.py."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = ROOT / "scripts" / "validate_dossier.py"
VALID = ROOT / "tests" / "valid-ready.md"
FIRST_PASS = ROOT / "tests" / "valid-first-pass.md"
INVALID = ROOT / "tests" / "invalid-unresolved.md"


def run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> int:
    valid = run(VALID)
    if valid.returncode != 0:
        print("VALID CASE FAILED")
        print(valid.stdout)
        print(valid.stderr)
        return 1

    first_pass = run(FIRST_PASS)
    if first_pass.returncode != 0:
        print("FIRST-PASS CASE FAILED")
        print(first_pass.stdout)
        print(first_pass.stderr)
        return 1

    invalid = run(INVALID)
    expected_fragments = (
        "进入 brief_locked 前必须确认 Brief Lock",
        "进入 brief_locked 前关键未决项必须为无",
        "B01 尚未确认",
        "跨过人工闸门前至少需要一条 Dxx 决策记录",
        "缺少属于 BL-v1 且确认该版本的 Dxx 决策记录",
    )
    if invalid.returncode != 1 or any(
        fragment not in invalid.stdout for fragment in expected_fragments
    ):
        print("INVALID CASE DID NOT FAIL AS EXPECTED")
        print(invalid.stdout)
        print(invalid.stderr)
        return 1

    with tempfile.TemporaryDirectory() as directory:
        stale_path = Path(directory) / "stale-decision.md"
        stale_text = VALID.read_text(encoding="utf-8").replace(
            "- Creative Decision 版本：CD-v1",
            "- Creative Decision 版本：CD-v2",
            1,
        )
        stale_path.write_text(stale_text, encoding="utf-8")
        stale = run(stale_path)
        interpretation_path = Path(directory) / "unconfirmed-interpretation.md"
        interpretation_text = VALID.read_text(encoding="utf-8").replace(
            "- Brief 解读确认状态：已确认",
            "- Brief 解读确认状态：未确认",
            1,
        )
        interpretation_path.write_text(interpretation_text, encoding="utf-8")
        interpretation = run(interpretation_path)
        missing_dimension_path = Path(directory) / "missing-dimension.md"
        missing_dimension_text = FIRST_PASS.read_text(encoding="utf-8").replace(
            "| 话题张力 | 当前 Brief 没有足够真实矛盾 | 以是否需要甜味形成温和讨论；讨论办公室饮料选择是否只看甜度 | 待调研假设：需看办公室饮料评论中的真实分歧 | 不制造含糖与无糖人群对立 |\n",
            "",
            1,
        )
        missing_dimension_path.write_text(missing_dimension_text, encoding="utf-8")
        missing_dimension = run(missing_dimension_path)
    expected_stale = "缺少在 CD-v2 选择 C02 的 Dxx 决策记录"
    if stale.returncode != 1 or expected_stale not in stale.stdout:
        print("STALE DECISION WAS INCORRECTLY ACCEPTED")
        print(stale.stdout)
        print(stale.stderr)
        return 1
    expected_interpretation = "进入 brief_locked 前必须人工确认 Brief 解读"
    if interpretation.returncode != 1 or expected_interpretation not in interpretation.stdout:
        print("UNCONFIRMED BRIEF INTERPRETATION WAS INCORRECTLY ACCEPTED")
        print(interpretation.stdout)
        print(interpretation.stderr)
        return 1
    expected_dimension = "缺少选题调研维度发散：话题张力"
    if missing_dimension.returncode != 1 or expected_dimension not in missing_dimension.stdout:
        print("MISSING TOPIC DIMENSION WAS INCORRECTLY ACCEPTED")
        print(missing_dimension.stdout)
        print(missing_dimension.stderr)
        return 1

    print(valid.stdout.strip())
    print(first_pass.stdout.strip())
    print("OK: an unconfirmed Brief can include dimension-led creative directions")
    print("OK: invalid-unresolved.md was rejected at the Brief gate")
    print("OK: an old Dxx cannot approve a new Creative Decision version")
    print("OK: hard requirements cannot substitute for human Brief interpretation approval")
    print("OK: a missing topic-research dimension is rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
