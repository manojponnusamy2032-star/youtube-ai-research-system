"""Tests for content generation service pipeline and persistence."""

from __future__ import annotations

from src.database.database_service import DatabaseService
from src.models.content_package import ScriptPlan
from src.services.content_generation_service import ContentGenerationService


def _payload() -> dict[str, object]:
    return {
        "topic": "YouTube AI Automation",
        "audience": "new creators",
        "niche": "education",
        "knowledge_entries": [
            {"category": "Hook", "pattern": "Open Loop", "frequency": 64.0, "confidence": 92.0},
            {"category": "Story", "pattern": "Problem-Solution", "frequency": 58.0, "confidence": 89.0},
        ],
        "pattern_report": {
            "hooks": {"Open Loop": 42.0, "Curiosity": 38.0},
            "emotions": {"Curiosity": 51.0},
        },
        "generated_titles": [
            {"title": "How I Automated YouTube Research in 7 Days", "confidence": 91.0, "estimated_ctr": 9.2},
            {"title": "Open Loop Framework for Creator Growth", "confidence": 88.0, "estimated_ctr": 8.4},
        ],
        "trend_info": ["AI workflow", "faceless channels"],
    }


def test_generate_hook_returns_supported_type_and_score(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)

    hook = service.generate_hook(**service.extract_generation_inputs(_payload()))

    assert hook["hook_type"] in ContentGenerationService.HOOK_TYPES
    assert isinstance(hook["script"], str) and hook["script"]
    assert 0.0 <= float(hook["retention_score"]) <= 99.0
    db.disconnect()


def test_generate_thumbnail_has_required_shape(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    normalized = service.extract_generation_inputs(_payload())
    best_title = service.select_best_title(normalized["generated_titles"], normalized["topic"])

    thumbnail = service.generate_thumbnail(best_title=best_title, **normalized)

    assert thumbnail["concept"]
    assert thumbnail["layout"]
    assert thumbnail["text"]
    assert len(thumbnail["color_palette"]) >= 3
    assert thumbnail["image_prompt"]
    db.disconnect()


def test_generate_script_contains_sections_and_duration(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    normalized = service.extract_generation_inputs(_payload())
    best_title = service.select_best_title(normalized["generated_titles"], normalized["topic"])
    hook = service.generate_hook(**normalized)

    script = service.generate_script(best_title=best_title, hook=hook, **normalized)

    assert script["intro"]
    assert len(script["sections"]) >= 3
    assert script["cta"]
    assert script["estimated_duration_minutes"] > 0
    db.disconnect()


def test_generate_seo_includes_keywords_tags_and_chapters(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    normalized = service.extract_generation_inputs(_payload())
    best_title = service.select_best_title(normalized["generated_titles"], normalized["topic"])

    seo = service.generate_seo(best_title=best_title, script={"sections": []}, **normalized)

    assert seo["description"]
    assert len(seo["keywords"]) >= 3
    assert len(seo["hashtags"]) >= 2
    assert len(seo["tags"]) >= 3
    assert len(seo["chapters"]) >= 3
    db.disconnect()


def test_generate_content_package_persists_all_outputs(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)

    package = service.generate_content_package(_payload())
    cursor = db.connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM generated_hooks")
    hooks_count = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM generated_thumbnails")
    thumbnails_count = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM generated_scripts")
    scripts_count = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM generated_seo")
    seo_count = int(cursor.fetchone()[0])

    assert package.topic == "YouTube AI Automation"
    assert package.best_title["title"]
    assert package.confidence > 0.0
    assert hooks_count == 1
    assert thumbnails_count == 1
    assert scripts_count == 1
    assert seo_count == 1
    assert db.get_content_package_count() == 1
    db.disconnect()


def test_validate_content_rejects_missing_fields(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)

    is_valid, errors = service.validate_content({"topic": "", "script": {}})

    assert is_valid is False
    assert errors
    db.disconnect()


def test_create_video_production_plan_preserves_scenes_and_duration(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    normalized = service.extract_generation_inputs(_payload())
    best_title = service.select_best_title(normalized["generated_titles"], normalized["topic"])
    hook = service.generate_hook(**normalized)
    script_data = service.generate_script(best_title=best_title, hook=hook, **normalized)
    script_plan = ScriptPlan(
        intro=script_data["intro"],
        sections=script_data["sections"],
        cta=script_data["cta"],
        estimated_duration_minutes=script_data["estimated_duration_minutes"],
        scenes=script_data.get("scenes", []),
    )

    production_plan = service.create_video_production_plan(script_plan)

    assert production_plan.title
    assert production_plan.total_duration_seconds > 0
    assert len(production_plan.scenes) == len(script_plan.scenes)
    for prod_scene, script_scene in zip(production_plan.scenes, script_plan.scenes):
        assert prod_scene.scene_number == script_scene["scene_number"]
        assert prod_scene.duration_seconds == script_scene["duration_seconds"]
        assert prod_scene.visual_description == script_scene["visual"]
        assert prod_scene.narration == script_scene["narration"]
        assert prod_scene.dialogue == script_scene["dialogue"]
        assert prod_scene.sound_effects == script_scene["sfx"]
        assert prod_scene.camera_direction
        assert prod_scene.animation_direction
        assert prod_scene.transition
    db.disconnect()


def test_video_production_plan_handles_empty_scenes(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    script_plan = ScriptPlan(intro="Test intro", sections=[], cta="Test CTA", scenes=[])

    production_plan = service.create_video_production_plan(script_plan)

    assert production_plan.title == "Test intro"
    assert production_plan.total_duration_seconds == 0
    assert len(production_plan.scenes) == 0
    db.disconnect()


def test_create_scene_asset_plan_preserves_scene_numbers_and_counts(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    normalized = service.extract_generation_inputs(_payload())
    best_title = service.select_best_title(normalized["generated_titles"], normalized["topic"])
    hook = service.generate_hook(**normalized)
    script_data = service.generate_script(best_title=best_title, hook=hook, **normalized)
    script_plan = ScriptPlan(
        intro=script_data["intro"],
        sections=script_data["sections"],
        cta=script_data["cta"],
        estimated_duration_minutes=script_data["estimated_duration_minutes"],
        scenes=script_data.get("scenes", []),
    )
    production_plan = service.create_video_production_plan(script_plan)
    asset_plan = service.create_scene_asset_plan(production_plan)

    assert asset_plan.total_assets == len(production_plan.scenes)
    assert len(asset_plan.assets) == len(production_plan.scenes)
    for asset, scene in zip(asset_plan.assets, production_plan.scenes):
        assert asset.scene_number == scene.scene_number
        assert asset.duration_seconds == scene.duration_seconds
        assert asset.asset_id == f"asset-scene-{scene.scene_number}"
    db.disconnect()


def test_scene_asset_plan_handles_empty_scenes(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    script_plan = ScriptPlan(intro="Test intro", sections=[], cta="Test CTA", scenes=[])
    production_plan = service.create_video_production_plan(script_plan)
    asset_plan = service.create_scene_asset_plan(production_plan)

    assert asset_plan.total_assets == 0
    assert len(asset_plan.assets) == 0
    db.disconnect()


def test_create_visual_style_plan_generates_consistent_plan(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    normalized = service.extract_generation_inputs(_payload())
    best_title = service.select_best_title(normalized["generated_titles"], normalized["topic"])
    hook = service.generate_hook(**normalized)
    script_data = service.generate_script(best_title=best_title, hook=hook, **normalized)
    script_plan = ScriptPlan(
        intro=script_data["intro"],
        sections=script_data["sections"],
        cta=script_data["cta"],
        estimated_duration_minutes=script_data["estimated_duration_minutes"],
        scenes=script_data.get("scenes", []),
    )
    production_plan = service.create_video_production_plan(script_plan)
    asset_plan = service.create_scene_asset_plan(production_plan)
    visual_style_plan = service.create_visual_style_plan(production_plan, asset_plan)

    assert visual_style_plan.style_name
    assert visual_style_plan.art_style
    assert visual_style_plan.background_style
    assert visual_style_plan.lighting_style
    assert visual_style_plan.camera_style
    assert len(visual_style_plan.characters) > 0
    assert len(visual_style_plan.consistency_rules) > 0
    # Verify character reuse - host character should appear in multiple assets
    host_chars = [c for c in visual_style_plan.characters if "host" in c.character_id]
    if host_chars:
        assert host_chars[0].name
        assert host_chars[0].role
    db.disconnect()


def test_visual_style_plan_handles_empty_scenes(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    script_plan = ScriptPlan(intro="Test intro", sections=[], cta="Test CTA", scenes=[])
    production_plan = service.create_video_production_plan(script_plan)
    asset_plan = service.create_scene_asset_plan(production_plan)
    visual_style_plan = service.create_visual_style_plan(production_plan, asset_plan)

    assert visual_style_plan.style_name
    assert len(visual_style_plan.characters) == 1  # Generic placeholder
    assert visual_style_plan.characters[0].character_id == "char-generic-host"
    assert len(visual_style_plan.consistency_rules) > 0
    db.disconnect()


def test_content_package_serialization_includes_visual_style_plan(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    package = service.generate_content_package(_payload())
    package_dict = package.to_dict()

    assert "visual_style_plan" in package_dict
    assert package_dict["visual_style_plan"] is not None
    assert "style_name" in package_dict["visual_style_plan"]
    assert "characters" in package_dict["visual_style_plan"]
    assert "consistency_rules" in package_dict["visual_style_plan"]
    db.disconnect()


def test_create_character_asset_plan_generates_specifications(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    normalized = service.extract_generation_inputs(_payload())
    best_title = service.select_best_title(normalized["generated_titles"], normalized["topic"])
    hook = service.generate_hook(**normalized)
    script_data = service.generate_script(best_title=best_title, hook=hook, **normalized)
    script_plan = ScriptPlan(
        intro=script_data["intro"],
        sections=script_data["sections"],
        cta=script_data["cta"],
        estimated_duration_minutes=script_data["estimated_duration_minutes"],
        scenes=script_data.get("scenes", []),
    )
    production_plan = service.create_video_production_plan(script_plan)
    asset_plan = service.create_scene_asset_plan(production_plan)
    visual_style_plan = service.create_visual_style_plan(production_plan, asset_plan)
    character_asset_plan = service.create_character_asset_plan(visual_style_plan)

    assert len(character_asset_plan.characters) > 0
    for char in character_asset_plan.characters:
        assert char.character_id
        assert char.name
        assert char.reference_prompt
        assert char.body_style
        assert char.face_style
        assert char.clothing
    assert len(character_asset_plan.global_character_rules) > 0
    db.disconnect()


def test_character_asset_plan_preserves_character_ids(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    normalized = service.extract_generation_inputs(_payload())
    best_title = service.select_best_title(normalized["generated_titles"], normalized["topic"])
    hook = service.generate_hook(**normalized)
    script_data = service.generate_script(best_title=best_title, hook=hook, **normalized)
    script_plan = ScriptPlan(
        intro=script_data["intro"],
        sections=script_data["sections"],
        cta=script_data["cta"],
        estimated_duration_minutes=script_data["estimated_duration_minutes"],
        scenes=script_data.get("scenes", []),
    )
    production_plan = service.create_video_production_plan(script_plan)
    asset_plan = service.create_scene_asset_plan(production_plan)
    visual_style_plan = service.create_visual_style_plan(production_plan, asset_plan)
    character_asset_plan = service.create_character_asset_plan(visual_style_plan)

    # Verify character IDs match VisualStylePlan
    visual_char_ids = {c.character_id for c in visual_style_plan.characters}
    asset_char_ids = {c.character_id for c in character_asset_plan.characters}
    assert visual_char_ids == asset_char_ids
    db.disconnect()


def test_character_asset_plan_handles_empty_characters(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    script_plan = ScriptPlan(intro="Test intro", sections=[], cta="Test CTA", scenes=[])
    production_plan = service.create_video_production_plan(script_plan)
    asset_plan = service.create_scene_asset_plan(production_plan)
    visual_style_plan = service.create_visual_style_plan(production_plan, asset_plan)
    character_asset_plan = service.create_character_asset_plan(visual_style_plan)

    assert len(character_asset_plan.characters) == 1  # Generic placeholder
    assert character_asset_plan.characters[0].character_id == "char-generic-host"
    assert character_asset_plan.characters[0].reference_prompt
    assert len(character_asset_plan.global_character_rules) > 0
    db.disconnect()


def test_content_package_serialization_includes_character_asset_plan(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    package = service.generate_content_package(_payload())
    package_dict = package.to_dict()

    assert "character_asset_plan" in package_dict
    assert package_dict["character_asset_plan"] is not None
    assert "characters" in package_dict["character_asset_plan"]
    assert "global_character_rules" in package_dict["character_asset_plan"]
    db.disconnect()


def test_create_render_job_plan_preserves_scene_data(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    normalized = service.extract_generation_inputs(_payload())
    best_title = service.select_best_title(normalized["generated_titles"], normalized["topic"])
    hook = service.generate_hook(**normalized)
    script_data = service.generate_script(best_title=best_title, hook=hook, **normalized)
    script_plan = ScriptPlan(
        intro=script_data["intro"],
        sections=script_data["sections"],
        cta=script_data["cta"],
        estimated_duration_minutes=script_data["estimated_duration_minutes"],
        scenes=script_data.get("scenes", []),
    )
    production_plan = service.create_video_production_plan(script_plan)
    asset_plan = service.create_scene_asset_plan(production_plan)
    visual_style_plan = service.create_visual_style_plan(production_plan, asset_plan)
    character_asset_plan = service.create_character_asset_plan(visual_style_plan)
    render_job_plan = service.create_render_job_plan(production_plan, asset_plan, character_asset_plan)

    assert render_job_plan.total_jobs == len(production_plan.scenes)
    assert len(render_job_plan.jobs) == len(production_plan.scenes)
    assert render_job_plan.total_duration_seconds == production_plan.total_duration_seconds
    for job, scene in zip(render_job_plan.jobs, production_plan.scenes):
        assert job.scene_number == scene.scene_number
        assert job.duration_seconds == scene.duration_seconds
        assert job.animation_instructions == scene.animation_direction
        assert job.camera_instructions == scene.camera_direction
    db.disconnect()


def test_render_job_plan_preserves_character_and_asset_ids(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    normalized = service.extract_generation_inputs(_payload())
    best_title = service.select_best_title(normalized["generated_titles"], normalized["topic"])
    hook = service.generate_hook(**normalized)
    script_data = service.generate_script(best_title=best_title, hook=hook, **normalized)
    script_plan = ScriptPlan(
        intro=script_data["intro"],
        sections=script_data["sections"],
        cta=script_data["cta"],
        estimated_duration_minutes=script_data["estimated_duration_minutes"],
        scenes=script_data.get("scenes", []),
    )
    production_plan = service.create_video_production_plan(script_plan)
    asset_plan = service.create_scene_asset_plan(production_plan)
    visual_style_plan = service.create_visual_style_plan(production_plan, asset_plan)
    character_asset_plan = service.create_character_asset_plan(visual_style_plan)
    render_job_plan = service.create_render_job_plan(production_plan, asset_plan, character_asset_plan)

    # Verify character IDs match character asset plan
    char_ids = {c.character_id for c in character_asset_plan.characters}
    for job in render_job_plan.jobs:
        assert all(cid in char_ids for cid in job.character_ids)
    # Verify asset IDs match scene asset plan
    asset_ids = {a.asset_id for a in asset_plan.assets}
    for job in render_job_plan.jobs:
        assert all(aid in asset_ids for aid in job.asset_ids)
    db.disconnect()


def test_render_job_plan_handles_empty_scenes(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    script_plan = ScriptPlan(intro="Test intro", sections=[], cta="Test CTA", scenes=[])
    production_plan = service.create_video_production_plan(script_plan)
    asset_plan = service.create_scene_asset_plan(production_plan)
    visual_style_plan = service.create_visual_style_plan(production_plan, asset_plan)
    character_asset_plan = service.create_character_asset_plan(visual_style_plan)
    render_job_plan = service.create_render_job_plan(production_plan, asset_plan, character_asset_plan)

    assert render_job_plan.total_jobs == 0
    assert len(render_job_plan.jobs) == 0
    assert render_job_plan.total_duration_seconds == 0
    db.disconnect()


def test_content_package_serialization_includes_render_job_plan(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "content.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    package = service.generate_content_package(_payload())
    package_dict = package.to_dict()

    assert "render_job_plan" in package_dict
    assert package_dict["render_job_plan"] is not None
    assert "total_jobs" in package_dict["render_job_plan"]
    assert "jobs" in package_dict["render_job_plan"]
    assert "total_duration_seconds" in package_dict["render_job_plan"]
    db.disconnect()
