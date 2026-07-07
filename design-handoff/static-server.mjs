import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = '/Users/shafin/Documents/ServerMind/design-handoff/design_handoff_serverally_site';
const PORT = 8931;

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

http.createServer((req, res) => {
  const decoded = decodeURIComponent(req.url.split('?')[0]);
  let rel = decoded === '/' ? '/Home.dc.html' : decoded;
  const abs = path.join(ROOT, rel);
  if (!abs.startsWith(ROOT)) { res.writeHead(403); res.end('forbidden'); return; }
  fs.readFile(abs, (err, data) => {
    if (err) { res.writeHead(404); res.end('not found: ' + rel); return; }
    const ext = path.extname(abs).toLowerCase();
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    res.end(data);
  });
}).listen(PORT, () => console.log(`serving ${ROOT} on :${PORT}`));
