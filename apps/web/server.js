const http = require("http");
const port = process.env.PORT || 3000;

const html = `<!doctype html><html lang="ru"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Clothing Site</title>
<style>body{font-family:system-ui;padding:40px}code{background:#f3f3f3;padding:2px 6px;border-radius:6px}</style>
</head><body>
<h1>Магазин одежды — skeleton</h1>
<p>Маршруты:</p>
<ul>
<li><code>/shop/</code> — web</li>
<li><code>/api/health</code> — api</li>
<li><code>/ai/health</code> — ai</li>
<li><code>/media/&lt;bucket&gt;/&lt;object&gt;</code> — файлы</li>
</ul>
</body></html>`;

http.createServer((req, res) => {
  if (req.url === "/health") { res.writeHead(200); return res.end("ok"); }
  res.writeHead(200, {"Content-Type":"text/html; charset=utf-8"});
  res.end(html);
}).listen(port, "0.0.0.0", () => console.log("web on", port));
