"""Deterministic geometry QA for existing scene compositions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from src.services.scene_composition import SAFE_MARGIN_RATIO


_SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "INFO": 3}


@dataclass(frozen=True)
class VisualQACheck:
    """One report-only composition check result."""

    id: str
    severity: str
    ok: bool
    message: str
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VisualQAReport:
    """Serializable aggregate of deterministic visual composition checks."""

    scene: str
    checks: list[VisualQACheck] = field(default_factory=list)
    passed: bool = True

    def __post_init__(self) -> None:
        self.checks.sort(key=lambda check: (_SEVERITY_ORDER.get(check.severity, 99), check.id))
        self.passed = all(check.ok or check.skipped for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene": self.scene,
            "checks": [check.to_dict() for check in self.checks],
            "passed": self.passed,
        }


class VisualQAService:
    """Observe composition geometry and report objective QA findings only."""

    def check_composition(
        self,
        composition: Any | None = None,
        *,
        scene: str = "scene",
        geometry: dict[str, Any] | None = None,
        protected_rects: Iterable[Any] | None = None,
        required_title: bool = False,
        min_object_size: float | None = None,
    ) -> VisualQAReport:
        elements = self._elements(composition)
        bounds = self._bounds(elements, geometry)
        checks = [
            self._safe_area(bounds),
            self._clipping(bounds),
            self._title_content_collision(elements, bounds, protected_rects),
            self._element_overlap(bounds),
            self._missing_title(elements, required_title),
            self._tiny_object(elements, bounds, min_object_size),
            self._skipped("excessive_empty_space", "Insufficient composition bounds to measure empty space"),
            self._invalid_geometry(bounds),
            self._skipped("off_screen_motion", "Motion is not simulated by report-only geometry QA"),
            self._skipped("scale_consistency", "No objective cross-element scale rule is defined"),
        ]
        return VisualQAReport(scene=str(scene), checks=checks)

    @staticmethod
    def _elements(composition: Any | None) -> list[tuple[str, str, Any]]:
        if composition is None:
            return []
        if isinstance(composition, dict):
            get = composition.get
        else:
            get = lambda key, default=None: getattr(composition, key, default)
        result: list[tuple[str, str, Any]] = []
        for key, kind, name_key in (
            ("characters", "character", "name"),
            ("objects", "object", "name"),
            ("text_elements", "text", "text"),
        ):
            for index, value in enumerate(get(key, []) or []):
                name = str(VisualQAService._field(value, name_key, "") or f"{kind}_{index}")
                result.append((name, kind, value))
        return result

    @staticmethod
    def _field(value: Any, key: str, default: Any = None) -> Any:
        return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)

    @classmethod
    def _bounds(cls, elements: list[tuple[str, str, Any]], geometry: dict[str, Any] | None) -> dict[str, tuple[float, float, float, float] | None]:
        result: dict[str, tuple[float, float, float, float] | None] = {}
        geometry = geometry or {}
        for name, kind, value in elements:
            raw = geometry.get(name, cls._field(value, "bounds"))
            if raw is None:
                x = cls._field(value, "x")
                y = cls._field(value, "y")
                if x is not None and y is not None:
                    raw = (float(x), float(y), float(x), float(y))
            result[name] = cls._rect(raw)
        for name, raw in geometry.items():
            if name not in result:
                result[name] = cls._rect(raw)
        return result

    @staticmethod
    def _rect(raw: Any) -> tuple[float, float, float, float] | None:
        if isinstance(raw, dict):
            if all(key in raw for key in ("x", "y", "width", "height")):
                return (float(raw["x"]), float(raw["y"]), float(raw["x"]) + float(raw["width"]), float(raw["y"]) + float(raw["height"]))
            if all(key in raw for key in ("left", "top", "right", "bottom")):
                return tuple(float(raw[key]) for key in ("left", "top", "right", "bottom"))  # type: ignore[return-value]
        if isinstance(raw, (list, tuple)) and len(raw) == 4:
            return tuple(float(value) for value in raw)  # type: ignore[return-value]
        return None

    @staticmethod
    def _safe_area(bounds: dict[str, tuple[float, float, float, float] | None]) -> VisualQACheck:
        margin = SAFE_MARGIN_RATIO
        violations = [name for name, rect in bounds.items() if rect and (rect[0] < margin or rect[1] < margin or rect[2] > 1 - margin or rect[3] > 1 - margin)]
        if violations:
            return VisualQACheck("safe_area", "P1", False, f"Elements outside safe margin: {', '.join(violations)}")
        if not bounds or not any(rect is not None for rect in bounds.values()):
            return VisualQAService._skipped("safe_area", "No element geometry supplied")
        return VisualQACheck("safe_area", "P1", True, "All known bounds respect the safe margin")

    @staticmethod
    def _clipping(bounds: dict[str, tuple[float, float, float, float] | None]) -> VisualQACheck:
        clipped = [name for name, rect in bounds.items() if rect and (rect[0] < 0 or rect[1] < 0 or rect[2] > 1 or rect[3] > 1)]
        if clipped:
            return VisualQACheck("clipping", "P0", False, f"Bounds extend beyond frame: {', '.join(clipped)}")
        if not any(rect is not None for rect in bounds.values()):
            return VisualQAService._skipped("clipping", "No element bounds supplied")
        return VisualQACheck("clipping", "P0", True, "Known bounds are inside the frame")

    @classmethod
    def _title_content_collision(cls, elements: list[tuple[str, str, Any]], bounds: dict[str, tuple[float, float, float, float] | None], protected_rects: Iterable[Any] | None) -> VisualQACheck:
        titles = {name for name, kind, value in elements if kind == "text" and cls._is_title(value)}
        title_rects = [bounds[name] for name in titles if bounds.get(name)]
        content_rects = [cls._rect(rect) for rect in (protected_rects or [])]
        content_rects += [rect for name, rect in bounds.items() if name not in titles and rect]
        if not title_rects:
            return cls._skipped("title_content_collision", "No title/header bounds supplied")
        collisions = any(cls._intersects(title, content) for title in title_rects for content in content_rects if content)
        if collisions:
            return VisualQACheck("title_content_collision", "P1", False, "Title/header intersects protected content")
        return VisualQACheck("title_content_collision", "P1", True, "Title/header does not intersect content")

    @staticmethod
    def _is_title(value: Any) -> bool:
        role = str(VisualQAService._field(value, "role", "")).lower()
        return bool(VisualQAService._field(value, "is_title", False)) or role in {"title", "header"} or VisualQAService._field(value, "size", "") == "headline"

    @staticmethod
    def _element_overlap(bounds: dict[str, tuple[float, float, float, float] | None]) -> VisualQACheck:
        named = [(name, rect) for name, rect in bounds.items() if rect]
        overlaps = [f"{left}/{right}" for index, (left, first) in enumerate(named) for right, second in named[index + 1:] if VisualQAService._intersects(first, second)]
        if overlaps:
            return VisualQACheck("element_overlap", "P1", False, f"Overlapping elements: {', '.join(overlaps)}")
        if len(named) < 2:
            return VisualQAService._skipped("element_overlap", "At least two element bounds are required")
        return VisualQACheck("element_overlap", "P1", True, "Known element bounds do not overlap")

    @staticmethod
    def _missing_title(elements: list[tuple[str, str, Any]], required: bool) -> VisualQACheck:
        if not required:
            return VisualQAService._skipped("missing_title", "Title is not required for this scene")
        has_title = any(kind == "text" and VisualQAService._is_title(value) and str(VisualQAService._field(value, "text", "")).strip() for _, kind, value in elements)
        if not has_title:
            return VisualQACheck("missing_title", "P1", False, "Required title/header is missing or empty")
        return VisualQACheck("missing_title", "P1", True, "Required title/header is present")

    @staticmethod
    def _tiny_object(elements: list[tuple[str, str, Any]], bounds: dict[str, tuple[float, float, float, float] | None], minimum: float | None) -> VisualQACheck:
        if minimum is None:
            return VisualQAService._skipped("tiny_object", "No objective minimum object size was supplied")
        tiny = [name for name, kind, value in elements if kind == "object" and bounds.get(name) and min(bounds[name][2] - bounds[name][0], bounds[name][3] - bounds[name][1]) < minimum]
        if tiny:
            return VisualQACheck("tiny_object", "P2", False, f"Objects below minimum size: {', '.join(tiny)}")
        return VisualQACheck("tiny_object", "P2", True, "Known objects meet the minimum size")

    @staticmethod
    def _invalid_geometry(bounds: dict[str, tuple[float, float, float, float] | None]) -> VisualQACheck:
        invalid = [name for name, rect in bounds.items() if rect and (rect[2] < rect[0] or rect[3] < rect[1])]
        if invalid:
            return VisualQACheck("invalid_geometry", "P0", False, f"Invalid bounds: {', '.join(invalid)}")
        return VisualQACheck("invalid_geometry", "P0", True, "Known geometry is structurally valid")

    @staticmethod
    def _intersects(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> bool:
        return first[0] < second[2] and first[2] > second[0] and first[1] < second[3] and first[3] > second[1]

    @staticmethod
    def _skipped(check_id: str, message: str) -> VisualQACheck:
        return VisualQACheck(check_id, "INFO", True, f"Skipped: {message}", skipped=True)
