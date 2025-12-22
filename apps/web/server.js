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
    <li><code>/shop/</code> — web</li>
    <li><code>/api/health</code> — api</li>
    <li><code>/ai/health</code> — ai</li>
    <li><code>/media/&lt;bucket&gt;/&lt;object&gt;</code> — файлы</li>
  </ul>
</body>
</html>`;

function proxy(req, res, targetHost, targetPort, stripPrefix) {
  const origUrl = req.url || "/";
  const path = origUrl.startsWith(stripPrefix)
    ? origUrl.slice(stripPrefix.length) || "/"
    : origUrl;

  const options = {
    hostname: targetHost,
    port: targetPort,
    path,
    method: req.method,
    headers: {
      ...req.headers,
      host: `${targetHost}:${targetPort}`,
    },
  };

  const pReq = http.request(options, (pRes) => {
    res.writeHead(pRes.statusCode || 502, pRes.headers);
    pRes.pipe(res, { end: true });
  });

  pReq.on("error", (err) => {
    res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    res.end(`Bad gateway: ${err.message}`);
  });

  req.pipe(pReq, { end: true });
}

const server = http.createServer((req, res) => {
  const url = req.url || "/";

  // API proxy: /api/* -> http://api:8001/*
  if (url.startsWith("/api/")) return proxy(req, res, "api", 8001, "/api");

  // AI proxy: /ai/* -> http://ai:8002/*
  if (url.startsWith("/ai/")) return proxy(req, res, "ai", 8002, "/ai");

  // Media proxy (MinIO S3): /media/bucket/object -> http://minio:9000/bucket/object
  if (url.startsWith("/media/")) return proxy(req, res, "minio", 9000, "/media");

  // Make root prettier
  if (url === "/") {
    res.writeHead(302, { Location: "/shop/" });
    return res.end();
  }

  // For now shop shows skeleton (пока UI не реализован)
  if (url.startsWith("/shop/")) {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    return res.end(INDEX_HTML);
  }

  res.writeHead(404, { "content-type": "application/json; charset=utf-8" });
  res.end(JSON.stringify({ detail: "Not Found" }));
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`web on ${PORT}`);
});