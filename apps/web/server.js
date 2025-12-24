// apps/web/server.js
const http = require("http");

const PORT = process.env.PORT || 3000;

const INDEX_HTML = `<!doctype html>
<html lang="ru">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Clothing — skeleton</title>
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:48px}
  h1{font-size:56px;margin:0 0 24px}
  code{background:#f2f2f2;padding:2px 6px;border-radius:6px}
</style>
</head>
<body>
  <h1>Магазин одежды — skeleton</h1>
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

function proxy(req, res, targetHost, targetPort, stripPrefix) {
  const origUrl = req.url || "/";
  const path = origUrl.startsWith(stripPrefix)
    ? origUrl.slice(stripPrefix.length) || "/"
    : origUrl;

  const headers = { ...req.headers };
  // Не подменяем Host на внутренние имена/порты — это ломает домен/ссылки/CORS.
  // Оставляем исходный Host, а для диагностики добавим forwarded заголовки.
  headers["x-forwarded-host"] = headers["host"] || "";
  headers["x-forwarded-proto"] = headers["x-forwarded-proto"] || "http";

  const options = {
    hostname: targetHost,
    port: targetPort,
    path,
    method: req.method,
    headers,
  };

  const pReq = http.request(options, (pRes) => {
    res.writeHead(pRes.statusCode || 502, pRes.headers);
    pRes.pipe(res, { end: true });
  });

  // Таймаут на апстрим, чтобы не висеть бесконечно
  pReq.setTimeout(30000, () => {
    pReq.destroy(new Error("Upstream timeout"));
  });

  pReq.on("error", (err) => {
    const msg = err && err.message ? err.message : "proxy error";
    const isTimeout = String(msg).toLowerCase().includes("timeout");
    res.writeHead(isTimeout ? 504 : 502, {
      "content-type": "text/plain; charset=utf-8",
    });
    res.end(`${isTimeout ? "Gateway timeout" : "Bad gateway"}: ${msg}`);
  });

  req.pipe(pReq, { end: true });
}

const server = http.createServer((req, res) => {
  const url = req.url || "/";

  // web health
  if (url === "/health") {
    res.writeHead(200, { "content-type": "application/json; charset=utf-8" });
    return res.end(JSON.stringify({ status: "ok" }));
  }

  // API proxy: /api/* -> http://api:8001/*
  if (url.startsWith("/api/")) return proxy(req, res, "api", 8001, "/api");

  // AI proxy: /ai/* -> http://ai:8002/*
  if (url.startsWith("/ai/")) return proxy(req, res, "ai", 8002, "/ai");

  // Media proxy (MinIO S3): /media/bucket/object -> http://minio:9000/bucket/object
  if (url.startsWith("/media/")) return proxy(req, res, "minio", 9000, "/media");

  // /shop (без слеша) -> /shop/
  if (url === "/shop") {
    res.writeHead(301, { Location: "/shop/" });
    return res.end();
  }

  // Root = shop (без редиректа)
  if (url === "/" || url.startsWith("/shop/")) {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    return res.end(INDEX_HTML);
  }

  res.writeHead(404, { "content-type": "application/json; charset=utf-8" });
  res.end(JSON.stringify({ detail: "Not Found" }));
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`web on ${PORT}`);
});
