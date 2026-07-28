"""
Analysis prompt for YouTube AI Research System.

This module contains the prompt template used to instruct the LLM
to analyze video transcripts and extract structured insights.
"""

ANALYSIS_PROMPT = """You are an expert YouTube video analyst. Your task is to analyze the provided video transcript and extract structured insights about the video's content, style, and strategy.

Analyze the following transcript and provide a JSON response with these exact fields:

{{
  "hook_type": "Type of hook used in the opening (e.g., 'question', 'statistic', 'story', 'controversy', 'promise')",
  "opening_summary": "Brief 1-2 sentence summary of how the video opens",
  "main_topic": "Primary topic or theme of the video",
  "sub_topics": ["List of 3-5 subtopics covered in the video"],
  "target_audience": "Intended audience (e.g., 'beginners', 'professionals', 'enthusiasts')",
  "emotion": "Emotional tone (e.g., 'excited', 'calm', 'urgent', 'inspiring')",
  "story_structure": "Narrative structure used (e.g., 'problem-solution', 'tutorial', 'listicle', 'case-study')",
  "title_formula": "Pattern/formula used in the title if observable (e.g., 'Number + Topic + Benefit')",
  "thumbnail_pattern": "Visual pattern in thumbnail if inferable (e.g., 'face + text overlay', 'before-after')",
  "retention_techniques": ["List of viewer retention techniques used (e.g., 'pattern interrupts', 'storytelling')"],
  "cta_type": "Type of call-to-action (e.g., 'direct', 'indirect', 'none')",
  "keywords": ["List of 5-10 key terms and phrases from the content"],
  "psychological_triggers": ["Psychological triggers identified (e.g., 'social proof', 'scarcity', 'authority')"],
  "value_proposition": "Main value offered to viewers in 1-2 sentences",
  "difficulty_level": "beginner, intermediate, advanced, or all_levels",
  "estimated_video_style": "Estimated production style (e.g., 'tutorial', 'vlog', 'animation', 'interview')",
  "summary": "Overall 2-3 sentence summary of the video content and purpose",
  "confidence_score": 0.0-1.0 (your confidence in this analysis based on transcript quality)
}}

TRANSCRIPT TO ANALYZE:
{transcript}

INSTRUCTIONS:
1. Base your analysis ONLY on the provided transcript
2. Be specific and actionable in your insights
3. If you cannot determine something, make a reasonable inference or use "unknown"
4. Ensure all JSON fields are present and properly formatted
5. Return ONLY valid JSON, no additional text or markdown

JSON RESPONSE:"""


def get_analysis_prompt(transcript: str, max_length: int = 8000) -> str:
    """
    Generate the analysis prompt for a given transcript.
    
    Args:
        transcript: Video transcript text to analyze
        max_length: Maximum transcript length to include (to avoid token limits)
        
    Returns:
        Formatted prompt string
    """
    # Truncate transcript if too long
    if len(transcript) > max_length:
        transcript = transcript[:max_length] + "...[truncated]"
    
    return ANALYSIS_PROMPT.format(transcript=transcript)