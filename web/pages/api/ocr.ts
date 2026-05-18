import type { NextApiRequest, NextApiResponse } from "next";

export const config = { api: { bodyParser: { sizeLimit: "10mb" } } };

const PROMPT = `Extract every Instagram username visible in the image.
The username is the @handle (e.g. "yoyommne"), not the display name (e.g. "Yohan Mamane").
Return a JSON object matching the schema. Use the bare username (no @ prefix).
If none are visible, return an empty array.`;

const SCHEMA = {
  type: "object",
  properties: {
    usernames: {
      type: "array",
      items: {
        type: "string",
        pattern: "^[A-Za-z0-9._]{2,30}$",
      },
    },
  },
  required: ["usernames"],
  additionalProperties: false,
};

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "POST") return res.status(405).end();
  const key = process.env.MISTRAL_API_KEY;
  if (!key) return res.status(500).json({ error: "MISTRAL_API_KEY not set on server" });
  const { image } = req.body || {};
  if (!image || typeof image !== "string") return res.status(400).json({ error: "missing image (base64 data URL)" });
  try {
    const r = await fetch("https://api.mistral.ai/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
      body: JSON.stringify({
        model: "pixtral-12b-2409",
        max_tokens: 1200,
        temperature: 0,
        response_format: {
          type: "json_schema",
          json_schema: { name: "instagram_usernames", strict: true, schema: SCHEMA },
        },
        messages: [{
          role: "user",
          content: [
            { type: "text", text: PROMPT },
            { type: "image_url", image_url: image },
          ],
        }],
      }),
    });
    if (!r.ok) {
      const txt = await r.text();
      return res.status(502).json({ error: `Mistral ${r.status}: ${txt.slice(0, 400)}` });
    }
    const j: any = await r.json();
    const raw: string = j?.choices?.[0]?.message?.content || "{}";
    let parsed: any = {};
    try { parsed = JSON.parse(raw); } catch { parsed = {}; }
    const list: string[] = Array.isArray(parsed?.usernames) ? parsed.usernames : [];
    const usernames = Array.from(new Set(
      list.map(s => String(s).trim().replace(/^@/, ""))
        .filter(s => /^[A-Za-z0-9._]{2,30}$/.test(s))
    ));
    return res.status(200).json({ usernames });
  } catch (e: any) {
    return res.status(500).json({ error: e.message || String(e) });
  }
}
