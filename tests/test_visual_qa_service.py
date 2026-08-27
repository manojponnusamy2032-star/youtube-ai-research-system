from __future__ import annotations

import ast
import copy
from pathlib import Path

from src.services.scene_composition import SAFE_MARGIN_RATIO, CharacterSpec, ObjectSpec, SceneComposition, TextSpec
from src.services.visual_qa import VisualQAService


service = VisualQAService()


def test_clean_composition_passes() -> None:
    report = service.check_composition(SceneComposition(
        characters=[CharacterSpec(name="hero", x=0.25, y=0.7)],
        objects=[ObjectSpec(name="desk", x=0.75, y=0.7)],
        text_elements=[TextSpec(text="Title", size="headline", x=0.5, y=0.15)],
    ), required_title=True)
    assert report.passed is True


def test_safe_margin_violation() -> None:
    report = service.check_composition({"objects": [{"name": "edge", "x": 0.01, "y": 0.5}]})
    check = next(item for item in report.checks if item.id == "safe_area")
    assert check.ok is False and check.severity == "P1"


def test_clipping() -> None:
    report = service.check_composition({}, geometry={"box": {"x": 0.9, "y": 0.2, "width": 0.2, "height": 0.2}})
    check = next(item for item in report.checks if item.id == "clipping")
    assert check.ok is False and check.severity == "P0"


def test_title_content_collision() -> None:
    composition = {"text_elements": [{"text": "Title", "role": "title"}], "objects": [{"name": "content"}]}
    report = service.check_composition(composition, geometry={"Title": (0.2, 0.1, 0.8, 0.2), "content": (0.5, 0.15, 0.7, 0.5)})
    check = next(item for item in report.checks if item.id == "title_content_collision")
    assert check.ok is False


def test_character_object_overlap() -> None:
    composition = {"characters": [{"name": "hero"}], "objects": [{"name": "desk"}]}
    report = service.check_composition(composition, geometry={"hero": (0.4, 0.4, 0.6, 0.8), "desk": (0.5, 0.6, 0.8, 0.9)})
    check = next(item for item in report.checks if item.id == "element_overlap")
    assert check.ok is False


def test_missing_title() -> None:
    report = service.check_composition(SceneComposition(characters=[CharacterSpec(name="hero")]), required_title=True)
    check = next(item for item in report.checks if item.id == "missing_title")
    assert check.ok is False


def test_tiny_object_with_explicit_threshold() -> None:
    report = service.check_composition({"objects": [{"name": "dot"}]}, geometry={"dot": (0.4, 0.4, 0.42, 0.42)}, min_object_size=0.05)
    check = next(item for item in report.checks if item.id == "tiny_object")
    assert check.ok is False


def test_invalid_geometry() -> None:
    report = service.check_composition({}, geometry={"bad": (0.6, 0.2, 0.4, 0.8)})
    check = next(item for item in report.checks if item.id == "invalid_geometry")
    assert check.ok is False and check.severity == "P0"


def test_multiple_failures_are_aggregated() -> None:
    report = service.check_composition(
        {"text_elements": [{"text": "Title", "role": "title"}], "objects": [{"name": "bad"}]},
        geometry={"Title": (-0.1, 0.0, 0.7, 0.2), "bad": (0.5, 0.1, 1.2, 0.3)},
        required_title=True,
    )
    assert report.passed is False
    assert sum(not check.ok for check in report.checks) >= 2


def test_severity_ordering() -> None:
    report = service.check_composition({}, geometry={"bad": (-0.2, 0.2, 1.2, 0.4)})
    severities = [check.severity for check in report.checks]
    assert severities == sorted(severities, key={"P0": 0, "P1": 1, "P2": 2, "INFO": 3}.get)


def test_deterministic_output() -> None:
    composition = {"objects": [{"name": "desk", "x": 0.2, "y": 0.5}]}
    assert service.check_composition(composition).to_dict() == service.check_composition(composition).to_dict()


def test_serialization() -> None:
    payload = service.check_composition({}, scene="scene_1").to_dict()
    assert payload["scene"] == "scene_1"
    assert isinstance(payload["checks"], list)
    assert isinstance(payload["passed"], bool)


def test_no_input_mutation() -> None:
    composition = {"objects": [{"name": "desk", "x": 0.2, "y": 0.5}]}
    before = copy.deepcopy(composition)
    service.check_composition(composition)
    assert composition == before


def test_empty_geometry_skips_geometry_dependent_checks() -> None:
    report = service.check_composition()
    checks = {check.id: check for check in report.checks}
    assert checks["safe_area"].skipped is True
    assert checks["clipping"].skipped is True
    assert report.passed is True


def test_subjective_checks_are_skipped() -> None:
    checks = {check.id: check for check in service.check_composition().checks}
    for check_id in ("excessive_empty_space", "off_screen_motion", "scale_consistency"):
        assert checks[check_id].skipped is True and checks[check_id].ok is True


def test_report_aggregates_failures_and_skips() -> None:
    report = service.check_composition({}, geometry={"bad": (-0.2, 0.2, 0.1, 0.3)})
    assert report.passed is False
    assert any(check.skipped for check in report.checks)
    assert any(not check.ok for check in report.checks)


def test_existing_safe_margin_constant_is_reused() -> None:
    import src.services.visual_qa as visual_qa

    assert visual_qa.SAFE_MARGIN_RATIO == SAFE_MARGIN_RATIO


def test_scene_composition_objects_are_consumed() -> None:
    composition = SceneComposition(objects=[ObjectSpec(name="desk", x=0.2, y=0.5)])
    report = service.check_composition(composition)
    assert next(check for check in report.checks if check.id == "safe_area").ok is True


def test_bounds_can_be_supplied_on_existing_specs() -> None:
    composition = {"objects": [{"name": "desk", "bounds": (0.2, 0.2, 0.4, 0.4)}]}
    report = service.check_composition(composition)
    assert next(check for check in report.checks if check.id == "clipping").ok is True


def test_protected_rectangles_are_checked() -> None:
    composition = {"text_elements": [{"text": "Title", "size": "headline"}]}
    report = service.check_composition(composition, geometry={"Title": (0.3, 0.1, 0.7, 0.2)}, protected_rects=[(0.4, 0.15, 0.6, 0.4)])
    assert next(check for check in report.checks if check.id == "title_content_collision").ok is False


def test_no_forbidden_imports() -> None:
    path = Path(__file__).parents[1] / "src" / "services" / "visual_qa.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imported.intersection({"stickman_renderer", "video_assembler", "ffmpeg", "requests", "openai", "anthropic"})
    source = path.read_text(encoding="utf-8").lower()
    assert "render_stickman" not in source
