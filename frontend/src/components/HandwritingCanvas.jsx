import { useEffect, useRef, useState } from "react";
import api from "../utils/api";

/**
 * HandwritingCanvas
 * - Calls /render on the ML backend to get a PNG image
 * - Falls back to CSS-styled Caveat font if backend unavailable
 * - Debounced: waits 400ms after text stops changing before calling API
 */
export default function HandwritingCanvas({ text, placeholder, paperStyle = "lined", inkColor = "#1a1714" }) {
  const [imgSrc, setImgSrc] = useState(null);
  const [loading, setLoading] = useState(false);
  const prevText = useRef("");

  useEffect(() => {
    if (!text || placeholder || text === prevText.current) return;
    prevText.current = text;

    let cancelled = false;
    const render = async () => {
      setLoading(true);
      try {
        const resp = await api.post(
          "/render",
          { text, paper_style: paperStyle, ink_color: inkColor, line_width: 760 },
          { responseType: "blob", timeout: 15000 }
        );
        if (!cancelled) {
          const url = URL.createObjectURL(resp.data);
          setImgSrc(url);
        }
      } catch {
        if (!cancelled) setImgSrc(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    const timer = setTimeout(render, 400);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [text, placeholder, paperStyle, inkColor]);

  return (
    <div className="hw-canvas-wrapper" style={{ minHeight: 160 }}>
      {loading && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: 12, color: "var(--text-muted)", fontSize: 13 }}>
          <div className="spinner" />
          Rendering in your handwriting…
        </div>
      )}
      {!loading && imgSrc && (
        <img src={imgSrc} alt="Handwriting render" style={{ width: "100%", display: "block", borderRadius: 4 }} />
      )}
      {!loading && !imgSrc && (
        <div className={`hw-text ${placeholder ? "placeholder" : ""}`} style={{ color: placeholder ? "var(--text-muted)" : inkColor }}>
          {text || "Your handwriting will appear here…"}
        </div>
      )}
    </div>
  );
}
