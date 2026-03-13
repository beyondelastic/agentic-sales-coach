/**
 * AudioWorklet processor for capturing microphone audio as 16-bit PCM.
 * Runs in the audio rendering thread; transfers PCM buffers to the main thread
 * so they can be base64-encoded and sent to the Voice Live API via WebSocket.
 *
 * Sample rate is set to 24000 Hz in the AudioContext (matching voice_live default).
 */
class PCMProcessor extends AudioWorkletProcessor {
    process(inputs) {
        const channel = inputs[0]?.[0];
        if (!channel || channel.length === 0) return true;

        // Convert Float32 [-1, 1] → Int16 [-32768, 32767]
        const pcm16 = new Int16Array(channel.length);
        for (let i = 0; i < channel.length; i++) {
            const clamped = Math.max(-1, Math.min(1, channel[i]));
            pcm16[i] = Math.round(clamped * 32767);
        }

        // Transfer the underlying buffer (zero-copy) to the main thread
        this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
        return true;
    }
}

registerProcessor("pcm-processor", PCMProcessor);
