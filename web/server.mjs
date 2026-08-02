// RetailFlowAI web — statik server (bog'liqliksiz, Node built-in).
//
// Nega `serve` emas: `serve` (serve-handler) serve.json'da `rewrites` bo'lsa
// `/` uchun avtomatik `index.html` bermaydi va faqat `**` root'ni ushlaydi —
// shu sabab `/`=landing va `/login`=SPA ni ajratib bo'lmaydi. Bu server aynan
// shuni beradi:
//   GET  /            -> dist/landing.html   (marketing landing)
//   GET  /<mavjud fayl> -> o'sha fayl        (assets, favicon, landing.html, ...)
//   GET  /login, ...  -> dist/index.html     (SPA fallback — React router)
//
// Health check (railway.json healthcheckPath "/") 200 qaytaradi.

import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { join, extname, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const DIST = join(fileURLToPath(new URL(".", import.meta.url)), "dist");
const PORT = process.env.PORT || 3000;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".txt": "text/plain; charset=utf-8",
  ".webmanifest": "application/manifest+json",
};

async function fileExists(p) {
  try {
    return (await stat(p)).isFile();
  } catch {
    return false;
  }
}

async function send(res, filePath, code = 200) {
  const buf = await readFile(filePath);
  const type = MIME[extname(filePath).toLowerCase()] || "application/octet-stream";
  res.writeHead(code, {
    "Content-Type": type,
    "Cache-Control": extname(filePath) === ".html" ? "no-cache" : "public, max-age=3600",
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
  });
  res.end(buf);
}

// ─── Demo so'rovi → Telegram (landing forma) ─────────────────────────────
// Same-origin: landing `/api/demo-request` ga POST qiladi (CORS yo'q).
// Token FAQAT server env'da (TELEGRAM_BOT_TOKEN / TELEGRAM_DEMO_CHAT_ID).
function jsonRes(res, code, obj) {
  res.writeHead(code, {
    "Content-Type": "application/json; charset=utf-8",
    "Strict-Transport-Security": "max-age=31536000",
  });
  res.end(JSON.stringify(obj));
}
function readJson(req, limit = 65536) {
  return new Promise((resolve, reject) => {
    let data = "", size = 0;
    req.on("data", (c) => { size += c.length; if (size > limit) { reject(new Error("too_large")); req.destroy(); } else data += c; });
    req.on("end", () => { try { resolve(data ? JSON.parse(data) : {}); } catch (e) { reject(e); } });
    req.on("error", reject);
  });
}
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

async function sendTelegram(text) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chat = process.env.TELEGRAM_DEMO_CHAT_ID;
  if (!token || !chat) { console.warn("[demo] telegram_not_configured — lead faqat logda"); return false; }
  try {
    const r = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chat, text, parse_mode: "HTML", disable_web_page_preview: true }),
    });
    if (r.ok) { const j = await r.json(); if (j.ok) return true; }
    console.error("[demo] telegram_send_failed", r.status);
  } catch (e) { console.error("[demo] telegram_error", e && e.message); }
  return false;
}

async function handleDemo(req, res) {
  let body;
  try { body = await readJson(req); } catch { return jsonRes(res, 400, { ok: false, error: "bad_json" }); }
  if (body.website) { return jsonRes(res, 200, { ok: true, message_key: "demo.received" }); } // honeypot
  const type = body.type === "korxona" ? "korxona" : "dokon";
  const business = String(body.business_name || "").trim();
  const name = String(body.name || "").trim();
  const phone = String(body.phone || "").trim();
  const region = String(body.region || "").trim();
  const note = String(body.note || "").trim();
  if (business.length < 2 || name.length < 2 || phone.length < 7) {
    return jsonRes(res, 422, { ok: false, error: "validation" });
  }
  console.log(`[demo] lead type=${type} business=${business} name=${name} phone=${phone} region=${region || "-"}`);
  const turi = type === "dokon" ? "🏪 Do'kon" : "🏭 Korxona";
  const lines = [
    "🆕 <b>Yangi demo so'rovi — RetailFlowAI</b>", "",
    `<b>Turi:</b> ${turi}`,
    `<b>Nomi:</b> ${esc(business)}`,
    `<b>Mas'ul:</b> ${esc(name)}`,
    `<b>Telefon:</b> ${esc(phone)}`,
  ];
  if (region) lines.push(`<b>Hudud:</b> ${esc(region)}`);
  if (note) lines.push(`<b>Izoh:</b> ${esc(note)}`);
  lines.push("", "📞 Sotuv bo'limi — bog'laning.");
  await sendTelegram(lines.join("\n"));
  return jsonRes(res, 200, { ok: true, message_key: "demo.received" });
}

const server = createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent((req.url || "/").split("?")[0]);

    // Demo so'rovi (public, same-origin)
    if (pathname === "/api/demo-request") {
      if (req.method !== "POST") return jsonRes(res, 405, { ok: false, error: "method_not_allowed" });
      return await handleDemo(req, res);
    }

    // Root -> landing
    if (pathname === "/" || pathname === "") {
      return await send(res, join(DIST, "landing.html"));
    }

    // Path-traversal himoyasi: leading `..`/slash'larni tozalab, DIST ichida qolamiz
    const safe = normalize(pathname).replace(/^([/\\]|\.\.([/\\]|$))+/, "");
    const candidate = join(DIST, safe);
    if (candidate.startsWith(DIST) && (await fileExists(candidate))) {
      return await send(res, candidate);
    }

    // Aks holda SPA fallback (React client-router /login, /dashboard, ...)
    return await send(res, join(DIST, "index.html"));
  } catch {
    res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Server error");
  }
});

server.listen(PORT, () => {
  console.log(`[web] RetailFlowAI static server on :${PORT} (dist=${DIST})`);
});
