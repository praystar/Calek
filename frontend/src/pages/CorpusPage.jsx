import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, Wand2, Download, RefreshCw, CheckCircle, Sparkles } from "lucide-react";
import toast from "react-hot-toast";
import HandwritingCanvas from "../components/HandwritingCanvas";
import api from "../utils/api";

const ALL_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,!?'\"".split("");

const PRESET_STYLES = [
  { id: "iam_a01", label: "Neat & Upright",   slant: "0°",   pressure: "medium", spacing: "normal" },
  { id: "iam_b02", label: "Casual Slanted",   slant: "-8°",  pressure: "light",  spacing: "wide"   },
  { id: "iam_c03", label: "Loopy Cursive",    slant: "-12°", pressure: "medium", spacing: "tight"  },
  { id: "iam_d04", label: "Tight & Small",    slant: "-4°",  pressure: "heavy",  spacing: "tight"  },
  { id: "iam_e05", label: "Wide & Relaxed",   slant: "2°",   pressure: "light",  spacing: "wide"   },
  { id: "iam_f06", label: "Bold & Blocky",    slant: "0°",   pressure: "heavy",  spacing: "normal" },
  { id: "iam_g07", label: "Hurried Scrawl",   slant: "-15°", pressure: "light",  spacing: "wide"   },
  { id: "iam_h08", label: "Elegant Longhand", slant: "-6°",  pressure: "medium", spacing: "normal" },
];

export default function CorpusPage() {
  const [mode,         setMode]         = useState("upload"); // "upload" | "preset"
  const [files,        setFiles]        = useState([]);
  const [analyzing,    setAnalyzing]    = useState(false);
  const [synthesizing, setSynthesizing] = useState(false);
  const [result,       setResult]       = useState(null);
  const [activeStyle,  setActiveStyle]  = useState(null);  // preset or "uploaded"
  const [previewText,  setPreviewText]  = useState("The quick brown fox jumps over the lazy dog.");

  // ── Dropzone ────────────────────────────────────────────────────────────────
  const onDrop = useCallback((accepted) => {
    setFiles(prev => [...prev, ...accepted.map(f => ({
      file: f, id: Math.random().toString(36).slice(2), preview: URL.createObjectURL(f),
    }))]);
    toast.success(`${accepted.length} photo(s) added`);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { "image/*": [".png", ".jpg", ".jpeg", ".webp"] }, multiple: true, maxFiles: 5,
  });

  // ── Upload + extract ─────────────────────────────────────────────────────────
  const analyze = async () => {
    if (!files.length) { toast.error("Upload at least one photo first"); return; }
    setAnalyzing(true);
    try {
      const formData = new FormData();
      files.forEach(f => formData.append("images", f.file));
      const { data } = await api.post("/corpus/analyze", formData);
      setResult(data);
      setActiveStyle("uploaded");
      toast.success(`Extracted ${data.characters_found} real characters from your handwriting!`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Extraction failed — try a clearer photo");
    }
    setAnalyzing(false);
  };

  // ── Synthesize missing ───────────────────────────────────────────────────────
  const synthesizeMissing = async () => {
    if (!result?.characters_missing?.length) return;
    setSynthesizing(true);
    try {
      const { data } = await api.post("/corpus/synthesize", { missing_chars: result.characters_missing });
      setResult(prev => ({ ...prev, characters_missing: [], synthesized_chars: data.synthesized, coverage_pct: 100 }));
      toast.success(`Filled ${data.synthesized.length} missing chars in your style`);
    } catch {
      toast.error("Synthesis failed");
    }
    setSynthesizing(false);
  };

  // ── Activate preset ──────────────────────────────────────────────────────────
  const activatePreset = async (style) => {
    try {
      await api.post("/corpus/set-preset", { style_id: style.id });
    } catch {
      // backend offline — still set locally for CSS preview
    }
    setActiveStyle(style.id);
    setResult(null);
    toast.success(`Style set: ${style.label}`);
  };

  const ready = activeStyle !== null;

  return (
    <div className="fade-in">
      <h1 className="page-title">Handwriting Style</h1>
      <p className="page-subtitle">
        Upload photos to render text in <strong>your actual handwriting</strong>, or pick a pre-built style from the IAM database.
      </p>

      {/* Mode tabs */}
      <div style={{ display: "flex", gap: 10, marginBottom: 28 }}>
        <button className={`btn ${mode === "upload" ? "btn-primary" : "btn-secondary"}`} onClick={() => setMode("upload")}>
          <Upload size={15} /> My handwriting
        </button>
        <button className={`btn ${mode === "preset" ? "btn-primary" : "btn-secondary"}`} onClick={() => setMode("preset")}>
          <Sparkles size={15} /> Pick a preset
        </button>
      </div>

      {/* ── UPLOAD MODE ─────────────────────────────────────────────────────── */}
      {mode === "upload" && (
        <div className="two-col" style={{ marginBottom: 24 }}>
          <div>
            <div {...getRootProps({ className: `upload-zone ${isDragActive ? "drag-active" : ""}` })}>
              <input {...getInputProps()} />
              <div className="upload-zone-icon"><Upload size={36} strokeWidth={1.2} /></div>
              <p><strong>Drop photos of your handwriting here</strong></p>
              <p style={{ marginTop: 6, fontSize: 13, color: "var(--text-secondary)" }}>
                A sticky note, notebook page, or any paper with dark ink on light background.
              </p>
              <span style={{ marginTop: 8, display: "block" }}>PNG · JPG · WEBP · up to 5 images</span>
            </div>

            {files.length > 0 && (
              <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
                {files.map(f => (
                  <div key={f.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", background: "var(--surface-2)", borderRadius: 8, border: "1px solid var(--border)" }}>
                    <img src={f.preview} alt="" style={{ width: 48, height: 48, borderRadius: 6, objectFit: "cover", flexShrink: 0 }} />
                    <span style={{ flex: 1, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.file.name}</span>
                    <button className="btn btn-ghost" style={{ padding: "4px 8px", fontSize: 12 }} onClick={() => setFiles(p => p.filter(x => x.id !== f.id))}>✕</button>
                  </div>
                ))}
                <button className="btn btn-primary" onClick={analyze} disabled={analyzing}>
                  {analyzing ? <><div className="spinner" /> Extracting your handwriting…</> : <><Wand2 size={15} /> Extract my handwriting</>}
                </button>
              </div>
            )}

            <div className="card" style={{ marginTop: 16, background: "var(--highlight-soft)", borderColor: "var(--highlight)" }}>
              <div className="card-title">📸 Tips for best results</div>
              <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.8 }}>
                • Dark ink on white/light paper only<br />
                • Flat lay, no shadows, good lighting<br />
                • Include every letter you'll need<br />
                • Write: <em>"Pack my box with five dozen liquor jugs"</em>
              </div>
            </div>
          </div>

          {/* Results panel */}
          {result ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                {[
                  { value: result.total_glyphs_extracted, label: "Glyphs extracted" },
                  { value: `${result.coverage_pct}%`,    label: "Coverage" },
                  { value: result.characters_found,       label: "Real chars", color: "var(--success)" },
                  { value: result.characters_missing?.length ?? 0, label: "Missing",
                    color: result.characters_missing?.length ? "var(--error)" : "var(--success)" },
                ].map(s => (
                  <div key={s.label} className="stat-card">
                    <div className="stat-value" style={s.color ? { color: s.color } : {}}>{s.value}</div>
                    <div className="stat-label">{s.label}</div>
                  </div>
                ))}
              </div>

              <div className="card">
                <div className="card-title">Style Detected</div>
                {Object.entries(result.style_metrics || {}).map(([k, v]) => (
                  <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, padding: "5px 0", borderBottom: "1px solid var(--border)" }}>
                    <span style={{ color: "var(--text-secondary)" }}>{k.replace(/_/g, " ")}</span>
                    <span style={{ fontWeight: 500 }}>{v}</span>
                  </div>
                ))}
              </div>

              {result.characters_missing?.length > 0 && (
                <div>
                  <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 8 }}>
                    {result.characters_missing.length} chars weren't in your photos — synthesize them in your style:
                  </p>
                  <button className="btn btn-primary" onClick={synthesizeMissing} disabled={synthesizing}>
                    {synthesizing ? <><div className="spinner" /> Synthesizing…</> : <><RefreshCw size={14} /> Fill {result.characters_missing.length} missing chars</>}
                  </button>
                </div>
              )}

              {!result.characters_missing?.length && (
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px", background: "#f0fdf4", borderRadius: 8, border: "1px solid #86efac" }}>
                  <CheckCircle size={16} color="var(--success)" />
                  <span style={{ fontSize: 13, color: "#15803d", fontWeight: 500 }}>Full coverage — rendering in your real handwriting</span>
                </div>
              )}
            </div>
          ) : (
            <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 12, color: "var(--text-muted)", minHeight: 240 }}>
              <Upload size={40} strokeWidth={1} />
              <span style={{ fontSize: 14 }}>Upload your photos to get started</span>
            </div>
          )}
        </div>
      )}

      {/* ── PRESET MODE ─────────────────────────────────────────────────────── */}
      {mode === "preset" && (
        <>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 18 }}>
            These are real writer styles from the <strong>IAM Handwriting Database</strong> — a public research corpus of 657 writers.
            The ML pipeline still runs: style metrics are loaded, missing chars are synthesized to match each style.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 14, marginBottom: 28 }}>
            {PRESET_STYLES.map(style => {
              const isActive = activeStyle === style.id;
              return (
                <div key={style.id} onClick={() => activatePreset(style)} className="card" style={{
                  cursor: "pointer", position: "relative", transition: "all 0.2s",
                  borderColor: isActive ? "var(--highlight)" : "var(--border)",
                  background:  isActive ? "var(--highlight-soft)" : "var(--surface)",
                }}>
                  {isActive && <div style={{ position: "absolute", top: 12, right: 12 }}><CheckCircle size={18} color="var(--highlight)" /></div>}
                  {/* Live CSS preview of each style */}
                  <div style={{
                    fontFamily: "'Caveat', cursive",
                    fontSize: 22,
                    marginBottom: 12,
                    color: "var(--text-primary)",
                    transform: `skewX(${parseFloat(style.slant) * 0.6}deg)`,
                    fontWeight: style.pressure === "heavy" ? 600 : 400,
                    letterSpacing: style.spacing === "wide" ? "0.08em" : style.spacing === "tight" ? "-0.02em" : "normal",
                    lineHeight: 1.4,
                  }}>
                    Hello World
                  </div>
                  <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{style.label}</div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <span className="chip">{style.slant}</span>
                    <span className="chip">{style.pressure}</span>
                    <span className="chip">{style.spacing}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* ── Glyph map (upload mode only) ────────────────────────────────────── */}
      {result && mode === "upload" && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-title">Character Coverage</div>
          <div style={{ display: "flex", gap: 16, marginBottom: 14, fontSize: 12 }}>
            {[
              { color: "#f0fdf4", border: "1px solid #86efac", label: "Your handwriting" },
              { color: "var(--highlight-soft)", border: "1px solid var(--highlight)", label: "Synthesized in your style" },
              { color: "#fef2f2", border: "1px dashed #fca5a5", label: "Missing" },
            ].map(s => (
              <span key={s.label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ width: 12, height: 12, background: s.color, border: s.border, borderRadius: 3, display: "inline-block" }} />
                {s.label}
              </span>
            ))}
          </div>
          <div className="glyph-grid">
            {ALL_CHARS.map(char => {
              const isReal  = result.characters_present?.includes(char);
              const isSynth = result.synthesized_chars?.includes(char);
              return (
                <div key={char}
                  className={`glyph-cell ${isSynth ? "synthesized" : isReal ? "present" : "missing"}`}
                  title={isReal ? "Real glyph from your photo" : isSynth ? "Synthesized in your style" : "Missing"}>
                  {char}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Preview ─────────────────────────────────────────────────────────── */}
      {ready && (
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div className="card-title" style={{ marginBottom: 0 }}>Preview</div>
            <span className="badge badge-gold">
              {activeStyle === "uploaded" ? "✦ Your real handwriting" : `✦ ${PRESET_STYLES.find(s => s.id === activeStyle)?.label}`}
            </span>
          </div>
          <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
            <input value={previewText} onChange={e => setPreviewText(e.target.value)} placeholder="Type to preview…" style={{ flex: 1 }} />
            <button className="btn btn-secondary"><Download size={14} /> Export PNG</button>
          </div>
          <HandwritingCanvas text={previewText} />
        </div>
      )}
    </div>
  );
}
