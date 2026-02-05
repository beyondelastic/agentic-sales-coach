"""
Azure Speech Service integration for real-time speech-to-text.
"""
import asyncio
import logging
from typing import List, Callable, Optional
import azure.cognitiveservices.speech as speechsdk

from src.config import config
from src.models.report import TranscriptSegment

logger = logging.getLogger(__name__)


class SpeechService:
    """
    Real-time speech-to-text service using Azure Speech SDK.
    Supports continuous recognition with callback-based transcript accumulation.
    """
    
    def __init__(self):
        """Initialize Speech Service with Azure credentials."""
        self.speech_config = speechsdk.SpeechConfig(
            subscription=config.settings.speech_key,
            region=config.settings.speech_region
        )
        
        # Configure for optimal quality
        self.speech_config.speech_recognition_language = "en-US"
        self.speech_config.set_property(
            speechsdk.PropertyId.SpeechServiceResponse_RequestSentenceBoundary,
            "true"
        )
        
        # Enable detailed output
        self.speech_config.output_format = speechsdk.OutputFormat.Detailed
        
        self.recognizer: Optional[speechsdk.SpeechRecognizer] = None
        self.segments: List[TranscriptSegment] = []
        self.full_transcript: str = ""
        self.is_recognizing: bool = False
        self.start_time: float = 0
        
        # Callbacks
        self.on_partial_result: Optional[Callable[[str], None]] = None
        self.on_final_result: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
    
    def _setup_recognizer(self):
        """Set up speech recognizer with event handlers."""
        # Use default microphone
        audio_config = speechsdk.AudioConfig(use_default_microphone=True)
        
        self.recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config,
            audio_config=audio_config
        )
        
        # Configure event handlers
        self.recognizer.recognizing.connect(self._on_recognizing)
        self.recognizer.recognized.connect(self._on_recognized)
        self.recognizer.session_started.connect(self._on_session_started)
        self.recognizer.session_stopped.connect(self._on_session_stopped)
        self.recognizer.canceled.connect(self._on_canceled)
    
    def _on_recognizing(self, evt: speechsdk.SpeechRecognitionEventArgs):
        """Handle interim recognition results."""
        if evt.result.reason == speechsdk.ResultReason.RecognizingSpeech:
            text = evt.result.text
            logger.debug(f"Recognizing: {text}")
            
            # Callback for partial results (optional real-time display)
            if self.on_partial_result:
                self.on_partial_result(text)
    
    def _on_recognized(self, evt: speechsdk.SpeechRecognitionEventArgs):
        """Handle final recognition results."""
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = evt.result.text
            
            if text.strip():  # Only process non-empty results
                # Calculate timestamp
                offset_seconds = evt.result.offset / 10_000_000  # Convert from ticks
                
                # Get confidence score if available
                confidence = None
                if hasattr(evt.result, 'best') and evt.result.best:
                    confidence = evt.result.best[0].confidence if evt.result.best else None
                
                # Store segment
                segment = TranscriptSegment(
                    text=text,
                    timestamp=offset_seconds,
                    confidence=confidence
                )
                self.segments.append(segment)
                
                # Append to full transcript
                self.full_transcript += text + " "
                
                logger.info(f"Recognized: {text}")
                
                # Callback for final segment
                if self.on_final_result:
                    self.on_final_result(text)
        
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            logger.debug("No speech could be recognized")
    
    def _on_session_started(self, evt: speechsdk.SessionEventArgs):
        """Handle session start."""
        logger.info("Speech recognition session started")
        self.is_recognizing = True
        import time
        self.start_time = time.time()
    
    def _on_session_stopped(self, evt: speechsdk.SessionEventArgs):
        """Handle session stop."""
        logger.info("Speech recognition session stopped")
        self.is_recognizing = False
    
    def _on_canceled(self, evt: speechsdk.SpeechRecognitionCanceledEventArgs):
        """Handle recognition cancellation or errors."""
        logger.warning(f"Recognition canceled: {evt.reason}")
        
        if evt.reason == speechsdk.CancellationReason.Error:
            error_msg = f"Error: {evt.error_details}"
            logger.error(error_msg)
            
            if self.on_error:
                self.on_error(error_msg)
        
        self.is_recognizing = False
    
    def start_continuous_recognition(self):
        """
        Start continuous speech recognition.
        Accumulates transcript until stop_continuous_recognition is called.
        """
        logger.info("Starting continuous speech recognition")
        
        # Reset state
        self.segments = []
        self.full_transcript = ""
        
        # Setup and start recognizer
        self._setup_recognizer()
        self.recognizer.start_continuous_recognition()
        
        logger.info("Listening... Speak into your microphone")
    
    def stop_continuous_recognition(self) -> tuple[str, List[TranscriptSegment], float]:
        """
        Stop continuous speech recognition and return accumulated transcript.
        
        Returns:
            tuple: (full_transcript, segments, duration_seconds)
        """
        logger.info("Stopping continuous speech recognition")
        
        if self.recognizer:
            self.recognizer.stop_continuous_recognition()
        
        import time
        duration = time.time() - self.start_time if self.start_time else 0
        
        # Clean up transcript
        transcript = self.full_transcript.strip()
        
        logger.info(f"Recognition complete. Transcript length: {len(transcript)} characters")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Segments captured: {len(self.segments)}")
        
        return transcript, self.segments, duration
    
    async def recognize_from_microphone_async(self) -> str:
        """
        Async wrapper for one-time microphone recognition.
        Useful for simple use cases.
        
        Returns:
            str: Recognized text
        """
        audio_config = speechsdk.AudioConfig(use_default_microphone=True)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config,
            audio_config=audio_config
        )
        
        logger.info("Listening for speech...")
        
        # Run recognition in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            recognizer.recognize_once
        )
        
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            logger.info(f"Recognized: {result.text}")
            return result.text
        elif result.reason == speechsdk.ResultReason.NoMatch:
            logger.warning("No speech could be recognized")
            return ""
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            logger.error(f"Recognition canceled: {cancellation.reason}")
            if cancellation.reason == speechsdk.CancellationReason.Error:
                logger.error(f"Error details: {cancellation.error_details}")
            raise Exception(f"Speech recognition failed: {cancellation.error_details}")
        
        return ""
    
    def get_current_transcript(self) -> str:
        """Get the current accumulated transcript without stopping recognition."""
        return self.full_transcript.strip()
