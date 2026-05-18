import { useRef, useState } from "react";

type Score = { name: number; slug: number; bio: number; face: number; combined: number };
type Cand = { url: string; slug: string; full_name: string; headline: string; score: Score };
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

type PhotoCand = {
  linkedin_url: string;
  slug: string;
  full_name: string;
  headline: string;
  face_similarity: number | null;
  source: string;
};

type PhotoResult = { candidates: PhotoCand[]; notes: string[]; error?: string };

const BACKEND = process.env.NEXT_PUBLIC_YOYO_BACKEND_URL || "";

function friendlyError(e: any, status?: number): string {
  if (status === 504 || /timeout|abort/i.test(String(e?.message || e))) return "Took too long to answer";
  if (status && status >= 500) return "The matcher had a hiccup — try again";
  if (status === 404) return "Couldn't find this account";
  if (/fetch|network/i.test(String(e?.message || e))) return "Couldn't reach the matcher";
  return "Something went wrong";
}

export default function Home() {
  const [mode, setMode] = useState<"handle" | "photo">("handle");
  return (
    <div className="container">
      <h1>yoyo</h1>
      <p className="sub">Find someone's LinkedIn — by their Instagram handle, or just their photo.</p>

      <div className="tabs">
        <button className={`tab ${mode === "handle" ? "active" : ""}`} onClick={() => setMode("handle")}>By Instagram handle</button>
        <button className={`tab ${mode === "photo" ? "active" : ""}`} onClick={() => setMode("photo")}>By photo</button>
      </div>

      {mode === "handle" ? <HandleMode /> : <PhotoMode />}

      <div className="footer">Instagram → LinkedIn matcher</div>
    </div>
  );
}

function HandleMode() {
  const [usernames, setUsernames] = useState<string>("");
  const [drag, setDrag] = useState(false);
  const [busyOcr, setBusyOcr] = useState(false);
  const [results, setResults] = useState<Match[]>([]);
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string>("");
  const fileRef = useRef<HTMLInputElement>(null);

  const handles = usernames.split(/[\s,]+/).map(s => s.trim().replace(/^@/, "")).filter(Boolean);

  async function handleImage(file: File) {
    setBusyOcr(true); setError("");
    try {
      const b64 = await fileToDataUrl(file);
      const res = await fetch("/api/ocr", { method: "POST", body: JSON.stringify({ image: b64 }), headers: { "Content-Type": "application/json" } });
      if (!res.ok) throw new Error(`OCR failed: ${res.status}`);
      const { usernames: found } = await res.json();
      if (!found || found.length === 0) { setError("No Instagram usernames found in the image."); return; }
      setUsernames(Array.from(new Set([...handles, ...found])).join("\n"));
    } catch (e: any) { setError(e.message || String(e)); } finally { setBusyOcr(false); }
  }

  async function runOne(h: string): Promise<Match> {
    if (!BACKEND) return { instagram_username: h, instagram_full_name: "", linkedin_url: null, confidence: 0, label: "reject", method: "error", candidates: [], notes: [], error: "Backend not configured" };
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 240_000);
    try {
      const r = await fetch(`${BACKEND.replace(/\/$/, "")}/match/${encodeURIComponent(h)}`, { signal: ctrl.signal });
      let j: any = {}; try { j = await r.json(); } catch {}
      if (!r.ok) return { instagram_username: h, instagram_full_name: "", linkedin_url: null, confidence: 0, label: "reject", method: "error", candidates: [], notes: [], error: friendlyError(j?.detail || j?.error, r.status) };
      return { ...j, instagram_username: j.instagram_username || h };
    } catch (e: any) {
      return { instagram_username: h, instagram_full_name: "", linkedin_url: null, confidence: 0, label: "reject", method: "error", candidates: [], notes: [], error: friendlyError(e) };
    } finally { clearTimeout(t); }
  }

  async function runAll() {
    setError(""); setResults([]); setRunning(new Set(handles));
    const out: Match[] = [];
    const queue = [...handles];
    async function worker() {
      while (queue.length) {
        const h = queue.shift()!;
        const res = await runOne(h);
        out.push(res);
        setRunning(prev => { const n = new Set(prev); n.delete(h); return n; });
        setResults([...out].sort((a, b) => b.confidence - a.confidence));
      }
    }
    await Promise.all(Array.from({ length: 2 }, () => worker()));
  }

  return (
    <>
      <p className="explainer">
        Paste Instagram handles (one per line) or drop a screenshot of an IG following/followers list.
        We extract names, search LinkedIn, and rank candidates by face match + name overlap.
      </p>
      <div className="row">
        <div className="col">
          <div className="card">
            <div className={`dropzone ${drag ? "drag" : ""}`}
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) handleImage(f); }}>
              <input ref={fileRef} type="file" accept="image/*" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleImage(f); }} />
              {busyOcr ? <><span className="spinner" />Reading handles from image…</> : <>📷 Drop a screenshot of IG handles, or click to upload</>}
            </div>
          </div>
        </div>
        <div className="col">
          <div className="card">
            <textarea placeholder={"one Instagram handle per line\ne.g.\nyoyommne\ndabittan"} value={usernames} onChange={(e) => setUsernames(e.target.value)} />
            {handles.length > 0 && (
              <div className="usernames">{handles.map(h => <span key={h} className="chip">@{h}</span>)}</div>
            )}
          </div>
        </div>
      </div>

      <div className="card actions">
        <div className="meta">
          {handles.length} handle{handles.length !== 1 ? "s" : ""} queued
          {running.size > 0 && <span style={{ marginLeft: 12 }}>· each can take ~30 s</span>}
        </div>
        <button className="go" disabled={handles.length === 0 || running.size > 0} onClick={runAll}>
          {running.size > 0 ? <><span className="spinner" />Looking up {running.size}…</> : "Find LinkedIn"}
        </button>
      </div>

      {error && <div className="err">{error}</div>}

      {results.length > 0 && (
        <div className="result">
          {results.map(r => (
            <div key={r.instagram_username} className={`r-row ${r.label}`}>
              <div>
                <div className="handle">@{r.instagram_username}</div>
                {r.instagram_full_name && <div className="sm">{r.instagram_full_name}</div>}
              </div>
              <div className="li-list">
                {r.linkedin_url ? (
                  <>
                    <a href={r.linkedin_url} target="_blank" rel="noreferrer">{r.linkedin_url.replace("https://www.linkedin.com/in/", "")}</a>
                    <span className={`label ${r.label}`}>{r.label}</span>
                  </>
                ) : (
                  <span className="sm">{r.error || "no match"}</span>
                )}
              </div>
              <div className="probability">{Math.round((r.confidence || 0) * 100)}%</div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function PhotoMode() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>("");
  const [drag, setDrag] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PhotoResult | null>(null);
  const [error, setError] = useState<string>("");
  const fileRef = useRef<HTMLInputElement>(null);

  function setImage(f: File) {
    setFile(f); setResult(null); setError("");
    const r = new FileReader(); r.onload = () => setPreview(r.result as string); r.readAsDataURL(f);
  }

  async function run() {
    if (!file || !BACKEND) return;
    setRunning(true); setError(""); setResult(null);
    const form = new FormData(); form.append("file", file);
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 240_000);
    try {
      const r = await fetch(`${BACKEND.replace(/\/$/, "")}/match-photo`, { method: "POST", body: form, signal: ctrl.signal });
      let j: any = {}; try { j = await r.json(); } catch {}
      if (!r.ok) { setError(friendlyError(j?.detail, r.status)); return; }
      setResult(j as PhotoResult);
    } catch (e: any) {
      setError(friendlyError(e));
    } finally { clearTimeout(t); setRunning(false); }
  }

  return (
    <>
      <p className="explainer">
        Drop any photo of the person's face. We run reverse-image search (Google Lens + Google Images) for LinkedIn matches,
        then score each candidate by face similarity (AWS Rekognition). No Instagram handle needed.
      </p>
      <div className="card">
        <div className={`dropzone tall ${drag ? "drag" : ""}`}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) setImage(f); }}>
          <input ref={fileRef} type="file" accept="image/*" onChange={(e) => { const f = e.target.files?.[0]; if (f) setImage(f); }} />
          {preview ? (
            <img src={preview} alt="preview" className="preview" />
          ) : (
            <>👤 Drop a photo of the person, or click to upload</>
          )}
        </div>
      </div>

      <div className="card actions">
        <div className="meta">
          {file ? file.name : "no photo yet"}
          {running && <span style={{ marginLeft: 12 }}>· this can take ~30–60 s</span>}
        </div>
        <button className="go" disabled={!file || running} onClick={run}>
          {running ? <><span className="spinner" />Searching…</> : "Find LinkedIn"}
        </button>
      </div>

      {error && <div className="err">{error}</div>}

      {result && (
        <div className="result">
          {result.candidates.length === 0 && <div className="card sm">No LinkedIn matches found for this photo. Try another image (clear face, well-lit, looking at camera).</div>}
          {result.candidates.map(c => {
            const pct = Math.round(((c.face_similarity ?? 0) * 100));
            const label = pct >= 80 ? "confident" : pct >= 50 ? "uncertain" : "reject";
            return (
              <div key={c.slug} className={`r-row ${label}`}>
                <div>
                  <div className="handle">{c.full_name || c.slug}</div>
                  {c.headline && <div className="sm">{c.headline}</div>}
                </div>
                <div className="li-list">
                  <a href={c.linkedin_url} target="_blank" rel="noreferrer">{c.linkedin_url.replace("https://www.linkedin.com/in/", "")}</a>
                  <span className={`label ${label}`}>{label}</span>
                  <div className="notes">found via {c.source}</div>
                </div>
                <div className="probability">{pct}%</div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as string);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}
