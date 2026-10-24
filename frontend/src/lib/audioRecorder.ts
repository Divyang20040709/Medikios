/**
 * Patient Kiosk Audio Recorder
 * ─────────────────────────────
 * Cross-browser microphone audio recorder for Hindi/Gujarati symptom input.
 * Supports live volume metering (for UI waveforms), max duration limit,
 * and produces standard Audio Blobs ready for upload to /api/speech/transcribe.
 */

export interface AudioRecorderOptions {
  maxDurationSeconds?: number;
  onVolumeChange?: (volume: number) => void; // 0.0 to 1.0
  onTimeUpdate?: (elapsedSeconds: number) => void;
  onMaxDurationReached?: () => void;
}

export class AudioRecorder {
  private mediaStream: MediaStream | null = null;
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private animFrameId: number | null = null;
  private timerInterval: NodeJS.Timeout | null = null;
  private startTime: number = 0;
  private options: AudioRecorderOptions;
  private isRecording: boolean = false;

  constructor(options: AudioRecorderOptions = {}) {
    this.options = {
      maxDurationSeconds: options.maxDurationSeconds || 60,
      onVolumeChange: options.onVolumeChange,
      onTimeUpdate: options.onTimeUpdate,
      onMaxDurationReached: options.onMaxDurationReached,
    };
  }

  /**
   * Request microphone access and start recording.
   */
  async start(): Promise<void> {
    if (this.isRecording) return;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("Microphone access is not supported by your browser.");
    }

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
    } catch (err: any) {
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        throw new Error("Microphone permission denied. Please allow microphone access to record symptoms.");
      } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
        throw new Error("No microphone device found on this system.");
      } else {
        throw new Error(`Microphone error: ${err.message || "Unable to access microphone"}`);
      }
    }

    // Set up AudioContext for live volume visualization
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (AudioCtx) {
        this.audioContext = new AudioCtx();
        const source = this.audioContext.createMediaStreamSource(this.mediaStream);
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 256;
        source.connect(this.analyser);
        this.startVolumeMonitoring();
      }
    } catch (e) {
      console.warn("AudioContext setup failed, volume metering disabled:", e);
    }

    // Pick best supported mimeType
    const mimeTypes = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/mp4",
      "audio/wav",
    ];
    let chosenMime = "";
    for (const mime of mimeTypes) {
      if (MediaRecorder.isTypeSupported(mime)) {
        chosenMime = mime;
        break;
      }
    }

    const recorderOptions: MediaRecorderOptions = {};
    if (chosenMime) {
      recorderOptions.mimeType = chosenMime;
    }

    this.audioChunks = [];
    this.mediaRecorder = new MediaRecorder(this.mediaStream, recorderOptions);

    this.mediaRecorder.ondataavailable = (event: BlobEvent) => {
      if (event.data && event.data.size > 0) {
        this.audioChunks.push(event.data);
      }
    };

    this.mediaRecorder.start(250); // Emit chunk every 250ms
    this.isRecording = true;
    this.startTime = Date.now();

    // Setup duration watchdog
    const maxSec = this.options.maxDurationSeconds || 60;
    this.timerInterval = setInterval(() => {
      if (!this.isRecording) return;
      const elapsed = Math.floor((Date.now() - this.startTime) / 1000);
      if (this.options.onTimeUpdate) {
        this.options.onTimeUpdate(elapsed);
      }
      if (elapsed >= maxSec) {
        if (this.options.onMaxDurationReached) {
          this.options.onMaxDurationReached();
        }
        this.stop().catch(console.error);
      }
    }, 500);
  }

  private startVolumeMonitoring(): void {
    if (!this.analyser) return;
    const dataArray = new Uint8Array(this.analyser.frequencyBinCount);

    const updateVolume = () => {
      if (!this.isRecording || !this.analyser) return;
      this.analyser.getByteFrequencyData(dataArray);
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
      }
      const avg = sum / dataArray.length;
      const normalized = Math.min(1.0, avg / 128); // 0.0 to 1.0

      if (this.options.onVolumeChange) {
        this.options.onVolumeChange(normalized);
      }
      this.animFrameId = requestAnimationFrame(updateVolume);
    };

    this.animFrameId = requestAnimationFrame(updateVolume);
  }

  /**
   * Stop recording and return the recorded audio Blob.
   */
  async stop(): Promise<Blob> {
    if (!this.isRecording && this.audioChunks.length > 0) {
      return new Blob(this.audioChunks, { type: this.mediaRecorder?.mimeType || "audio/webm" });
    }

    this.isRecording = false;

    if (this.timerInterval) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
    if (this.audioContext && this.audioContext.state !== "closed") {
      this.audioContext.close().catch(() => {});
      this.audioContext = null;
    }

    return new Promise((resolve, reject) => {
      if (!this.mediaRecorder) {
        reject(new Error("MediaRecorder is not initialized."));
        return;
      }

      this.mediaRecorder.onstop = () => {
        const mime = this.mediaRecorder?.mimeType || "audio/webm";
        const audioBlob = new Blob(this.audioChunks, { type: mime });

        // Stop all audio tracks to release microphone hardware light
        if (this.mediaStream) {
          this.mediaStream.getTracks().forEach((track) => track.stop());
          this.mediaStream = null;
        }

        resolve(audioBlob);
      };

      if (this.mediaRecorder.state !== "inactive") {
        this.mediaRecorder.stop();
      } else {
        const mime = this.mediaRecorder.mimeType || "audio/webm";
        resolve(new Blob(this.audioChunks, { type: mime }));
      }
    });
  }

  /**
   * Cancel and discard recording immediately without returning data.
   */
  cancel(): void {
    this.isRecording = false;
    if (this.timerInterval) clearInterval(this.timerInterval);
    if (this.animFrameId) cancelAnimationFrame(this.animFrameId);
    if (this.audioContext && this.audioContext.state !== "closed") {
      this.audioContext.close().catch(() => {});
    }
    if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
      try {
        this.mediaRecorder.stop();
      } catch (e) {}
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }
    this.audioChunks = [];
  }

  get recording(): boolean {
    return this.isRecording;
  }
}

/**
 * Upload audio blob to MediKiosk backend speech API for real transcription.
 */
export async function transcribeAudioBlob(
  audioBlob: Blob,
  language: string = "hi"
): Promise<{
  transcript: string;
  language: string;
  confidence: number;
  provider: string;
  clinical_grounding?: any;
}> {
  const formData = new FormData();
  // Ensure the file has an extension matching its type or .wav/.webm
  const ext = audioBlob.type.includes("wav") ? "wav" : "webm";
  formData.append("audio", audioBlob, `input.${ext}`);
  formData.append("language", language);

  const response = await fetch("/api/speech/transcribe", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let errorDetail = "Speech recognition failed.";
    try {
      const errJson = await response.json();
      errorDetail = errJson.detail || errorDetail;
    } catch {
      errorDetail = `HTTP ${response.status}: ${response.statusText}`;
    }
    throw new Error(errorDetail);
  }

  return await response.json();
}
