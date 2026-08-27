"""V1.2 visual stabilization regression tests.

Covers the audit findings: S6 boundary clipping (P0), S1 character/large-object
separation, S4 empty-board hosting, S8 title/content separation, and title
presence for S4/S5/S9 in the demo plan. Pure unit tests -- no FFmpeg.
"""

from __future__ import annotations

import json
import os

import pytest

from src.pipeline.auto_publish_pipeline import AutoPublishPipeline, VisualScene
from src.services.scene_composition import (
    SAFE_MARGIN_RATIO,
    CameraSpec,
    CharacterSpec,
    ObjectSpec,
    SceneComposition,
    resolve_text_placement,
)
from src.services.stickman_renderer import StickmanRenderer

W, H = 540, 960

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _renderer() -> StickmanRenderer:
    return StickmanRenderer(execute_enabled=False)


# ---------------------------------------------------------------------------
# S6 (P0): boundary clipping -- focus camera must keep bystanders in-frame
# ---------------------------------------------------------------------------


class TestFocusCameraSafeArea:
    def test_bystander_stays_inside_safe_region_at_max_zoom(self) -> None:
        """S6 regression: character at x=0.25 while the camera focuses an
        object at x=0.68 used to project the bystander off the left edge."""
        r = _renderer()
        st = r._evaluate_motion_state(
            [], 3.0, 3.0, W, H, "talk",
            composition=SceneComposition(
                characters=[
                    CharacterSpec(name="student", pose="talk", x=0.25, y=0.76),
                ],
                objects=[
                    ObjectSpec(name="screen", type="screen", x=0.68, y=0.42),
                ],
                camera=CameraSpec(pattern="focus_on_object", focus_target="screen"),
            ),
        )
        zoom = st["camera_zoom"]
        assert zoom > 1.2  # focus zoom is preserved, not flattened
        tx = (0.25 * W - W / 2) * zoom + W / 2 + st["camera_pan_x"]
        ty = (0.76 * H - H / 2) * zoom + H / 2 + st["camera_pan_y"]
        margin_x = SAFE_MARGIN_RATIO * W
        margin_y = SAFE_MARGIN_RATIO * H
        assert margin_x - 2 <= tx <= W - margin_x + 2
        assert margin_y - 2 <= ty <= H - margin_y + 2

    def test_focus_target_still_centered_with_bystander_present(self) -> None:
        r = _renderer()
        st = r._evaluate_motion_state(
            [], 3.0, 3.0, W, H, "talk",
            composition=SceneComposition(
                characters=[
                    CharacterSpec(name="student", pose="talk", x=0.25, y=0.76),
                ],
                objects=[
                    ObjectSpec(name="screen", type="screen", x=0.68, y=0.42),
                ],
                camera=CameraSpec(pattern="focus_on_object", focus_target="screen"),
            ),
        )
        zoom = st["camera_zoom"]
        tx = (0.68 * W - W / 2) * zoom + W / 2 + st["camera_pan_x"]
        # Bystander safety takes precedence over exact centering; the clamp
        # shifts the pan only as far as the safe-area constraint requires, so
        # the target must stay inside the central band (|dx| <= 20% width).
        assert abs(tx - W / 2) < W * 0.20

    def test_no_bystanders_keeps_exact_centered_pan(self) -> None:
        """Scenes without bystanders keep the untouched centered contract."""
        r = _renderer()
        st = r._evaluate_motion_state(
            [], 3.0, 3.0, W, H, "idle",
            composition=SceneComposition(
                objects=[
                    ObjectSpec(name="screen", type="screen", x=0.68, y=0.42),
                ],
                camera=CameraSpec(pattern="focus_on_object", focus_target="screen"),
            ),
        )
        zoom = st["camera_zoom"]
        expected_pan = (W / 2.0 - 0.68 * W) * zoom
        # Renderer int()-casts the pan, so allow sub-pixel rounding only.
        assert st["camera_pan_x"] == pytest.approx(expected_pan, abs=1.0)
        tx = (0.68 * W - W / 2) * zoom + W / 2 + st["camera_pan_x"]
        assert abs(tx - W / 2) < 2.0


# ---------------------------------------------------------------------------
# S1 / S5: large floor props claim footprints -- characters stand outside
# ---------------------------------------------------------------------------


def _staged(visual: VisualScene) -> dict:
    return AutoPublishPipeline._stage_structured_visual(visual, 3.0, None)


class TestLargeObjectFootprintStaging:
    def test_s1_character_pushed_out_of_desk_footprint(self) -> None:
        """S1 regression: the student stood inside the desk footprint,
        producing the overlapping 'speed-line' clutter audit finding."""
        visual = VisualScene(
            scene_role="hook",
            environment={"type": "study_desk", "ground_y": 0.78},
            characters=[
                {"name": "student", "pose": "surprised", "x": 0.42, "y": 0.76, "scale": 1.15},
            ],
            objects=[
                {"name": "desk", "type": "desk", "x": 0.45, "y": 0.88, "scale": 1.3},
                {"name": "books", "type": "stack_of_books", "x": 0.16, "y": 0.72},
                {"name": "clock", "type": "clock", "x": 0.84, "y": 0.16},
            ],
        )
        staged = _staged(visual)
        cx = float(staged["characters"][0]["x"])
        # Desk (scale 1.3 > 1.0, on the ground) claims half-width 0.16*1.3+0.02;
        # the staged center must sit a full clearance gap outside the footprint.
        half = 0.16 * 1.3 + 0.02
        gap = 0.09
        assert abs(cx - 0.45) - half >= gap - 1e-6
        assert 0.05 <= cx <= 0.95

    def test_s5_interaction_character_clears_desk_and_notebook(self) -> None:
        """S5 regression: the character stood inside the desk footprint next
        to the notebook, making the square/character relationship ambiguous."""
        visual = VisualScene(
            scene_role="object_interaction",
            environment={"type": "study_desk", "ground_y": 0.80},
            characters=[{"name": "student", "pose": "point", "x": 0.34, "y": 0.76}],
            objects=[
                {"name": "desk", "type": "desk", "x": 0.48, "y": 0.88, "scale": 1.2},
                {"name": "notebook", "type": "notebook", "x": 0.62, "y": 0.68, "scale": 1.3},
                {"name": "pen", "type": "pen", "x": 0.80, "y": 0.70},
            ],
        )
        staged = _staged(visual)
        cx = float(staged["characters"][0]["x"])
        for ox, half in ((0.48, 0.212), (0.62, 0.228)):
            assert not (ox - half - 0.09 <= cx <= ox + half + 0.09)
        # Interaction approach preserved: still on the desk side he started.
        assert cx < 0.48

    def test_small_objects_do_not_claim_footprints(self) -> None:
        """Objects at default scale (<= 1.0) never displace characters."""
        visual = VisualScene(
            characters=[{"name": "student", "pose": "idle", "x": 0.30, "y": 0.70}],
            objects=[{"name": "books", "type": "stack_of_books", "x": 0.30, "y": 0.72}],
        )
        staged = _staged(visual)
        assert float(staged["characters"][0]["x"]) == 0.30


# ---------------------------------------------------------------------------
# S8: title/content separation -- text placement avoids environment decor
# ---------------------------------------------------------------------------


class TestTitleContentSeparation:
    def test_placement_shifts_below_blocked_window_rect(self) -> None:
        """S8 regression: the 'ASK A QUESTION' banner used to overlap the
        bedroom window decor in the top-right of the frame."""
        win = (int(0.68 * W), int(0.06 * H), int(0.88 * W), int(0.21 * H))
        block_w, block_h = int(W * 0.55), int(H * 0.06)
        x0, y0 = resolve_text_placement(
            0.5, 0.13, block_w, block_h, W, H, blocked_rects=[win],
        )
        overlaps = (
            x0 < win[2] and x0 + block_w > win[0]
            and y0 < win[3] and y0 + block_h > win[1]
        )
        assert not overlaps
        margin_y = int(H * SAFE_MARGIN_RATIO)
        assert margin_y <= y0 <= H - margin_y - block_h

    def test_placement_unblocked_when_no_rects(self) -> None:
        block_w, block_h = int(W * 0.4), int(H * 0.05)
        x0, y0 = resolve_text_placement(0.5, 0.5, block_w, block_h, W, H)
        assert x0 == int(W / 2 - block_w / 2)
        assert y0 == int(H / 2 - block_h / 2)

    def test_environment_layers_register_blocked_rects(self) -> None:
        """Bedroom windows are registered as blocked rects for the text pass."""
        r = _renderer()
        frame = bytearray(W * H * 3)
        state: dict = {"text_specs": []}
        r._draw_environment_layers(
            frame, W, H, lambda v: v, lambda v: v,
            {"type": "bedroom", "background_color": (205, 215, 230)},
            (255, 225, 150), motion_state=state,
        )
        rects = state.get("blocked_rects") or []
        assert len(rects) == 1
        wx0, wy0, wx1, wy1 = rects[0]
        assert wx0 == int(0.68 * W)
        assert wx1 == int(0.68 * W) + int(0.20 * W)
        assert wy0 == int(0.06 * H)
        assert wy1 == int(0.06 * H) + int(0.15 * H)

    def test_s8_headline_geometry_misses_window(self) -> None:
        """Guard with the real S8 banner/window geometry at headline size."""
        r = _renderer()
        frame = bytearray(W * H * 3)
        state: dict = {"text_specs": []}
        r._draw_environment_layers(
            frame, W, H, lambda v: v, lambda v: v,
            {"type": "bedroom", "background_color": (205, 215, 230)},
            (255, 225, 150), motion_state=state,
        )
        win = state["blocked_rects"][0]
        px = max(10, int(min(W, H) * 0.030 * 2.0))  # headline scale factor
        block_w = int(W * 0.55)
        block_h = int(px * 1.32) + 2 * int(px * 0.28)
        x0, y0 = resolve_text_placement(
            0.5, 0.13, block_w, block_h, W, H, blocked_rects=[win],
        )
        assert not (
            x0 < win[2] and x0 + block_w > win[0]
            and y0 < win[3] and y0 + block_h > win[1]
        )


# ---------------------------------------------------------------------------
# S4: classroom board hosts the headline (never an empty box)
# ---------------------------------------------------------------------------


class TestClassroomBoardHosting:
    BOARD = (int(0.12 * W), int(0.08 * H), int(0.42 * W), int(0.16 * H))

    def _decorate(self, state: dict) -> bytearray:
        r = _renderer()
        frame = bytearray(W * H * 3)
        bx, by, bw, bh = self.BOARD
        r._decorate_classroom_board(
            frame, W, H, state, bx, by, bw, bh, (245, 245, 230),
        )
        return frame

    def test_board_zone_headline_is_hosted(self) -> None:
        """S4 regression: a headline addressed at the board region is rendered
        as chalk writing on the board and skipped by the regular text pass."""
        state = {"text_specs": [
            {"text": "BUSY != EFFECTIVE", "size": "headline", "x": 0.33, "y": 0.16},
        ]}
        frame = self._decorate(state)
        assert state["_board_hosted"] == {0}
        assert any(frame)  # chalk writing actually drawn

    def test_board_without_headline_gets_chalk_marks(self) -> None:
        """Boards with no headline show faint chalk lines, never an empty box."""
        state: dict = {"text_specs": []}
        frame = self._decorate(state)
        assert not state["_board_hosted"]
        assert any(frame)  # chalk fallback marks drawn

    def test_headline_outside_board_zone_not_hosted(self) -> None:
        state = {"text_specs": [
            {"text": "THE FOCUS CLIFF", "size": "headline", "x": 0.75, "y": 0.12},
        ]}
        frame = self._decorate(state)
        assert not state["_board_hosted"]
        assert any(frame)  # falls back to chalk marks, not blank


# ---------------------------------------------------------------------------
# Plan guard: the demo plan keeps titles on every scene (S4 / S5 / S9 fix)
# ---------------------------------------------------------------------------


class TestPlanTitles:
    @staticmethod
    def _scenes() -> list[dict]:
        path = os.path.join(PROJECT_ROOT, "examples", "plan_visual_quality_v1.json")
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)["scenes"]

    def test_fixed_scenes_have_titles(self) -> None:
        scenes = self._scenes()
        for idx in (3, 4, 8):  # S4, S5, S9 (1-based audit numbering)
            texts = scenes[idx].get("visual", {}).get("text_elements") or []
            assert any(str(t.get("text", "")).strip() for t in texts), (
                f"scene {idx + 1} lost its title"
            )

    def test_s4_title_is_addressed_to_the_board(self) -> None:
        spec = self._scenes()[3]["visual"]["text_elements"][0]
        assert spec["size"] == "headline"
        assert 0.10 <= float(spec["x"]) <= 0.56
        assert 0.06 <= float(spec["y"]) <= 0.26

    def test_every_demo_scene_keeps_a_text_element(self) -> None:
        for i, scene in enumerate(self._scenes(), start=1):
            texts = scene.get("visual", {}).get("text_elements") or []
            assert texts, f"scene {i} has no on-screen text"
