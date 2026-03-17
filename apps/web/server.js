// apps/web/server.js
// Edge Web Proxy v2
// Responsibilities:
// - Serve web routes
// - Proxy API / AI / Media requests
// - Reliably forward request bodies (JSON, form, etc.)
// - Provide basic observability (logs)
// - Protect from oversized requests (DoS guard)

const http = require("http");

// --------------------
// Configuration (ENV)
// --------------------
const PORT = Number(process.env.PORT) || 3000;

const API_HOST = process.env.API_HOST || "api";
const API_PORT = Number(process.env.API_PORT) || 8001;

const AI_HOST = process.env.AI_HOST || "ai";
const AI_PORT = Number(process.env.AI_PORT) || 8002;

const MINIO_HOST = process.env.MINIO_HOST || "minio";
const MINIO_PORT = Number(process.env.MINIO_PORT) || 9000;

// Max request body size (bytes)
// Applies to POST/PUT/PATCH proxied requests
const MAX_BODY_SIZE = 10 * 1024 * 1024; // 10 MB

// --------------------
// Simple web index (fallback)
// --------------------
const INDEX_HTML = `<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Clothing — skeleton</title>
  <style>
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:48px}
    h1{font-size:56px;margin:0 0 24px}
    code{background:#f2f2f2;padding:2px 6px;border-radius:6px}
  </style>
</head>
<body>
  <h1>личный гардероб — skeleton</h1>
  <h2>Маршруты:</h2>
  <ul>
    <li><code>/</code> — магазин (web)</li>
    <li><code>/shop/</code> — магазин (alias)</li>
    <li><code>/api/health</code> — api</li>
    <li><code>/ai/health</code> — ai</li>
    <li><code>/media/&lt;bucket&gt;/&lt;object&gt;</code> — файлы</li>
    <li><code>/health</code> — health web</li>
  </ul>
</body>
</html>`;

// --------------------
// Proxy implementation
// --------------------
function proxy(req, res, targetHost, targetPort, stripPrefix) {
  const startTs = Date.now();
  const origUrl = req.url || "/";
  const path = origUrl.startsWith(stripPrefix)
    ? origUrl.slice(stripPrefix.length) || "/"
    : origUrl;

  // Basic request log (edge-level)
  console.log(
    `[${new Date().toISOString()}] → ${req.method} ${origUrl} -> ${targetHost}:${targetPort}${path}`
  );

  // Buffer request body (reliable for JSON/form)
  const bodyChunks = [];
  let bodyLength = 0;
  let aborted = false;

  req.on("data", (chunk) => {
    bodyLength += chunk.length;

    // Body size guard
    if (bodyLength > MAX_BODY_SIZE) {
      aborted = true;
      console.warn(
        `[${new Date().toISOString()}] ! Request body too large (${bodyLength} bytes) ${req.method} ${origUrl}`
      );
      res.writeHead(413, { "content-type": "text/plain; charset=utf-8" });
      res.end("Request Entity Too Large");
      req.destroy();
      return;
    }

    bodyChunks.push(chunk);
  });

  req.on("end", () => {
    if (aborted) return;

    const bodyBuffer = Buffer.concat(bodyChunks);

    // Clone and sanitize headers
    const headers = { ...req.headers };

    // Do NOT forward original content-length blindly
    delete headers["content-length"];

    if (bodyBuffer.length > 0) {
      headers["content-length"] = Buffer.byteLength(bodyBuffer);
    }

    // Forwarding headers (for diagnostics / tracing)
    headers["x-forwarded-host"] = headers["host"] || "";
    headers["x-forwarded-proto"] = headers["x-forwarded-proto"] || "http";

    // Optional diagnostic: chunked requests
    if (headers["transfer-encoding"] === "chunked") {
      console.warn(
        `[${new Date().toISOString()}] ~ Chunked request ${req.method} ${origUrl}`
      );
    }

    const options = {
      hostname: targetHost,
      port: targetPort,
      path,
      method: req.method,
      headers,
    };

    const upstreamReq = http.request(options, (upstreamRes) => {
      res.writeHead(upstreamRes.statusCode || 502, upstreamRes.headers);
      upstreamRes.pipe(res, { end: true });

      upstreamRes.on("end", () => {
        const ms = Date.now() - startTs;
        console.log(
          `[${new Date().toISOString()}] ← ${upstreamRes.statusCode} ${req.method} ${origUrl} (${ms}ms)`
        );
      });
    });

    // Upstream timeout protection
    upstreamReq.setTimeout(30000, () => {
      upstreamReq.destroy(new Error("Upstream timeout"));
    });

    upstreamReq.on("error", (err) => {
      const msg = err && err.message ? err.message : "proxy error";
      const isTimeout = String(msg).toLowerCase().includes("timeout");

      console.error(
        `[${new Date().toISOString()}] ! Proxy error ${req.method} ${origUrl}: ${msg}`
      );

      res.writeHead(isTimeout ? 504 : 502, {
        "content-type": "text/plain; charset=utf-8",
      });
      res.end(
        `${isTimeout ? "Gateway timeout" : "Bad gateway"}: ${msg}`
      );
    });

    // Write buffered body if present
    if (bodyBuffer.length > 0) {
      upstreamReq.write(bodyBuffer);
    }

    upstreamReq.end();
  });

  req.on("error", (err) => {
    console.error(
      `[${new Date().toISOString()}] ! Request error ${req.method} ${origUrl}: ${err.message}`
    );
    res.writeHead(400, { "content-type": "text/plain; charset=utf-8" });
    res.end("Bad request");
  });
}

// --------------------
// HTTP server
// --------------------
const server = http.createServer((req, res) => {
  const url = req.url || "/";

  // Web health
  if (url === "/health") {
    res.writeHead(200, { "content-type": "application/json; charset=utf-8" });
    return res.end(JSON.stringify({ status: "ok" }));
  }

  // API proxy
  if (url.startsWith("/api/")) {
    return proxy(req, res, API_HOST, API_PORT, "/api");
  }

  // AI proxy
  if (url.startsWith("/ai/")) {
    return proxy(req, res, AI_HOST, AI_PORT, "/ai");
  }

  // Media proxy
  if (url.startsWith("/media/")) {
    return proxy(req, res, MINIO_HOST, MINIO_PORT, "/media");
  }

  // /shop (no slash) -> /shop/
  if (url === "/shop") {
    res.writeHead(301, { Location: "/shop/" });
    return res.end();
  }

  // Root = shop
  if (url === "/" || url.startsWith("/shop/")) {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    return res.end(INDEX_HTML);
  }

  // Fallback
  res.writeHead(404, { "content-type": "application/json; charset=utf-8" });
  res.end(JSON.stringify({ detail: "Not Found" }));
});

// --------------------
// Start server
// --------------------
server.listen(PORT, "0.0.0.0", () => {
  console.log(`web on ${PORT}`);
});
