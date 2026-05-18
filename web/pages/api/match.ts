import type { NextApiRequest, NextApiResponse } from "next";

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  const backend = process.env.YOYO_BACKEND_URL;
  if (!backend) return res.status(500).json({ error: "YOYO_BACKEND_URL not set on server" });
  const username = String(req.query.username || "").trim();
  if (!username) return res.status(400).json({ error: "missing username" });
  try {
    const r = await fetch(`${backend.replace(/\/$/, "")}/match/${encodeURIComponent(username)}`, {
      headers: { Accept: "application/json" },
    });
    const text = await r.text();
    res.status(r.status).setHeader("Content-Type", "application/json").send(text);
  } catch (e: any) {
    res.status(502).json({ error: `backend unreachable: ${e.message || e}` });
  }
}
