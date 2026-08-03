#!/usr/bin/env python3
"""Validate deterministic gates in a commercial planning Markdown dossier."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


STATUSES = (
    "brief_draft",
    "brief_locked",
    "creative_draft",
    "creative_selected",
    "outline_draft",
    "outline_locked",
    "ready_for_director",
)
RANK = {status: index for index, status in enumerate(STATUSES)}
PLACEHOLDER_PATTERNS = (
    re.compile(r"〔[^〕]+〕"),
    re.compile(r"\bTODO\b", re.IGNORECASE),
)
DIVERGENCE_DIMENSIONS = (
    "群众基础",
    "情绪浓度",
    "认知反差",
    "社交货币",
    "话题张力",
    "价值获得",
)
REQUIRED_DIMENSION_ROWS = DIVERGENCE_DIMENSIONS + ("适配与风控",)


def parse_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, value in re.findall(r"^- ([^：\n]+)：\s*(.*)$", text, re.MULTILINE):
        fields[key.strip()] = value.strip()
    return fields


def table_rows(text: str, prefix: str) -> list[list[str]]:
    rows: list[list[str]] = []
    pattern = re.compile(rf"^\|\s*{re.escape(prefix)}\d+\s*\|", re.IGNORECASE)
    for line in text.splitlines():
        if pattern.match(line):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def dimension_rows(text: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] in REQUIRED_DIMENSION_ROWS:
            rows[cells[0]] = cells
    return rows


def has_placeholder(value: str) -> bool:
    return not value or any(pattern.search(value) for pattern in PLACEHOLDER_PATTERNS)


def require_fields(
    errors: list[str], fields: dict[str, str], names: tuple[str, ...]
) -> None:
    for name in names:
        if name not in fields:
            errors.append(f"缺少字段：{name}")
        elif has_placeholder(fields[name]):
            errors.append(f"字段未填写：{name}")


def validate_rows(
    errors: list[str], rows: list[list[str]], prefix: str, columns: int
) -> None:
    seen: set[str] = set()
    for row in rows:
        row_id = row[0] if row else prefix
        if len(row) != columns:
            errors.append(f"{row_id} 应有 {columns} 列，实际为 {len(row)} 列")
            continue
        if row_id in seen:
            errors.append(f"编号重复：{row_id}")
        seen.add(row_id)
        for index, cell in enumerate(row[1:], start=2):
            if has_placeholder(cell):
                errors.append(f"{row_id} 第 {index} 列未填写")


def referenced_ids(cell: str, prefix: str) -> set[str]:
    return set(re.findall(rf"\b{re.escape(prefix)}\d+\b", cell, re.IGNORECASE))


def decision_has_target(
    rows: list[list[str]], target: str, stage_version: str
) -> bool:
    return any(
        len(row) == 8 and row[2] == stage_version and target in row[4]
        for row in rows
    )


def validate(path: Path, expected_status: str | None) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    fields = parse_fields(text)

    base_fields = (
        "项目名称",
        "项目状态",
        "当前版本",
        "主内容项目档案",
        "账号名称",
        "账号定位版本",
        "原始 Brief 位置",
        "保密级别",
        "创建日期",
    )
    require_fields(errors, fields, base_fields)

    status = fields.get("项目状态", "")
    if status not in RANK:
        errors.append(f"无效项目状态：{status or '空'}")
        return errors
    if expected_status and status != expected_status:
        errors.append(f"项目状态为 {status}，预期为 {expected_status}")

    for heading in (
        "## 原始 Brief 留存",
        "## Brief Lock",
        "## 创意方向与决定",
        "## Outline Lock",
        "## 数字人导演交接包",
        "## 决策记录",
    ):
        if heading not in text:
            errors.append(f"缺少章节：{heading}")

    decision_rows = table_rows(text, "D")
    if RANK[status] >= RANK["brief_locked"]:
        if not decision_rows:
            errors.append("跨过人工闸门前至少需要一条 Dxx 决策记录")
        validate_rows(errors, decision_rows, "D", 8)

    brief_fields = (
        "Brief Lock 版本",
        "Brief Lock 确认状态",
        "Brief 要求确认状态",
        "Brief 解读确认状态",
        "核心商业目标",
        "Brief 一句话解读",
        "目标受众",
        "受众当前状态",
        "期望受众变化",
        "品牌角色",
        "必须表达",
        "禁止表达",
        "可协商空间",
        "交付限制",
        "成功标准",
        "既定语气边界",
        "Brief 中的真实矛盾",
        "Brief 解读依据",
        "可发挥空间",
        "不应擅自发挥",
        "关键未决项",
        "Brief Lock 人工确认记录",
    )
    require_fields(errors, fields, brief_fields)
    brief_version = fields.get("Brief Lock 版本", "")
    if brief_version and not re.fullmatch(r"BL-v\d+", brief_version):
        errors.append("Brief Lock 版本必须使用 BL-vN")

    brief_rows = table_rows(text, "B")
    if not brief_rows:
        errors.append("至少需要一条 Bxx Brief 要求")
    validate_rows(errors, brief_rows, "B", 6)
    brief_ids = {row[0] for row in brief_rows if row}

    if RANK[status] >= RANK["brief_locked"]:
        if fields.get("Brief Lock 确认状态") != "已确认":
            errors.append("进入 brief_locked 前必须确认 Brief Lock")
        if fields.get("Brief 要求确认状态") != "已确认":
            errors.append("进入 brief_locked 前必须人工确认 Brief 要求")
        if fields.get("Brief 解读确认状态") != "已确认":
            errors.append("进入 brief_locked 前必须人工确认 Brief 解读")
        if fields.get("关键未决项") != "无":
            errors.append("进入 brief_locked 前关键未决项必须为无")
        if fields.get("Brief Lock 人工确认记录") == "未确认":
            errors.append("进入 brief_locked 前必须记录人工确认")
        if brief_version and not decision_has_target(
            decision_rows, brief_version, brief_version
        ):
            errors.append(f"缺少属于 {brief_version} 且确认该版本的 Dxx 决策记录")
        for row in brief_rows:
            if len(row) == 6 and row[5] != "已确认":
                errors.append(f"{row[0]} 尚未确认")

    creative_fields = (
        "Creative Decision 版本",
        "创意方向确认状态",
        "方向数量偏离理由",
        "推荐方向",
        "推荐理由与代价",
        "选定方向",
        "组合或删改说明",
        "人工决定理由",
    )
    creative_rows = table_rows(text, "C")
    creative_ids = {row[0] for row in creative_rows if row}
    if creative_rows:
        dimensions = dimension_rows(text)
        missing_dimensions = [
            name for name in REQUIRED_DIMENSION_ROWS if name not in dimensions
        ]
        if missing_dimensions:
            errors.append(
                "缺少选题调研维度发散：" + "、".join(missing_dimensions)
            )
        for name, row in dimensions.items():
            if len(row) != 5:
                errors.append(f"{name} 发散行应有 5 列，实际为 {len(row)} 列")
            else:
                for index, cell in enumerate(row[1:], start=2):
                    if has_placeholder(cell):
                        errors.append(f"{name} 发散行第 {index} 列未填写")
        validate_rows(errors, creative_rows, "C", 10)
        if len(creative_rows) < 6 and fields.get("方向数量偏离理由") in ("", "无"):
            errors.append("少于六个完整创意方向时必须说明偏离理由")
        for row in creative_rows:
            if len(row) == 10:
                if not any(name in row[2] for name in DIVERGENCE_DIMENSIONS):
                    errors.append(f"{row[0]} 没有写明重点选题维度")
                mapped = referenced_ids(row[8], "B")
                if not mapped:
                    errors.append(f"{row[0]} 没有 Brief 映射")
                elif not mapped.issubset(brief_ids):
                    errors.append(f"{row[0]} 引用了不存在的 Brief ID")

    if RANK[status] >= RANK["creative_draft"]:
        require_fields(errors, fields, creative_fields)
        creative_version = fields.get("Creative Decision 版本", "")
        if creative_version and not re.fullmatch(r"CD-v\d+", creative_version):
            errors.append("Creative Decision 版本必须使用 CD-vN")
        if len(creative_rows) < 4:
            errors.append("正式创意比较不得少于四个方向")
        if fields.get("推荐方向") not in creative_ids:
            errors.append("推荐方向必须引用现有 Cxx")

    if RANK[status] >= RANK["creative_selected"]:
        if fields.get("创意方向确认状态") != "已确认":
            errors.append("进入 creative_selected 前必须确认创意方向")
        if fields.get("选定方向") not in creative_ids:
            errors.append("选定方向必须引用现有 Cxx")
        if fields.get("人工决定理由") == "未确认":
            errors.append("进入 creative_selected 前必须记录人工决定理由")
        selected = fields.get("选定方向", "")
        creative_version = fields.get("Creative Decision 版本", "")
        if selected and not decision_has_target(
            decision_rows, selected, creative_version
        ):
            errors.append(
                f"缺少在 {creative_version} 选择 {selected} 的 Dxx 决策记录"
            )

    outline_fields = (
        "Outline Lock 版本",
        "Outline Lock 确认状态",
        "大纲对应创意",
        "大纲一句话结构",
        "Outline Lock 人工确认记录",
    )
    if RANK[status] >= RANK["outline_draft"]:
        require_fields(errors, fields, outline_fields)
        outline_version = fields.get("Outline Lock 版本", "")
        if outline_version and not re.fullmatch(r"OL-v\d+", outline_version):
            errors.append("Outline Lock 版本必须使用 OL-vN")
        if fields.get("大纲对应创意") not in creative_ids:
            errors.append("大纲对应创意必须引用现有 Cxx")
        outline_rows = table_rows(text, "O")
        if len(outline_rows) < 2:
            errors.append("正式大纲至少需要两个结构段落")
        validate_rows(errors, outline_rows, "O", 8)
        for row in outline_rows:
            if len(row) == 8:
                mapped = referenced_ids(row[6], "B")
                if not mapped:
                    errors.append(f"{row[0]} 没有 Brief 映射")
                elif not mapped.issubset(brief_ids):
                    errors.append(f"{row[0]} 引用了不存在的 Brief ID")

    if RANK[status] >= RANK["outline_locked"]:
        if fields.get("Outline Lock 确认状态") != "已确认":
            errors.append("进入 outline_locked 前必须确认 Outline Lock")
        if fields.get("Outline Lock 人工确认记录") == "未确认":
            errors.append("进入 outline_locked 前必须记录人工确认")
        outline_version = fields.get("Outline Lock 版本", "")
        if outline_version and not decision_has_target(
            decision_rows, outline_version, outline_version
        ):
            errors.append(
                f"缺少属于 {outline_version} 且确认该版本的 Dxx 决策记录"
            )

    if status == "ready_for_director":
        handoff_fields = (
            "交接状态",
            "目标 Skill",
            "已确认 Brief Lock",
            "已确认 Creative Decision",
            "已确认 Outline Lock",
            "目标平台",
            "预计时长",
            "内容类型",
            "必须保留的事实或原话",
            "不可夸大的内容与合规禁区",
            "品牌露出边界",
            "必须使用的证据或素材及来源状态",
            "下游未决项",
            "上游变更规则",
        )
        require_fields(errors, fields, handoff_fields)
        if fields.get("交接状态") != "就绪":
            errors.append("ready_for_director 状态下交接状态必须为就绪")
        if fields.get("目标 Skill") != "direct-digital-human-script":
            errors.append("目标 Skill 必须为 direct-digital-human-script")
        if fields.get("已确认 Brief Lock") != fields.get("Brief Lock 版本"):
            errors.append("交接包引用的 Brief Lock 不是当前确认版本")
        if fields.get("已确认 Creative Decision") != fields.get(
            "Creative Decision 版本"
        ):
            errors.append("交接包引用的 Creative Decision 不是当前确认版本")
        if fields.get("已确认 Outline Lock") != fields.get("Outline Lock 版本"):
            errors.append("交接包引用的 Outline Lock 不是当前确认版本")
        if fields.get("下游未决项") != "无":
            errors.append("交接前下游未决项必须为无")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dossier", type=Path, help="Markdown 项目档案路径")
    parser.add_argument("--expect-status", choices=STATUSES)
    args = parser.parse_args()

    if not args.dossier.is_file():
        print(f"ERROR: 文件不存在：{args.dossier}", file=sys.stderr)
        return 2

    try:
        errors = validate(args.dossier, args.expect_status)
    except UnicodeDecodeError:
        print("ERROR: 项目档案必须是 UTF-8 Markdown", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"FAILED: {len(errors)} 个问题")
        return 1

    fields = parse_fields(args.dossier.read_text(encoding="utf-8"))
    print(f"OK: {args.dossier.name} ({fields['项目状态']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
