"""Visual Focus Resolver (V1.3-B).

Converts a :class:`VisualBeat` (V1.3-A) plus available scene composition
information into a deterministic attention hierarchy:

    What should the viewer notice first, second, and what recedes?

This is *derived/staging metadata only* -- it says WHAT deserves attention,
never HOW to animate it (that is V1.3-C / later staging).  It does not mutate
any element, lower emphasis into Motion/EffectSpec, or touch rendering.

Invariants:

- Never invents a scene element (unmatched subjects fall back to an existing
  element or empty).
- Never mutates VisualScene / SceneComposition / any spec.
- No LLM, network, FFmpeg, StickmanRenderer, randomness.
- Repeated identical inputs produce identical outputs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class VisualFocus:
    """Deterministic attention hierarchy for a single scene.

    References (``primary``/``secondary``/``supporting``/``background``/
    ``emphasis_target``/``deemphasis_targets``) name *existing* scene elements:
    a character/object ``name`` or a text element's ``text`` content.  Empty
    strings/lists mean no such role was deterministically assignable.

    ``emphasis`` is a low/medium/high label carried over from the beat.
    ``timing`` is intentionally left empty unless reliably derivable.
    """

    primary: str = ""
    secondary: str = ""
    supporting: list[str] = field(default_factory=list)
    background: list[str] = field(default_factory=list)
    emphasis_target: str = ""
    deemphasis_targets: list[str] = field(default_factory=list)
    emphasis: str = "medium"
    timing: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


class VisualFocusResolver:
    """Deterministic VisualBeat + composition -> VisualFocus resolution.

    Priority order:
      1. Explicit existing ``primary_focus`` / camera ``focus_target``
      2. Beat subject matched to a real scene element
      3. Beat-aware rules (e.g. CTA prefers text)
      4. First meaningful scene element
      5. Empty fallback
    """

    # -- Public API ---------------------------------------------------------

    def resolve(
        self,
        beat: Any,
        *,
        characters: list[Any] | None = None,
        objects: list[Any] | None = None,
        text_elements: list[Any] | None = None,
        primary_focus: str = "",
        focus_target: str | None = None,
    ) -> VisualFocus:
        """Resolve a focus hierarchy from a beat and available scene elements.

        ``beat`` is a V1.3-A ``VisualBeat`` (or any object with ``type`` and
        ``subject`` attributes).  ``characters``/``objects``/``text_elements``
        accept SceneComposition specs or plain dicts.  Nothing is mutated.
        """
        beat_type = self._beat_type(beat)
        subject = self._subject(beat)
        emphasis = self._emphasis(beat)

        candidates = self._collect_candidates(characters, objects, text_elements)
        if not candidates:
            return VisualFocus(emphasis=emphasis)

        ordered = self._ordered(candidates, beat_type, subject, primary_focus, focus_target)
        if not ordered:
            return VisualFocus(emphasis=emphasis)

        primary = ordered[0]
        secondary = ordered[1] if len(ordered) > 1 else ""
        supporting = ordered[2:4]
        background = ordered[4:]

        return VisualFocus(
            primary=primary,
            secondary=secondary,
            supporting=_unique(supporting),
            background=_unique(background),
            emphasis_target=primary,
            deemphasis_targets=_unique(supporting + background),
            emphasis=emphasis,
            timing={},
        )

    # -- Candidate collection ----------------------------------------------

    @staticmethod
    def _collect_candidates(
        characters: list[Any] | None,
        objects: list[Any] | None,
        text_elements: list[Any] | None,
    ) -> list[dict[str, Any]]:
        """Normalize available elements into reference candidates (no mutation)."""
        candidates: list[dict[str, Any]] = []

        def _add(spec: Any, field_name: str, kind: str, name: str) -> None:
            matcher = " ".join(
                str(_get_field(spec, f) or "") for f in (field_name, "type", "text")
            ).lower()
            candidates.append({"kind": kind, "name": name, "matcher": matcher})

        for ch in (characters or []):
            name = _get_field(ch, "name")
            if name:
                _add(ch, "name", "character", name)
        for ob in (objects or []):
            name = _get_field(ob, "name")
            if name:
                _add(ob, "name", "object", name)
        for tx in (text_elements or []):
            text = _get_field(tx, "text")
            if text:
                matcher = f"{text} {_get_field(tx, 'size') or ''}".lower()
                candidates.append({"kind": "text", "name": text, "matcher": matcher})
        return candidates


    # -- Ordering (priority 1..4) -------------------------------------------

    def _ordered(
        self,
        candidates: list[dict[str, Any]],
        beat_type: str,
        subject: str,
        primary_focus: str,
        focus_target: str | None,
    ) -> list[str]:
        ordered: list[str] = []
        used: set[str] = set()

        def _add(ref: str) -> None:
            if ref and ref not in used:
                ordered.append(ref)
                used.add(ref)

        # 1. Explicit primary_focus / focus_target -- only if it names a real
        #    element (never invent).  Generic role words are ignored.
        explicit = self._first_matching(candidates, primary_focus) or \
            self._first_matching(candidates, focus_target or "")
        _add(explicit)

        # 2. Beat subject match(es).  CONTRAST splits "A vs B" into two.
        if beat_type == "CONTRAST":
            sides = self._contrast_sides(subject)
            for side in sides:
                _add(self._first_matching(candidates, side))
        else:
            _add(self._first_matching(candidates, subject))

        # 3. Beat-aware rule: CTA prefers a text element.
        if beat_type == "CTA":
            for cand in candidates:
                if cand["kind"] == "text":
                    _add(cand["name"])

        # 4. First meaningful element (input order) to fill the hierarchy.
        for cand in candidates:
            _add(cand["name"])

        return ordered

    # -- Matching helpers ---------------------------------------------------

    @staticmethod
    def _first_matching(candidates: list[dict[str, Any]], query: str) -> str:
        query = _normalize(query)
        if not query:
            return ""
        for cand in candidates:
            if _matches(cand["matcher"], query):
                return cand["name"]
        return ""

    @staticmethod
    def _contrast_sides(subject: str) -> list[str]:
        lowered = subject.lower()
        for sep in ("vs", "versus"):
            if sep in lowered:
                parts = [p.strip() for p in lowered.split(sep, 1)]
                return [p for p in parts if p]
        return [subject]

    # -- Beat introspection -------------------------------------------------

    @staticmethod
    def _beat_type(beat: Any) -> str:
        return str(getattr(beat, "type", "")).strip().upper()

    @staticmethod
    def _subject(beat: Any) -> str:
        return str(getattr(beat, "subject", "") or "")

    @staticmethod
    def _emphasis(beat: Any) -> str:
        emph = str(getattr(beat, "emphasis", "") or "").strip().lower()
        return emph if emph in {"low", "medium", "high"} else "medium"


def _get_field(spec: Any, name: str) -> Any:
    """Read a field from a spec dataclass or a plain dict, case-insensitively."""
    if spec is None:
        return None
    if isinstance(spec, dict):
        if name in spec:
            return spec.get(name)
        for key, value in spec.items():
            if str(key).lower() == name.lower():
                return value
        return None
    return getattr(spec, name, None)


def _normalize(value: str) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum() or ch.isspace()).strip()


def _matches(haystack: str, query: str) -> bool:
    h = _normalize(haystack)
    q = _normalize(query)
    if not q:
        return False
    return q in h or h in q


def _unique(items: list[str]) -> list[str]:
    """Return deduplicated, non-empty strings preserving order."""
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out

