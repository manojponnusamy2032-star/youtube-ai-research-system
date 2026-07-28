"""
Analysis service for YouTube AI Research System.

This module handles transcript analysis using LLM integration,
including prompt preparation, JSON validation, and result normalization.
"""

import json
import logging
import re
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod

from src.models.analysis import Analysis, DifficultyLevel
from src.models.transcript import Transcript
from src.database.database_service import DatabaseService
from src.prompts.analysis_prompt import get_analysis_prompt

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """Custom exception for LLM provider errors."""
    pass


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    Implement this interface to add support for different LLM providers
    (Ollama, OpenAI, Groq, etc.)
    """
    
    @abstractmethod
    def generate(self, prompt: str, max_retries: int = 3) -> str:
        """
        Generate a response from the LLM.
        
        Args:
            prompt: The prompt to send to the LLM
            max_retries: Maximum number of retry attempts
            
        Returns:
            LLM response as string
            
        Raises:
            LLMProviderError: If generation fails after all retries
        """
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """
        Get the name/version of the model being used.
        
        Returns:
            Model name string
        """
        pass


class OllamaProvider(LLMProvider):
    """
    LLM provider implementation for Ollama.
    
    Supports local LLM inference via Ollama API.
    """
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2:latest") -> None:
        """
        Initialize Ollama provider.
        
        Args:
            base_url: Ollama API base URL
            model: Model name to use
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        logger.info(f"Ollama provider initialized: {base_url} (model: {model})")
    
    def generate(self, prompt: str, max_retries: int = 3) -> str:
        """
        Generate a response using Ollama API.
        
        Args:
            prompt: The prompt to send
            max_retries: Maximum retry attempts
            
        Returns:
            LLM response string
            
        Raises:
            LLMProviderError: If generation fails
        """
        import requests
        
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 2048
            }
        }
        
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(url, json=payload, timeout=120)
                response.raise_for_status()
                
                data = response.json()
                generated_text = data.get("response", "")
                
                if not generated_text:
                    raise LLMProviderError("Empty response from Ollama")
                
                return generated_text
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Ollama request failed (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    import time
                    time.sleep(2 ** attempt)
                else:
                    raise LLMProviderError(f"Ollama request failed after {max_retries} attempts: {e}")
    
    def get_model_name(self) -> str:
        """Get the model name."""
        return self.model


class AnalysisServiceError(Exception):
    """Custom exception for analysis service errors."""
    pass


class AnalysisService:
    """
    Service for analyzing video transcripts using LLM.
    
    Responsibilities:
    - Prepare transcript for analysis
    - Send prompt to LLM
    - Validate JSON response
    - Normalize fields
    - Save results to database
    
    Attributes:
        llm_provider: LLM provider instance
        database_service: Database service instance
    """
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        database_service: DatabaseService
    ) -> None:
        """
        Initialize the analysis service.
        
        Args:
            llm_provider: LLM provider instance
            database_service: Database service instance
        """
        self.llm_provider = llm_provider
        self.database_service = database_service
        logger.info(f"Analysis service initialized with {llm_provider.get_model_name()}")
    
    def _prepare_transcript(self, transcript: Transcript) -> str:
        """
        Prepare transcript for analysis.
        
        Args:
            transcript: Transcript model instance
            
        Returns:
            Prepared transcript text
        """
        # For now, just return the transcript text
        # Could add preprocessing, summarization, etc. here
        return transcript.transcript
    
    def _extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """
        Extract JSON from LLM response.
        
        Handles cases where LLM wraps JSON in markdown code blocks
        or adds extra text before/after the JSON.
        
        Args:
            response: Raw LLM response string
            
        Returns:
            Parsed JSON dictionary
            
        Raises:
            AnalysisServiceError: If JSON cannot be extracted
        """
        # Try to find JSON in markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'(\{.*\})', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response
        
        # Clean up common issues
        json_str = json_str.strip()
        
        # Remove trailing commas (common LLM mistake)
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}\nResponse: {response[:500]}")
            raise AnalysisServiceError(f"Invalid JSON response from LLM: {e}")
    
    def _normalize_analysis(self, data: Dict[str, Any], video_id: str, model_name: str) -> Analysis:
        """
        Normalize and validate analysis data.
        
        Args:
            data: Raw analysis dictionary from LLM
            video_id: YouTube video ID
            model_name: Name of the LLM model used
            
        Returns:
            Validated Analysis model instance
            
        Raises:
            AnalysisServiceError: If validation fails
        """
        try:
            # Ensure list fields are lists
            list_fields = ['sub_topics', 'retention_techniques', 'keywords', 'psychological_triggers']
            for field in list_fields:
                if field in data:
                    if isinstance(data[field], str):
                        # Try to parse as JSON list
                        try:
                            data[field] = json.loads(data[field])
                        except json.JSONDecodeError:
                            # Split by comma if it's a comma-separated string
                            data[field] = [item.strip() for item in data[field].split(',') if item.strip()]
                    elif not isinstance(data[field], list):
                        data[field] = [str(data[field])]
            
            # Normalize difficulty_level
            if 'difficulty_level' in data:
                difficulty = data['difficulty_level'].lower().replace(' ', '_')
                if difficulty not in ['beginner', 'intermediate', 'advanced', 'all_levels']:
                    difficulty = 'all_levels'
                data['difficulty_level'] = difficulty
            
            # Ensure confidence_score is a float
            if 'confidence_score' in data:
                try:
                    data['confidence_score'] = float(data['confidence_score'])
                    # Clamp to valid range
                    data['confidence_score'] = max(0.0, min(1.0, data['confidence_score']))
                except (ValueError, TypeError):
                    data['confidence_score'] = 0.5
            
            # Create Analysis model
            analysis = Analysis(
                video_id=video_id,
                **data,
                analysis_model=model_name
            )
            
            return analysis
            
        except Exception as e:
            logger.error(f"Failed to normalize analysis data: {e}\nData: {data}")
            raise AnalysisServiceError(f"Failed to validate analysis: {e}")
    
    def analyze_transcript(self, transcript: Transcript) -> Analysis:
        """
        Analyze a single transcript.
        
        Args:
            transcript: Transcript model instance to analyze
            
        Returns:
            Analysis model instance with results
            
        Raises:
            AnalysisServiceError: If analysis fails
        """
        video_id = transcript.video_id
        logger.info(f"Analyzing transcript for video: {video_id}")
        
        # Prepare transcript
        prepared_text = self._prepare_transcript(transcript)
        
        # Generate prompt
        prompt = get_analysis_prompt(prepared_text)
        
        # Send to LLM
        try:
            response = self.llm_provider.generate(prompt)
        except Exception as e:
            logger.error(f"LLM generation failed for {video_id}: {e}")
            raise AnalysisServiceError(f"LLM generation failed: {e}")
        
        # Extract and parse JSON
        try:
            data = self._extract_json_from_response(response)
        except Exception as e:
            logger.error(f"Failed to extract JSON from LLM response for {video_id}: {e}")
            raise AnalysisServiceError(f"Failed to parse LLM response: {e}")
        
        # Normalize and validate
        try:
            analysis = self._normalize_analysis(data, video_id, self.llm_provider.get_model_name())
        except Exception as e:
            logger.error(f"Failed to normalize analysis for {video_id}: {e}")
            raise AnalysisServiceError(f"Failed to validate analysis: {e}")
        
        logger.info(f"Analysis completed for {video_id} (confidence: {analysis.confidence_score:.2f})")
        return analysis
    
    def save_analysis(self, analysis: Analysis) -> bool:
        """
        Save analysis to database.
        
        Args:
            analysis: Analysis model instance to save
            
        Returns:
            True if saved, False if duplicate
        """
        return self.database_service.insert_analysis(analysis)
    
    def process_transcript(self, transcript: Transcript) -> tuple[bool, Optional[str]]:
        """
        Process a single transcript: analyze and save.
        
        Args:
            transcript: Transcript model instance to process
            
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        video_id = transcript.video_id
        
        # Check if analysis already exists
        if self.database_service.analysis_exists(video_id):
            logger.info(f"Analysis already exists for {video_id}")
            return True, "already_exists"
        
        # Analyze transcript
        try:
            analysis = self.analyze_transcript(transcript)
        except AnalysisServiceError as e:
            logger.error(f"Analysis failed for {video_id}: {e}")
            return False, str(e)
        
        # Save analysis
        try:
            saved = self.save_analysis(analysis)
            if saved:
                logger.info(f"Saved analysis for {video_id}")
                return True, None
            else:
                logger.warning(f"Duplicate analysis skipped: {video_id}")
                return True, "duplicate"
        except Exception as e:
            logger.error(f"Failed to save analysis for {video_id}: {e}")
            return False, str(e)