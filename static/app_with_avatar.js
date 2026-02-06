/**
 * AI Sales Coach - Frontend JavaScript with Real-time Avatar
 */

// Session variables
let sessionId = null;
let isRecording = false;
let startTime = null;
let transcriptAccumulator = "";

// Avatar variables
let avatarSynthesizer = null;
let peerConnection = null;
let avatarVideoElement = null;
let isAvatarConnected = false;
let avatarConfig = null;

// Interactive mode variables
let interactiveWebSocket = null;
let isInteractiveMode = false;
let lastTranscriptSent = "";
let pauseTimer = null;
let lastSpeechTime = Date.now();
let hasRespondedToCurrentText = false;
let avatarIsSpeaking = false;  // Track when avatar is talking
let shouldRestartRecognition = true;  // Control auto-restart of recognition
let currentUtterance = "";  // Track current speaking segment
let recentAvatarSpeech = [];  // Track recent avatar utterances to filter feedback
let avatarSpeechEndTime = 0;  // Track when avatar finished speaking

// Speech Recognition setup
let recognition = null;
if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
} else if ('SpeechRecognition' in window) {
    recognition = new SpeechRecognition();
}

if (recognition) {
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
    
    // Try to enable echo cancellation (browser-dependent)
    try {
        recognition.maxAlternatives = 1;
    } catch (e) {
        console.log('Could not set maxAlternatives:', e);
    }
    
    recognition.onstart = function() {
        console.log('Speech recognition started');
    };
    
    recognition.onresult = function(event) {
        // Don't process if avatar is currently speaking OR just finished recently
        const timeSinceAvatarSpeech = Date.now() - avatarSpeechEndTime;
        if (avatarIsSpeaking || timeSinceAvatarSpeech < 3000) {
            console.log(`🚫 Blocked - avatar speaking: ${avatarIsSpeaking}, time since speech: ${timeSinceAvatarSpeech}ms`);
            return;
        }
        
        let interimTranscript = '';
        let finalTranscript = '';
        
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += transcript + ' ';
            } else {
                interimTranscript += transcript;
            }
        }
        
        if (finalTranscript) {
            // Check if this matches recent avatar speech (feedback detection)
            const cleanTranscript = finalTranscript.trim().toLowerCase();
            const isAvatarEcho = recentAvatarSpeech.some(avatarText => {
                const similarity = stringSimilarity(cleanTranscript, avatarText.toLowerCase());
                return similarity > 0.7;  // 70% similarity = likely echo
            });
            
            if (isAvatarEcho) {
                console.log('🚫 Filtered out avatar echo:', finalTranscript.substring(0, 50) + '...');
                return;
            }
            
            transcriptAccumulator += finalTranscript;
            currentUtterance += finalTranscript;  // Add to current speaking segment
            lastSpeechTime = Date.now();
            hasRespondedToCurrentText = false;  // New speech, haven't responded yet
            
            // Send to WebSocket in interactive mode
            if (isInteractiveMode && interactiveWebSocket && interactiveWebSocket.readyState === WebSocket.OPEN) {
                const newText = transcriptAccumulator.substring(lastTranscriptSent.length).trim();
                if (newText) {
                    interactiveWebSocket.send(JSON.stringify({
                        type: "transcript_update",
                        text: newText
                    }));
                    lastTranscriptSent = transcriptAccumulator;
                }
            }
            
            // Reset pause timer
            if (pauseTimer) {
                clearTimeout(pauseTimer);
            }
            
            // Only detect pause if in interactive mode and haven't responded yet
            if (isInteractiveMode && interactiveWebSocket && 
                interactiveWebSocket.readyState === WebSocket.OPEN && 
                !hasRespondedToCurrentText) {
                
                // Wait 6 seconds of silence before avatar considers responding
                pauseTimer = setTimeout(() => {
                    const textToRespond = transcriptAccumulator.substring(lastTranscriptSent.length - transcriptAccumulator.length).trim();
                    
                    // Only send if there's substantial content (more than 10 words for better context)
                    if (textToRespond.split(' ').length >= 10) {
                        hasRespondedToCurrentText = true;
                        
                        // Create a new bubble for the completed utterance
                        if (currentUtterance.trim()) {
                            createUserBubble(currentUtterance.trim());
                            currentUtterance = "";  // Reset for next utterance
                        }
                        
                        interactiveWebSocket.send(JSON.stringify({
                            type: "pause_detected",
                            recent_text: textToRespond
                        }));
                    }
                }, 6000);  // Increased to 6 seconds - longer pauses mean clearer turn-taking
            }
        }
        
        // Show current utterance + interim text (live update)
        updateTranscriptDisplay(currentUtterance + interimTranscript);
    };
    
    recognition.onerror = function(event) {
        console.error('Speech recognition error:', event.error);
        showError('Speech recognition error: ' + event.error);
    };
    
    recognition.onend = function() {
        console.log('Speech recognition ended');
        if (isRecording && shouldRestartRecognition) {
            console.log('Auto-restarting recognition');
            recognition.start();
        } else {
            console.log('Not restarting - shouldRestartRecognition:', shouldRestartRecognition);
        }
    };
}

// ============================================================================
// AVATAR FUNCTIONS
// ============================================================================

// Helper function to calculate string similarity (Levenshtein distance based)
function stringSimilarity(str1, str2) {
    const longer = str1.length > str2.length ? str1 : str2;
    const shorter = str1.length > str2.length ? str2 : str1;
    
    if (longer.length === 0) return 1.0;
    
    const editDistance = levenshteinDistance(longer, shorter);
    return (longer.length - editDistance) / longer.length;
}

function levenshteinDistance(str1, str2) {
    const matrix = [];
    
    for (let i = 0; i <= str2.length; i++) {
        matrix[i] = [i];
    }
    
    for (let j = 0; j <= str1.length; j++) {
        matrix[0][j] = j;
    }
    
    for (let i = 1; i <= str2.length; i++) {
        for (let j = 1; j <= str1.length; j++) {
            if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
                matrix[i][j] = matrix[i - 1][j - 1];
            } else {
                matrix[i][j] = Math.min(
                    matrix[i - 1][j - 1] + 1,
                    matrix[i][j - 1] + 1,
                    matrix[i - 1][j] + 1
                );
            }
        }
    }
    
    return matrix[str2.length][str1.length];
}

async function connectAvatar() {
    console.log('Connecting to avatar...');
    updateAvatarStatus('🔄 Initializing avatar connection...');
    
    try {
        // Get avatar configuration from backend
        updateAvatarStatus('🔄 Requesting authentication token...');
        const configResponse = await fetch('/api/avatar/config');
        if (!configResponse.ok) {
            throw new Error('Failed to get avatar configuration');
        }
        
        avatarConfig = await configResponse.json();
        console.log('Avatar config received:', {
            region: avatarConfig.region,
            character: avatarConfig.avatar_character,
            style: avatarConfig.avatar_style,
            voice: avatarConfig.voice_name,
            hasKey: !!avatarConfig.subscription_key
        });
        
        // Step 1: Create SpeechConfig with voice
        updateAvatarStatus('🔄 Configuring speech synthesis...');
        const speechConfig = SpeechSDK.SpeechConfig.fromSubscription(
            avatarConfig.subscription_key,
            avatarConfig.region
        );
        speechConfig.speechSynthesisVoiceName = avatarConfig.voice_name || "en-US-JennyNeural";
        console.log('✓ SpeechConfig created');
        
        // Step 2: Fetch ICE server token
        updateAvatarStatus('🔄 Fetching WebRTC connection token...');
        const iceResponse = await fetch(
            `https://${avatarConfig.region}.tts.speech.microsoft.com/cognitiveservices/avatar/relay/token/v1`,
            {
                method: 'GET',
                headers: {
                    'Ocp-Apim-Subscription-Key': avatarConfig.subscription_key
                }
            }
        );
        
        if (!iceResponse.ok) {
            throw new Error(`ICE server request failed: ${iceResponse.status}`);
        }
        
        const iceData = await iceResponse.json();
        const iceServerUrl = iceData.Urls[0];
        const iceServerUsername = iceData.Username;
        const iceServerCredential = iceData.Password;
        console.log('✓ ICE server token received');
        
        // Step 3: Create AvatarConfig with remoteIceServers (CRITICAL!)
        const videoFormat = new SpeechSDK.AvatarVideoFormat();
        const sdkAvatarConfig = new SpeechSDK.AvatarConfig(
            "lisa",  // lowercase as per official samples
            avatarConfig.avatar_style || "casual-sitting",
            videoFormat
        );
        
        // CRITICAL: Set remoteIceServers BEFORE creating synthesizer
        sdkAvatarConfig.remoteIceServers = [{
            urls: [ iceServerUrl ],
            username: iceServerUsername,
            credential: iceServerCredential
        }];
        console.log('✓ AvatarConfig created with ICE servers');
        
        // Step 4: Create AvatarSynthesizer
        avatarSynthesizer = new SpeechSDK.AvatarSynthesizer(speechConfig, sdkAvatarConfig);
        console.log('✓ AvatarSynthesizer created');
        
        // Step 5: Setup WebRTC peer connection
        updateAvatarStatus('Establishing connection...');
        peerConnection = new RTCPeerConnection({
            iceServers: [{
                urls: [ iceServerUrl ],
                username: iceServerUsername,
                credential: iceServerCredential
            }]
        });
        
        // Monitor connection states
        peerConnection.oniceconnectionstatechange = () => {
            console.log('ICE connection state:', peerConnection.iceConnectionState);
            if (peerConnection.iceConnectionState === 'connected') {
                // Don't update status here - let the main flow handle it
                console.log('✓ Avatar WebRTC connected!');
            } else if (peerConnection.iceConnectionState === 'failed' || 
                       peerConnection.iceConnectionState === 'disconnected') {
                isAvatarConnected = false;
                updateAvatarStatus('⚠️ Disconnected');
            }
        };
        
        // Handle incoming video/audio tracks
        peerConnection.ontrack = (event) => {
            console.log('Track received:', event.track.kind);
            
            if (event.track.kind === 'video') {
                // Get the existing avatar video element (not container!)
                avatarVideoElement = document.getElementById('avatarVideo');
                if (!avatarVideoElement) {
                    console.error('Avatar video element not found!');
                    return;
                }
                
                // Set the stream directly on the existing video element
                avatarVideoElement.srcObject = event.streams[0];
                avatarVideoElement.muted = false;
                
                // Ensure video plays when ready
                avatarVideoElement.onloadedmetadata = () => {
                    console.log('Video metadata loaded, playing...');
                    avatarVideoElement.play().then(() => {
                        console.log('✓ Video playing successfully');
                    }).catch(err => {
                        console.error('Video play error:', err);
                    });
                };
                
                console.log('✓ Video stream connected to element');
                
            } else if (event.track.kind === 'audio') {
                // Create audio element (unmuted)
                const audioElement = document.createElement('audio');
                audioElement.srcObject = event.streams[0];
                audioElement.autoplay = true;
                audioElement.muted = false;
                document.body.appendChild(audioElement);
                console.log('✓ Audio track added');
            }
        };
        
        // Add transceivers
        peerConnection.addTransceiver('video', { direction: 'sendrecv' });
        peerConnection.addTransceiver('audio', { direction: 'sendrecv' });
        
        // Step 6: Start avatar
        updateAvatarStatus('🔄 Establishing WebRTC connection...');
        
        // Track if we've already succeeded via connection state
        let avatarReady = false;
        
        const result = await new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                // If ICE is connected and we have video, consider it successful
                if (peerConnection.iceConnectionState === 'connected' && avatarVideoElement) {
                    console.log('✓ Avatar connected via WebRTC (callback timeout bypassed)');
                    resolve({ reason: SpeechSDK.ResultReason.SynthesizingAudioCompleted });
                } else {
                    reject(new Error('Avatar start timeout - this can take 10-20 seconds, please wait'));
                }
            }, 30000); // 30 seconds is reasonable for Azure Speech SDK
            
            avatarSynthesizer.startAvatarAsync(peerConnection, (r) => {
                clearTimeout(timeout);
                console.log('✓ startAvatarAsync callback received');
                resolve(r);
            }, (err) => {
                clearTimeout(timeout);
                reject(err);
            });
        });
        
        if (result.reason === SpeechSDK.ResultReason.SynthesizingAudioCompleted) {
            console.log('✓ Avatar started successfully!');
            isAvatarConnected = true;
            updateAvatarStatus('✅ Avatar connected - Ready for interactive presentation');
            document.getElementById('connectAvatarBtn').disabled = true;
            document.getElementById('disconnectAvatarBtn').disabled = false;
            document.getElementById('avatarMessage').style.display = 'block';
            
            // Set up WebSocket for interactive mode
            setupInteractiveWebSocket();
            
            return true;
        } else if (result.reason === SpeechSDK.ResultReason.Canceled) {
            const details = SpeechSDK.CancellationDetails.fromResult(result);
            throw new Error(details.errorDetails);
        }
        
    } catch (error) {
        console.error('Error connecting avatar:', error);
        updateAvatarStatus('Connection failed');
        showError('Failed to connect avatar: ' + error.message);
        isAvatarConnected = false;
        return false;
    }
}

function setupInteractiveWebSocket() {
    console.log('Setting up interactive WebSocket...');
    
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/interactive`;
    
    interactiveWebSocket = new WebSocket(wsUrl);
    
    interactiveWebSocket.onopen = () => {
        console.log('✓ Interactive WebSocket connected');
        // Don't send start_session yet - wait for user to start recording
    };
    
    interactiveWebSocket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        console.log('WebSocket message:', message);
        
        if (message.type === 'avatar_speak') {
            // Set flag IMMEDIATELY before any processing to block speech recognition
            avatarIsSpeaking = true;
            console.log('Avatar about to speak - blocking mic input');
            
            // Track avatar speech for echo detection
            recentAvatarSpeech.push(message.text);
            // Keep only last 3 avatar utterances
            if (recentAvatarSpeech.length > 3) {
                recentAvatarSpeech.shift();
            }
            
            // Remove any live preview bubble before avatar speaks
            const livePreview = document.getElementById('transcriptBox').querySelector('[data-speaker="user-live"]');
            if (livePreview) {
                livePreview.remove();
            }
            
            // Make avatar speak and show in transcript
            updateTranscriptDisplay(message.text, 'Avatar');
            speakToAvatar(message.text);
        } else if (message.type === 'coaching_report') {
            // Display final coaching report
            displayReport(message.report);
            updateAvatarStatus('Coaching complete');
            resetUI();
        }
    };
    
    interactiveWebSocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        isInteractiveMode = false;
    };
    
    interactiveWebSocket.onclose = () => {
        console.log('Interactive WebSocket closed');
        isInteractiveMode = false;
    };
}

async function disconnectAvatar() {
    console.log('Disconnecting avatar...');
    updateAvatarStatus('Disconnecting...');
    
    // Close WebSocket
    if (interactiveWebSocket) {
        interactiveWebSocket.close();
        interactiveWebSocket = null;
        isInteractiveMode = false;
    }
    
    if (avatarSynthesizer) {
        await avatarSynthesizer.stopAvatarAsync();
        avatarSynthesizer.close();
        avatarSynthesizer = null;
    }
    
    if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
    }
    
    if (avatarVideoElement) {
        avatarVideoElement.srcObject = null;
    }
    
    isAvatarConnected = false;
    updateAvatarStatus('Disconnected');
    document.getElementById('connectAvatarBtn').disabled = false;
    document.getElementById('disconnectAvatarBtn').disabled = true;
    document.getElementById('avatarMessage').style.display = 'none';
    
    console.log('Avatar disconnected');
}

function speakToAvatar(text) {
    if (!avatarSynthesizer || !isAvatarConnected) {
        console.log('Avatar not connected, skipping speech');
        avatarIsSpeaking = false;  // Ensure flag is cleared
        return;
    }
    
    console.log('Avatar speaking:', text.substring(0, 50) + '...');
    
    // Flag should already be set by the caller, but ensure it's set
    avatarIsSpeaking = true;
    updateAvatarStatus('🗣️ Avatar speaking...');
    
    // CRITICAL: Stop speech recognition to prevent feedback
    if (recognition && isRecording) {
        console.log('🔇 Stopping speech recognition during avatar speech');
        shouldRestartRecognition = false;  // Prevent auto-restart
        recognition.stop();
    }
    
    avatarSynthesizer.speakTextAsync(text).then((result) => {
        if (result.reason === SpeechSDK.ResultReason.SynthesizingAudioCompleted) {
            console.log("Avatar speech completed - waiting for audio playback to finish");
            // INCREASED BUFFER: Wait longer for audio to fully finish playing
            // The synthesizer completes before audio finishes playing through speakers
            setTimeout(() => {
                avatarIsSpeaking = false;
                avatarSpeechEndTime = Date.now();  // Track when avatar finished
                updateAvatarStatus('👂 Listening...');
                console.log('Avatar audio playback complete - restarting mic in 1 second');
                
                // Add another delay before actually restarting to ensure audio is fully done
                setTimeout(() => {
                    shouldRestartRecognition = true;  // Re-enable auto-restart
                    if (isRecording && recognition) {
                        console.log('✅ Restarting speech recognition');
                        recognition.start();
                    }
                }, 1000);  // Additional 1 second buffer
            }, 3000);  // Increased to 3 seconds for audio playback completion
        } else {
            console.error("Avatar speech failed:", result.errorDetails);
            avatarIsSpeaking = false;
            shouldRestartRecognition = true;
            updateAvatarStatus('👂 Listening...');
            if (isRecording && recognition) {
                recognition.start();
            }
        }
    }).catch((error) => {
        console.error("Avatar speech error:", error);
        avatarIsSpeaking = false;
        shouldRestartRecognition = true;
        updateAvatarStatus('👂 Listening...');
        if (isRecording && recognition) {
            recognition.start();
        }
    });
}

function updateAvatarStatus(status) {
    const statusElement = document.getElementById('avatarStatus');
    if (statusElement) {
        statusElement.textContent = status;
    }
}

// ============================================================================
// RECORDING FUNCTIONS
// ============================================================================

async function startRecording() {
    if (!recognition) {
        showError('Speech recognition not supported in this browser. Please use Chrome or Edge.');
        return;
    }
    
    if (!isAvatarConnected) {
        showError('Please connect the avatar first before starting your presentation.');
        return;
    }
    
    try {
        // Request microphone permission
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach(track => track.stop());
        
        // Start new session
        const response = await fetch('/api/session/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            throw new Error('Failed to start session');
        }
        
        const data = await response.json();
        sessionId = data.session_id;
        
        // Signal WebSocket that session is starting
        if (interactiveWebSocket && interactiveWebSocket.readyState === WebSocket.OPEN) {
            isInteractiveMode = true;
            interactiveWebSocket.send(JSON.stringify({
                type: "start_session"
            }));
            console.log('Sent start_session signal');
        }
        
        // Reset state
        transcriptAccumulator = "";
        lastTranscriptSent = "";
        currentUtterance = "";  // Reset current utterance
        startTime = Date.now();
        isRecording = true;
        hasRespondedToCurrentText = false;
        
        // Update UI
        updateStatus('recording');
        document.getElementById('startBtn').disabled = true;
        document.getElementById('stopBtn').disabled = false;
        document.getElementById('reportContainer').classList.remove('visible');
        
        // Clear transcript display
        const box = document.getElementById('transcriptBox');
        box.innerHTML = '<span style="opacity: 0.5;">Your presentation transcript will appear here as you speak...</span>';
        
        // Update avatar
        updateAvatarStatus('Listening...');
        
        // Start speech recognition
        recognition.start();
        
        console.log('Recording started, session:', sessionId);
        
    } catch (error) {
        console.error('Error starting recording:', error);
        showError('Failed to start recording: ' + error.message);
    }
}

async function stopRecording() {
    if (!isRecording) return;
    
    isRecording = false;
    
    // Stop speech recognition
    if (recognition) {
        recognition.stop();
    }
    
    // Update UI
    updateStatus('analyzing');
    updateAvatarStatus('Analyzing presentation...');
    document.getElementById('stopBtn').disabled = true;
    
    // Calculate duration
    const duration = (Date.now() - startTime) / 1000;
    
    console.log('Recording stopped. Duration:', duration, 'seconds');
    console.log('Transcript:', transcriptAccumulator);
    
    if (!transcriptAccumulator.trim()) {
        showError('No speech detected. Please try again and speak into your microphone.');
        resetUI();
        updateAvatarStatus('Ready');
        return;
    }
    
    // In interactive mode, signal end via WebSocket
    if (isInteractiveMode && interactiveWebSocket && interactiveWebSocket.readyState === WebSocket.OPEN) {
        interactiveWebSocket.send(JSON.stringify({
            type: "end_presentation",
            duration: duration
        }));
        // Report will come back via WebSocket
        console.log('Sent end_presentation signal via WebSocket');
        return;
    }
    
    // Fallback to REST API for non-interactive mode
    try {
        const analyzeResponse = await fetch(`/api/session/${sessionId}/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                transcript: transcriptAccumulator,
                duration: duration
            })
        });
        
        if (!analyzeResponse.ok) {
            throw new Error('Analysis failed');
        }
        
        const analysisData = await analyzeResponse.json();
        console.log('Analysis complete:', analysisData);
        
        // Display report
        displayReport(analysisData.report);
        
        // Have avatar deliver coaching feedback
        updateAvatarStatus('Delivering coaching...');
        speakToAvatar(analysisData.coaching_script);
        
        // Wait for avatar to finish, then update status
        setTimeout(() => {
            updateAvatarStatus('Coaching complete');
        }, 5000);
        
        resetUI();
        
    } catch (error) {
        console.error('Error analyzing presentation:', error);
        showError('Failed to analyze presentation: ' + error.message);
        resetUI();
        updateAvatarStatus('Ready');
    }
}

// ============================================================================
// UI UPDATE FUNCTIONS
// ============================================================================

function createUserBubble(text) {
    const box = document.getElementById('transcriptBox');
    box.classList.remove('empty');
    
    const userMsg = document.createElement('div');
    userMsg.style.cssText = 'margin: 10px 0; padding: 10px; background: #e3f2fd; border-left: 3px solid #2196F3; border-radius: 4px;';
    userMsg.innerHTML = `<strong style="color: #2196F3;">You:</strong> ${text}`;
    box.appendChild(userMsg);
    box.scrollTop = box.scrollHeight;
}

function updateTranscriptDisplay(text, speaker = 'You') {
    const box = document.getElementById('transcriptBox');
    
    if (!text || !text.trim()) {
        box.innerHTML = '<span style="opacity: 0.5;">Your presentation transcript will appear here as you speak...</span>';
        box.classList.add('empty');
        return;
    }
    
    box.classList.remove('empty');
    
    if (speaker === 'Avatar') {
        // Create avatar message element
        const avatarMsg = document.createElement('div');
        avatarMsg.style.cssText = 'margin: 10px 0; padding: 10px; background: #e8f5e9; border-left: 3px solid #4CAF50; border-radius: 4px;';
        avatarMsg.innerHTML = `<strong style="color: #4CAF50;">🤖 Avatar:</strong> ${text}`;
        box.appendChild(avatarMsg);
        box.scrollTop = box.scrollHeight;
    } else {
        // Update live preview bubble (interim text)
        const existingUser = box.querySelector('[data-speaker="user-live"]');
        if (existingUser) {
            existingUser.remove();
        }
        if (text.trim()) {
            const userMsg = document.createElement('div');
            userMsg.setAttribute('data-speaker', 'user-live');
            userMsg.style.cssText = 'margin: 10px 0; padding: 10px; background: #e3f2fd; border-left: 3px solid #2196F3; border-radius: 4px; opacity: 0.7;';
            userMsg.innerHTML = `<strong style="color: #2196F3;">You:</strong> ${text}`;
            box.appendChild(userMsg);
            box.scrollTop = box.scrollHeight;
        }
    }
}

function updateStatus(status) {
    const badge = document.getElementById('statusBadge');
    badge.className = 'status-badge';
    
    switch(status) {
        case 'recording':
            badge.classList.add('status-recording');
            badge.textContent = '🔴 Recording';
            break;
        case 'analyzing':
            badge.classList.add('status-analyzing');
            badge.textContent = '🔄 Analyzing';
            break;
        default:
            badge.classList.add('status-idle');
            badge.textContent = 'Ready';
    }
}

function displayReport(report) {
    // Show report container
    document.getElementById('reportContainer').classList.add('visible');
    
    // Overall score
    document.getElementById('overallScore').textContent = report.overall_score.toFixed(1) + '/10';
    
    const levelElement = document.getElementById('performanceLevel');
    levelElement.textContent = report.performance_level.replace('_', ' ');
    levelElement.className = 'performance-level level-' + report.performance_level;
    
    // Criteria scores
    const criteriaGrid = document.getElementById('criteriaGrid');
    criteriaGrid.innerHTML = '';
    
    for (const [key, value] of Object.entries(report.criteria_scores)) {
        const div = document.createElement('div');
        div.className = 'criterion';
        div.innerHTML = `
            <div class="criterion-name">${key.replace(/_/g, ' ')}</div>
            <div class="criterion-score">${value.toFixed(1)}/10</div>
        `;
        criteriaGrid.appendChild(div);
    }
    
    // Strengths
    const strengthsList = document.getElementById('strengthsList');
    strengthsList.innerHTML = '';
    report.strengths.forEach(strength => {
        const div = document.createElement('div');
        div.className = 'list-item';
        div.textContent = strength;
        strengthsList.appendChild(div);
    });
    
    // Improvements
    const improvementsList = document.getElementById('improvementsList');
    improvementsList.innerHTML = '';
    report.improvements.forEach(item => {
        const div = document.createElement('div');
        div.className = 'list-item improvement-item';
        div.innerHTML = `
            <div class="item-title">${item.area}</div>
            <div class="item-detail"><strong>Current:</strong> ${item.current_state}</div>
            <div class="item-detail"><strong>Recommendation:</strong> ${item.recommendation}</div>
            ${item.example ? `<div class="item-example">"${item.example}"</div>` : ''}
        `;
        improvementsList.appendChild(div);
    });
    
    // Rule violations
    if (report.rule_violations && report.rule_violations.length > 0) {
        document.getElementById('violationsSection').style.display = 'block';
        const violationsList = document.getElementById('violationsList');
        violationsList.innerHTML = '';
        
        report.rule_violations.forEach(violation => {
            const div = document.createElement('div');
            div.className = 'list-item violation-item';
            div.innerHTML = `
                <div class="item-title">${violation.rule_name} (${violation.severity})</div>
                <div class="item-detail">${violation.description}</div>
                <div class="item-detail"><strong>Suggestion:</strong> ${violation.suggestion}</div>
                ${violation.example ? `<div class="item-example">"${violation.example}"</div>` : ''}
            `;
            violationsList.appendChild(div);
        });
    } else {
        document.getElementById('violationsSection').style.display = 'none';
    }
    
    // Summary
    document.getElementById('summaryText').textContent = report.summary;
    
    // Next steps
    const nextStepsList = document.getElementById('nextStepsList');
    nextStepsList.innerHTML = '';
    report.next_steps.forEach(step => {
        const div = document.createElement('div');
        div.className = 'list-item';
        div.textContent = step;
        nextStepsList.appendChild(div);
    });
    
    // Scroll to report
    document.getElementById('reportContainer').scrollIntoView({ behavior: 'smooth' });
}

function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.textContent = message;
    errorDiv.classList.add('visible');
    
    setTimeout(() => {
        errorDiv.classList.remove('visible');
    }, 5000);
}

function resetUI() {
    updateStatus('idle');
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('AI Sales Coach initialized');
    
    // Check browser compatibility
    if (!recognition) {
        showError('Speech recognition not supported. Please use Chrome or Edge browser.');
    }
    
    // Check if Speech SDK is loaded
    if (typeof SpeechSDK === 'undefined') {
        showError('Azure Speech SDK not loaded. Please refresh the page.');
    } else {
        console.log('Azure Speech SDK loaded successfully');
    }
});
