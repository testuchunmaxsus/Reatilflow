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
  });
  res.end(buf);
}

const server = createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent((req.url || "/").split("?")[0]);

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
