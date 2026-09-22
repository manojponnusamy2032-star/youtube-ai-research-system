"""Day-3 Script QC tests."""
from __future__ import annotations

import pytest
from src.orchestration.qc.script_qc import run_script_qc
from src.orchestration.qc.models import QCStatus, QCSeverity
from src.orchestration.schemas.script import ScriptPackage, ScriptSection


def _valid_script() -> ScriptPackage:
    sections = [
        ScriptSection(
            heading=f"Section {i}",
            narration=f"Narration text for section {i} with enough words.",
            duration_seconds=10,
        )
        for i in range(1, 4)
    ]
    return ScriptPackage(
        topic="Test Topic",
        title="Test Title",
        hook="Test hook narration.",
        sections=sections,
        call_to_action="Subscribe.",
        total_duration_seconds=30,
    )


class TestScriptQCValid:
    def test_valid_script_passes(self):
        script = _valid_script()
        checks = run_script_qc(script)
        assert len(checks) == 4
        for check in checks:
            assert check.status == QCStatus.PASS, f"{check.check_name}: {check.message}"

    def test_valid_cta(self):
        script = _valid_script()
        checks = run_script_qc(script)
        integrity_check = next(c for c in checks if c.check_name == "script_content_integrity")
        assert integrity_check.status == QCStatus.PASS


class TestScriptQCMissingFields:
    def test_missing_title(self):
        script = _valid_script()
        script.title = ""
        checks = run_script_qc(script)
        required = next(c for c in checks if c.check_name == "script_required_fields")
        assert required.status == QCStatus.FAIL
        assert "missing title" in required.message

    def test_missing_hook(self):
        script = _valid_script()
        script.hook = ""
        checks = run_script_qc(script)
        required = next(c for c in checks if c.check_name == "script_required_fields")
        assert required.status == QCStatus.FAIL
        assert "missing hook" in required.message

    def test_missing_sections(self):
        script = _valid_script()
        script.sections = []
        checks = run_script_qc(script)
        required = next(c for c in checks if c.check_name == "script_required_fields")
        assert required.status == QCStatus.FAIL
        assert "missing sections" in required.message

    def test_none_script(self):
        checks = run_script_qc(None)
        assert len(checks) == 1
        assert checks[0].status == QCStatus.FAIL
        assert checks[0].severity == QCSeverity.FAIL


class TestScriptQCDuration:
    def test_invalid_duration_negative(self):
        script = _valid_script()
        script.total_duration_seconds = -5
        checks = run_script_qc(script)
        duration = next(c for c in checks if c.check_name == "script_duration")
        assert duration.status == QCStatus.FAIL

    def test_duration_mismatch_major(self):
        script = _valid_script()
        script.total_duration_seconds = 100  # sections sum to 30
        checks = run_script_qc(script)
        duration = next(c for c in checks if c.check_name == "script_duration")
        assert duration.status == QCStatus.FAIL
        assert "Major" in duration.message

    def test_duration_mismatch_minor(self):
        script = _valid_script()
        script.total_duration_seconds = 32  # sections sum to 30
        checks = run_script_qc(script)
        duration = next(c for c in checks if c.check_name == "script_duration")
        assert duration.status == QCStatus.WARN


class TestScriptQCContentIntegrity:
    def test_empty_sections(self):
        script = _valid_script()
        script.sections = []
        checks = run_script_qc(script)
        integrity = next(c for c in checks if c.check_name == "script_section_integrity")
        assert integrity.status == QCStatus.FAIL

    def test_empty_narration(self):
        script = _valid_script()
        script.sections[0].narration = ""
        checks = run_script_qc(script)
        integrity = next(c for c in checks if c.check_name == "script_section_integrity")
        assert integrity.status == QCStatus.FAIL

    def test_repeated_narration(self):
        script = _valid_script()
        for s in script.sections:
            s.narration = "identical text"
        checks = run_script_qc(script)
        content = next(c for c in checks if c.check_name == "script_content_integrity")
        assert content.status == QCStatus.FAIL
        assert "identical" in content.message

    def test_placeholder_text_todo(self):
        script = _valid_script()
        script.hook = "TODO: write hook"
        checks = run_script_qc(script)
        content = next(c for c in checks if c.check_name == "script_content_integrity")
        assert content.status == QCStatus.FAIL
        assert "placeholder" in content.message

    def test_placeholder_text_lorem(self):
        script = _valid_script()
        script.sections[0].narration = "Lorem ipsum dolor sit amet."
        checks = run_script_qc(script)
        content = next(c for c in checks if c.check_name == "script_content_integrity")
        assert content.status == QCStatus.FAIL

    def test_empty_script(self):
        script = ScriptPackage(
            topic="Test",
            title="Title",
            hook="",
            sections=[],
            call_to_action="",
            total_duration_seconds=0,
        )
        checks = run_script_qc(script)
        content = next(c for c in checks if c.check_name == "script_content_integrity")
        assert content.status == QCStatus.FAIL
        assert "empty" in content.message.lower()
