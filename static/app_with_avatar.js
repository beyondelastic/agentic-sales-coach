/**
 * AI Sales Coach — Voice Live edition
 *
 * Architecture: Browser ⟷ Voice Live WebSocket (direct, api-key in query param)
 *   • Audio IN  : getUserMedia → AudioWorklet (pcm-worklet.js) → base64 PCM →
 *                 input_audio_buffer.append events over WebSocket
 *   • Audio OUT : Voice Live avatar → WebRTC stream (video + audio) → <video> element
 *   • Transcript: conversation.item.input_audio_transcription.completed events
 *                 → accumulated locally → POST /api/session/{id}/analyze on stop
 *
 * The old STT (Web Speech API) → WS text → backend GPT → TTS pipeline is replaced
 * by a single managed Voice Live WebSocket connection with gpt-4.1, Azure STT, and
 * Azure HD TTS voices. Server-side echo cancellation removes all manual timing hacks.
 */

// ============================================================================
// STATE
// ============================================================================

let sessionId = null;
let isRecording = false;
let startTime = null;

// Voice Live WebSocket
let voiceLiveWs = null;
let voiceLiveConfig = null;
let isConnected = false;

// Avatar WebRTC
let peerConnection = null;

// Audio capture
let audioContext = null;
let audioWorkletNode = null;
let micStream = null;
let silencerGain = null;
let audioChunksSent = 0;

// Transcript accumulation (for post-session analysis)
let transcriptSegments = []; // [{speaker: "presenter"|"customer", text: string}]
let userTranscriptText = "";  // plain user words — used for empty-check

// Streaming avatar bubble state
let avatarStreamingBubble = null;

// Video emotion analysis
let mediaRecorder = null;
let recordedChunks = [];
let userVideoStream = null;
let isRecordingVideo = false;

// Webcam frame capture for visual analysis
let capturedFrames = [];
let frameIntervalId = null;
let cameraPreviewVideo = null; // off-screen video element used only for canvas drawing



// ============================================================================
// VOICE LIVE CONNECTION
// ============================================================================

/**
 * Connect to Voice Live and set up the avatar WebRTC session.
 * Called by the "Connect Avatar" button.
 */
async function connectAvatar() {
    updateAvatarStatus("🔄 Connecting to Voice Live...");

    try {
        // 1. Fetch session config + instructions from backend
        const configResp = await fetch("/api/voice-live/config");
        if (!configResp.ok) {
            const err = await configResp.json().catch(() => ({}));
            throw new Error(err.detail || `Config fetch failed (${configResp.status})`);
        }
        voiceLiveConfig = await configResp.json();

        // 2. Create a session record on the backend (used by the analyze endpoint later)
        const sessionResp = await fetch("/api/session/start", { method: "POST" });
        if (!sessionResp.ok) throw new Error("Failed to start backend session");
        sessionId = (await sessionResp.json()).session_id;
        console.log("Session started:", sessionId);

        // 3. Open a direct WebSocket to Voice Live.
        //    The API key is in the query string — encrypted over wss.
        console.log("[VoiceLive] Connecting to:", voiceLiveConfig.ws_url);
        const wsUrl = `${voiceLiveConfig.ws_url}&api-key=${encodeURIComponent(voiceLiveConfig.api_key)}`;
        voiceLiveWs = new WebSocket(wsUrl);
        voiceLiveWs.onmessage = handleVoiceLiveMessage;
        voiceLiveWs.onerror   = (evt) => {
            console.error("[VoiceLive] WebSocket error event:", evt);
            // Note: browsers do not expose HTTP status in onerror — wait for onclose for code/reason.
        };
        voiceLiveWs.onclose   = onVoiceLiveClosed;

        await new Promise((resolve, reject) => {
            const t = setTimeout(() => reject(new Error("Connection timeout (15 s)")), 15000);
            // Capture the original onclose so we can restore it after a successful open.
            const origClose = voiceLiveWs.onclose;
            voiceLiveWs.onopen = () => {
                clearTimeout(t);
                // Restore the original close handler so normal close handling runs.
                voiceLiveWs.onclose = origClose;
                resolve();
            };
            // Override onclose inside the promise so a fast rejection (e.g. 401/404) rejects
            voiceLiveWs.onclose = (evt) => {
                clearTimeout(t);
                voiceLiveWs.onclose = origClose;
                const reason = evt.reason || "(no reason sent by server)";
                reject(new Error(`WebSocket closed before open — code ${evt.code}: ${reason}`));
            };
        });

        // 4. Configure the session — persona, voice, avatar, turn detection, noise/echo.
        //    gpt-4.1 uses the Azure STT + Azure TTS pipeline (best transcription quality
        //    and HD Neural voices); gpt-realtime uses native audio (lower latency but less
        //    voice control — suboptimal for structured sales-pitch practice).
        sendEvent({
            type: "session.update",
            session: {
                instructions: voiceLiveConfig.instructions,
                modalities: ["text", "audio", "avatar"],
                voice: {
                    name: voiceLiveConfig.voice_name,   // e.g. en-US-Ava:DragonHDLatestNeural
                    type: "azure-standard",
                },
                // 16-bit PCM at 24 kHz mono — matches the AudioWorklet output format.
                input_audio_format: "pcm16",
                // Azure STT provides clean transcription events for the post-session report.
                input_audio_transcription: {
                    model: "azure-speech",
                    language: "en",
                },
                // Server-side AEC subtracts the avatar's own outgoing audio from the
                // incoming mic stream, as a second line of defence after browser AEC.
                input_audio_echo_cancellation: { type: "server_echo_cancellation" },
                // server_vad: auto-detect end-of-turn and automatically create a response.
                // threshold raised to 0.7 to reduce false triggers from residual echo.
                turn_detection: {
                    type: "server_vad",
                    threshold: 0.7,
                    prefix_padding_ms: 300,
                    silence_duration_ms: 800,
                    create_response: true,
                    interrupt_response: true,
                },
                // Avatar block — omit ice_servers; Voice Live returns them in session.updated.
                avatar: {
                    type: "video-avatar",
                    character: voiceLiveConfig.avatar_character,
                    style: voiceLiveConfig.avatar_style,
                    customized: false,
                },
            },
        });

        updateAvatarStatus("🔄 Waiting for avatar ICE servers...");

    } catch (error) {
        console.error("Voice Live connect error:", error);
        updateAvatarStatus("Connection failed");
        showError("Failed to connect: " + error.message);
    }
}

/** Send a JSON event on the Voice Live WebSocket. */
function sendEvent(event) {
    if (voiceLiveWs && voiceLiveWs.readyState === WebSocket.OPEN) {
        voiceLiveWs.send(JSON.stringify(event));
    }
}

/** Central handler for all Voice Live server → client events. */
async function handleVoiceLiveMessage(event) {
    let msg;
    try { msg = JSON.parse(event.data); } catch { return; }

    switch (msg.type) {

        // Session ready — server returns ICE servers for the avatar WebRTC stream
        case "session.updated":
            console.log("[VoiceLive] session.updated FULL:", JSON.stringify(msg.session));
            if (msg.session?.avatar !== undefined) {
                // Avatar was configured — get ICE servers (may be nested differently)
                const iceServers = msg.session.avatar?.ice_servers
                    ?? msg.session.avatar?.iceServers
                    ?? msg.session.ice_servers
                    ?? [];
                console.log("[VoiceLive] ICE servers from session.updated:", JSON.stringify(iceServers));
                if (iceServers.length === 0) {
                    console.warn("[VoiceLive] No ICE servers in session.updated — using public STUN fallback");
                }
                await setupAvatarWebRTC(iceServers);
            } else if (!isConnected) {
                onVoiceLiveConnected();   // Audio-only mode (no avatar configured)
            }
            break;

        // Avatar WebRTC: server answer SDP
        case "session.avatar.connecting":
            console.log("[VoiceLive] session.avatar.connecting received; full msg:", JSON.stringify(msg));
            updateAvatarStatus("🔄 WebRTC: Setting remote description...");
            if (peerConnection) {
                const rawServerSdp = msg.server_sdp ?? msg.sdp;
                if (!rawServerSdp) {
                    console.error("[VoiceLive] session.avatar.connecting had no server_sdp field!");
                    showError("Avatar error: server sent no SDP in session.avatar.connecting");
                    break;
                }
                try {
                    // server_sdp = base64(JSON.stringify({type:"answer", sdp:"..."}))
                    // Try to decode as base64-JSON-descriptor first, fall back to raw.
                    let answerSdp;
                    try {
                        const decoded = atob(rawServerSdp);
                        const descriptor = JSON.parse(decoded);
                        answerSdp = descriptor.sdp ?? decoded;
                        console.log("[VoiceLive] server_sdp decoded as base64-JSON descriptor OK");
                    } catch (e) {
                        // Maybe it's base64 of raw SDP, or raw SDP directly
                        try { answerSdp = atob(rawServerSdp); } catch { answerSdp = rawServerSdp; }
                        console.warn("[VoiceLive] server_sdp fallback decode:", e.message);
                    }
                    await peerConnection.setRemoteDescription({ type: "answer", sdp: answerSdp });
                    console.log("[VoiceLive] setRemoteDescription OK; ICE state:", peerConnection.iceConnectionState);
                    updateAvatarStatus("🔄 WebRTC: ICE negotiating...");
                } catch (err) {
                    console.error("[VoiceLive] setRemoteDescription failed:", err);
                    showError("Avatar WebRTC error: " + err.message);
                }
            }
            break;

        // VAD detected speech start
        case "input_audio_buffer.speech_started":
            console.log("[VoiceLive] VAD: speech_started (item", msg.item_id, ")");
            updateAvatarStatus("👂 Listening — speech detected...");
            break;

        // VAD detected end of speech — buffer will be auto-committed
        case "input_audio_buffer.speech_stopped":
            console.log("[VoiceLive] VAD: speech_stopped (item", msg.item_id, ")");
            updateAvatarStatus("🔄 Processing your speech...");
            break;

        // Audio buffer committed to conversation history
        case "input_audio_buffer.committed":
            console.log("[VoiceLive] Audio buffer committed, item:", msg.item_id);
            break;

        // Response generation started — flush any bubble left over from an interrupted previous response
        case "response.created":
            if (avatarStreamingBubble) {
                const leftover = avatarStreamingBubble.querySelector(".avatar-text")?.textContent?.trim();
                if (leftover && /\w/.test(leftover)) {
                    // Partial speech from the interrupted turn — keep it, mark as done
                    avatarStreamingBubble.style.opacity = "1";
                } else {
                    // Nothing useful was spoken — remove the empty bubble
                    avatarStreamingBubble.remove();
                }
                avatarStreamingBubble = null;
            }
            console.log("[VoiceLive] Response generation started:", msg.response?.id);
            updateAvatarStatus("💬 Avatar responding...");
            break;

        // User speech fully transcribed — accumulate for the post-session report
        case "conversation.item.input_audio_transcription.completed": {
            const userText = msg.transcript?.trim();
            if (userText) {
                userTranscriptText += userText + " ";
                transcriptSegments.push({ speaker: "presenter", text: userText });
                createUserBubble(userText);
            }
            break;
        }

        // Assistant response text (streaming deltas) — show in transcript while avatar speaks
        case "response.audio_transcript.delta":
            if (msg.delta) updateAvatarStreamingText(msg.delta);
            break;

        // Assistant response complete — Voice Live delivers the full transcript here.
        // Try part.transcript (audio parts) first, then part.text (text parts).
        case "response.content_part.done": {
            const assistantText = (msg.part?.transcript || msg.part?.text || "").trim();
            // Require at least one word character — filters whitespace-only / punctuation-only fragments
            // from interrupted responses that would otherwise appear as blank coach bubbles.
            if (assistantText && /\w/.test(assistantText)) {
                console.log("[VoiceLive] Coach said:", assistantText.slice(0, 80));
                transcriptSegments.push({ speaker: "customer", text: assistantText });
                finalizeAvatarMessage(assistantText);
            } else if (avatarStreamingBubble) {
                // Response was interrupted before a valid transcript arrived.
                // Salvage whatever streaming-delta text already accumulated in the bubble.
                const deltaText = avatarStreamingBubble.querySelector(".avatar-text")?.textContent?.trim();
                if (deltaText && /\w/.test(deltaText)) {
                    console.log("[VoiceLive] Coach (interrupted, using delta):", deltaText.slice(0, 80));
                    transcriptSegments.push({ speaker: "customer", text: deltaText });
                    avatarStreamingBubble.style.opacity = "1";
                } else {
                    avatarStreamingBubble.remove();
                }
                avatarStreamingBubble = null;
            }
            break;
        }

        case "error": {
            const errCode = msg.error?.code;
            // response_cancel_not_active fires when response.cancel is sent after the
            // greeting has already finished — benign race, suppress it.
            if (errCode === "response_cancel_not_active") {
                console.log("[VoiceLive] response.cancel was a no-op (response already done) — ignoring");
                break;
            }
            console.error("[VoiceLive] ERROR:", JSON.stringify(msg.error));
            showError(`Voice Live: ${msg.error?.message || JSON.stringify(msg.error)}`);
            break;
        }

        default:
            // Log ALL unhandled events at info level so we can diagnose handshake issues
            console.log("[VoiceLive] unhandled event:", msg.type, JSON.stringify(msg).slice(0, 300));
            break;
    }
}

function onVoiceLiveConnected() {
    isConnected = true;
    updateAvatarStatus("✅ Ready — start your presentation");
    document.getElementById("connectAvatarBtn").disabled = true;
    document.getElementById("disconnectAvatarBtn").disabled = false;
    const msg = document.getElementById("avatarMessage");
    if (msg) { msg.style.display = "block"; msg.textContent = "Voice Live connected. Click 'Start Presentation' when ready."; }
}

function onVoiceLiveClosed(evt) {
    if (evt) {
        console.warn(`[VoiceLive] Connection closed — code: ${evt.code}, reason: "${evt.reason || '(none)'}", clean: ${evt.wasClean}`);
    }
    isConnected = false;
    updateAvatarStatus("Disconnected");
    document.getElementById("connectAvatarBtn").disabled = false;
    document.getElementById("disconnectAvatarBtn").disabled = true;
    const msg = document.getElementById("avatarMessage");
    if (msg) msg.style.display = "none";
}

/** Disconnect from Voice Live and tear down WebRTC. */
async function disconnectAvatar() {
    stopRecordingInternal();

    if (voiceLiveWs) {
        voiceLiveWs.onclose = null;   // suppress UI update inside onVoiceLiveClosed
        voiceLiveWs.close();
        voiceLiveWs = null;
    }
    if (peerConnection) { peerConnection.close(); peerConnection = null; }

    const video = document.getElementById("avatarVideo");
    if (video) video.srcObject = null;

    isConnected = false;
    sessionId = null;
    onVoiceLiveClosed();
}


// ============================================================================
// AVATAR WEBRTC  (ICE + SDP negotiation via Voice Live WebSocket)
// ============================================================================

async function setupAvatarWebRTC(iceServers) {
    // Always include at least one public STUN server so ICE can work even without TURN
    const allIceServers = iceServers.length > 0
        ? iceServers
        : [{ urls: "stun:stun.l.google.com:19302" }];
    console.log("[VoiceLive] Creating RTCPeerConnection with ICE servers:", JSON.stringify(allIceServers));
    peerConnection = new RTCPeerConnection({ iceServers: allIceServers });

    // Receive-only — mic audio travels via WebSocket PCM, NOT via WebRTC.
    peerConnection.addTransceiver("video", { direction: "recvonly" });
    peerConnection.addTransceiver("audio", { direction: "recvonly" });

    const videoEl = document.getElementById("avatarVideo");

    peerConnection.ontrack = (event) => {
        console.log("[VoiceLive] ontrack fired — kind:", event.track.kind,
                    "streams:", event.streams.length,
                    "stream id:", event.streams[0]?.id ?? "none");
        // Attach the stream to the video element on the first track (video or audio)
        if (event.streams[0] && !videoEl.srcObject) {
            videoEl.srcObject = event.streams[0];
            videoEl.muted = false;
            console.log("[VoiceLive] srcObject set from ontrack stream");
            videoEl.play().catch(e => console.warn("[VoiceLive] video.play() blocked:", e));
        }
        if (event.track.kind === "video") {
            onVoiceLiveConnected();
        }
    };

    peerConnection.oniceconnectionstatechange = () => {
        const state = peerConnection.iceConnectionState;
        console.log("[VoiceLive] ICE connection state:", state);
        updateAvatarStatus("🔄 WebRTC ICE: " + state);
        if (state === "connected" || state === "completed") {
            updateAvatarStatus("🔄 WebRTC ICE connected, waiting for track...");
            // Log transceiver receiver-track states for diagnostics.
            // NOTE: receiver.track always exists (dormant) once addTransceiver() is called,
            //       so we must NOT use it to set isConnected — ontrack handles that correctly.
            for (const transceiver of peerConnection.getTransceivers()) {
                const track = transceiver.receiver?.track;
                console.log("[VoiceLive] Transceiver receiver track:", track?.kind, track?.readyState);
            }
            // Always send response.create so the avatar starts its opening greeting and
            // begins streaming video/audio via WebRTC (which will fire ontrack → onVoiceLiveConnected).
            console.log("[VoiceLive] ICE connected — triggering initial avatar response");
            sendEvent({ type: "response.create" });
        } else if (state === "failed") {
            showError("Avatar ICE connection failed. Check that UDP/TURN ports are accessible.");
        } else if (state === "disconnected") {
            updateAvatarStatus("⚠️ Avatar connection lost");
        }
    };

    peerConnection.onicegatheringstatechange = () => {
        console.log("[VoiceLive] ICE gathering state:", peerConnection.iceGatheringState);
    };

    peerConnection.onicecandidate = (event) => {
        console.log("[VoiceLive] ICE candidate:", event.candidate ? event.candidate.type + "/" + event.candidate.protocol : "(end-of-candidates)");
    };

    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);
    updateAvatarStatus("🔄 Gathering ICE candidates...");

    // Wait for ICE gathering with a 15 s safety timeout
    await new Promise((resolve) => {
        if (peerConnection.iceGatheringState === "complete") { resolve(); return; }
        const timer = setTimeout(() => {
            console.warn("[VoiceLive] ICE gathering timed out after 15 s — sending partial SDP");
            resolve();
        }, 15000);
        peerConnection.addEventListener("icegatheringstatechange", () => {
            if (peerConnection.iceGatheringState === "complete") { clearTimeout(timer); resolve(); }
        });
    });

    const finalSdp = peerConnection.localDescription.sdp;
    // Server expects client_sdp = base64(JSON.stringify({type, sdp})) — not just the raw SDP text.
    // It does: json.loads(base64.decode(client_sdp)) server-side.
    const sdpDescriptor = JSON.stringify({ type: "offer", sdp: finalSdp });
    console.log("[VoiceLive] Sending SDP offer (length:", finalSdp.length, ")");
    sendEvent({ type: "session.avatar.connect", client_sdp: btoa(sdpDescriptor) });
    updateAvatarStatus("🔄 Waiting for server SDP answer...");
    console.log("[VoiceLive] session.avatar.connect sent");

    // Fail visibly if no track arrives within 30 s
    setTimeout(() => {
        if (!isConnected) {
            const iceState = peerConnection?.iceConnectionState ?? "unknown";
            console.error("[VoiceLive] WebRTC handshake timed out. ICE state was:", iceState);
            showError(`Avatar timed out (ICE state: ${iceState}). Check browser console for details.`);
        }
    }, 30000);
}


// ============================================================================
// AUDIO CAPTURE  (microphone → PCM16 → Voice Live WebSocket)
// ============================================================================

async function startAudioCapture() {
    // echoCancellation + noiseSuppression must be ENABLED so the browser's AEC
    // removes the avatar's audio (played via the <video> element) from the mic
    // signal before it reaches Voice Live.  Without this the avatar hears itself,
    // VAD fires on its own voice, and every response gets interrupted.
    micStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });

    audioContext = new AudioContext({ sampleRate: 24000 });
    await audioContext.audioWorklet.addModule("/static/pcm-worklet.js");

    const source = audioContext.createMediaStreamSource(micStream);
    audioWorkletNode = new AudioWorkletNode(audioContext, "pcm-processor");

    audioWorkletNode.port.onmessage = (event) => {
        if (!voiceLiveWs || voiceLiveWs.readyState !== WebSocket.OPEN) return;
        sendEvent({ type: "input_audio_buffer.append", audio: uint8ToBase64(new Uint8Array(event.data)) });
        audioChunksSent++;
        if (audioChunksSent === 1 || audioChunksSent % 200 === 0) {
            console.log("[VoiceLive] Mic audio chunks sent:", audioChunksSent);
        }
    };

    // Silent gain node required to "pull" the audio graph (AudioContext won't process
    // nodes that aren't reachable from the destination).
    silencerGain = audioContext.createGain();
    silencerGain.gain.value = 0;
    source.connect(audioWorkletNode);
    audioWorkletNode.connect(silencerGain);
    silencerGain.connect(audioContext.destination);

    console.log("Audio capture started (24 kHz PCM → Voice Live)");
}

function stopAudioCapture() {
    if (audioWorkletNode) { audioWorkletNode.disconnect(); audioWorkletNode = null; }
    if (silencerGain)     { silencerGain.disconnect();     silencerGain = null; }
    if (audioContext)     { audioContext.close();           audioContext = null; }
    if (micStream)        { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
    console.log("Audio capture stopped. Total mic chunks sent:", audioChunksSent);
    audioChunksSent = 0;
}

/** Fast base64 encoding of a Uint8Array (chunked to avoid stack overflow). */
function uint8ToBase64(bytes) {
    let binary = "";
    const CHUNK = 8192;
    for (let i = 0; i < bytes.length; i += CHUNK) {
        binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
    }
    return btoa(binary);
}


// ============================================================================
// RECORDING CONTROL
// ============================================================================

async function startRecording() {
    if (!isConnected) { showError("Please connect the avatar first."); return; }

    try {
        transcriptSegments = [];
        userTranscriptText = "";
        avatarStreamingBubble = null;
        startTime = Date.now();
        isRecording = true;

        updateStatus("recording");
        updateAvatarStatus("👂 Listening...");
        document.getElementById("startBtn").disabled = true;
        document.getElementById("stopBtn").disabled = false;
        document.getElementById("reportContainer").classList.remove("visible");
        document.getElementById("transcriptBox").innerHTML =
            '<span class="transcript-placeholder" style="opacity:0.5">Your presentation transcript will appear here as you speak...</span>';

        const notice = document.getElementById("cameraNotice");
        if (notice) {
            notice.classList.add("recording");
            notice.querySelector("strong").textContent = "🔴 Recording in Progress";
            notice.querySelector("small").textContent =
                "Camera active — video is recorded locally and deleted immediately after the session.";
        }

        // Cancel any pending/in-flight response from the initial greeting so Voice Live
        // enters idle state and will respond to user VAD input immediately.
        sendEvent({ type: "response.cancel" });

        await startVideoCapture();
        startFrameCapture();
        await startAudioCapture();

        // Browser autoplay policy may have blocked avatar audio/video before user interaction.
        // Now that we're inside a click handler, explicitly resume playback.
        const avatarVideoEl = document.getElementById("avatarVideo");
        if (avatarVideoEl && avatarVideoEl.paused) {
            avatarVideoEl.play().catch(e => console.warn("[VoiceLive] avatarVideo.play() on start:", e));
        }
        if (audioContext && audioContext.state === "suspended") {
            audioContext.resume().catch(e => console.warn("[VoiceLive] audioContext.resume():", e));
        }

        console.log("Presentation started, session:", sessionId);

    } catch (error) {
        console.error("Error starting recording:", error);
        showError("Failed to start recording: " + error.message);
        isRecording = false;
        resetUI();
    }
}

async function stopRecording() {
    if (!isRecording) return;
    stopRecordingInternal();

    updateStatus("analyzing");
    updateAvatarStatus("Analyzing presentation...");
    document.getElementById("stopBtn").disabled = true;

    const processingIndicator = document.getElementById("processingIndicator");
    if (processingIndicator) {
        processingIndicator.classList.add("visible");
        processingIndicator.textContent = "Analyzing presentation...";
    }

    const duration = (Date.now() - startTime) / 1000;

    if (!userTranscriptText.trim()) {
        showError("No speech detected. Please try again and speak into your microphone.");
        resetUI();
        updateAvatarStatus("Ready");
        if (processingIndicator) processingIndicator.classList.remove("visible");
        return;
    }

    try {
        // Build the full conversation transcript (presenter + customer turns)
        const fullTranscript = transcriptSegments.map(s => `${s.speaker.toUpperCase()}: ${s.text}`).join("\n");
        const allFrames = capturedFrames.splice(0); // clear the array immediately

        // Evenly sample up to frame_max_count frames so the POST payload stays bounded
        // regardless of session length, and coverage is spread across the whole session
        const maxFrames = voiceLiveConfig?.frame_max_count ?? 20;
        const framesToSend = allFrames.length <= maxFrames
            ? allFrames
            : Array.from({ length: maxFrames }, (_, i) => allFrames[Math.floor(i * allFrames.length / maxFrames)]);

        if (framesToSend.length > 0) {
            updateAvatarStatus(`Analyzing presentation + ${framesToSend.length} visual frames...`);
        }

        const resp = await fetch(`/api/session/${sessionId}/analyze`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ transcript: fullTranscript, duration, frames: framesToSend }),
        });
        if (!resp.ok) throw new Error(`Analysis failed (${resp.status})`);

        const { report } = await resp.json();
        displayReport(report, framesToSend.length > 0);
        resetUI();
        updateAvatarStatus("✅ Coaching report ready — review below");

        // Hide processing indicator immediately — emotional analysis is now
        // included synchronously in the GPT-4o report (no Video Indexer polling needed).
        const indicator = document.getElementById("processingIndicator");
        if (indicator) indicator.classList.remove("visible");

    } catch (error) {
        console.error("Analysis error:", error);
        showError("Failed to analyze presentation: " + error.message);
        resetUI();
        updateAvatarStatus("Error during analysis");
        const indicator = document.getElementById("processingIndicator");
        if (indicator) indicator.classList.remove("visible");
    }
}

/** Stop audio + video capture without changing UI status — used internally. */
function stopRecordingInternal() {
    const wasRecording = isRecording;
    isRecording = false;
    stopAudioCapture();
    stopVideoCapture();
    stopFrameCapture();

    if (wasRecording) {
        const notice = document.getElementById("cameraNotice");
        if (notice) {
            notice.classList.remove("recording");
            notice.querySelector("strong").textContent = "⚠️ Camera & Emotion Analysis Active";
            notice.querySelector("small").textContent =
                "Your webcam will activate when you start recording to capture facial expressions for emotion analysis. All video is processed securely and automatically deleted after analysis for your privacy.";
        }
    }
}


// ============================================================================
// TRANSCRIPT DISPLAY
// ============================================================================

function createUserBubble(text) {
    const box = document.getElementById("transcriptBox");
    const placeholder = box.querySelector(".transcript-placeholder");
    if (placeholder) placeholder.remove();
    box.classList.remove("empty");

    const div = document.createElement("div");
    div.style.cssText = "margin:10px 0;padding:10px;background:#e3f2fd;border-left:3px solid #2196F3;border-radius:4px;";

    // Build the bubble content safely so transcript text is treated as plain text.
    const strong = document.createElement("strong");
    strong.style.color = "#2196F3";
    strong.textContent = "You:";
    div.appendChild(strong);
    div.appendChild(document.createTextNode(" " + String(text)));

    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

function updateAvatarStreamingText(delta) {
    const box = document.getElementById("transcriptBox");
    if (!avatarStreamingBubble) {
        avatarStreamingBubble = document.createElement("div");
        avatarStreamingBubble.style.cssText =
            "margin:10px 0;padding:10px;background:#e8f5e9;border-left:3px solid #4CAF50;border-radius:4px;opacity:0.85;";
        avatarStreamingBubble.innerHTML =
            `<strong style="color:#4CAF50;">🤖 Coach:</strong> <span class="avatar-text"></span>`;
        box.appendChild(avatarStreamingBubble);
    }
    avatarStreamingBubble.querySelector(".avatar-text").textContent += delta;
    box.scrollTop = box.scrollHeight;
}

function finalizeAvatarMessage(fullText) {
    const box = document.getElementById("transcriptBox");
    if (avatarStreamingBubble) {
        // Overwrite with the authoritative final text from response.content_part.done —
        // the streaming deltas may have been incomplete or arrived out of order.
        avatarStreamingBubble.querySelector(".avatar-text").textContent = fullText;
        avatarStreamingBubble.style.opacity = "1";
        avatarStreamingBubble = null;
    } else {
        // No streaming bubble exists (e.g. no deltas arrived) — create the bubble now.
        const div = document.createElement("div");
        div.style.cssText =
            "margin:10px 0;padding:10px;background:#e8f5e9;border-left:3px solid #4CAF50;border-radius:4px;";
        div.innerHTML = `<strong style="color:#4CAF50;">🤖 Coach:</strong> <span class="avatar-text"></span>`;
        div.querySelector(".avatar-text").textContent = fullText;
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    }
}

function updateAvatarStatus(status) {
    const el = document.getElementById("avatarStatus");
    if (el) el.textContent = status;
}

function updateStatus(status) {
    const badge = document.getElementById("statusBadge");
    badge.className = "status-badge";
    switch (status) {
        case "recording": badge.classList.add("status-recording"); badge.textContent = "🔴 Recording"; break;
        case "analyzing": badge.classList.add("status-analyzing"); badge.textContent = "🔄 Analyzing"; break;
        default:          badge.classList.add("status-idle");      badge.textContent = "Ready";
    }
}

function resetUI() {
    updateStatus("idle");
    document.getElementById("startBtn").disabled = false;
    document.getElementById("stopBtn").disabled = true;
}


// ============================================================================
// COACHING REPORT DISPLAY
// ============================================================================

function displayReport(report, isEnhanced = false) {
    document.getElementById("reportContainer").classList.add("visible");
    if (isEnhanced) showNotification("✨ Report enhanced with facial emotion analysis!", "success");

    document.getElementById("overallScore").textContent = report.overall_score.toFixed(1) + "/10";

    const levelEl = document.getElementById("performanceLevel");
    levelEl.textContent = report.performance_level.replace("_", " ");
    levelEl.className = "performance-level level-" + report.performance_level;

    const grid = document.getElementById("criteriaGrid");
    grid.innerHTML = "";
    for (const [key, value] of Object.entries(report.criteria_scores)) {
        const div = document.createElement("div");
        div.className = "criterion";
        div.innerHTML = `<div class="criterion-name">${key.replace(/_/g, " ")}</div>
                         <div class="criterion-score">${value.toFixed(1)}/10</div>`;
        grid.appendChild(div);
    }

    const renderList = (id, items, render) => {
        const el = document.getElementById(id);
        el.innerHTML = "";
        items.forEach(item => { const d = document.createElement("div"); d.innerHTML = render(item); el.appendChild(d); });
    };

    renderList("strengthsList", report.strengths, s => {
        return `<div class="list-item">${s}</div>`;
    });

    renderList("improvementsList", report.improvements, item => `
        <div class="list-item improvement-item">
            <div class="item-title">${item.area}</div>
            <div class="item-detail"><strong>Current:</strong> ${item.current_state}</div>
            <div class="item-detail"><strong>Recommendation:</strong> ${item.recommendation}</div>
            ${item.example ? `<div class="item-example">"${item.example}"</div>` : ""}
        </div>`);

    if (report.rule_violations?.length > 0) {
        document.getElementById("violationsSection").style.display = "block";
        renderList("violationsList", report.rule_violations, v => `
            <div class="list-item violation-item">
                <div class="item-title">${v.rule_name} (${v.severity})</div>
                <div class="item-detail">${v.description}</div>
                <div class="item-detail"><strong>Suggestion:</strong> ${v.suggestion}</div>
                ${v.example ? `<div class="item-example">"${v.example}"</div>` : ""}
            </div>`);
    } else {
        document.getElementById("violationsSection").style.display = "none";
    }

    document.getElementById("summaryText").textContent = report.summary;

    // Emotional tone section
    const et = report.emotional_tone;
    if (et) {
        document.getElementById("emotionalToneSection").style.display = "block";
        const sentimentEmoji = { positive: "😊", neutral: "😐", negative: "😟", mixed: "🎭" }[et.overall_sentiment] ?? "🎭";
        document.getElementById("emotionalToneSummary").innerHTML =
            `${sentimentEmoji} <strong>${et.overall_sentiment.charAt(0).toUpperCase() + et.overall_sentiment.slice(1)} sentiment</strong>
             &nbsp;·&nbsp; Confidence: <strong>${et.confidence_level}</strong>
             &nbsp;·&nbsp; Energy: <strong>${et.energy_level}</strong>`;
        const momentsEl = document.getElementById("emotionalKeyMoments");
        momentsEl.innerHTML = "";
        (et.key_moments || []).forEach(m => {
            const d = document.createElement("div");
            d.className = "list-item";
            d.textContent = m;
            momentsEl.appendChild(d);
        });
        if (et.authenticity_note) {
            document.getElementById("emotionalAuthenticity").textContent = et.authenticity_note;
        }
    } else {
        document.getElementById("emotionalToneSection").style.display = "none";
    }

    // Visual analysis section
    const va = report.visual_analysis;
    const vaSection = document.getElementById("visualAnalysisSection");
    if (va && vaSection) {
        vaSection.style.display = "block";
        const rows = [
            ["😊 Expressions",        va.expressions],
            ["👁️ Eye Contact",         va.eye_contact],
            ["🧍 Posture & Gestures",  va.posture_and_gestures],
            ["👔 Appearance",          va.professional_appearance],
            ["📈 Confidence Arc",      va.confidence_arc],
        ];
        document.getElementById("visualAnalysisRows").innerHTML = rows.map(([label, value]) =>
            `<div class="list-item"><strong>${label}:</strong> ${value}</div>`
        ).join("");
        document.getElementById("visualOverallNote").textContent = va.overall_note;
    } else if (vaSection) {
        vaSection.style.display = "none";
    }

    renderList("nextStepsList", report.next_steps, step => `<div class="list-item">${step}</div>`);

    document.getElementById("reportContainer").scrollIntoView({ behavior: "smooth" });
}


// ============================================================================
// VIDEO CAPTURE  (camera preview only — not uploaded anywhere)
// ============================================================================

async function startVideoCapture() {
    try {
        userVideoStream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
            audio: false,
        });

        // For preview-only usage, we do not need to record or buffer video data.
        // Just mark that video capture is active; other code can use `userVideoStream`
        // directly (e.g., attach it to a <video> element or draw to a <canvas>.
        isRecordingVideo = true;
        console.log("Video capture (preview) started.");
        return true;
    } catch (error) {
        console.error("Video capture error:", error);
        showError("Could not access webcam: " + error.message);
        return false;
    }
}

function stopVideoCapture() {
    // Stop the preview stream and clear state.
    if (userVideoStream) {
        userVideoStream.getTracks().forEach(t => t.stop());
        userVideoStream = null;
    }
    isRecordingVideo = false;
}

async function processRecordedVideo() {
    // Raw MediaRecorder chunks are discarded — frames were captured separately via canvas.
    recordedChunks = [];
    console.log("Video capture discarded (not uploaded to Azure).");
}


// ============================================================================
// FRAME CAPTURE  (webcam snapshots for visual/emotion analysis)
// ============================================================================

function startFrameCapture() {
    if (!userVideoStream) return;

    // Create an off-screen video element to draw from
    cameraPreviewVideo = document.createElement("video");
    cameraPreviewVideo.srcObject = userVideoStream;
    cameraPreviewVideo.muted = true;
    cameraPreviewVideo.playsInline = true;
    cameraPreviewVideo.play().catch(() => {});

    capturedFrames = [];

    // Interval and max count come from server config so they're tuneable via .env
    const intervalMs = voiceLiveConfig?.frame_interval_ms ?? 30000;

    // Capture first frame after a 1.5s warm-up, then at the configured interval
    setTimeout(captureFrame, 1500);
    frameIntervalId = setInterval(captureFrame, intervalMs);
    console.log(`[Visual] Frame capture started (every ${intervalMs / 1000}s)`);
}

function captureFrame() {
    if (!cameraPreviewVideo || !userVideoStream || cameraPreviewVideo.readyState < 2) return;
    const w = 640;
    const h = cameraPreviewVideo.videoHeight
        ? Math.round(w * cameraPreviewVideo.videoHeight / cameraPreviewVideo.videoWidth)
        : 360;
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    canvas.getContext("2d").drawImage(cameraPreviewVideo, 0, 0, w, h);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.65);
    capturedFrames.push(dataUrl);
    console.log(`[Visual] Frame ${capturedFrames.length} captured (~${Math.round(dataUrl.length / 1024)}KB)`);
}

function stopFrameCapture() {
    if (frameIntervalId) { clearInterval(frameIntervalId); frameIntervalId = null; }
    if (cameraPreviewVideo) { cameraPreviewVideo.srcObject = null; cameraPreviewVideo = null; }
    console.log(`[Visual] Frame capture stopped. ${capturedFrames.length} frames ready for analysis.`);
}


// ============================================================================
// NOTIFICATIONS
// ============================================================================

function showError(message) {
    const el = document.getElementById("errorMessage");
    el.textContent = message;
    el.style.background = "";
    el.classList.add("visible");
    setTimeout(() => el.classList.remove("visible"), 5000);
}

function showNotification(message, type = "info") {
    const el = document.getElementById("errorMessage");
    el.textContent = message;
    el.style.background = type === "success" ? "#4CAF50" : type === "info" ? "#2196F3" : "#f44336";
    el.classList.add("visible");
    setTimeout(() => { el.classList.remove("visible"); el.style.background = ""; }, 5000);
}


// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener("DOMContentLoaded", () => {
    console.log("AI Sales Coach (Voice Live) initialised");

    const missing = [];
    if (!window.WebSocket)                       missing.push("WebSocket");
    if (!window.AudioWorklet || !window.AudioContext) missing.push("AudioWorklet");
    if (!window.RTCPeerConnection)               missing.push("WebRTC");
    if (!navigator.mediaDevices?.getUserMedia)   missing.push("getUserMedia");

    if (missing.length > 0) {
        showError(`Browser missing required APIs: ${missing.join(", ")}. Please use Chrome 80+ or Edge 80+.`);
    }
});
