"""Script QC validator.

Validates a ``ScriptPackage`` for structural and content integrity.
Detects obvious generation failures without attempting semantic scoring.
"""

from __future__ import annotations

import re
from typing import Any

from src.orchestration.qc.models import QCCheck, QCStatus, QCSeverity


# Placeholder / failure markers that indicate a broken generation.
_PLACEHOLDER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\bTBD\b", re.IGNORECASE),
    re.compile(r"\bLorem\s+ipsum\b", re.IGNORECASE),
    re.compile(r"\bPLACEHOLDER\b", re.IGNORECASE),
    re.compile(r"\bINSERT\s+(?:TEXT|CONTENT|SCRIPT|HERE)\b", re.IGNORECASE),
    re.compile(r"\[(?:INSERT|TODO|TBD)\s", re.IGNORECASE),
]


def _placeholder_text(text: str) -> str | None:
    """Return the first placeholder marker found in ``text``, else None."""
    for pattern in _PLACEHOLDER_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None
def _check_required_fields(script: Any) -> QCCheck:
    """Validate that all required fields exist."""
    problems: list[str] = []

    topic = getattr(script, "topic", None)
    title = getattr(script, "title", None)
    hook = getattr(script, "hook", None)
    sections = getattr(script, "sections", None)

    if not topic or not str(topic).strip():
        problems.append("missing topic")
    if not title or not str(title).strip():
        problems.append("missing title")
    if not hook or not str(hook).strip():
        problems.append("missing hook")
    if not sections:
        problems.append("missing sections")

    if problems:
        return QCCheck(
            check_name="script_required_fields",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"Required field(s) missing: {', '.join(problems)}",
            details={"missing": problems},
        )

    return QCCheck(
        check_name="script_required_fields",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message="All required fields present",
    )


def _check_duration(script: Any) -> QCCheck:
    """Validate total_duration_seconds against sum of section durations."""
    sections: list[Any] = getattr(script, "sections", None) or []
    declared = getattr(script, "total_duration_seconds", 0) or 0

    if not sections:
        return QCCheck(
            check_name="script_duration",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No sections; duration cannot be validated",
        )

    if declared is not None and declared < 0:
        return QCCheck(
            check_name="script_duration",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"Negative total_duration_seconds: {declared}",
            details={"declared": declared},
        )

    section_sum = sum(
        getattr(s, "duration_seconds", 0) or 0 for s in sections
    )

    if declared is not None and declared > 0 and section_sum > 0:
        mismatch = abs(declared - section_sum)
        if mismatch > max(5, declared * 0.25):
            return QCCheck(
                check_name="script_duration",
                status=QCStatus.FAIL,
                severity=QCSeverity.FAIL,
                message=(
                    f"Major duration mismatch: declared={declared}s, "
                    f"section_sum={section_sum}s (delta={mismatch}s)"
                ),
                details={"declared": declared, "section_sum": section_sum, "delta": mismatch},
            )
        if mismatch > 0:
            return QCCheck(
                check_name="script_duration",
                status=QCStatus.WARN,
                severity=QCSeverity.WARN,
                message=(
                    f"Minor duration mismatch: declared={declared}s, "
                    f"section_sum={section_sum}s (delta={mismatch}s)"
                ),
                details={"declared": declared, "section_sum": section_sum, "delta": mismatch},
            )

    return QCCheck(
        check_name="script_duration",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"Duration consistent: {section_sum}s",
        details={"declared": declared, "section_sum": section_sum},
    )

def _check_section_integrity(script: Any) -> QCCheck:
    """Validate section count and per-section content."""
    sections: list[Any] = getattr(script, "sections", None) or []

    if not sections:
        return QCCheck(
            check_name="script_section_integrity",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No sections in script",
        )

    problems: list[str] = []
    empty_narration = 0
    empty_heading = 0

    for idx, section in enumerate(sections):
        heading = getattr(section, "heading", None)
        narration = getattr(section, "narration", None)
        duration = getattr(section, "duration_seconds", 0)

        if not heading or not str(heading).strip():
            empty_heading += 1
        if not narration or not str(narration).strip():
            empty_narration += 1
        if duration is not None and duration <= 0:
            problems.append(f"section {idx + 1}: non-positive duration ({duration}s)")

    if empty_narration:
        problems.append(f"{empty_narration} section(s) with empty narration")
    if empty_heading:
        problems.append(f"{empty_heading} section(s) with empty heading")
    if len(sections) < 2:
        problems.append(f"only {len(sections)} section(s); expected at least 2")

    if problems:
        return QCCheck(
            check_name="script_section_integrity",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"Section integrity issues: {'; '.join(problems)}",
            details={"problems": problems, "section_count": len(sections)},
        )

    return QCCheck(
        check_name="script_section_integrity",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"All {len(sections)} sections structurally valid",
        details={"section_count": len(sections)},
    )


def _check_content_integrity(script: Any) -> QCCheck:
    """Detect placeholder text, repeated narration, and empty script."""
    problems: list[str] = []

    hook = str(getattr(script, "hook", "") or "").strip()
    cta = str(getattr(script, "call_to_action", "") or "").strip()
    sections: list[Any] = getattr(script, "sections", None) or []
    all_narration = " ".join(
        str(getattr(s, "narration", "") or "").strip() for s in sections
    ).strip()

    if not hook and not all_narration and not cta:
        return QCCheck(
            check_name="script_content_integrity",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="Script is empty (no hook, narration, or CTA)",
        )

    full_text = f"{hook}\n{all_narration}\n{cta}"
    marker = _placeholder_text(full_text)
    if marker:
        problems.append(f"placeholder text detected: {marker!r}")

    narrations = [
        str(getattr(s, "narration", "") or "").strip() for s in sections
    ]
    narrations = [n for n in narrations if n]
    if narrations and len(set(narrations)) == 1 and len(narrations) > 1:
        problems.append("all sections have identical narration")
    elif narrations and len(set(narrations)) < len(narrations):
        duplicates = len(narrations) - len(set(narrations))
        problems.append(f"{duplicates} duplicate narration(s) across sections")

    if problems:
        return QCCheck(
            check_name="script_content_integrity",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"Content issues: {'; '.join(problems)}",
            details={"problems": problems},
        )

    return QCCheck(
        check_name="script_content_integrity",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message="No placeholder text or repeated narration detected",
    )


def run_script_qc(script: Any) -> list[QCCheck]:
    """Run all script QC checks.

    Args:
        script: A ``ScriptPackage`` (or None).

    Returns:
        A list of ``QCCheck`` results.  When ``script`` is None every check
        returns FAIL with a clear message.
    """
    if script is None:
        return [
            QCCheck(
                check_name="script_present",
                status=QCStatus.FAIL,
                severity=QCSeverity.FAIL,
                message="ScriptPackage is missing (None)",
            )
        ]

    return [
        _check_required_fields(script),
        _check_duration(script),
        _check_section_integrity(script),
        _check_content_integrity(script),
    ]

