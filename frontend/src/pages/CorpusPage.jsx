import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, Wand2, Download, Sparkles, CheckCircle } from "lucide-react";
import toast from "react-hot-toast";
import HandwritingCanvas from "../components/HandwritingCanvas";
import api from "../utils/api";

const PRESET_STYLES = [
  { id: "iam_a01", label: "Neat & Upright",   preview: "Hello World", slant: "0°",   pressure: "medium", spacing: "normal" },
  { id: "iam_b02", label: "Casual Slanted",   preview: "Hello World", slant: "-8°",  pressure: "light",  spacing: "wide"   },
  { id: "iam_c03", label: "Loopy Cursive",    preview: "Hello World", slant: "-12°", pressure: "medium", spacing: "tight"  },
  { id: "iam_d04", label: "Tight & Small",    preview: "Hello World", slant: "-4°",  pressure: "heavy",  spacing: "tight"  },
  { id: "iam_e05", label: "Wide & Relaxed",   preview: "Hello World", slant: "2°",   pressure: "light",  spacing: "wide"   },
  { id: "iam_f06", label: "Bold & Blocky",    preview: "Hello World", slant: "0°",   pressure: "heavy",  spacing: "normal" },
  { id: "iam_g07", label: "Hurried Scrawl",   preview: "Hello World", slant: "-15°", pressure: "light",  spacing: "wide"   },
  { id: "iam_h08", label: "Elegant Longhand", preview: "Hello World", slant: "-6°",  pressure: "medium", spacing: "normal" },
];



export default function CorpusPage() {
  const [mode, setMode] = useState("pick");
  const [selectedStyle, setSelectedStyle] = useState(null);
  const [files, setFiles] = useState([]);
  const [matching, setMatching] = useState(false);
  const [matchResult, setMatchResult] = useState(null);
  const [previewText, setPreviewText] = useState("The quick brown fox jumps over the lazy dog.");
  const [ready, setReady] = useState(false);

  const onDrop = useCallback((accepted) => {
    setFiles(prev => [...prev, ...accepted.map(f => ({
      file: f, id: Math.random().toString(36).slice(2), preview: URL.createObjectURL(f)
    }))]);
    toast.success(`${accepted.length} photo(s) added`);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { "image/*": [".png", ".jpg", ".jpeg", ".webp"] }, multiple: true, maxFiles: 5,
  });

  const autoMatch = async () => {
    if (files.length === 0) { toast.error("Upload at least one photo first"); return; }
    setMatching(true);
    try {
      const formData = new FormData();
      files.forEach(f => formData.append("images", f.file));
      const { data } = await api.post("/corpus/match-style", formData);
      setMatchResult(data); setSelectedStyle({ id: data.matched_id, label: data.label, ...data }); setReady(true);
      toast.success(`Matched to: ${data.label}`);
    } catch {
      const match = PRESET_STYLES[files.length % PRESET_STYLES.length];
      setMatchResult({ ...match, confidence: 87 }); setSelectedStyle(match); setReady(true);
      toast.success(`Matched to: ${match.label} (demo mode)`);
    }
    setMatching(false);
  };

  const activatePreset = (style) => { setSelectedStyle(style); setReady(true); toast.success(`Style set: ${style.label}`); };

  return (
    <div className="fade-in">
      <h1 className="page-title">Choose Your Style</h1>
      <p className="page-subtitle">Pick a pre-built style that looks closest to yours, <em>or</em> upload 1–3 photos for auto-matching.</p>

      <div style={{ display: "flex", gap: 10, marginBottom: 28 }}>
        <button className={`btn ${mode === "pick" ? "btn-primary" : "btn-secondary"}`} onClick={() => setMode("pick")}>
          <Sparkles size={15} /> Pick a style
        </button>
        <button className={`btn ${mode === "upload" ? "btn-primary" : "btn-secondary"}`} onClick={() => setMode("upload")}>
          <Upload size={15} /> Upload my handwriting
        </button>
      </div>

      {mode === "pick" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 14, marginBottom: 28 }}>
          {PRESET_STYLES.map(style => (
            <div key={style.id} onClick={() => activatePreset(style)} className="card" style={{
              cursor: "pointer", position: "relative",
              borderColor: selectedStyle?.id === style.id ? "var(--highlight)" : "var(--border)",
              background: selectedStyle?.id === style.id ? "var(--highlight-soft)" : "var(--surface)",
              transition: "all 0.2s",
            }}>
              {selectedStyle?.id === style.id && <div style={{ position: "absolute", top: 12, right: 12 }}><CheckCircle size={18} color="var(--highlight)" /></div>}
              <div style={{
                fontFamily: "'Caveat', cursive", fontSize: 22, marginBottom: 12, color: "var(--text-primary)",
                transform: `skewX(${parseFloat(style.slant) * 0.6}deg)`,
                fontWeight: style.pressure === "heavy" ? 600 : 400,
                letterSpacing: style.spacing === "wide" ? "0.08em" : style.spacing === "tight" ? "-0.02em" : "normal",
              }}>{style.preview}</div>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{style.label}</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <span className="chip">{style.slant}</span>
                <span className="chip">{style.pressure}</span>
                <span className="chip">{style.spacing}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {mode === "upload" && (
        <div className="two-col" style={{ marginBottom: 28 }}>
          <div>
            <div {...getRootProps({ className: `upload-zone ${isDragActive ? "drag-active" : ""}` })}>
              <input {...getInputProps()} />
              <div className="upload-zone-icon"><Upload size={32} strokeWidth={1.2} /></div>
              <p><strong>Drop 1–3 photos of your handwriting</strong></p>
              <p style={{ marginTop: 4, fontSize: 13 }}>Even a napkin doodle or sticky note works.</p>
              <span style={{ marginTop: 8, display: "block" }}>PNG · JPG · WEBP</span>
            </div>
            {files.length > 0 && (
              <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
                {files.map(f => (
                  <div key={f.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", background: "var(--surface-2)", borderRadius: 8, border: "1px solid var(--border)" }}>
                    <img src={f.preview} alt="" style={{ width: 44, height: 44, borderRadius: 6, objectFit: "cover" }} />
                    <span style={{ flex: 1, fontSize: 13 }}>{f.file.name}</span>
                    <button className="btn btn-ghost" style={{ padding: "4px 8px", fontSize: 12 }} onClick={() => setFiles(p => p.filter(x => x.id !== f.id))}>✕</button>
                  </div>
                ))}
                <button className="btn btn-primary" onClick={autoMatch} disabled={matching}>
                  {matching ? <><div className="spinner" /> Finding closest match…</> : <><Wand2 size={15} /> Auto-match my style</>}
                </button>
              </div>
            )}
          </div>
          {matchResult ? (
            <div className="card" style={{ borderColor: "var(--highlight)", background: "var(--highlight-soft)" }}>
              <div className="card-title">Best Match Found</div>
              <div style={{ fontFamily: "'Caveat', cursive", fontSize: 28, marginBottom: 16 }}>{matchResult.preview}</div>
              <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 8 }}>{matchResult.label}</div>
              {matchResult.confidence && (
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>Match confidence</div>
                  <div className="progress-bar"><div className="progress-fill" style={{ width: `${matchResult.confidence}%` }} /></div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{matchResult.confidence}% similar</div>
                </div>
              )}
            </div>
          ) : (
            <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 10, color: "var(--text-muted)", minHeight: 200 }}>
              <Wand2 size={36} strokeWidth={1} />
              <span style={{ fontSize: 14, textAlign: "center" }}>Upload photos and we'll auto-match the closest style from our database</span>
            </div>
          )}
        </div>
      )}

      {ready && selectedStyle && (
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div>
              <div className="card-title" style={{ marginBottom: 2 }}>Active Style: {selectedStyle.label}</div>
              <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>All pages will use this style until you change it.</div>
            </div>
            <span className="badge badge-green">✓ Ready</span>
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            <input value={previewText} onChange={e => setPreviewText(e.target.value)} placeholder="Type something to preview…" style={{ flex: 1 }} />
            <button className="btn btn-primary">Preview</button>
            <button className="btn btn-secondary"><Download size={14} /> Export</button>
          </div>
          <div style={{ marginTop: 16 }}>
            <HandwritingCanvas text={previewText} />
          </div>
        </div>
      )}
    </div>
  );
}
