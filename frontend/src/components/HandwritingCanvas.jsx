import { useEffect, useRef, useState } from "react";
import api from "../utils/api";

export default function HandwritingCanvas({
  text,
  placeholder,
  paperStyle = "lined",
  inkColor = "#1a1714",
}) {
  const [imgSrc,  setImgSrc]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);   // "fallback" | "error" | null
  const [reason,  setReason]  = useState("");
  const prevText = useRef("");

  useEffect(() => {
    if (!text || placeholder) return;
    if (text === prevText.current) return;
    prevText.current = text;

    let cancelled = false;
    setError(null);
    setReason("");

    const render = async () => {
      setLoading(true);
      try {
        const resp = await api.post(
          "/render",
          { text, paper_style: paperStyle, ink_color: inkColor, line_width: 760 },
          { responseType: "blob", timeout: 20000 }
        );

        // Backend can return JSON fallback even with 200 status
        // Detect by content-type
        const contentType = resp.headers?.["content-type"] || "";

        if (contentType.includes("application/json")) {
          // Read the JSON from the blob
          const jsonText = await resp.data.text();
          const json = JSON.parse(jsonText);
          if (!cancelled) {
            setImgSrc(null);
            setError("fallback");
            setReason(json.reason || "No handwriting style loaded yet.");
          }
          return;
        }

        if (!cancelled) {
          const url = URL.createObjectURL(resp.data);
          setImgSrc(prev => {
            if (prev) URL.revokeObjectURL(prev); // free old blob
            return url;
          });
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setImgSrc(null);
          setError("error");
          setReason(err.message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    const timer = setTimeout(render, 500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [text, placeholder, paperStyle, inkColor]);

  return (
    <div className="hw-canvas-wrapper" style={{ minHeight: 160 }}>

      {/* Loading */}
      {loading && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "16px 12px", color: "var(--text-muted)", fontSize: 13 }}>
          <div className="spinner" />
          Rendering in your handwriting…
        </div>
      )}

      {/* Rendered image */}
      {!loading && imgSrc && (
        <img
          src={imgSrc}
          alt="Handwriting render"
          style={{ width: "100%", display: "block", borderRadius: 4 }}
        />
      )}

      {/* Fallback — no glyphs uploaded yet */}
      {!loading && !imgSrc && error === "fallback" && (
        <div style={{ padding: "16px 12px" }}>
          <div className="hw-text" style={{ color: inkColor, opacity: 0.5 }}>
            {text}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 10, fontStyle: "italic" }}>
            ↑ Preview only (CSS font) — {reason}
          </div>
        </div>
      )}

      {/* Error */}
      {!loading && !imgSrc && error === "error" && (
        <div style={{ padding: "16px 12px" }}>
          <div className="hw-text" style={{ color: inkColor, opacity: 0.45 }}>{text}</div>
          <div style={{ fontSize: 12, color: "var(--error)", marginTop: 10 }}>
            Render failed: {reason}
          </div>
        </div>
      )}

      {/* Placeholder */}
      {!loading && !imgSrc && !error && (
        <div className={`hw-text ${placeholder ? "placeholder" : ""}`} style={{ color: placeholder ? "var(--text-muted)" : inkColor }}>
          {text || "Your handwriting will appear here…"}
        </div>
      )}

    </div>
  );
}
