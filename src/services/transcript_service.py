"""
Transcript service for YouTube AI Research System.

This module handles transcript retrieval using a fallback chain:
1. youtube-transcript-api
2. yt-dlp captions
3. Download audio using yt-dlp
4. Transcribe locally using Faster-Whisper
"""

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from src.models.transcript import Transcript, TranscriptMethod, TranscriptStatus
from src.database.database_service import DatabaseService

logger = logging.getLogger(__name__)


class TranscriptServiceError(Exception):
    """Custom exception for transcript service errors."""
    pass


class TranscriptService:
    """
    Service for retrieving video transcripts with automatic fallback.
    
    Implements a four-step fallback chain to maximize transcript retrieval
    success rate. Each method is attempted in order until one succeeds.
    
    Attributes:
        database_service: Database service for storing transcripts
        downloads_dir: Directory for temporary audio downloads
    """
    
    def __init__(self, database_service: DatabaseService, downloads_dir: str = "downloads") -> None:
        """
        Initialize the transcript service.
        
        Args:
            database_service: Database service instance
            downloads_dir: Directory for temporary audio downloads
        """
        self.database_service = database_service
        self.downloads_dir = Path(downloads_dir)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Transcript service initialized")
    
    def get_transcript(self, video_id: str) -> Optional[Transcript]:
        """
        Retrieve a transcript using the fallback chain.
        
        Attempts each method in order:
        1. youtube-transcript-api
        2. yt-dlp captions
        3. Download audio via yt-dlp
        4. Transcribe with Faster-Whisper
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            Transcript if successful, None if all methods fail
        """
        # Method 1: youtube-transcript-api
        transcript = self._try_youtube_transcript_api(video_id)
        if transcript is not None:
            return transcript
        
        # Method 2: yt-dlp captions
        transcript = self._try_ytdlp_captions(video_id)
        if transcript is not None:
            return transcript
        
        # Method 3: Download audio + Faster-Whisper
        transcript = self._try_whisper(video_id)
        if transcript is not None:
            return transcript
        
        logger.warning(f"All transcript methods failed for video: {video_id}")
        return None
    
    def _try_youtube_transcript_api(self, video_id: str) -> Optional[Transcript]:
        """
        Attempt to get transcript using youtube-transcript-api.
        
        This is the fastest and most reliable method for videos that have
        manually uploaded or auto-generated captions.
        """
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            from youtube_transcript_api._errors import (
                NoTranscriptFound,
                TranscriptsDisabled,
                VideoUnavailable
            )
            
            logger.info(f"Method 1: Trying youtube-transcript-api for {video_id}")
            
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Try to find an English transcript first, then any transcript
            try:
                transcript_data = transcript_list.find_transcript(['en'])
            except NoTranscriptFound:
                # Try to get any manually created transcript, then any auto-generated
                try:
                    transcript_data = transcript_list.find_manually_created_transcript(
                        transcript_list._transcripts.keys()
                    )
                except (NoTranscriptFound, StopIteration):
                    # Fall back to any generated transcript
                    transcript_data = transcript_list.find_generated_transcript(
                        transcript_list._transcripts.keys()
                    )
            
            # Fetch the transcript segments
            segments = transcript_data.fetch()
            language = transcript_data.language_code
            
            # Combine segments into full text
            full_text = " ".join([segment['text'] for segment in segments])
            full_text = self._clean_transcript(full_text)
            
            logger.info(f"Method 1 succeeded for {video_id} (language: {language})")
            
            return Transcript(
                video_id=video_id,
                language=language,
                transcript=full_text,
                method=TranscriptMethod.YOUTUBE_API
            )
            
        except ImportError:
            logger.warning("youtube-transcript-api not installed")
            return None
        except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as e:
            logger.info(f"Method 1 failed for {video_id}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Method 1 error for {video_id}: {e}")
            return None
    
    def _try_ytdlp_captions(self, video_id: str) -> Optional[Transcript]:
        """
        Attempt to get transcript using yt-dlp captions.
        
        This method can access subtitle formats that youtube-transcript-api
        might not support.
        """
        try:
            import yt_dlp
            
            logger.info(f"Method 2: Trying yt-dlp captions for {video_id}")
            
            url = f"https://www.youtube.com/watch?v={video_id}"
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['en', 'en-US', 'en-GB'],
                'skip_download': True,
                'outtmpl': str(self.downloads_dir / '%(id)s.%(ext)s'),
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Check for subtitles
                subtitles = info.get('subtitles', {})
                automatic_captions = info.get('automatic_captions', {})
                
                # Try manually uploaded subtitles first
                for lang in ['en', 'en-US', 'en-GB']:
                    if lang in subtitles and subtitles[lang]:
                        caption_data = subtitles[lang]
                        # Try to get the vtt/srt format
                        text = self._extract_caption_text(caption_data)
                        if text:
                            logger.info(f"Method 2 succeeded for {video_id} (manual captions, lang: {lang})")
                            return Transcript(
                                video_id=video_id,
                                language=lang,
                                transcript=text,
                                method=TranscriptMethod.YTDLP_CAPTIONS
                            )
                
                # Try auto-generated captions
                for lang in ['en', 'en-US', 'en-GB', 'a-en']:
                    if lang in automatic_captions and automatic_captions[lang]:
                        caption_data = automatic_captions[lang]
                        text = self._extract_caption_text(caption_data)
                        if text:
                            logger.info(f"Method 2 succeeded for {video_id} (auto captions, lang: {lang})")
                            return Transcript(
                                video_id=video_id,
                                language='en',
                                transcript=text,
                                method=TranscriptMethod.YTDLP_CAPTIONS
                            )
                
                logger.info(f"Method 2 failed for {video_id}: no captions found")
                return None
                
        except ImportError:
            logger.warning("yt-dlp not installed")
            return None
        except Exception as e:
            logger.warning(f"Method 2 error for {video_id}: {e}")
            return None
    
    def _extract_caption_text(self, caption_data: list) -> Optional[str]:
        """
        Extract text from caption data (supports vtt and srt formats).
        
        Args:
            caption_data: List of caption format dictionaries
            
        Returns:
            Extracted text or None
        """
        import requests
        
        for fmt in caption_data:
            ext = fmt.get('ext', '')
            url = fmt.get('url', '')
            
            if not url:
                continue
            
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                content = response.text
                
                # Remove VTT/SRT timestamps and metadata
                text = re.sub(r'^\d+\n\d{2}:\d{2}:\d{2}[.,]\d{3} --> \d{2}:\d{2}:\d{2}[.,]\d{3}', '', content, flags=re.MULTILINE)
                text = re.sub(r'^\d{2}:\d{2}:\d{2}[.,]\d{3} --> \d{2}:\d{2}:\d{2}[.,]\d{3}', '', text, flags=re.MULTILINE)
                text = re.sub(r'<[^>]+>', '', text)
                text = re.sub(r'^WEBVTT.*$', '', text, flags=re.MULTILINE)
                text = re.sub(r'^Kind:.*$', '', text, flags=re.MULTILINE)
                text = re.sub(r'^Language:.*$', '', text, flags=re.MULTILINE)
                text = '\n'.join(line for line in text.split('\n') if line.strip())
                text = self._clean_transcript(text)
                
                if text.strip():
                    return text.strip()
                    
            except Exception as e:
                logger.debug(f"Failed to download caption format {ext}: {e}")
                continue
        
        return None
    
    def _try_whisper(self, video_id: str) -> Optional[Transcript]:
        """
        Attempt to download audio and transcribe using Faster-Whisper.
        
        This is the last resort method for videos without any captions.
        """
        audio_path: Optional[Path] = None
        
        try:
            import yt_dlp
            from faster_whisper import WhisperModel
            
            logger.info(f"Method 3: Trying Whisper transcription for {video_id}")
            
            url = f"https://www.youtube.com/watch?v={video_id}"
            
            # Download audio
            audio_path = self.downloads_dir / f"{video_id}.mp3"
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'format': 'bestaudio/best',
                'outtmpl': str(audio_path.with_suffix('')),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }],
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Check if audio file was created
            mp3_path = audio_path.with_suffix('.mp3')
            webm_path = audio_path.with_suffix('.webm')
            m4a_path = audio_path.with_suffix('.m4a')
            
            if mp3_path.exists():
                actual_audio = mp3_path
            elif webm_path.exists():
                actual_audio = webm_path
            elif m4a_path.exists():
                actual_audio = m4a_path
            else:
                # Try to find any audio file
                files = list(self.downloads_dir.glob(f"{video_id}.*"))
                if files:
                    actual_audio = files[0]
                else:
                    logger.warning(f"Method 3 failed for {video_id}: no audio file downloaded")
                    return None
            
            # Transcribe with Faster-Whisper
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, info = model.transcribe(str(actual_audio), language="en")
            
            # Combine segments into full text
            full_text = " ".join([segment.text for segment in segments])
            full_text = self._clean_transcript(full_text)
            
            logger.info(f"Method 3 succeeded for {video_id} (language: {info.language})")
            
            return Transcript(
                video_id=video_id,
                language=info.language,
                transcript=full_text,
                method=TranscriptMethod.WHISPER
            )
            
        except ImportError as e:
            logger.warning(f"Whisper dependency not available: {e}")
            return None
        except Exception as e:
            logger.warning(f"Method 3 error for {video_id}: {e}")
            return None
        finally:
            # Cleanup audio files
            if audio_path:
                for ext in ['.mp3', '.webm', '.m4a', '.wav', '.opus']:
                    p = audio_path.with_suffix(ext)
                    if p.exists():
                        try:
                            p.unlink()
                            logger.debug(f"Cleaned up audio file: {p}")
                        except OSError:
                            pass
    
    def _clean_transcript(self, text: str) -> str:
        """
        Clean and normalize transcript text.
        
        Args:
            text: Raw transcript text
            
        Returns:
            Cleaned transcript text
        """
        if not text:
            return ""
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Decode HTML entities using html module
        import html as html_module
        text = html_module.unescape(text)
        
        # Remove residual ampersands that are not part of valid entities
        text = text.replace('&', '').replace('&', '')
        
        # Remove leading/trailing whitespace per line
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)
        
        return text.strip()
    
    def save_transcript(self, transcript: Transcript) -> bool:
        """
        Save a transcript to the database.
        
        Args:
            transcript: Transcript to save
            
        Returns:
            True if saved, False if duplicate
        """
        return self.database_service.insert_transcript(transcript)
    
    def process_video(self, video_id: str) -> tuple[bool, Optional[str]]:
        """
        Process a single video: retrieve and save transcript.
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            Tuple of (success: bool, method_or_error: Optional[str])
        """
        # Check if transcript already exists
        if self.database_service.transcript_exists(video_id):
            logger.info(f"Transcript already exists for {video_id}")
            return True, "already_exists"
        
        # Retrieve transcript
        transcript = self.get_transcript(video_id)
        
        if transcript is None:
            # Save a failed transcript entry
            failed_transcript = Transcript(
                video_id=video_id,
                language="en",
                transcript="",
                method=TranscriptMethod.YOUTUBE_API,
                status=TranscriptStatus.FAILED
            )
            self.save_transcript(failed_transcript)
            logger.warning(f"Failed to retrieve transcript for {video_id}")
            return False, None
        
        # Save transcript
        self.save_transcript(transcript)
        logger.info(f"Saved transcript for {video_id} (method: {transcript.method.value})")
        return True, transcript.method.value