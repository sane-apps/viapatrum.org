import { defineConfig } from 'vite';
import { readFileSync } from 'node:fs';
// Development-only viewport harness; never emitted into the static production build.
export default defineConfig({
  root: 'dist',
  server: { host: '0.0.0.0', allowedHosts: ['terminal.local'] },
  plugins: [{ name: 'viewport-review', configureServer(server) {
    server.middlewares.use('/__night.js', (_req, res) => { res.setHeader('Content-Type', 'text/javascript'); res.end(readFileSync(new URL('./node_modules/darkreader/darkreader.js', import.meta.url))); });
    server.middlewares.use('/__qa__', (_req, res) => {
      res.setHeader('Content-Type', 'text/html');
      res.end(`<!doctype html><html lang="en"><meta charset="utf-8"><title>Fathers viewport review</title>
      <style>body{margin:0;background:#ddd;font:16px system-ui}nav{padding:10px}button,select{font:inherit;padding:8px}iframe{display:block;border:0;margin:0 auto;background:white;width:390px;height:844px}</style>
      <nav><label>Page <select id="page"><option value="/works/origen-numbers-homily-21/">Reader</option><option value="/">Home</option><option value="/works/">Works</option><option value="/topics/">Topics</option><option value="/authors/">Authors</option><option value="/explore/">Explore</option><option value="/contribute/">Help</option><option value="/about/">About</option><option value="/methodology/">Methodology</option></select></label>
      <button data-width="320">320</button><button data-width="390">390</button><button data-width="768">768</button><button data-width="1280">1280</button><label><input type="checkbox" id="night"> Simulated night mode</label></nav>
      <iframe title="Website preview" src="/works/origen-numbers-homily-21/"></iframe>
      <script>const frame=document.querySelector('iframe'); const night=document.querySelector('#night'); function theme(){ const w=frame.contentWindow; if(w.DarkReader){night.checked?w.DarkReader.enable({brightness:100,contrast:100}):w.DarkReader.disable();} } frame.onload=()=>{const s=frame.contentDocument.createElement('script');s.src='/__night.js';s.onload=theme;frame.contentDocument.head.appendChild(s);}; night.onchange=theme; document.querySelector('#page').onchange=e=>frame.src=e.target.value; document.querySelectorAll('button').forEach(b=>b.onclick=()=>frame.style.width=b.dataset.width+'px');</script></html>`);
    });
  }}],
});
