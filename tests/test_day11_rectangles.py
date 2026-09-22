"""Exact RGB equivalence against the frozen pre-optimization rectangle path."""
import pytest

from scripts.compare_day11_rectangles import difference, rectangle_pair, scene_pair


@pytest.mark.parametrize('seed', range(20))
def test_rectangle_sequences_match_original(seed):
    result = difference(*rectangle_pair(seed))
    assert result['different_pixels'] == 0
    assert result['maximum_channel_difference'] == 0


@pytest.mark.parametrize('index', range(9))
def test_complete_frames_match_original(index):
    result = difference(*scene_pair(index))
    assert result['different_pixels'] == 0
    assert result['maximum_channel_difference'] == 0
