"""Data models for generated long-form YouTube content packages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ThumbnailPlan:
    """Represents thumbnail strategy and image-generation guidance."""

    concept: str
    layout: str
    text: str
    color_palette: list[str] = field(default_factory=list)
    emotion: str = ""
    image_prompt: str = ""


@dataclass
class HookPlan:
    """Represents an opening hook and retention estimate."""

    script: str
    hook_type: str
    retention_score: float


@dataclass
class ScriptPlan:
    """Represents generated script structure."""

    intro: str
    sections: list[dict[str, Any]] = field(default_factory=list)
    cta: str = ""
    estimated_duration_minutes: int = 0
    scenes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SeoPlan:
    """Represents packaged SEO deliverables."""

    description: str
    keywords: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    chapters: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class VideoProductionScene:
    """Production-ready scene instructions for video generation."""

    scene_number: int
    duration_seconds: int
    visual_description: str
    narration: str
    dialogue: str
    sound_effects: str
    camera_direction: str
    animation_direction: str
    transition: str


@dataclass
class VideoProductionPlan:
    """Structured production plan for video generation."""

    title: str
    total_duration_seconds: int
    scenes: list[VideoProductionScene]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "title": self.title,
            "total_duration_seconds": self.total_duration_seconds,
            "scenes": [asdict(scene) for scene in self.scenes],
        }


@dataclass
class SceneAsset:
    """Deterministic asset requirement derived from a scene."""

    asset_id: str
    asset_type: str
    description: str
    scene_number: int
    character: str = ""
    action: str = ""
    position: str = ""
    expression: str = ""
    duration_seconds: int = 0


@dataclass
class SceneAssetPlan:
    """Aggregated asset requirements for all scenes."""

    total_assets: int
    assets: list[SceneAsset]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "total_assets": self.total_assets,
            "assets": [asdict(asset) for asset in self.assets],
        }


@dataclass
class CharacterSpec:
    """Reusable character specification for visual consistency."""

    character_id: str
    name: str
    description: str
    role: str
    visual_style: str
    default_expression: str
    color: str
    clothing: str
    consistency_notes: str


@dataclass
class VisualStylePlan:
    """Overall visual style and character consistency plan."""

    style_name: str
    art_style: str
    background_style: str
    lighting_style: str
    camera_style: str
    characters: list[CharacterSpec]
    consistency_rules: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "style_name": self.style_name,
            "art_style": self.art_style,
            "background_style": self.background_style,
            "lighting_style": self.lighting_style,
            "camera_style": self.camera_style,
            "characters": [asdict(char) for char in self.characters],
            "consistency_rules": self.consistency_rules,
        }


@dataclass
class CharacterAssetSpec:
    """Detailed character asset specification for consistent generation."""

    character_id: str
    name: str
    base_description: str
    body_style: str
    head_style: str
    face_style: str
    pose_style: str
    clothing: str
    primary_color: str
    secondary_color: str
    visual_style: str
    default_expression: str
    reference_prompt: str
    consistency_rules: list[str]


@dataclass
class CharacterAssetPlan:
    """Aggregated character asset specifications."""

    characters: list[CharacterAssetSpec]
    global_character_rules: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "characters": [asdict(char) for char in self.characters],
            "global_character_rules": self.global_character_rules,
        }


@dataclass
class AudioRequest:
    """Audio production contract for a single scene.

    Describes the audio elements needed for a scene without performing
    any actual audio generation, mixing, or downloading.
    """

    scene_number: int
    duration_seconds: int = 0
    narration_text: str = ""
    voice_reference: str = ""
    background_music_reference: str = ""
    sound_effect_references: list[str] = field(default_factory=list)
    audio_format: str = "aac"

    def __post_init__(self) -> None:
        """Validate audio request values."""
        if self.scene_number <= 0:
            raise ValueError("scene_number must be positive")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")
        if not isinstance(self.narration_text, str):
            raise ValueError("narration_text must be a string")
        if not isinstance(self.voice_reference, str):
            raise ValueError("voice_reference must be a string")
        if not isinstance(self.background_music_reference, str):
            raise ValueError("background_music_reference must be a string")
        if not isinstance(self.sound_effect_references, list):
            raise ValueError("sound_effect_references must be a list")
        if not self.audio_format.strip():
            raise ValueError("audio_format cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass
class RenderJobSpec:
    """Specification for a single render job."""

    job_id: str
    scene_number: int
    duration_seconds: int
    render_type: str
    character_ids: list[str]
    asset_ids: list[str]
    visual_prompt: str
    animation_instructions: str
    camera_instructions: str
    audio_requirements: str
    audio_request: AudioRequest | None = None


@dataclass
class RenderConfig:
    """Configuration for video rendering."""

    width: int = 1920
    height: int = 1080
    fps: int = 30
    aspect_ratio: str = "16:9"
    video_format: str = "mp4"
    video_codec: str = "h264"
    audio_format: str = "aac"
    output_directory: str = "output"
    filename_template: str = "{job_id}.mp4"

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.width <= 0:
            raise ValueError("width must be positive")
        if self.height <= 0:
            raise ValueError("height must be positive")
        if self.fps <= 0:
            raise ValueError("fps must be positive")
        if not self.aspect_ratio.strip():
            raise ValueError("aspect_ratio cannot be empty")
        if not self.video_format.strip():
            raise ValueError("video_format cannot be empty")
        if not self.video_codec.strip():
            raise ValueError("video_codec cannot be empty")
        if not self.audio_format.strip():
            raise ValueError("audio_format cannot be empty")
        if not self.output_directory.strip():
            raise ValueError("output_directory cannot be empty")
        if not self.filename_template.strip():
            raise ValueError("filename_template cannot be empty")


@dataclass
class RenderJobPlan:
    """Aggregated render job plan for all scenes."""

    total_jobs: int
    jobs: list[RenderJobSpec]
    total_duration_seconds: int
    render_config: RenderConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        result = {
            "total_jobs": self.total_jobs,
            "jobs": [asdict(job) for job in self.jobs],
            "total_duration_seconds": self.total_duration_seconds,
        }
        if self.render_config is not None:
            result["render_config"] = asdict(self.render_config)
        return result


@dataclass
class ContentPackage:
    """End-to-end content package assembled by the generation pipeline."""

    topic: str
    best_title: dict[str, Any]
    thumbnail: ThumbnailPlan
    hook: HookPlan
    script: ScriptPlan
    seo: SeoPlan
    confidence: float
    video_production_plan: dict[str, Any] | None = None
    scene_asset_plan: dict[str, Any] | None = None
    visual_style_plan: dict[str, Any] | None = None
    character_asset_plan: dict[str, Any] | None = None
    render_job_plan: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)
