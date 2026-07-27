import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = '/Users/shafin/Documents/ServerMind/marketing-site';
const PORT = 8932;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.json': 'application/json',
};

// Resolve a URL the same way Caddy does in production (`try_files {path} {path}.html`),
// so what we see locally is what visitors get. Without the .html fallback a link to
// /pricing 404s here but works live — a preview that lies is worse than no preview.
function resolve(rel) {
  const candidates = rel === '/' ? ['/index.html'] : [rel, `${rel}.html`, `${rel}/index.html`];
  for (const c of candidates) {
    const abs = path.join(ROOT, c);
    if (abs.startsWith(ROOT) && fs.existsSync(abs) && fs.statSync(abs).isFile()) return abs;
  }
  return null;
}

http.createServer((req, res) => {
  const rel = decodeURIComponent(req.url.split('?')[0]);
  const abs = resolve(rel);
  if (!abs) { res.writeHead(404); res.end('not found: ' + rel); return; }
  fs.readFile(abs, (err, data) => {
    if (err) { res.writeHead(404); res.end('not found: ' + rel); return; }
    const ext = path.extname(abs).toLowerCase();
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    res.end(data);
  });
}).listen(PORT, () => console.log(`serving ${ROOT} on :${PORT}`));
