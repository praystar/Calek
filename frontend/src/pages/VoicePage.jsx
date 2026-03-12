import { useState, useRef, useEffect } from "react";
import { Mic, Square, Download, RotateCcw } from "lucide-react";
import toast from "react-hot-toast";
import HandwritingCanvas from "../components/HandwritingCanvas";
import api from "../utils/api";

export default function VoicePage() {
  const [recording, setRecording] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [renderedText, setRenderedText] = useState("");
  const [duration, setDuration] = useState(0);
  const [processing, setProcessing] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const analyserRef = useRef(null);
  const animFrameRef = useRef(null);
  const recognitionRef = useRef(null);

  // Browser speech recognition (Web Speech API)
  const startWebSpeech = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) { toast.error("Browser speech recognition not supported. Use Chrome."); return false; }
    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognitionRef.current = recognition;

    let finalTranscript = "";
    recognition.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalTranscript += e.results[i][0].transcript;
        else interim += e.results[i][0].transcript;
      }
      setTranscript(finalTranscript + interim);
    };
    recognition.onerror = (e) => toast.error(`Speech error: ${e.error}`);
    recognition.start();
    return true;
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Audio level visualizer
      const audioCtx = new AudioContext();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      const updateLevel = () => {
        const data = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b) / data.length;
        setAudioLevel(avg / 128);
        animFrameRef.current = requestAnimationFrame(updateLevel);
      };
      updateLevel();

      // MediaRecorder for Whisper backend
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = e => chunksRef.current.push(e.data);
      mr.start(100);
      mediaRecorderRef.current = mr;

      // Also use Web Speech API for real-time transcript
      startWebSpeech();

      setRecording(true);
      setDuration(0);
      timerRef.current = setInterval(() => setDuration(d => d + 1), 1000);
      toast.success("Recording started");
    } catch (err) {
      toast.error("Microphone access denied");
    }
  };

  const stopRecording = async () => {
    setRecording(false);
    setProcessing(true);
    clearInterval(timerRef.current);
    cancelAnimationFrame(animFrameRef.current);
    setAudioLevel(0);

    recognitionRef.current?.stop();

    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(t => t.stop());
    }

    // Try Whisper backend, fallback to Web Speech transcript
    try {
      await new Promise(r => setTimeout(r, 500)); // wait for chunks
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      const formData = new FormData();
      formData.append("audio", blob, "recording.webm");
      const { data } = await api.post("/transcribe", formData);
      setTranscript(data.transcript);
      setRenderedText(data.transcript);
    } catch {
      // Use Web Speech transcript
      if (transcript) setRenderedText(transcript);
      else toast.error("No transcript captured");
    }
    setProcessing(false);
  };

  const reset = () => {
    setTranscript(""); setRenderedText(""); setDuration(0);
  };

  const formatTime = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  const bars = 24;

  return (
    <div className="fade-in">
      <h1 className="page-title">Voice to Handwriting</h1>
      <p className="page-subtitle">Speak naturally — your words will be transcribed and rendered in your handwriting style.</p>

      <div className="two-col" style={{ marginBottom: 24 }}>
        {/* Recorder */}
        <div className="card" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 24, padding: 40 }}>
          {/* Waveform visualizer */}
          <div style={{ display: "flex", alignItems: "center", gap: 3, height: 48 }}>
            {Array.from({ length: bars }).map((_, i) => {
              const base = 0.1;
              const wave = recording ? Math.abs(Math.sin((i / bars) * Math.PI)) * audioLevel : base;
              const h = Math.max(4, wave * 40 + 4);
              return (
                <div key={i} style={{
                  width: 3, height: `${h}px`,
                  background: recording ? "var(--accent)" : "var(--border-strong)",
                  borderRadius: 99,
                  transition: "height 0.1s ease, background 0.3s ease"
                }} />
              );
            })}
          </div>

          {/* Timer */}
          <div style={{ fontFamily: "monospace", fontSize: 32, fontWeight: 600, color: recording ? "#dc2626" : "var(--text-muted)", letterSpacing: "0.08em" }}>
            {formatTime(duration)}
          </div>

          {/* Mic button */}
          <button
            className={`mic-btn ${recording ? "recording" : ""}`}
            onClick={recording ? stopRecording : startRecording}
            disabled={processing}
          >
            {processing ? <div className="spinner" style={{ borderColor: "rgba(255,255,255,0.3)", borderTopColor: "#fff" }} />
              : recording ? <Square size={28} fill="white" /> : <Mic size={28} />}
          </button>

          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            {processing ? "Processing audio…" : recording ? "Tap to stop" : "Tap to start recording"}
          </div>

          {/* Controls */}
          <div style={{ display: "flex", gap: 10, width: "100%" }}>
            <button className="btn btn-secondary" style={{ flex: 1 }} onClick={reset} disabled={recording || processing}>
              <RotateCcw size={14} /> Reset
            </button>
            <button className="btn btn-secondary" style={{ flex: 1 }} disabled={!renderedText}>
              <Download size={14} /> Export
            </button>
          </div>
        </div>

        {/* Live transcript */}
        <div className="card" style={{ display: "flex", flexDirection: "column" }}>
          <div className="card-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>Live Transcript</span>
            {recording && <span className="badge badge-red" style={{ animation: "pulse-red 1.5s infinite" }}>● REC</span>}
          </div>
          <div style={{
            flex: 1, minHeight: 180,
            padding: 16, borderRadius: 8,
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            fontSize: 15, lineHeight: 1.7,
            color: transcript ? "var(--text-primary)" : "var(--text-muted)",
            fontStyle: transcript ? "normal" : "italic",
            overflowY: "auto"
          }}>
            {transcript || "Your spoken words will appear here in real time…"}
          </div>

          {transcript && (
            <div style={{ marginTop: 12 }}>
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  value={transcript}
                  onChange={e => setTranscript(e.target.value)}
                  style={{ flex: 1 }}
                />
                <button className="btn btn-primary" onClick={() => setRenderedText(transcript)}>Render →</button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Handwriting output */}
      <div className="card">
        <div className="card-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>Handwriting Output</span>
          {renderedText && <span className="badge badge-gold">Rendered</span>}
        </div>
        <HandwritingCanvas text={renderedText} placeholder={!renderedText} />
        {!renderedText && (
          <div style={{ textAlign: "center", marginTop: 16, fontSize: 13, color: "var(--text-muted)" }}>
            Start recording to see your handwriting render here
          </div>
        )}
      </div>

      {/* Tips */}
      <div className="card" style={{ marginTop: 24, background: "var(--highlight-soft)", borderColor: "var(--highlight)" }}>
        <div className="card-title">💡 Tips for Best Results</div>
        <div style={{ display: "flex", gap: 32, fontSize: 13, color: "var(--text-secondary)" }}>
          <div>• Speak clearly at a normal pace</div>
          <div>• Use Chrome for best speech recognition</div>
          <div>• Upload your corpus first on the Corpus page</div>
          <div>• Edit transcript before rendering if needed</div>
        </div>
      </div>
    </div>
  );
}
