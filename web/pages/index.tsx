import { useEffect, useRef, useState } from "react";

type Cand = { url: string; slug: string; full_name: string; headline: string; score: { name: number; slug: number; bio: number; face: number; combined: number } };
type Match = {
  instagram_username: string;
  instagram_full_name: string;
  linkedin_url: string | null;
  confidence: number;
  label: "confident" | "uncertain" | "reject";
  method: string;
  candidates: Cand[];
  notes: string[];
  error?: string;
};

export default function Home() {
  const [usernames, setUsernames] = useState<string>("");
  const [drag, setDrag] = useState(false);
  const [busyOcr, setBusyOcr] = useState(false);
  const [results, setResults] = useState<Match[]>([]);
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string>("");
  const fileRef = useRef<HTMLInputElement>(null);

  const handles = usernames.split(/[\s,]+/).map(s => s.trim().replace(/^@/, "")).filter(Boolean);

  async function handleImage(file: File) {
    setBusyOcr(true);
    setError("");
    try {
      const b64 = await new Promise<string>((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result as string);
        r.onerror = reject;
        r.readAsDataURL(file);
      });
      const res = await fetch("/api/ocr", { method: "POST", body: JSON.stringify({ image: b64 }), headers: { "Content-Type": "application/json" } });
      if (!res.ok) throw new Error(`OCR failed: ${res.status}`);
      const { usernames: found } = await res.json();
      if (!found || found.length === 0) {
        setError("No Instagram usernames detected in the image.");
        return;
      }
      const merged = Array.from(new Set([...handles, ...found]));
      setUsernames(merged.join("\n"));
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusyOcr(false);
    }
  }

  async function runAll() {
    setError("");
    setResults([]);
    setRunning(new Set(handles));
    const out: Match[] = [];
    await Promise.all(handles.map(async (h) => {
      try {
        const r = await fetch(`/api/match?username=${encodeURIComponent(h)}`);
        const j = await r.json();
        if (!r.ok || j?.error) {
          out.push({ instagram_username: h, instagram_full_name: "", linkedin_url: null, confidence: 0, label: "reject", method: "error", candidates: [], notes: [], error: j?.error || `HTTP ${r.status}` });
        } else {
          out.push({ ...j, instagram_username: j.instagram_username || h });
        }
      } catch (e: any) {
        out.push({ instagram_username: h, instagram_full_name: "", linkedin_url: null, confidence: 0, label: "reject", method: "error", candidates: [], notes: [], error: e.message || String(e) });
      } finally {
        setRunning(prev => { const n = new Set(prev); n.delete(h); return n; });
        setResults([...out].sort((a, b) => b.confidence - a.confidence));
      }
    }));
  }

  return (
    <div className="container">
      <h1>yoyo</h1>
      <p className="sub">Instagram → LinkedIn. Drop a screenshot or paste handles. Returns ranked candidates with confidence.</p>

      <div className="row">
        <div className="col">
          <div className="card">
            <div
              className={`dropzone ${drag ? "drag" : ""}`}
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) handleImage(f); }}
            >
              <input ref={fileRef} type="file" accept="image/*" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleImage(f); }} />
              {busyOcr ? <><span className="spinner" />OCR via Mistral…</> : <>📷 Drop image with IG handles, or click to upload</>}
            </div>
          </div>
        </div>

        <div className="col">
          <div className="card">
            <textarea
              placeholder="one Instagram handle per line, or comma-separated&#10;e.g. yoyommne, dabittan, ayrtonnn_b"
              value={usernames}
              onChange={(e) => setUsernames(e.target.value)}
            />
            {handles.length > 0 && (
              <div className="usernames">
                {handles.map(h => <span key={h} className="chip">@{h}</span>)}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 14, color: "#9aa0a6" }}>{handles.length} handle{handles.length !== 1 ? "s" : ""} queued</div>
        <button className="go" disabled={handles.length === 0 || running.size > 0} onClick={runAll}>
          {running.size > 0 ? <><span className="spinner" />running {running.size}…</> : "Resolve"}
        </button>
      </div>

      {error && <div className="err">{error}</div>}

      {results.length > 0 && (
        <div className="result">
          {results.map(r => (
            <div key={r.instagram_username} className={`r-row ${r.label}`}>
              <div>
                <div className="handle">@{r.instagram_username}</div>
                {r.instagram_full_name && <div style={{ fontSize: 13, color: "#9aa0a6" }}>{r.instagram_full_name}</div>}
              </div>
              <div className="li-list">
                {r.linkedin_url ? (
                  <>
                    <a href={r.linkedin_url} target="_blank" rel="noreferrer">{r.linkedin_url.replace("https://www.linkedin.com/in/", "")}</a>
                    <span className={`label ${r.label}`}>{r.label}</span>
                    {r.candidates && r.candidates.length > 1 && (
                      <div className="notes">runners-up: {r.candidates.slice(1, 4).map(c => c.slug).join(", ")}</div>
                    )}
                  </>
                ) : (
                  <span style={{ color: "#9aa0a6" }}>{r.error || "no match"}</span>
                )}
              </div>
              <div className="probability">{Math.round((r.confidence || 0) * 100)}%</div>
            </div>
          ))}
        </div>
      )}

      <div className="footer">backend: {process.env.NEXT_PUBLIC_YOYO_BACKEND_URL || "configure YOYO_BACKEND_URL"}</div>
    </div>
  );
}
