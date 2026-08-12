"""Service layer for modular YouTube content package generation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.database.database_service import DatabaseService
from src.models.content_package import ContentPackage, HookPlan, ScriptPlan, SeoPlan, ThumbnailPlan, VideoProductionPlan, VideoProductionScene, SceneAsset, SceneAssetPlan, CharacterSpec, VisualStylePlan, CharacterAssetSpec, CharacterAssetPlan, RenderJobSpec, RenderJobPlan
from src.models.idea import Idea
from src.services.script_service import ScriptService
from src.services.title_generation_service import TitleGenerationService
from src.utils.generation_utils import normalize_trends, unique


class ContentGenerationService:
    """Coordinates hook, thumbnail, script, SEO generation and package scoring."""

    HOOK_TYPES = (
        "Curiosity",
        "Shock",
        "Story",
        "Problem",
        "Transformation",
        "Question",
        "Open Loop",
    )

    def __init__(self, database_service: DatabaseService, title_service: TitleGenerationService | None = None, script_service: ScriptService | None = None) -> None:
        self.database_service = database_service
        # prefer injected services when available; fallback to None
        self.title_service = title_service
        self.script_service = script_service

    def generate_content_package(
        self,
        payload: dict[str, Any],
        hook: dict[str, Any] | None = None,
        thumbnail: dict[str, Any] | None = None,
        script: dict[str, Any] | None = None,
        seo: dict[str, Any] | None = None,
    ) -> ContentPackage:
        """Build, validate, score, and persist a complete content package."""
        normalized = self._normalize_inputs(payload)
        if self.title_service:
            best_title = self.title_service.select_best_title(normalized["generated_titles"], normalized["topic"])
        else:
            # fallback to local selection if title service not injected
            best_title = self.select_best_title(normalized["generated_titles"], normalized["topic"])
        hook_data = hook or self.generate_hook(**normalized)
        thumbnail_data = thumbnail or self.generate_thumbnail(best_title=best_title, **normalized)
        if self.script_service:
            script_data = script or self.generate_script_via_script_service(best_title=best_title, hook=hook_data, **normalized)
        else:
            script_data = script or self.generate_script(best_title=best_title, hook=hook_data, **normalized)
        seo_data = seo or self.generate_seo(best_title=best_title, script=script_data, **normalized)
        script_plan = ScriptPlan(
            intro=str(script_data["intro"]),
            sections=list(script_data["sections"]),
            cta=str(script_data["cta"]),
            estimated_duration_minutes=int(script_data["estimated_duration_minutes"]),
            scenes=list(script_data.get("scenes", [])),
        )
        video_production_plan = self.create_video_production_plan(script_plan)
        scene_asset_plan = self.create_scene_asset_plan(video_production_plan)
        visual_style_plan = self.create_visual_style_plan(video_production_plan, scene_asset_plan)
        character_asset_plan = self.create_character_asset_plan(visual_style_plan)
        render_job_plan = self.create_render_job_plan(video_production_plan, scene_asset_plan, character_asset_plan)
        package = ContentPackage(
            topic=normalized["topic"],
            best_title=best_title,
            thumbnail=ThumbnailPlan(**thumbnail_data),
            hook=HookPlan(
                script=str(hook_data["script"]),
                hook_type=str(hook_data["hook_type"]),
                retention_score=float(hook_data["retention_score"]),
            ),
            script=script_plan,
            seo=SeoPlan(**seo_data),
            confidence=0.0,
            video_production_plan=video_production_plan.to_dict(),
            scene_asset_plan=scene_asset_plan.to_dict(),
            visual_style_plan=visual_style_plan.to_dict(),
            character_asset_plan=character_asset_plan.to_dict(),
            render_job_plan=render_job_plan.to_dict(),
        )
        valid, errors = self.validate_content(package.to_dict())
        if not valid:
            raise ValueError(f"Invalid content package: {', '.join(errors)}")
        scored = replace(package, confidence=self.score_package(package.to_dict()))
        self.database_service.insert_content_package(scored.to_dict())
        return scored

    def extract_generation_inputs(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Public wrapper to normalize workflow payload."""
        return self._normalize_inputs(payload)

    def select_best_title(self, titles: list[dict[str, Any]], topic: str) -> dict[str, Any]:
        """Public wrapper to choose best title candidate. Delegates to TitleGenerationService when available."""
        if self.title_service:
            return self.title_service.select_best_title(titles, topic)
        # fallback
        if not titles:
            return {"title": f"{topic} Blueprint for 2026", "confidence": 70.0, "estimated_ctr": 6.5}
        ranked = sorted(
            titles,
            key=lambda item: (float(item.get("confidence", 0.0)), float(item.get("estimated_ctr", 0.0))),
            reverse=True,
        )
        return ranked[0]

    def generate_hook(
        self,
        topic: str,
        audience: str,
        niche: str,
        pattern_report: dict[str, Any],
        generated_titles: list[dict[str, Any]] | None = None,
        knowledge_base: list[dict[str, Any]] | None = None,
        trend_info: Any = None,
    ) -> dict[str, Any]:
        """Generate and select the strongest hook across supported hook types."""
        trend_terms = normalize_trends(trend_info)
        candidates = [self._build_hook_candidate(hook_type, topic, audience, niche, trend_terms) for hook_type in self.HOOK_TYPES]
        hooks_distribution = pattern_report.get("hooks", {}) if isinstance(pattern_report, dict) else {}
        scored = [self._score_hook(candidate, hooks_distribution) for candidate in candidates]
        best = max(scored, key=lambda item: float(item["retention_score"]))
        self.database_service.insert_generated_hook(topic, best, scored)
        return best

    def generate_thumbnail(
        self,
        topic: str,
        audience: str,
        niche: str,
        pattern_report: dict[str, Any],
        generated_titles: list[dict[str, Any]] | None = None,
        knowledge_base: list[dict[str, Any]] | None = None,
        trend_info: Any = None,
        best_title: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate thumbnail concept, composition, and AI image prompt."""
        title_text = str((best_title or {}).get("title", topic))
        emotion = self._top_pattern(pattern_report, "emotions", "Curiosity")
        concept = f"{title_text}: visual proof moment for {audience}"
        layout = "Rule-of-thirds split: subject left, proof element right, bold text top-right"
        text_overlay = self._thumbnail_text(title_text)
        palette = self._palette_for_emotion(emotion)
        image_prompt = (
            f"High-contrast YouTube thumbnail for '{topic}' in {niche}. "
            f"Primary subject shows {emotion.lower()} emotion, clean background, cinematic lighting, "
            f"text area reserved: '{text_overlay}', color palette {', '.join(palette)}."
        )
        thumbnail = {
            "concept": concept,
            "layout": layout,
            "text": text_overlay,
            "color_palette": palette,
            "emotion": emotion,
            "image_prompt": image_prompt,
        }
        self.database_service.insert_generated_thumbnail(topic, thumbnail)
        return thumbnail

    def generate_script(
        self,
        topic: str,
        audience: str,
        niche: str,
        pattern_report: dict[str, Any],
        generated_titles: list[dict[str, Any]] | None = None,
        knowledge_base: list[dict[str, Any]] | None = None,
        trend_info: Any = None,
        best_title: dict[str, Any] | None = None,
        hook: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate script intro, sections with transitions/examples, and CTA.

        This legacy method remains for backward compatibility. Prefer generate_script_via_script_service
        which delegates to the dedicated ScriptService when available.
        """
        title_text = str((best_title or {}).get("title", topic))
        hook_script = str((hook or {}).get("script", f"Today we break down {topic}."))
        kb_signals = self._knowledge_signals(knowledge_base or [])
        sections = [
            {
                "heading": "Context & Stakes",
                "content": f"Explain why {topic} matters for {audience} in {niche}.",
                "transition": "Now that stakes are clear, let us map the strategy.",
                "example": f"Example: creator used {kb_signals[0]} and doubled retention.",
                "retention_checkpoint": "0:45 - Pattern interrupt question.",
            },
            {
                "heading": "Core Framework",
                "content": f"Teach a 3-step execution framework tied to {title_text}.",
                "transition": "Next, we convert strategy into repeatable actions.",
                "example": f"Example: apply {kb_signals[1]} to one video draft.",
                "retention_checkpoint": "2:30 - Promise a teardown in section 3.",
            },
            {
                "heading": "Execution Walkthrough",
                "content": "Walk through implementation, common mistakes, and fixes.",
                "transition": "To lock results, summarize and set next step.",
                "example": f"Example: compare before/after metrics using {kb_signals[2]}.",
                "retention_checkpoint": "5:00 - Open loop closure + mini payoff.",
            },
        ]
        scenes = [
            {
                "scene_number": 1,
                "duration_seconds": 45,
                "visual": f"Opening shot: host on camera with text overlay '{title_text}'",
                "narration": hook_script,
                "dialogue": "",
                "sfx": "whoosh",
            },
            {
                "scene_number": 2,
                "duration_seconds": 90,
                "visual": f"B-roll: {topic} examples with lower-third graphics",
                "narration": f"Here is why {topic} matters for {audience} in {niche}.",
                "dialogue": "",
                "sfx": "transition",
            },
            {
                "scene_number": 3,
                "duration_seconds": 150,
                "visual": f"Screen share: 3-step framework diagram for {title_text}",
                "narration": "The framework has three parts. First, identify the bottleneck. Second, apply the fix. Third, measure results.",
                "dialogue": "",
                "sfx": "click",
            },
            {
                "scene_number": 4,
                "duration_seconds": 120,
                "visual": f"Before/after comparison: metrics dashboard showing improvement",
                "narration": "Here is the result when you apply this consistently.",
                "dialogue": "",
                "sfx": "ding",
            },
            {
                "scene_number": 5,
                "duration_seconds": 45,
                "visual": "End screen: subscribe button and video links",
                "narration": f"If this helped, subscribe for weekly {topic} breakdowns.",
                "dialogue": "",
                "sfx": "upbeat",
            },
        ]
        script = {
            "intro": f"{hook_script} In this video, you will leave with a clear playbook.",
            "sections": sections,
            "cta": f"If this helped, subscribe for weekly {topic} breakdowns and comment your biggest blocker.",
            "estimated_duration_minutes": 8,
            "scenes": scenes,
        }
        self.database_service.insert_generated_script(topic, script)
        return script

    def generate_script_via_script_service(
        self,
        topic: str,
        audience: str,
        niche: str,
        pattern_report: dict[str, Any],
        generated_titles: list[dict[str, Any]] | None = None,
        knowledge_base: list[dict[str, Any]] | None = None,
        trend_info: Any = None,
        best_title: dict[str, Any] | None = None,
        hook: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Delegate script generation to the dedicated ScriptService and adapt
        its Script model to the content package structure.
        """
        if not self.script_service:
            # fallback to legacy generator
            return self.generate_script(
                topic,
                audience,
                niche,
                pattern_report,
                generated_titles,
                knowledge_base,
                trend_info,
                best_title,
                hook,
            )
        # Build Idea for script service
        title_text = str((best_title or {}).get("title", topic))
        hook_text = str((hook or {}).get("script", f"Today we break down {topic}."))
        confidence = float((best_title or {}).get("confidence", 70.0))
        virality = float((best_title or {}).get("estimated_ctr", 6.5))
        idea = Idea(
            title=title_text,
            hook=hook_text,
            emotion=str((best_title or {}).get("emotion", "Neutral")),
            topic=topic,
            virality_score=min(10.0, max(0.0, confidence / 10.0)),
            confidence_score=min(10.0, max(0.0, confidence / 10.0)),
        )
        script_model = self.script_service.generate(idea)
        # Adapt Script model to expected dict shape
        sections = [
            {
                "heading": "Main",
                "content": script_model.body,
                "transition": "",
                "example": "",
                "retention_checkpoint": "",
            }
        ]
        payload = {
            "intro": script_model.introduction,
            "sections": sections,
            "cta": script_model.call_to_action,
            "estimated_duration_minutes": int(max(1, script_model.estimated_duration) // 60),
        }
        self.database_service.insert_generated_script(topic, payload)
        return payload

    def generate_seo(
        self,
        topic: str,
        audience: str,
        niche: str,
        pattern_report: dict[str, Any],
        generated_titles: list[dict[str, Any]] | None = None,
        knowledge_base: list[dict[str, Any]] | None = None,
        trend_info: Any = None,
        best_title: dict[str, Any] | None = None,
        script: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate YouTube description, keywords, tags, hashtags, and chapters."""
        title_text = str((best_title or {}).get("title", topic))
        trend_terms = normalize_trends(trend_info)
        keywords = unique([
            topic,
            f"{topic} strategy",
            f"{niche} growth",
            f"{audience} guide",
            *trend_terms[:4],
        ])
        hashtags = [f"#{item.replace(' ', '')}" for item in unique([topic, niche, "YouTubeGrowth"])[:3]]
        tags = unique(keywords + [title_text, "content strategy", "creator economy"])
        chapters = [
            {"timestamp": "00:00", "title": "Hook"},
            {"timestamp": "00:45", "title": "Why this matters"},
            {"timestamp": "02:30", "title": "Framework"},
            {"timestamp": "05:00", "title": "Execution examples"},
            {"timestamp": "07:20", "title": "CTA"},
        ]
        description = (
            f"{title_text}\n\n"
            f"This video breaks down a practical {topic} framework for {audience} in {niche}. "
            f"You will get actionable examples, transitions, and retention checkpoints to apply today."
        )
        seo = {
            "description": description,
            "keywords": keywords,
            "hashtags": hashtags,
            "tags": tags[:15],
            "chapters": chapters,
        }
        self.database_service.insert_generated_seo(topic, seo)
        return seo

    def validate_content(self, package: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate package structure and required non-empty fields."""
        errors: list[str] = []
        if not str(package.get("topic", "")).strip():
            errors.append("topic is required")
        if not package.get("best_title"):
            errors.append("best_title is required")
        for section in ("thumbnail", "hook", "script", "seo"):
            if not isinstance(package.get(section), dict):
                errors.append(f"{section} is required")
        script = package.get("script", {})
        if isinstance(script, dict) and not script.get("sections"):
            errors.append("script.sections is required")
        return len(errors) == 0, errors

    def score_package(self, package: dict[str, Any]) -> float:
        """Score package quality across hook, script depth, and SEO completeness."""
        hook_score = float(package.get("hook", {}).get("retention_score", 0.0))
        script_sections = package.get("script", {}).get("sections", [])
        script_score = min(100.0, 60.0 + len(script_sections) * 10.0)
        seo = package.get("seo", {})
        seo_score = min(
            100.0,
            40.0
            + len(seo.get("keywords", [])) * 4.0
            + len(seo.get("hashtags", [])) * 5.0
            + len(seo.get("chapters", [])) * 4.0,
        )
        return round((hook_score + script_score + seo_score) / 3.0, 2)

    def _normalize_inputs(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize workflow payload to required generation inputs."""
        topic = str(payload.get("topic") or payload.get("title_topic") or payload.get("keyword") or "").strip()
        if not topic:
            raise ValueError("topic is required for content generation")
        return {
            "topic": topic,
            "audience": str(payload.get("audience") or "creators").strip(),
            "niche": str(payload.get("niche") or "youtube").strip(),
            "knowledge_base": list(payload.get("knowledge_entries") or payload.get("knowledge_base") or []),
            "pattern_report": payload.get("pattern_report") if isinstance(payload.get("pattern_report"), dict) else {},
            "generated_titles": list(payload.get("generated_titles") or []),
            "trend_info": payload.get("trend_info", payload.get("trend_data")),
        }


    def _build_hook_candidate(
        self,
        hook_type: str,
        topic: str,
        audience: str,
        niche: str,
        trend_terms: list[str],
    ) -> dict[str, Any]:
        """Create one hook candidate for a hook type."""
        trend = trend_terms[0] if trend_terms else "current trend"
        templates = {
            "Curiosity": f"What if your next {topic} video could outperform your last 10 combined?",
            "Shock": f"Most {audience} are silently killing growth with one {topic} mistake.",
            "Story": f"Last quarter, a {niche} creator changed one line and transformed their {topic} results.",
            "Problem": f"If your {topic} videos are stalling, this hidden bottleneck is why.",
            "Transformation": f"Here is the exact system to go from inconsistent uploads to predictable {topic} wins.",
            "Question": f"Can you build a repeatable {topic} engine without burning out?",
            "Open Loop": f"In seven minutes I will show the one pattern behind the fastest {topic} channels in {trend}.",
        }
        return {"script": templates[hook_type], "hook_type": hook_type}

    def _score_hook(self, candidate: dict[str, Any], hooks_distribution: dict[str, Any]) -> dict[str, Any]:
        """Apply retention scoring from historical hook prevalence + priors."""
        hook_type = str(candidate["hook_type"])
        pattern_boost = float(hooks_distribution.get(hook_type, 0.0)) if isinstance(hooks_distribution, dict) else 0.0
        priors = {
            "Curiosity": 85.0,
            "Shock": 83.0,
            "Story": 82.0,
            "Problem": 80.0,
            "Transformation": 84.0,
            "Question": 81.0,
            "Open Loop": 87.0,
        }
        score = min(99.0, priors.get(hook_type, 75.0) + pattern_boost * 0.15)
        return {"script": candidate["script"], "hook_type": hook_type, "retention_score": round(score, 2)}

    def _top_pattern(self, report: dict[str, Any], key: str, fallback: str) -> str:
        """Return the top label from a pattern distribution."""
        values = report.get(key, {}) if isinstance(report, dict) else {}
        if not isinstance(values, dict) or not values:
            return fallback
        return str(max(values.items(), key=lambda item: float(item[1]))[0])

    def _thumbnail_text(self, title: str) -> str:
        """Create a concise thumbnail text overlay."""
        words = [word for word in title.replace(":", " ").split() if word]
        trimmed = " ".join(words[:4]).upper()
        return trimmed[:28] if trimmed else "WATCH THIS"

    def _palette_for_emotion(self, emotion: str) -> list[str]:
        """Select color palette based on intended emotional response."""
        emotion_lower = emotion.lower()
        if "shock" in emotion_lower or "fear" in emotion_lower:
            return ["#0F172A", "#DC2626", "#F8FAFC"]
        if "curiosity" in emotion_lower:
            return ["#111827", "#7C3AED", "#F59E0B"]
        return ["#0B3C5D", "#F95738", "#F4D35E"]

    def _knowledge_signals(self, knowledge_base: list[dict[str, Any]]) -> list[str]:
        """Extract top three knowledge patterns for script examples."""
        if not knowledge_base:
            return ["open loops", "pattern interrupts", "proof-backed storytelling"]
        ranked = sorted(
            knowledge_base,
            key=lambda item: (float(item.get("confidence", 0.0)), float(item.get("frequency", 0.0))),
            reverse=True,
        )
        picked = [str(item.get("pattern", "")).strip() for item in ranked if str(item.get("pattern", "")).strip()]
        while len(picked) < 3:
            picked.append("proof-backed storytelling")
        return picked[:3]

    def create_video_production_plan(self, script_plan: ScriptPlan) -> VideoProductionPlan:
        """Convert ScriptPlan scenes to VideoProductionPlan with sensible defaults.
        
        This creates a structured production plan that a future video-generation agent can consume.
        No LLM calls are made; defaults are applied for camera, animation, and transitions.
        """
        scenes = []
        total_duration = 0
        
        for scene_data in script_plan.scenes:
            scene_number = int(scene_data.get("scene_number", len(scenes) + 1))
            duration_seconds = int(scene_data.get("duration_seconds", 30))
            visual = str(scene_data.get("visual", ""))
            narration = str(scene_data.get("narration", ""))
            dialogue = str(scene_data.get("dialogue", ""))
            sfx = str(scene_data.get("sfx", ""))
            
            # Apply sensible defaults for production direction
            camera_direction = self._default_camera_direction(scene_number, visual)
            animation_direction = self._default_animation_direction(visual)
            transition = self._default_transition(scene_number)
            
            scene = VideoProductionScene(
                scene_number=scene_number,
                duration_seconds=duration_seconds,
                visual_description=visual,
                narration=narration,
                dialogue=dialogue,
                sound_effects=sfx,
                camera_direction=camera_direction,
                animation_direction=animation_direction,
                transition=transition,
            )
            scenes.append(scene)
            total_duration += duration_seconds
        
        # Use script intro as title base, or fallback to topic
        title = script_plan.intro[:50] + "..." if len(script_plan.intro) > 50 else script_plan.intro
        
        return VideoProductionPlan(
            title=title,
            total_duration_seconds=total_duration,
            scenes=scenes,
        )

    def _default_camera_direction(self, scene_number: int, visual: str) -> str:
        """Generate sensible camera direction based on scene position and visual content."""
        visual_lower = visual.lower()
        if "opening" in visual_lower or "intro" in visual_lower:
            return "Wide establishing shot, slow zoom in"
        elif "b-roll" in visual_lower or "screen share" in visual_lower:
            return "Static medium shot with picture-in-picture overlay"
        elif "comparison" in visual_lower or "before/after" in visual_lower:
            return "Split-screen with smooth pan across both sides"
        elif "end screen" in visual_lower or "cta" in visual_lower:
            return "Medium close-up, slight tilt up for engagement"
        elif scene_number == 1:
            return "Wide establishing shot"
        elif scene_number % 3 == 0:
            return "Close-up for emphasis"
        else:
            return "Medium shot, steady framing"

    def _default_animation_direction(self, visual: str) -> str:
        """Generate animation direction based on visual content."""
        visual_lower = visual.lower()
        if "b-roll" in visual_lower:
            return "Ken Burns effect: slow zoom and pan over footage"
        elif "screen share" in visual_lower or "diagram" in visual_lower:
            return "Fade in elements sequentially with highlight animations"
        elif "comparison" in visual_lower or "dashboard" in visual_lower:
            return "Animated data visualization with smooth transitions"
        elif "text overlay" in visual_lower or "graphics" in visual_lower:
            return "Text pop-in with subtle bounce animation"
        else:
            return "Smooth fade in/out with subtle motion"

    def _default_transition(self, scene_number: int) -> str:
        """Generate transition type based on scene position."""
        if scene_number == 1:
            return "Fade in from black"
        elif scene_number % 4 == 0:
            return "Hard cut for pacing change"
        elif scene_number % 3 == 0:
            return "Cross dissolve for smooth flow"
        else:
            return "Cut to next scene"

    def create_scene_asset_plan(self, video_production_plan: VideoProductionPlan) -> SceneAssetPlan:
        """Convert VideoProductionPlan scenes into deterministic asset requirements.
        
        Derives asset requirements from existing scene data without LLM calls or external APIs.
        """
        assets: list[SceneAsset] = []
        
        for scene in video_production_plan.scenes:
            visual_lower = scene.visual_description.lower()
            
            # Determine asset type from visual description
            if "b-roll" in visual_lower:
                asset_type = "b-roll"
            elif "screen share" in visual_lower or "diagram" in visual_lower:
                asset_type = "screen_capture"
            elif "comparison" in visual_lower or "before/after" in visual_lower:
                asset_type = "comparison_visual"
            elif "end screen" in visual_lower or "cta" in visual_lower:
                asset_type = "end_screen"
            else:
                asset_type = "host_footage"
            
            # Derive character from visual description
            character = "host" if "host" in visual_lower or "opening" in visual_lower else ""
            
            # Derive action from visual description
            action_parts = []
            if "opening" in visual_lower:
                action_parts.append("establishing shot")
            if "b-roll" in visual_lower:
                action_parts.append("show examples")
            if "screen share" in visual_lower or "diagram" in visual_lower:
                action_parts.append("demonstrate framework")
            if "comparison" in visual_lower or "dashboard" in visual_lower:
                action_parts.append("compare metrics")
            if "end screen" in visual_lower:
                action_parts.append("call to action")
            action = ", ".join(action_parts) if action_parts else "present content"
            
            # Derive position from camera direction
            position = ""
            if "wide" in scene.camera_direction.lower():
                position = "wide"
            elif "medium" in scene.camera_direction.lower():
                position = "medium"
            elif "close-up" in scene.camera_direction.lower():
                position = "close-up"
            elif "split-screen" in scene.camera_direction.lower():
                position = "split-screen"
            else:
                position = "medium"
            
            # Derive expression from emotion context
            expression = "neutral"
            if "curiosity" in visual_lower or "hook" in visual_lower:
                expression = "curious"
            elif "shock" in visual_lower or "problem" in visual_lower:
                expression = "concerned"
            elif "transformation" in visual_lower or "result" in visual_lower:
                expression = "confident"
            elif "end screen" in visual_lower or "cta" in visual_lower:
                expression = "engaging"
            
            asset = SceneAsset(
                asset_id=f"asset-scene-{scene.scene_number}",
                asset_type=asset_type,
                description=scene.visual_description,
                scene_number=scene.scene_number,
                character=character,
                action=action,
                position=position,
                expression=expression,
                duration_seconds=scene.duration_seconds,
            )
            assets.append(asset)
        
        return SceneAssetPlan(total_assets=len(assets), assets=assets)

    def create_visual_style_plan(self, video_production_plan: VideoProductionPlan, scene_asset_plan: SceneAssetPlan) -> VisualStylePlan:
        """Generate deterministic visual style and character consistency plan.
        
        Derives style guidance from existing scene and asset data without LLM calls or external APIs.
        """
        # Collect unique characters from assets
        unique_characters = {asset.character for asset in scene_asset_plan.assets if asset.character}
        
        # Create character specs - reuse generic placeholder if no specific characters found
        characters: list[CharacterSpec] = []
        
        if unique_characters:
            for char_name in sorted(unique_characters):
                # Derive visual style from asset type and position
                char_assets = [a for a in scene_asset_plan.assets if a.character == char_name]
                asset_types = {a.asset_type for a in char_assets}
                positions = {a.position for a in char_assets}
                expressions = {a.expression for a in char_assets if a.expression}
                
                # Determine visual style based on asset types
                if "host_footage" in asset_types:
                    visual_style = "photorealistic"
                    clothing = "casual professional"
                    color = "neutral palette"
                elif "screen_capture" in asset_types:
                    visual_style = "digital"
                    clothing = "N/A"
                    color = "brand colors"
                else:
                    visual_style = "clean vector"
                    clothing = "N/A"
                    color = "vibrant accent"
                
                # Determine default expression
                default_expression = list(expressions)[0] if expressions else "neutral"
                
                # Derive role from asset types
                if "host_footage" in asset_types:
                    role = "presenter"
                elif "screen_capture" in asset_types:
                    role = "instructor"
                else:
                    role = "supporting"
                
                character = CharacterSpec(
                    character_id=f"char-{char_name.lower().replace(' ', '-')}",
                    name=char_name.title(),
                    description=f"Main {role} character appearing across {len(char_assets)} scenes",
                    role=role,
                    visual_style=visual_style,
                    default_expression=default_expression,
                    color=color,
                    clothing=clothing,
                    consistency_notes=f"Maintain {visual_style} style throughout. Use {default_expression} expression by default.",
                )
                characters.append(character)
        else:
            # Generic placeholder character when no specific characters identified
            characters.append(CharacterSpec(
                character_id="char-generic-host",
                name="Generic Host",
                description="Default presenter character for scenes without specific character assignments",
                role="presenter",
                visual_style="photorealistic",
                default_expression="neutral",
                color="neutral palette",
                clothing="casual professional",
                consistency_notes="Maintain consistent appearance across all scenes. Use neutral expression by default.",
            ))
        
        # Derive art style from scene content
        has_b_roll = any("b-roll" in scene.visual_description.lower() for scene in video_production_plan.scenes)
        has_screen_share = any("screen share" in scene.visual_description.lower() for scene in video_production_plan.scenes)
        
        if has_b_roll and has_screen_share:
            art_style = "mixed media: live action + screen capture"
        elif has_b_roll:
            art_style = "live action with b-roll inserts"
        elif has_screen_share:
            art_style = "screen recording with overlays"
        else:
            art_style = "clean vector animation"
        
        # Derive background style
        background_style = "gradient background with subtle texture"
        
        # Derive lighting style
        lighting_style = "soft key light with fill"
        
        # Derive camera style from production plan
        camera_styles = [scene.camera_direction for scene in video_production_plan.scenes]
        if any("split-screen" in style.lower() for style in camera_styles):
            camera_style = "multi-angle with split-screen capability"
        elif any("close-up" in style.lower() for style in camera_styles):
            camera_style = "dynamic close-up to medium shots"
        else:
            camera_style = "steady medium to wide shots"
        
        # Consistency rules
        consistency_rules = [
            "Maintain consistent character appearance across all scenes",
            f"Use {art_style} throughout",
            "Keep lighting consistent: soft key light with fill",
            "Match color palette to brand colors",
            "Ensure smooth transitions between scenes",
        ]
        
        return VisualStylePlan(
            style_name="YouTube Educational Content",
            art_style=art_style,
            background_style=background_style,
            lighting_style=lighting_style,
            camera_style=camera_style,
            characters=characters,
            consistency_rules=consistency_rules,
        )

    def create_character_asset_plan(self, visual_style_plan: VisualStylePlan) -> CharacterAssetPlan:
        """Generate detailed character asset specifications from visual style plan.
        
        Creates reusable character specifications with deterministic reference prompts.
        """
        characters: list[CharacterAssetSpec] = []
        
        for char_spec in visual_style_plan.characters:
            # Derive body style from role and visual style
            if char_spec.role == "presenter":
                body_style = "standing upright, confident posture, gesturing naturally"
                head_style = "well-lit, centered in frame"
                face_style = "friendly and approachable, direct eye contact"
                pose_style = "natural presenter stance with occasional hand gestures"
            elif char_spec.role == "instructor":
                body_style = "seated at desk, professional posture"
                head_style = "well-lit, slightly off-center"
                face_style = "focused and informative, looking at screen"
                pose_style = "stationary, pointing at screen elements"
            else:
                body_style = "standard upright position"
                head_style = "centered in frame"
                face_style = "neutral expression"
                pose_style = "static position"
            
            # Derive colors from character spec
            if "neutral" in char_spec.color.lower():
                primary_color = "navy blue"
                secondary_color = "light gray"
            elif "brand" in char_spec.color.lower():
                primary_color = "brand primary"
                secondary_color = "brand secondary"
            elif "vibrant" in char_spec.color.lower():
                primary_color = "vibrant accent"
                secondary_color = "complementary tone"
            else:
                primary_color = "neutral"
                secondary_color = "accent"
            
            # Build deterministic reference prompt
            reference_prompt = (
                f"A {char_spec.visual_style} character design for {char_spec.name}, "
                f"a {char_spec.role} in a YouTube educational video. "
                f"{char_spec.description}. "
                f"Body style: {body_style}. "
                f"Face: {face_style}. "
                f"Wearing {char_spec.clothing}. "
                f"Color palette: {primary_color} and {secondary_color}. "
                f"Expression: {char_spec.default_expression}. "
                f"Maintain consistency across all scenes."
            )
            
            character_asset = CharacterAssetSpec(
                character_id=char_spec.character_id,
                name=char_spec.name,
                base_description=char_spec.description,
                body_style=body_style,
                head_style=head_style,
                face_style=face_style,
                pose_style=pose_style,
                clothing=char_spec.clothing,
                primary_color=primary_color,
                secondary_color=secondary_color,
                visual_style=char_spec.visual_style,
                default_expression=char_spec.default_expression,
                reference_prompt=reference_prompt,
                consistency_rules=[char_spec.consistency_notes],
            )
            characters.append(character_asset)
        
        # Global character rules
        global_character_rules = [
            "Maintain consistent character appearance across all scenes",
            "Use same character model for each unique character_id",
            "Ensure lighting matches scene lighting style",
            "Keep proportions consistent across all shots",
            "Apply color palette consistently",
        ]
        
        return CharacterAssetPlan(
            characters=characters,
            global_character_rules=global_character_rules,
        )

    def create_render_job_plan(self, video_production_plan: VideoProductionPlan, scene_asset_plan: SceneAssetPlan, character_asset_plan: CharacterAssetPlan) -> RenderJobPlan:
        """Generate provider-independent render job specifications.
        
        Creates deterministic render jobs from existing plans without LLM calls or external APIs.
        """
        jobs: list[RenderJobSpec] = []
        total_duration = 0
        
        # Build character lookup
        char_lookup = {char.character_id: char for char in character_asset_plan.characters}
        
        for scene in video_production_plan.scenes:
            # Find matching assets for this scene
            scene_assets = [a for a in scene_asset_plan.assets if a.scene_number == scene.scene_number]
            asset_ids = [a.asset_id for a in scene_assets]
            
            # Find character IDs for this scene - map character names to character IDs
            character_names = {a.character for a in scene_assets if a.character}
            character_ids = []
            for name in character_names:
                # Try to find matching character ID from character asset plan
                matching_id = next((cid for cid in char_lookup if cid.endswith(f"-{name.lower()}") or cid == f"char-{name.lower().replace(' ', '-')}"), None)
                if matching_id:
                    character_ids.append(matching_id)
                else:
                    # Fallback: use the name as-is if no matching ID found
                    character_ids.append(name)
            if not character_ids and char_lookup:
                # Fallback to first available character from character asset plan
                character_ids = [list(char_lookup.keys())[0]]
            
            # Determine render type from asset types
            asset_types = {a.asset_type for a in scene_assets}
            if "screen_capture" in asset_types:
                render_type = "screen_capture"
            elif "b-roll" in asset_types:
                render_type = "b-roll"
            elif "comparison_visual" in asset_types:
                render_type = "comparison"
            elif "end_screen" in asset_types:
                render_type = "end_screen"
            else:
                render_type = "host_footage"
            
            # Build visual prompt from existing data
            visual_prompt_parts = [
                f"Scene {scene.scene_number}: {scene.visual_description}",
                f"Art style: {character_asset_plan.characters[0].visual_style if character_asset_plan.characters else 'photorealistic'}",
            ]
            if character_ids:
                char_id = character_ids[0]
                if char_id in char_lookup:
                    char_spec = char_lookup[char_id]
                    visual_prompt_parts.append(f"Character: {char_spec.name}, {char_spec.clothing}, {char_spec.primary_color}")
                    visual_prompt_parts.append(f"Expression: {char_spec.default_expression}")
            visual_prompt = ". ".join(visual_prompt_parts)
            
            # Build audio requirements from scene data
            audio_parts = []
            if scene.narration:
                audio_parts.append(f"Narration: {scene.narration}")
            if scene.dialogue:
                audio_parts.append(f"Dialogue: {scene.dialogue}")
            if scene.sound_effects:
                audio_parts.append(f"SFX: {scene.sound_effects}")
            audio_requirements = ". ".join(audio_parts) if audio_parts else "No audio"
            
            job = RenderJobSpec(
                job_id=f"render-scene-{scene.scene_number}",
                scene_number=scene.scene_number,
                duration_seconds=scene.duration_seconds,
                render_type=render_type,
                character_ids=character_ids,
                asset_ids=asset_ids,
                visual_prompt=visual_prompt,
                animation_instructions=scene.animation_direction,
                camera_instructions=scene.camera_direction,
                audio_requirements=audio_requirements,
            )
            jobs.append(job)
            total_duration += scene.duration_seconds
        
        return RenderJobPlan(
            total_jobs=len(jobs),
            jobs=jobs,
            total_duration_seconds=total_duration,
        )

