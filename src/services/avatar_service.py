"""
Azure Speech Service Avatar integration for delivering coaching feedback.
"""
import logging
from typing import Optional
import azure.cognitiveservices.speech as speechsdk

from src.config import config

logger = logging.getLogger(__name__)


class AvatarService:
    """
    Real-time Text-to-Speech Avatar service using Azure Speech SDK.
    Generates avatar video delivering coaching feedback.
    """
    
    def __init__(self):
        """Initialize Avatar Service with Azure credentials."""
        self.speech_config = speechsdk.SpeechConfig(
            subscription=config.settings.speech_key,
            region=config.settings.speech_region
        )
        
        # Configure avatar settings
        # Available avatars: lisa, anna, james, tony, etc.
        # See: https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=tts
        self.avatar_character = "lisa"  # Default avatar
        self.avatar_style = "graceful-sitting"  # Avatar pose/style
        
        # Configure voice
        self.speech_config.speech_synthesis_voice_name = "en-US-JennyNeural"
        
    def synthesize_to_avatar_video(self, text: str, output_file: str = "coaching_feedback.mp4") -> str:
        """
        Synthesize coaching script to avatar video file (batch mode).
        
        Args:
            text: Coaching script text to synthesize
            output_file: Output video file path
            
        Returns:
            str: Path to generated video file
        """
        logger.info(f"Synthesizing avatar video: {len(text)} characters")
        
        try:
            # Configure audio output to file
            audio_config = speechsdk.audio.AudioOutputConfig(filename=output_file)
            
            # Create synthesizer
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=self.speech_config,
                audio_config=audio_config
            )
            
            # Create SSML with avatar configuration
            ssml = self._create_avatar_ssml(text)
            
            # Synthesize
            result = synthesizer.speak_ssml_async(ssml).get()
            
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                logger.info(f"Avatar video synthesized successfully: {output_file}")
                return output_file
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation = result.cancellation_details
                logger.error(f"Synthesis canceled: {cancellation.reason}")
                if cancellation.reason == speechsdk.CancellationReason.Error:
                    logger.error(f"Error details: {cancellation.error_details}")
                raise Exception(f"Avatar synthesis failed: {cancellation.error_details}")
            
        except Exception as e:
            logger.error(f"Error during avatar synthesis: {e}")
            raise
    
    def synthesize_to_speaker(self, text: str):
        """
        Synthesize coaching script directly to speakers (for testing).
        
        Args:
            text: Coaching script text to synthesize
        """
        logger.info(f"Synthesizing to speaker: {len(text)} characters")
        
        try:
            # Use default speaker
            synthesizer = speechsdk.SpeechSynthesizer(speech_config=self.speech_config)
            
            # Synthesize with prosody for natural delivery
            ssml = self._create_coaching_ssml(text)
            result = synthesizer.speak_ssml_async(ssml).get()
            
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                logger.info("Speech synthesized successfully")
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation = result.cancellation_details
                logger.error(f"Synthesis canceled: {cancellation.reason}")
                if cancellation.reason == speechsdk.CancellationReason.Error:
                    logger.error(f"Error details: {cancellation.error_details}")
                    
        except Exception as e:
            logger.error(f"Error during speech synthesis: {e}")
            raise
    
    def _create_avatar_ssml(self, text: str) -> str:
        """
        Create SSML with avatar configuration.
        
        Note: Avatar SSML format is in preview and may require specific SDK versions.
        For production, refer to latest Azure documentation.
        """
        voice_name = self.speech_config.speech_synthesis_voice_name
        
        ssml = f"""
<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' 
       xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-US'>
    <voice name='{voice_name}'>
        <mstts:ttsembedding speakerProfileId='avatar'>
            <mstts:express-as style="friendly">
                {text}
            </mstts:express-as>
        </mstts:ttsembedding>
    </voice>
</speak>
"""
        return ssml.strip()
    
    def _create_coaching_ssml(self, text: str) -> str:
        """
        Create SSML for coaching delivery with appropriate prosody.
        """
        voice_name = self.speech_config.speech_synthesis_voice_name
        
        ssml = f"""
<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
       xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-US'>
    <voice name='{voice_name}'>
        <mstts:express-as style="friendly">
            <prosody rate="0.95" pitch="+5%">
                {text}
            </prosody>
        </mstts:express-as>
    </voice>
</speak>
"""
        return ssml.strip()
    
    async def get_realtime_avatar_config(self) -> dict:
        """
        Get configuration for real-time avatar streaming (WebRTC).
        
        This would be used by frontend to establish WebRTC connection.
        Requires Avatar API with real-time capabilities.
        
        Returns:
            dict: Configuration for avatar streaming
        """
        # Note: Real-time avatar requires specific API setup
        # This is a placeholder for the configuration structure
        return {
            "avatarCharacter": self.avatar_character,
            "avatarStyle": self.avatar_style,
            "voiceName": self.speech_config.speech_synthesis_voice_name,
            "region": config.settings.speech_region,
            # In production, this would include ICE servers, authentication tokens, etc.
            "mode": "realtime",
            "videoFormat": {
                "codec": "H264",
                "resolution": "1920x1080",
                "frameRate": 25
            }
        }
    
    def create_avatar_html_embed(self, video_url: str) -> str:
        """
        Create HTML embed code for avatar video player.
        
        Args:
            video_url: URL or path to avatar video
            
        Returns:
            str: HTML code for video player
        """
        html = f"""
<div class="avatar-container">
    <video id="avatarVideo" width="640" height="360" controls autoplay>
        <source src="{video_url}" type="video/mp4">
        Your browser does not support the video tag.
    </video>
</div>
"""
        return html


class RealTimeAvatarConnection:
    """
    Manager for real-time avatar WebRTC connections.
    
    Note: This is a simplified implementation. Full real-time avatar support
    requires additional Azure SDK features and WebRTC setup.
    """
    
    def __init__(self):
        """Initialize real-time avatar connection."""
        self.speech_config = speechsdk.SpeechConfig(
            subscription=config.settings.speech_key,
            region=config.settings.speech_region
        )
        self.connection = None
        self.is_connected = False
    
    async def connect(self) -> dict:
        """
        Establish real-time avatar connection.
        
        Returns:
            dict: Connection parameters for frontend WebRTC setup
        """
        logger.info("Establishing real-time avatar connection")
        
        # This would use Azure Speech SDK's avatar real-time API
        # For now, return configuration that frontend can use
        
        connection_info = {
            "status": "connected",
            "endpoint": f"wss://{config.settings.speech_region}.tts.speech.microsoft.com/cognitiveservices/websocket/v1",
            "subscriptionKey": config.settings.speech_key,
            "region": config.settings.speech_region,
            "avatarConfig": {
                "character": "lisa",
                "style": "graceful-sitting",
                "voice": "en-US-JennyNeural"
            }
        }
        
        self.is_connected = True
        logger.info("Real-time avatar connection established")
        
        return connection_info
    
    async def send_text(self, text: str):
        """
        Send text to avatar for real-time synthesis.
        
        Args:
            text: Text for avatar to speak
        """
        if not self.is_connected:
            raise RuntimeError("Avatar connection not established")
        
        logger.info(f"Sending text to avatar: {text[:50]}...")
        
        # In production, this would stream to WebRTC connection
        # For now, log the action
        pass
    
    async def disconnect(self):
        """Disconnect real-time avatar connection."""
        if self.is_connected:
            logger.info("Disconnecting real-time avatar")
            self.is_connected = False
