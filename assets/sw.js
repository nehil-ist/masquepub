// Masque service worker: keeps the app shell available offline. Never caches API calls or photos.
const V = "mq-shell-96bcdefgh";
// the wordmark font is kept with the shell so the offline page below looks right even with no connection
const FONT = () => new URL("assets/fonts/PirataOne-Regular.ttf", self.registration.scope).href;
self.addEventListener("install", e => {
  self.skipWaiting();
  e.waitUntil(caches.open(V).then(c => c.add(FONT())).catch(() => {}));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET" || u.origin !== location.origin) return;
  if (u.searchParams.has("a") || u.searchParams.has("img") || u.searchParams.has("stk") || u.searchParams.has("sw") || u.searchParams.has("manifest") || u.searchParams.has("mr") || u.searchParams.has("mv")) return; // mr/mv = one-time email links, never cache them
  const nav = r.mode === "navigate", shell = nav || u.pathname.includes("/assets/");
  if (!shell) return;
  // nothing in the cache and no connection (or the server is restarting): a Masque-looking page instead of the browser's error screen
  const back = () => caches.match(r).then(m => m || (nav ? caches.match(location.origin + u.pathname).then(n => n || caches.match(self.registration.scope)).then(n => n || offline()) : null));
  e.respondWith(fetch(r).then(res => {
    if (res.ok) { const c = res.clone(); caches.open(V).then(x => x.put(r, c)); }
    else if (nav && (res.status === 502 || res.status === 503 || res.status === 504)) return back();
    return res;
  }).catch(back));
});

function offline() {
  const html = OFFLINE.replace("__FONT__", FONT()).replace("__SCOPE__", self.registration.scope);
  return new Response(html, { status: 503, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
}
const OFFLINE = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><title>Masque</title>
<style>
@font-face{font-family:"Pirata One";src:local("Pirata One"),url(__FONT__) format("truetype");font-display:swap}
:root{--bg:#e8ede4;--card:#fff;--ink:#16352a;--mute:#586c5f;--ol:#1b2420;--sigil:#3d4447;--dot:rgba(22,53,42,.09)}
@media(prefers-color-scheme:dark){:root{--bg:#0c0f0e;--card:#171c1a;--ink:#edf2ee;--mute:#9db0a5;--ol:#7d9086;--sigil:#c9cfd2;--dot:rgba(255,255,255,.045)}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;min-height:100dvh;display:grid;place-items:center;padding:24px;background:radial-gradient(var(--dot) 1.1px,transparent 1.5px) 0 0/7px 7px,var(--bg);color:var(--ink);font:1rem/1.45 system-ui,sans-serif}
main{width:100%;max-width:380px}
.logo{margin:0 0 20px;text-align:center;font:3.4rem/1 "Pirata One",Georgia,serif}.logo i{font-style:normal;color:var(--sigil)}
.card{background:var(--card);border:2.5px solid var(--ol);border-radius:6px;box-shadow:5px 5px 0 var(--ol);padding:24px 22px}
h1{margin:0 0 8px;font:1.7rem/1.1 "Pirata One",Georgia,serif;font-weight:400}
p{margin:0 0 18px;color:var(--mute)}
button{width:100%;min-height:46px;border:2.5px solid var(--ol);border-radius:6px;background:var(--ink);color:var(--bg);font:700 .85rem ui-monospace,Menlo,monospace;letter-spacing:.07em;text-transform:uppercase;box-shadow:3px 3px 0 var(--ol);cursor:pointer}
button:active{transform:translate(3px,3px);box-shadow:none}
.st{margin:16px 0 0;text-align:center;font:.72rem ui-monospace,Menlo,monospace;letter-spacing:.07em;text-transform:uppercase;color:var(--mute)}
.st:before{content:"";display:inline-block;width:8px;height:8px;margin-right:8px;border-radius:50%;background:var(--mute);animation:b 1.2s ease-in-out infinite}
@keyframes b{50%{opacity:.25}}
@media(prefers-reduced-motion:reduce){.st:before{animation:none}}
</style></head><body><main><div class="logo">Mas<i>que</i></div>
<div class="card"><h1>Can't reach Masque</h1><p>Your connection dropped, or Masque is restarting. This page tries again by itself.</p><button id="b" type="button">Try again</button></div>
<p class="st" id="s" role="status">Waiting for a connection</p></main>
<script>
var go=function(){document.getElementById("s").textContent="Reconnecting";location.reload()};
document.getElementById("b").onclick=go;
addEventListener("online",go);
setInterval(function(){fetch("__SCOPE__",{method:"HEAD",cache:"no-store"}).then(function(r){if(r.ok)go()}).catch(function(){})},5000);
</script></body></html>`;

// Push: the server sends a small encrypted JSON {t: title, b: body, u: where to open, g: tag}. Never shows names.
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) {}
  e.waitUntil((async () => {
    const cs = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    if (cs.some(c => c.visibilityState === "visible") && d.g !== "test") return; // you're looking at Masque right now: the app already shows it
    await self.registration.showNotification(d.t || "Masque", {
      body: d.b || "",
      icon: new URL("assets/icon-192.png", self.registration.scope).href,
      badge: new URL("assets/icon-192.png", self.registration.scope).href,
      tag: d.g || undefined,
      data: { u: d.u || "./" }
    });
  })());
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const to = new URL((e.notification.data && e.notification.data.u) || "./", self.registration.scope).href;
  e.waitUntil((async () => {
    const cs = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of cs) {
      if (c.url.startsWith(self.registration.scope)) {
        try { await c.focus(); await c.navigate(to); return; } catch (_) {}
      }
    }
    await self.clients.openWindow(to);
  })());
});
