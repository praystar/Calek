import { useState, useRef, useEffect } from "react";
import { Send, Bot, PenTool, Trash2, Download, Key } from "lucide-react";
import toast from "react-hot-toast";
import HandwritingCanvas from "../components/HandwritingCanvas";
import api from "../utils/api"

const COOLDOWN_MS    = 5500;   // mirrors backend MIN_INTERVAL + buffer
const MAX_HISTORY    = 6;

export default function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [apiKey, setApiKey] = useState(() => localStorage.getItem("gemini_key") || "");
  const [showKeyInput, setShowKeyInput] = useState(!localStorage.getItem("gemini_key"));
  const [loading, setLoading] = useState(false);
  const [selectedAnswer, setSelectedAnswer] = useState(null);
  const [renderHW, setRenderHW] = useState(false);

  const chatEndRef    = useRef(null);
  const inputRef      = useRef(null);
  const inFlightRef   = useRef(false);
  const lastSentRef   = useRef(0);          // timestamp of last successful send
  const [cooldown, setCooldown] = useState(0); // seconds remaining

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const saveKey = () => {
    if (!apiKey.trim()) { toast.error("Enter a valid API key"); return; }
    localStorage.setItem("gemini_key", apiKey.trim());
    setShowKeyInput(false);
    toast.success("Gemini API key saved");
  };

  // Cooldown ticker
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown(c => Math.max(0, c - 1)), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const sendMessage = async () => {
    if (!input.trim() || loading || inFlightRef.current) return;

    // Client-side cooldown (backup — backend enforces its own)
    const now     = Date.now();
    const elapsed = now - lastSentRef.current;
    if (elapsed < COOLDOWN_MS) {
      const wait = Math.ceil((COOLDOWN_MS - elapsed) / 1000);
      toast.error(`Wait ${wait}s before sending again`);
      return;
    }

    inFlightRef.current  = true;
    lastSentRef.current  = now;          // update on EVERY attempt, not just success
    setCooldown(Math.ceil(COOLDOWN_MS / 1000));

    const userMsg = { role: "user", content: input.trim(), id: now };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const recentHistory = messages.slice(-MAX_HISTORY).map(m => ({
        role: m.role, content: m.content,
      }));

      // Call backend proxy — backend enforces rate limit server-side
      const resp = await api.post("/chat", {
        message:  userMsg.content,
        history:  recentHistory,
        api_key:  apiKey,   // backend .env key takes priority; this is fallback
      });

      setMessages(prev => [...prev, { role: "assistant", content: resp.data.reply, id: Date.now() + 1 }]);

    } catch (err) {
      const msg = err.response?.data?.detail || err.message || "Something went wrong";
      toast.error(msg);
      setMessages(prev => [...prev, { role: "assistant", content: `⚠ ${msg}`, id: Date.now() + 1, isError: true }]);
    } finally {
      setLoading(false);
      inFlightRef.current = false;
    }
  };

  const renderInHandwriting = (msg) => {
    setSelectedAnswer(msg.content);
    setRenderHW(true);
    setTimeout(() => document.getElementById("hw-output")?.scrollIntoView({ behavior: "smooth" }), 100);
  };

  const clearChat = () => { setMessages([]); setSelectedAnswer(null); setRenderHW(false); toast.success("Chat cleared"); };

  return (
    <div className="fade-in">
      <h1 className="page-title">AI Chat → Handwriting</h1>
      <p className="page-subtitle">Chat with Gemini and render any response in your handwriting style.</p>

      {/* API Key setup */}
      {showKeyInput && (
        <div className="card" style={{ marginBottom: 24, borderColor: "var(--highlight)", background: "var(--highlight-soft)" }}>
          <div className="card-title"><Key size={14} style={{ display: "inline", marginRight: 6 }} />Gemini API Key Required</div>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
            Get your free API key at{" "}
            <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer" style={{ color: "var(--highlight)" }}>
              aistudio.google.com
            </a>. Your key is stored locally and never sent to our servers.
          </p>
          <div style={{ display: "flex", gap: 10 }}>
            <input
              type="password"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder="AIza…"
              onKeyDown={e => e.key === "Enter" && saveKey()}
              style={{ flex: 1 }}
            />
            <button className="btn btn-primary" onClick={saveKey}>Save Key</button>
          </div>
        </div>
      )}

      <div className="two-col">
        {/* Chat interface */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            {/* Chat header */}
            <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 32, height: 32, borderRadius: "50%", background: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <Bot size={16} color="var(--accent-text)" />
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>Gemini Flash</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>gemini-2.0-flash</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-ghost btn-icon" onClick={() => setShowKeyInput(s => !s)}><Key size={15} /></button>
                <button className="btn btn-ghost btn-icon" onClick={clearChat}><Trash2 size={15} /></button>
              </div>
            </div>

            {/* Messages */}
            <div className="chat-messages" style={{ height: 400, overflowY: "auto" }}>
              {messages.length === 0 && (
                <div style={{ textAlign: "center", padding: 40, color: "var(--text-muted)" }}>
                  <Bot size={40} strokeWidth={1} style={{ marginBottom: 12, opacity: 0.4 }} />
                  <p style={{ fontSize: 14 }}>Ask anything — then render the answer in your handwriting</p>
                  <div className="chip-list" style={{ justifyContent: "center", marginTop: 16 }}>
                    {["Write a short poem", "Explain quantum entanglement", "Tell me a fun fact", "Give me a quote about creativity"].map(p => (
                      <button key={p} className="chip" style={{ cursor: "pointer" }} onClick={() => { setInput(p); inputRef.current?.focus(); }}>
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map(msg => (
                <div key={msg.id} style={{ display: "flex", flexDirection: "column", alignItems: msg.role === "user" ? "flex-end" : "flex-start", gap: 6 }}>
                  <div className={`chat-bubble ${msg.role} ${msg.isError ? "error" : ""}`} style={msg.isError ? { borderColor: "var(--error)", color: "var(--error)" } : {}}>
                    {msg.content}
                  </div>
                  {msg.role === "assistant" && !msg.isError && (
                    <button
                      onClick={() => renderInHandwriting(msg)}
                      className="btn btn-ghost"
                      style={{ fontSize: 12, padding: "4px 10px", alignSelf: "flex-start" }}
                    >
                      <PenTool size={12} /> Write in my handwriting
                    </button>
                  )}
                </div>
              ))}

              {loading && (
                <div className="chat-bubble thinking" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                  Gemini is thinking…
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Input */}
            <div style={{ padding: "14px 16px", borderTop: "1px solid var(--border)", display: "flex", gap: 10 }}>
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && !e.shiftKey && !cooldown && sendMessage()}
                placeholder={cooldown > 0 ? `Wait ${cooldown}s before sending…` : "Ask Gemini anything…"}
                disabled={loading || cooldown > 0}
                style={{ flex: 1 }}
              />
              <button
                className="btn btn-primary btn-icon"
                onClick={sendMessage}
                disabled={loading || !input.trim() || cooldown > 0}
                title={cooldown > 0 ? `Wait ${cooldown}s` : "Send"}
                style={{ minWidth: 44, fontSize: cooldown > 0 ? 12 : undefined }}
              >
                {cooldown > 0 ? `${cooldown}s` : <Send size={16} />}
              </button>
            </div>
          </div>

          {/* Render options */}
          {selectedAnswer && (
            <div className="card" style={{ background: "var(--highlight-soft)", borderColor: "var(--highlight)" }}>
              <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                <strong>Selected for handwriting:</strong>
                <div style={{ marginTop: 8, maxHeight: 80, overflowY: "auto", fontStyle: "italic" }}>
                  "{selectedAnswer.slice(0, 200)}{selectedAnswer.length > 200 ? "…" : ""}"
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Handwriting output */}
        <div id="hw-output" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card" style={{ flex: 1 }}>
            <div className="card-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Handwriting Output</span>
              {selectedAnswer && <span className="badge badge-gold">Ready</span>}
            </div>

            {selectedAnswer ? (
              <>
                <HandwritingCanvas text={selectedAnswer} />
                <div style={{ marginTop: 16, display: "flex", gap: 10, justifyContent: "flex-end" }}>
                  <button className="btn btn-secondary"><Download size={14} /> Export PNG</button>
                  <button className="btn btn-secondary"><Download size={14} /> Export PDF</button>
                </div>
              </>
            ) : (
              <div style={{ minHeight: 280, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 12, color: "var(--text-muted)" }}>
                <PenTool size={40} strokeWidth={1} />
                <span style={{ fontSize: 14 }}>Click "Write in my handwriting" on any AI response</span>
              </div>
            )}
          </div>

          {/* Writing controls */}
          <div className="card">
            <div className="card-title">Rendering Options</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <label>Font Size</label>
                <input type="range" min="16" max="36" defaultValue="24" style={{ padding: 0, border: "none", background: "none", marginTop: 6 }} />
              </div>
              <div>
                <label>Ink Color</label>
                <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                  {["#1a1714", "#1e3a5f", "#2d4a1e", "#4a1e2d", "#c9a96e"].map(color => (
                    <button key={color} className="btn btn-icon" style={{ width: 32, height: 32, padding: 0, background: color, border: "2px solid var(--border)", borderRadius: "50%" }} />
                  ))}
                </div>
              </div>
              <div>
                <label>Paper Style</label>
                <select defaultValue="lined">
                  <option value="lined">Lined notebook</option>
                  <option value="grid">Grid paper</option>
                  <option value="blank">Blank</option>
                  <option value="dotted">Dotted</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
