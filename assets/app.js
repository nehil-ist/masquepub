/* masque build 2026-10-13 live-view-theme */
/* profile layout (Settings > Profile layout): saved on this device; no value means the new compact look */
/* Experimental (Settings > Appearance > Experimental, saved on this device): game invites and the profile designs (themes, frames, layouts, marketplace) only show when it is on. Off = the classic look. */
let XPV = false;
try {
  XPV = localStorage.getItem("mq-xp") === "1";
} catch (e) {}
const XP = () => XPV;
/* the real setting lives on the account (and an admin switch turns it on for everyone); every server reply that carries "me" refreshes the device copy, and the page reloads once if it changed */
function xpSync(me) {
  if (!me || typeof me.xp === "undefined") return;
  const on = !!(+me.xp || +me.xpall);
  if (on === XPV) return;
  try {
    on ? localStorage.setItem("mq-xp", "1") : localStorage.removeItem("mq-xp");
    if ((localStorage.getItem("mq-xp") === "1") !== on) return;
    XPV = on;
    location.reload();
  } catch (e) {}
}
try {
  const pl0 = XP() ? localStorage.getItem("mq-pl") : "classic";
  if (pl0 === "classic" || pl0 === "card") document.documentElement.dataset.pl = pl0;
} catch (e) {}
/* Accessibility: a "Reduce motion" switch in Settings (saved on this device, on top of the device's own setting). Every place that asks matchMedia("(prefers-reduced-motion...)") goes through this wrapper, so one switch covers all of them live; the CSS side is html[data-motion=reduce]. */
(() => {
  const mm = window.matchMedia.bind(window),
    on = () => document.documentElement.dataset.motion === "reduce";
  window.matchMedia = (q) => {
    const m = mm(q);
    if (!/prefers-reduced-motion\s*:\s*reduce/.test(String(q))) return m;
    return {
      get matches() {
        return on() || m.matches;
      },
      media: m.media,
      onchange: null,
      addEventListener: (...a) => m.addEventListener(...a),
      removeEventListener: (...a) => m.removeEventListener(...a),
      addListener: (...a) => m.addListener && m.addListener(...a),
      removeListener: (...a) => m.removeListener && m.removeListener(...a),
      dispatchEvent: (e) => m.dispatchEvent(e),
    };
  };
})();
// App root folder ("/" normally). Pretty links like /u/name load the page from a deeper path, so the root comes from <base>, not location.pathname.
const BASE = new URL(".", document.baseURI).pathname;
if (!document.querySelector("base")) {
  const b = document.createElement("base");
  b.href = location.origin + BASE;
  document.head.prepend(b);
}
/* Sounds: tiny synthesized cues (no audio files). Off switch + volume in Settings > Accessibility, saved on this device. The audio context can only start after the first tap or key press, so it is created then. */
const SFX = (() => {
  let ctx = null,
    master = null;
  const last = {},
    on = () => {
      try {
        return localStorage.getItem("mq-snd") !== "0";
      } catch (e) {
        return true;
      }
    },
    vol = () => {
      try {
        const v = parseFloat(localStorage.getItem("mq-sndv"));
        return v >= 0 && v <= 1 ? v : 0.6;
      } catch (e) {
        return 0.6;
      }
    },
    boot = () => {
      if (ctx) return ctx;
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      try {
        ctx = new AC();
        master = ctx.createGain();
        master.connect(ctx.destination);
      } catch (e) {
        ctx = null;
      }
      return ctx;
    },
    wake = () => {
      boot();
      if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
    },
    /* one soft bell note: a sine plus a quiet inharmonic partial for a glassy edge, quick attack, gentle decay */
    bell = (t, f, peak, dec) => {
      const o = ctx.createOscillator(),
        o2 = ctx.createOscillator(),
        g = ctx.createGain(),
        g2 = ctx.createGain(),
        lp = ctx.createBiquadFilter();
      o.type = "sine";
      o.frequency.value = f;
      o2.type = "sine";
      o2.frequency.value = f * 2.76;
      lp.type = "lowpass";
      lp.frequency.value = 5200;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(peak, t + 0.006);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dec);
      g2.gain.setValueAtTime(0.0001, t);
      g2.gain.exponentialRampToValueAtTime(peak * 0.22, t + 0.004);
      g2.gain.exponentialRampToValueAtTime(0.0001, t + dec * 0.35);
      o.connect(g).connect(lp);
      o2.connect(g2).connect(lp);
      lp.connect(master);
      o.start(t);
      o2.start(t);
      o.stop(t + dec + 0.05);
      o2.stop(t + dec + 0.05);
    },
    /* a breath of filtered noise, like a whisper behind a mask */
    breath = (t, peak, len) => {
      const n = Math.floor(ctx.sampleRate * len),
        b = ctx.createBuffer(1, n, ctx.sampleRate),
        d = b.getChannelData(0);
      for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
      const s = ctx.createBufferSource(),
        bp = ctx.createBiquadFilter(),
        g = ctx.createGain();
      s.buffer = b;
      bp.type = "bandpass";
      bp.frequency.value = 2600;
      bp.Q.value = 0.9;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(peak, t + len * 0.35);
      g.gain.exponentialRampToValueAtTime(0.0001, t + len);
      s.connect(bp).connect(g).connect(master);
      s.start(t);
    },
    /* a sine that glides from f0 to f1 */
    tone = (t, f0, f1, dur, peak) => {
      const o = ctx.createOscillator(),
        g = ctx.createGain();
      o.type = "sine";
      o.frequency.setValueAtTime(f0, t);
      o.frequency.exponentialRampToValueAtTime(f1, t + dur);
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(peak, t + Math.min(0.02, dur / 3));
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g).connect(master);
      o.start(t);
      o.stop(t + dur + 0.03);
    },
    /* filtered noise whose centre pitch glides from f0 to f1: a soft whoosh */
    sweep = (t, f0, f1, dur, peak) => {
      const n = Math.floor(ctx.sampleRate * dur),
        b = ctx.createBuffer(1, n, ctx.sampleRate),
        d = b.getChannelData(0);
      for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
      const s = ctx.createBufferSource(),
        bp = ctx.createBiquadFilter(),
        g = ctx.createGain();
      s.buffer = b;
      bp.type = "bandpass";
      bp.Q.value = 1.4;
      bp.frequency.setValueAtTime(f0, t);
      bp.frequency.exponentialRampToValueAtTime(f1, t + dur);
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(peak, t + dur * 0.4);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      s.connect(bp).connect(g).connect(master);
      s.start(t);
    },
    voices = {
      /* the Masque notification: a whisper, then two bell notes that rise (A5 then E6) */
      notif: (t) => {
        breath(t, 0.035, 0.14);
        bell(t + 0.02, 880, 0.085, 0.75);
        bell(t + 0.15, 1318.5, 0.07, 0.95);
      },
      /* a message arrives: a soft bubble that rises, with a tiny high bell on top. Shorter and lighter than the notification */
      msg: (t) => {
        const o = ctx.createOscillator(),
          g = ctx.createGain();
        o.type = "sine";
        o.frequency.setValueAtTime(430, t);
        o.frequency.exponentialRampToValueAtTime(780, t + 0.07);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.1, t + 0.012);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
        o.connect(g).connect(master);
        o.start(t);
        o.stop(t + 0.2);
        bell(t + 0.05, 1568, 0.04, 0.35);
      },
      /* sending a message or comment: a tiny upward swish */
      send: (t) => {
        sweep(t, 900, 2600, 0.12, 0.035);
        tone(t, 700, 1000, 0.09, 0.03);
      },
      /* a gift is waiting: the same two notes plus a third, higher one */
      gift: (t) => {
        breath(t, 0.035, 0.14);
        bell(t + 0.02, 880, 0.085, 0.75);
        bell(t + 0.15, 1318.5, 0.07, 0.95);
        bell(t + 0.29, 1760, 0.055, 1.1);
      },
    },
    gap = { notif: 1500, gift: 1500, msg: 350, send: 150 };
  ["pointerdown", "keydown", "touchend"].forEach((e) => addEventListener(e, wake, { passive: true, capture: true }));
  return {
    on,
    vol,
    wake,
    play(name, force) {
      try {
        if (!on() || !voices[name] || document.hidden) return;
        const now = Date.now();
        if (!force && now - (last[name] || 0) < (gap[name] || 80)) return;
        if (!ctx || ctx.state !== "running") return; /* never played before the person has tapped the page once */
        last[name] = now;
        master.gain.value = vol();
        voices[name](ctx.currentTime + 0.01);
      } catch (e) {}
    },
    set(v) {
      try {
        v ? localStorage.removeItem("mq-snd") : localStorage.setItem("mq-snd", "0");
      } catch (e) {}
    },
    setVol(v) {
      try {
        localStorage.setItem("mq-sndv", String(v));
      } catch (e) {}
      if (master) master.gain.value = v;
    },
  };
})();
let REF = "",
  CURH = "",
  FSCR = 0,
  FREST = 0,
  M = null,
  T = "",
  POLL = null,
  FEED = "foryou",
  SHOWN = "",
  CUR = null,
  ITAB = "",
  INSET = null,
  LV = { t: 0, busy: 0, fail: 0, mv: null, nv: null, af: 0, gaf: 0, act: Date.now() },
  SEENT = new Set(),
  MAILOK = 0;
function h(t, a, ...k) {
  const e = document.createElement(t);
  for (const x in a || {}) {
    const v = a[x];
    if (typeof v === "function") e[x] = v;
    else if (typeof v === "boolean" && /^(disabled|hidden|checked|readonly|required|selected|multiple|autofocus)$/.test(x)) {
      /* true/false means on/off. A plain setAttribute(x, false) would write disabled="false", which still disables the element. */
      if (v) e.setAttribute(x, "");
    } else e.setAttribute(x, v);
  }
  /* text boxes (comments, chat, bios, captions...) opt out of browser autofill, so the keyboard stops offering saved passwords, cards and addresses. Sign-in and sign-up fields keep working because they name their own autocomplete value. */
  if ((t === "input" || t === "textarea") && !e.hasAttribute("autocomplete") && !/^(password|file|checkbox|radio|range|color|hidden|submit|button|image|reset)$/i.test(e.getAttribute("type") || "")) {
    e.setAttribute("autocomplete", "off");
    e.setAttribute("data-lpignore", "true");
    e.setAttribute("data-1p-ignore", "");
    e.setAttribute("data-bwignore", "true");
    e.setAttribute("data-form-type", "other");
    if (!e.hasAttribute("name")) e.setAttribute("name", "mq" + Math.random().toString(36).slice(2, 8)); /* a neutral name, so heuristics cannot read it as an address or card field */
  }
  k.flat(Infinity).forEach((c) => c != null && e.append(c));
  return e;
}
async function api(a, d, q = "") {
  const o = {};
  if (d) {
    o.method = "POST";
    o.headers = { "X-CSRF": T };
    o.body = d;
  }
  let r;
  try {
    r = await fetch("?a=" + a + q, o);
  } catch (e) {
    throw {
      e:
        !d || navigator.onLine === false
          ? "No connection."
          : "The upload did not reach the server (" +
            ((e && e.name) || "network") +
            "). Check your signal and try again.",
    };
  }
  const j = await r.json().catch(() => ({ e: "Server error." }));
  if (!r.ok) {
    if (j && j.mt) maint(j.msg);
    if (j && typeof j === "object") j.s = r.status;
    throw j;
  }
  if (j && j.me) xpSync(j.me);
  return j;
}
const fd = (o) => {
  const f = new FormData();
  for (const k in o) if (o[k] != null) f.append(k, o[k]);
  return f;
};
/* photos: redraw through a canvas so they are smaller (faster on mobile) and carry no EXIF/GPS data; throws {e} if still over 4 MB */
/* chat drafts: unsent text is kept on this device per chat, comes back when you reopen it, and shows as "Draft:" in the chat list */
const dkD = (n, a) => "mq-md-" + M.name + "-" + n + (a ? "-m" : ""),
  dkG = (id) => "mq-gd-" + M.name + "-" + id,
  dget = (k) => {
    try {
      return localStorage.getItem(k) || "";
    } catch (e) {
      return "";
    }
  },
  dprev = (c) => {
    const t = dget(c.k === "g" ? dkG(c.id) : dkD(c.name, +c.ms)).trim();
    return t.length > 60 ? t.slice(0, 60) + "\u2026" : t;
  },
  dbind = (inp, k) => {
    const t = dget(k);
    if (t && !inp.value) inp.value = t;
    inp.addEventListener("input", () => {
      try {
        inp.value ? localStorage.setItem(k, inp.value) : localStorage.removeItem(k);
      } catch (e) {}
    });
    return () => {
      try {
        localStorage.removeItem(k);
      } catch (e) {}
    };
  };
const AUDMAX = 25e6,
  AUDMB = 25,
  isAud = (f) => /^audio\//.test(f.type) || /\.(mp3|m4a|aac|ogg|oga|opus|wav|flac)$/i.test(f.name),
  isAudN = (n) => /\.(mp3|m4a|aac|ogg|opus|wav|flac)$/.test(n || "");
const IMGMAX = 50e6,
  IMGMB = 50; /* biggest file we accept before resizing; it is shrunk below 4 MB for the server */
const readable = async (f) => {
  try {
    return new Blob([await f.arrayBuffer()], { type: f.type });
  } catch (e) {
    throw { e: "Could not read that photo from your device. Pick it again, or save it to your phone first." };
  }
};
const decode = async (b) => {
  try {
    return await createImageBitmap(b, { imageOrientation: "from-image" });
  } catch (e) {}
  try {
    return await createImageBitmap(b);
  } catch (e) {}
  return await new Promise((ok, no) => {
    const u = URL.createObjectURL(b),
      i = new Image();
    i.onload = () => {
      URL.revokeObjectURL(u);
      ok(i);
    };
    i.onerror = () => {
      URL.revokeObjectURL(u);
      no();
    };
    i.src = u;
  });
};
const shrink = async (f, max = 1600) => {
  const src = await readable(f);
  let out = src,
    ok = false;
  if (f.type !== "image/gif") {
    try {
      const b = await decode(src),
        w0 = b.naturalWidth || b.width,
        h0 = b.naturalHeight || b.height;
      /* long side to max, but very tall/wide images keep a readable short side; stay under 12 megapixels so phones can draw it */
      let s = Math.max(Math.min(1, max / Math.max(w0, h0)), Math.min(1, (0.55 * max) / Math.min(w0, h0)));
      s = Math.min(s, 1, Math.sqrt(12e6 / (w0 * h0)));
      const c = document.createElement("canvas"),
        x = c.getContext("2d"),
        enc = (t, qq) => new Promise((r) => c.toBlob(r, t, qq));
      /* Photos (posts, chats, answers) are saved as WebP, about 500 KB: roughly a third smaller than the old JPEG for the same look. Avatars and covers (max below 1600) stay JPEG, because link-preview cards and some apps cannot read WebP everywhere. A browser that cannot write WebP (Safari) gets JPEG at about 900 KB. */
      let fmt = max >= 1600 ? "image/webp" : "image/jpeg",
        q = fmt === "image/webp" ? 0.8 : 0.82,
        lim = fmt === "image/webp" ? 5e5 : 9e5,
        bl = null;
      for (let i = 0; i < 8; i++) {
        c.width = Math.max(1, Math.round(w0 * s));
        c.height = Math.max(1, Math.round(h0 * s));
        x.fillStyle = "#fff";
        x.fillRect(0, 0, c.width, c.height);
        x.drawImage(b, 0, 0, c.width, c.height);
        bl = await enc(fmt, q);
        if (bl && fmt === "image/webp" && bl.type !== "image/webp") {
          fmt = "image/jpeg";
          q = 0.82;
          lim = 9e5;
          bl = await enc(fmt, q);
        }
        if (!bl || bl.size <= lim) break;
        if (q > 0.6) q -= 0.1;
        else s *= 0.85;
      }
      if (b.close) b.close();
      if (bl) {
        out = bl;
        ok = true;
      }
    } catch (e) {}
  }
  if (out.size > 4e6)
    throw {
      e:
        f.type === "image/gif"
          ? "That GIF is over 4 MB. Try a smaller GIF or a normal photo."
          : "Could not shrink that image. Try a JPG or PNG.",
    };
  if (!ok && f.type !== "image/gif" && !/^image\/(jpeg|png|webp)$/.test(f.type))
    throw { e: "Your browser could not read that photo format (HEIC?). Pick a JPG or PNG instead." };
  return new File([out], ok ? (out.type === "image/webp" ? "photo.webp" : "photo.jpg") : f.name || "photo", {
    type: ok ? out.type || "image/jpeg" : f.type,
  });
};
const MASK =
  '<svg viewBox="0 0 24 24" width="62%" height="62%" aria-hidden="true"><path d="M3 8c0-1.7 4-3 9-3s9 1.3 9 3v2c0 4-3 8-9 8s-9-4-9-8z" fill="#fff"/><ellipse cx="8.5" cy="10" rx="2.3" ry="1.4" fill="#8b959c"/><ellipse cx="15.5" cy="10" rx="2.3" ry="1.4" fill="#8b959c"/></svg>';
/* a Masque is someone posting anonymously. Its mark is a laughing mask: closed happy eyes (.lme) and an open mouth (.lmm). */
const LAUGH =
  '<svg class="lm" viewBox="0 0 24 24" width="62%" height="62%" aria-hidden="true"><path class="lmf" d="M3 8c0-1.7 4-3 9-3s9 1.3 9 3v2c0 4-3 8-9 8s-9-4-9-8z"/><g class="lme"><path d="M5.6 11.4c.8-2 3.4-2 4.2 0M14.2 11.4c.8-2 3.4-2 4.2 0"/></g><path class="lmm" d="M7.6 13.2c.2 2.6 2.2 3.8 4.4 3.8s4.2-1.2 4.4-3.8z"/></svg>';
const lmIcon = (z) => {
  const e = h("span", { class: "ico lmi" });
  e.innerHTML = LAUGH.replace('width="62%" height="62%"', 'width="' + z + '" height="' + z + '"');
  return e;
};
/* presence dots: green online, amber idle, hollow grey offline. Masque chats show the laughing mask instead and never a status. */
const ST = { on: "Online", idle: "Idle", lurk: "Lurking", off: "Offline" };
/* status bubble: a person's status line ("studying", "on a break") drawn as a small chat bubble.
   "up" floats above an avatar, "in" sits inline next to a name, "ps" is the bigger one on a profile (tap to read all of it). */
function sbub(txt, mode, fn) {
  if (!txt) return null;
  return h(fn ? "button" : "span", { class: "sbub " + (mode || "up"), title: txt, ...(fn ? { type: "button", onclick: fn } : {}) }, h("span", { class: "sbt" }, txt));
}
function avw(el, st, mk, name, sx) {
  const w = h("span", { class: "avw" }, el);
  if (sx && !mk) w.append(sbub(sx, "up"));
  if (mk)
    w.append(
      h("span", { class: "pdot mk", role: "img", "aria-label": "Masque chat", title: "Masque chat" }, lmIcon(12)),
    );
  else if (st) {
    const d = h("span", { class: "pdot s-" + st, role: "img", "aria-label": ST[st], title: ST[st] });
    if (name) d.dataset.u = name;
    w.append(d);
  }
  return w;
}
function setDot(d, st) {
  if (!d || !ST[st]) return;
  d.className = "pdot s-" + st;
  d.setAttribute("aria-label", ST[st]);
  d.title = ST[st];
}
function statusSheet(done) {
  sheet("Your status", (close) => {
    const e = h("p", { class: "err", role: "alert" }),
      opts = [
        ["", "Auto", "auto", "automatic"],
        ["online", "Online", "on", ""],
        ["idle", "Idle", "idle", ""],
        ["lurk", "Lurking", "lurk", "here, quietly"],
        ["off", "Invisible", "off", ""],
      ];
    return h(
      "div",
      { class: "form" },
      ...opts.map(([v, l, k, d]) =>
        h(
          "button",
          {
            type: "button",
            class: "ghost srow",
            "aria-pressed": String((M.pst || "") === v),
            onclick: async () => {
              e.textContent = "";
              try {
                const x = await api("setst", fd({ st: v }));
                M.pst = x.pst;
                close();
                if (done) done();
              } catch (x) {
                e.textContent = x.e || "Could not save.";
              }
            },
          },
          h("i", { class: "pdot s-" + k, "aria-hidden": "true" }),
          h("b", {}, l),
          d ? h("small", { class: "hint" }, d) : null,
        ),
      ),
      e,
      customStatus(close, done),
    );
  });
}
/* custom status inside the "Your status" sheet: a few words shown as a chat bubble on your avatar for 24 hours */
function customStatus(close, done) {
  const inp = h("input", { type: "text", maxlength: STMAX, placeholder: "What are you up to?", "aria-label": "Custom status" }),
    cnt = h("small", { class: "hint stcnt" }),
    msg = h("p", { class: "err", role: "alert" }),
    upd = () => {
      const n = inp.value.length;
      cnt.textContent = n + " / " + STMAX;
      cnt.classList.toggle("near", n >= STMAX * 0.8 && n < STMAX);
      cnt.classList.toggle("full", n >= STMAX);
    },
    save = async (v) => {
      msg.textContent = "";
      try {
        const r = await api("setstatus", fd({ txt: v }));
        M.status = r.status;
        close();
        if (done) done();
        else route();
      } catch (x) {
        msg.textContent = (x && x.e) || "Could not save.";
      }
    };
  /* M does not carry your status from the server (only this sheet and the profile set it), so ask for it: the box then shows what you already set, wherever you set it */
  let touched = false;
  const clr = h("button", { type: "button", class: "ghost stcclr", hidden: !M.status, onclick: () => save("") }, "Clear status");
  inp.value = M.status || "";
  inp.addEventListener("input", () => {
    touched = true;
    upd();
  });
  upd();
  api("user", null, "&u=" + encodeURIComponent(M.name))
    .then((r) => {
      M.status = (r && r.u && r.u.status) || "";
      if (!touched && inp.isConnected) {
        inp.value = M.status;
        upd();
      }
      clr.hidden = !M.status;
    })
    .catch(() => {});
  return h(
    "form",
    { class: "stcus", onsubmit: (ev) => { ev.preventDefault(); save(inp.value.trim()); } },
    h("p", { class: "tlab" }, "Custom status"),
    h("div", { class: "stcrow" }, inp, h("button", { type: "submit", class: "btn" }, "Set")),
    h("div", { class: "stcfoot" }, h("small", { class: "hint" }, "Shows over your avatar for 24 hours."), cnt),
    clr,
    msg,
  );
}
const lmAv = (z) => {
  const d = h("div", { class: "av lmv", "aria-hidden": "true" });
  d.innerHTML = LAUGH;
  d.style.cssText = `width:${z}px;height:${z}px;background:linear-gradient(145deg,#a3acb2,#7d878e)`;
  return d;
};
/* the laughing mask on a Masque post: it laughs (hops, eyes squint, mouth pulses, a little "ha ha" floats off) whenever you interact with that post */
const laugh = (art) => {
  const s = art && art.querySelector(".lmst");
  if (!s || matchMedia("(prefers-reduced-motion:reduce)").matches) return;
  s.classList.remove("ha");
  void s.offsetWidth;
  s.classList.add("ha");
  clearTimeout(s._t);
  s.querySelector(".hahat")?.remove();
  const b = h("span", { class: "hahat", "aria-hidden": "true" }, "ha ha");
  s.append(b);
  s._t = setTimeout(() => {
    s.classList.remove("ha");
    b.remove();
  }, 1000);
};
/* a slight vibration that dies away on its own: the element shakes a little (and phones buzz) */
const buzz = (e) => {
  if (!matchMedia("(prefers-reduced-motion:reduce)").matches) {
    e.classList.remove("vib");
    void e.offsetWidth;
    e.classList.add("vib");
    clearTimeout(e._v);
    e._v = setTimeout(() => e.classList.remove("vib"), 520);
  }
  if (navigator.vibrate)
    try {
      navigator.vibrate(8);
    } catch (_) {}
};
const dn = (u) => u.nick || u.name;
const pdn = (u) => u.pn || dn(u); // the nickname you gave someone privately, else their normal name
function pollEl(p) {
  const q = p.poll;
  if (!q) return null;
  const box = h("div", { class: "poll", role: "group", "aria-label": "Poll" }),
    key = "mq-pv-" + p.id,
    calm = matchMedia("(prefers-reduced-motion: reduce)").matches,
    multi = !!+q.multi,
    suf = multi ? "" : "%";
  /* Your own vote is remembered only in this browser: which option(s), plus a secret token that proves it is yours. The server never learns which option you chose, so it needs the token to move or remove your vote. */
  const mem = () => {
      try {
        const j = JSON.parse(localStorage.getItem(key) || "null");
        const okO = j && (Number.isInteger(j.o) || (Array.isArray(j.o) && j.o.length && j.o.every(Number.isInteger)));
        return okO && /^[a-f0-9]{32}$/.test(j.t) ? j : null;
      } catch (_) {
        return null;
      }
    },
    setMem = (j) => {
      try {
        j ? localStorage.setItem(key, JSON.stringify(j)) : localStorage.removeItem(key);
      } catch (_) {}
    },
    newTok = () => [...crypto.getRandomValues(new Uint8Array(16))].map((x) => x.toString(16).padStart(2, "0")).join(""),
    isMine = (m, i) => !!m && (Array.isArray(m.o) ? m.o.includes(i) : m.o === i);
  let mine = +q.v ? mem() : null,
    busy = false,
    fetched = false;
  const sel = new Set(),
    isEnded = () => !!+q.done || (+q.end > 0 && Date.now() >= +q.end * 1000),
    rows = q.o.map((t) => {
      const bar = h("i", { "aria-hidden": "true" }),
        pc = h("b", {}),
        b = h("button", { type: "button", class: "popt" }, bar, h("span", {}, t), pc);
      return { b, bar, pc, shown: 0 };
    }),
    st = h("small", { class: "pstat" }),
    hint = h("small", { class: "hint" }),
    vb = h("button", { type: "button", class: "btn pvb", hidden: "" }, "Vote"),
    ub = h("button", { type: "button", class: "ghost pvb", hidden: "" }, "Change my vote"),
    fmtLeft = (ms) => {
      const m = Math.max(1, Math.ceil(ms / 60000)),
        hh = Math.ceil(ms / 3600000),
        d = Math.ceil(ms / 86400000);
      return ms >= 172800000 ? d + "d" : ms >= 3600000 ? hh + "h" : m + " min";
    },
    count = (r, to) => {
      /* the number counts up (or down) to its new value */
      const from = r.shown;
      r.shown = to;
      if (calm || from === to) {
        r.pc.textContent = to + suf;
        return;
      }
      const t0 = performance.now();
      const step = (t) => {
        const k = Math.min(1, (t - t0) / 550),
          e = 1 - Math.pow(1 - k, 3);
        r.pc.textContent = Math.round(from + (to - from) * e) + suf;
        if (k < 1 && r.shown === to) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };
  const draw = () => {
    const n = q.n,
      tot = n ? n.reduce((a, b) => a + +b, 0) : 0,
      top = n ? Math.max(0, ...n.map((x) => +x)) : 0,
      voted = !!+q.v,
      ended = isEnded();
    box.classList.toggle("ended", ended);
    rows.forEach((r, i) => {
      const pc = n && tot ? Math.round((100 * +n[i]) / tot) : 0,
        val = multi ? (n ? +n[i] : 0) : pc,
        wid = multi ? (top ? Math.round((100 * +n[i]) / top) : 0) : pc,
        chosen = mine ? isMine(mine, i) : !voted && !ended && sel.has(i);
      r.b.classList.toggle("res", !!n);
      r.b.classList.toggle("mine", chosen);
      r.b.classList.toggle("win", ended && !!n && top > 0 && +n[i] === top);
      r.b.setAttribute("aria-pressed", chosen ? "true" : "false");
      r.b.disabled = busy || ended || (multi ? voted : voted && !mine);
      r.bar.style.width = wid + "%";
      if (n) count(r, val);
      else {
        r.shown = 0;
        r.pc.textContent = "";
      }
    });
    const bits = [];
    if (ended) bits.push("Poll ended");
    else if (+q.end > 0) bits.push("Ends in " + fmtLeft(+q.end * 1000 - Date.now()));
    if (multi && !ended) bits.push("Pick one or more");
    st.textContent = bits.join(" \u00b7 ");
    st.hidden = !bits.length;
    vb.hidden = !(multi && !voted && !ended);
    vb.disabled = busy || !sel.size;
    ub.hidden = !(multi && voted && !ended && !!mine);
    ub.disabled = busy;
    const unit = multi ? (tot === 1 ? " pick" : " picks") : tot === 1 ? " vote" : " votes";
    hint.textContent = n
      ? tot +
        unit +
        " \u00b7 anonymous" +
        (ended ? "" : mine && !multi ? " \u00b7 tap another option to change, or yours again to take it back" : "")
      : multi
        ? "Votes are anonymous. Nobody can see who chose what."
        : "Votes are anonymous. Nobody can see who chose what.";
  };
  const fail = (x) => {
    if (x && x.s === 409) {
      if (/ended|locked/i.test(x.e || "")) q.done = 1;
      else {
        mine = null;
        setMem(null);
      }
    }
    alert((x && x.e) || "Could not vote.");
  };
  rows.forEach((r, i) => {
    r.b.onclick = async () => {
      if (busy || isEnded()) return;
      if (multi) {
        if (+q.v) return;
        sel.has(i) ? sel.delete(i) : sel.add(i);
        if (!calm) r.b.animate([{ transform: "scale(1)" }, { transform: "scale(1.025)" }, { transform: "scale(1)" }], { duration: 200, easing: "ease-out" });
        draw();
        return;
      }
      busy = true;
      draw();
      if (!calm) r.b.animate([{ transform: "scale(1)" }, { transform: "scale(1.025)" }, { transform: "scale(1)" }], { duration: 260, easing: "ease-out" });
      try {
        if (!+q.v) {
          const t = newTok(),
            r2 = await api("pvote", fd({ id: p.id, opt: i, t }));
          q.v = 1;
          q.n = r2.poll.n;
          mine = { o: i, t };
          setMem(mine);
        } else if (mine) {
          const same = mine.o === i,
            t = same ? "" : newTok(),
            r2 = await api("pchange", fd({ id: p.id, from: mine.o, ot: mine.t, opt: same ? -1 : i, t }));
          q.v = r2.poll.v;
          q.n = r2.poll.n;
          mine = same ? null : { o: i, t };
          setMem(mine);
        }
      } catch (x) {
        fail(x);
      }
      busy = false;
      draw();
    };
  });
  /* "pick several": choose any options, then Vote sends them all in one go; Change my vote takes it back (needs this device) and puts your picks back so you can edit them */
  vb.onclick = async () => {
    if (busy || !sel.size || isEnded()) return;
    busy = true;
    draw();
    try {
      const t = newTok(),
        o = [...sel].sort((a, b) => a - b),
        r2 = await api("pvote", fd({ id: p.id, opts: JSON.stringify(o), t }));
      q.v = 1;
      q.n = r2.poll.n;
      mine = { o, t };
      setMem(mine);
    } catch (x) {
      fail(x);
    }
    busy = false;
    draw();
  };
  ub.onclick = async () => {
    if (busy || !mine || isEnded()) return;
    busy = true;
    draw();
    try {
      const r2 = await api("pchange", fd({ id: p.id, from: JSON.stringify(mine.o), ot: mine.t, opt: -1 }));
      sel.clear();
      mine.o.forEach((x) => sel.add(x));
      q.v = 0;
      q.n = r2.poll.n;
      mine = null;
      setMem(null);
    } catch (x) {
      fail(x);
    }
    busy = false;
    draw();
  };
  box.append(st, ...rows.map((r) => r.b), vb, ub, hint);
  draw();
  /* a poll with a closing time ticks the countdown, and when the time runs out the page locks the buttons and asks for the final results */
  if (+q.end > 0 && !isEnded()) {
    const iv = setInterval(async () => {
      if (!box.isConnected) {
        clearInterval(iv);
        return;
      }
      if (isEnded()) {
        clearInterval(iv);
        q.done = 1;
        if (!q.n && !fetched) {
          fetched = true;
          try {
            q.n = (await api("pres", fd({ id: p.id }))).poll.n;
          } catch (_) {}
        }
      }
      draw();
    }, 10000);
  } else if (isEnded() && !q.n) {
    fetched = true;
    api("pres", fd({ id: p.id }))
      .then((r2) => {
        q.n = r2.poll.n;
        draw();
      })
      .catch(() => {});
  }
  return box;
}
const left = (t) => {
  const s = Math.max(60, +t - Math.floor(Date.now() / 1000));
  return s >= 86400
    ? Math.round(s / 86400) + " d"
    : s >= 3600
      ? Math.round(s / 3600) + " h"
      : Math.round(s / 60) + " min";
};
const av = (u, s) => {
  const d = h("div", { class: "av", "aria-hidden": "true" }),
    src = u.src ?? (u.avatar ? "?img=" + u.avatar : "");
  if (src) d.append(h("img", { src, alt: "" }));
  else d.innerHTML = +u.mk ? LAUGH : MASK;
  d.style.cssText = `width:${s}px;height:${s}px;background:linear-gradient(145deg,#a3acb2,#7d878e)`;
  return d;
};
const linkify = (s) =>
  String(s)
    .split(/(#[A-Za-z0-9_]{1,40}|(?<![A-Za-z0-9_])@[A-Za-z0-9_]{3,20})/)
    .map((x, i) =>
      i % 2
        ? (() => {
          const g = x[0] === "#" ? "#/t/" + x.slice(1).toLowerCase() : "#/u/" + x.slice(1);
          return h("a", { href: BASE + g, class: "tag", onclick: (e) => (e.preventDefault(), (location.hash = g)) }, x);
        })()
        : x,
    );
/* chat links: turn http(s):// and www. URLs in a message into tappable links (no #tag/@mention handling here, chats keep those as plain text).
   Trailing punctuation stays outside the link, and only http/https URLs are ever linked. Same-site links open in the app, everything else asks "Leave Masque?" first and opens in a new tab. */
const URLRE = /((?:https?:\/\/|www\.)[^\s<>"']+)/gi;
/* one matched token -> { u: the link text, tail: punctuation after it, url: the parsed URL } or null when it is not a safe web link */
const urlPick = (x) => {
  let u = x,
    tail = "";
  for (;;) {
    const m = u.match(/[.,!?;:'"\]}]$/);
    if (m || (u.endsWith(")") && (u.match(/\(/g) || []).length < (u.match(/\)/g) || []).length)) {
      tail = u.slice(-1) + tail;
      u = u.slice(0, -1);
    } else break;
  }
  let url;
  try {
    url = new URL(/^www\./i.test(u) ? "https://" + u : u);
  } catch (e) {
    return null;
  }
  if (!/^https?:$/.test(url.protocol) || !url.hostname.includes(".")) return null;
  return { u, tail, url };
};
const askLeave = async (url) => {
  if (await cbox("Leave Masque? You're about to open " + url.host + ". Only continue if you trust this link.")) {
    if (!window.open(url.href, "_blank", "noopener,noreferrer")) location.href = url.href;
  }
};
const urlText = (s) =>
  String(s)
    .split(URLRE)
    .map((x, i) => {
      if (!(i % 2)) return x;
      const k = urlPick(x);
      if (!k) return x;
      const { u, tail, url } = k;
      return [
        h(
          "a",
          url.origin === location.origin
            ? { href: url.href, class: "lnk" }
            : {
                href: url.href,
                class: "lnk",
                target: "_blank",
                rel: "noopener noreferrer nofollow",
                onclick: (e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  askLeave(url);
                },
              },
          u,
        ),
        tail,
      ];
    })
    .flat();
/* @mentions in chats: a name that belongs to someone in the chat is highlighted (stronger when it is you); @everyone pings a whole group. rs(name) -> null | { me, all } */
const mentionText = (s, rs) => {
  const parts = urlText(s);
  if (!rs) return parts;
  return parts
    .map((p) =>
      typeof p !== "string"
        ? p
        : p.split(/((?<![A-Za-z0-9_])@[A-Za-z0-9_]{3,20}(?![A-Za-z0-9_]))/).map((x, i) => {
            if (!(i % 2)) return x;
            const r = rs(x.slice(1));
            return r ? h("span", { class: "mnt" + (r.me ? " mnme" : "") + (r.all ? " mnall" : "") }, x) : x;
          }),
    )
    .flat();
};
const isMe = (n) => {
  n = String(n).toLowerCase();
  return n === String(M.name).toLowerCase() || (!!M.mask && n === String(M.mask.name).toLowerCase());
};
/* the @ picker: type @ in a box and a short list of people to pick from appears above (or below) it. cands(query) returns [{ name, nick?, avatar?, mk?, every? }] (or a promise of that). */
function mentionPick(inp, cands, below) {
  const box = h("div", { class: "mpick" + (below ? " dn" : ""), role: "listbox", "aria-label": "Mention someone", hidden: "" });
  let items = [],
    sel = 0,
    tok = null,
    seq = 0;
  const mount = () => {
    const par = inp.parentNode;
    if (!par || box.parentNode === par) return !!par;
    if (getComputedStyle(par).position === "static") par.style.position = "relative";
    par.append(box);
    return true;
  };
  const hide = () => {
    seq++;
    box.hidden = true;
    items = [];
    tok = null;
  };
  const token = () => {
    const c = inp.selectionStart;
    if (c == null || c !== inp.selectionEnd) return null;
    const m = inp.value.slice(0, c).match(/(?:^|[^A-Za-z0-9_])@([A-Za-z0-9_]{0,20})$/);
    return m ? { q: m[1], at: c - m[1].length - 1, end: c } : null;
  };
  const choose = (u) => {
    if (!tok) return;
    const ins = "@" + u.name + " ";
    let v = inp.value.slice(0, tok.at) + ins + inp.value.slice(tok.end);
    if (inp.maxLength > 0) v = v.slice(0, inp.maxLength);
    const pos = Math.min(tok.at + ins.length, v.length);
    hide();
    inp.value = v;
    inp.focus();
    try {
      inp.setSelectionRange(pos, pos);
    } catch (e) {}
    inp.dispatchEvent(new Event("input", { bubbles: true }));
  };
  const paint = () => {
    if (!items.length) return hide();
    box.replaceChildren(
      ...items.map((u, i) =>
        h(
          "button",
          {
            type: "button",
            role: "option",
            class: "mpi" + (i === sel ? " on" : ""),
            "aria-selected": i === sel ? "true" : "false",
            onpointerdown: (e) => e.preventDefault(),
            onclick: () => choose(u),
          },
          u.every ? h("span", { class: "mpe", "aria-hidden": "true" }, ic("users", 16)) : av(u, 28),
          h("span", { class: "mpn" }, h("b", {}, u.every ? "everyone" : dn(u)), h("small", { class: "hint" }, u.every ? "Notify the whole group" : "@" + u.name)),
        ),
      ),
    );
    if (!mount()) return;
    if (below) {
      box.style.top = inp.offsetTop + inp.offsetHeight + 4 + "px";
      box.style.left = inp.offsetLeft + "px";
      box.style.width = inp.offsetWidth + "px";
    }
    box.hidden = false;
  };
  const update = async () => {
    tok = token();
    if (!tok) return hide();
    const n = ++seq,
      t = tok;
    let l = [];
    try {
      l = (await cands(t.q.toLowerCase())) || [];
    } catch (e) {}
    if (n !== seq || !tok) return;
    items = l.slice(0, 6);
    sel = 0;
    paint();
  };
  inp.addEventListener("input", update);
  inp.addEventListener("click", update);
  inp.addEventListener("keyup", (e) => {
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) update();
  });
  inp.addEventListener("blur", () => setTimeout(() => !box.hidden && hide(), 150));
  inp.addEventListener(
    "keydown",
    (e) => {
      if (box.hidden || !items.length || e.isComposing) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        sel = (sel + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length;
        paint();
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        e.stopImmediatePropagation();
        choose(items[sel]);
      } else if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        hide();
      }
    },
    true,
  );
  return box;
}
/* people to offer when @mentioning in a post or comment: your friends first, then whoever matches what you typed */
let MPF = null;
const mentionPeople = async (q) => {
  const me = String(M.name).toLowerCase();
  if (!MPF) {
    MPF = [];
    try {
      MPF = (await api("friends")).list.filter((x) => +x.st === 1);
    } catch (e) {}
  }
  const hit = (x) => String(x.name).toLowerCase().includes(q) || String(x.nick || "").toLowerCase().includes(q);
  let l = MPF.filter(hit);
  if (q) {
    try {
      const f = (await api("find", null, "&q=" + encodeURIComponent(q))).users || [];
      for (const x of f) if (!l.some((y) => String(y.name).toLowerCase() === String(x.name).toLowerCase())) l.push(x);
    } catch (e) {}
  }
  return l.filter((x) => String(x.name).toLowerCase() !== me);
};
/* link preview card under a chat message: the SERVER fetches the page's title and description (api "lpv"), so the other site never sees the reader's IP. Answers are remembered here so chat refreshes do not ask again. */
const LPC = new Map(),
  LPP = new Map();
const lpGet = (href) => {
  if (LPC.has(href)) return Promise.resolve(LPC.get(href));
  if (!LPP.has(href))
    LPP.set(
      href,
      api("lpv", null, "&lu=" + encodeURIComponent(href))
        .then((r) => {
          const v = r && r.t ? r : null;
          LPC.set(href, v);
          return v;
        })
        .catch(() => null)
        .finally(() => LPP.delete(href)),
    );
  return LPP.get(href);
};
const lpCard = (txt) => {
  let url = null;
  for (const x of String(txt).split(URLRE).filter((_, i) => i % 2)) {
    const k = urlPick(x);
    if (k) {
      url = k.url;
      break;
    }
  }
  if (!url) return null;
  const own = url.origin === location.origin,
    box = h("div", { class: "lpw", hidden: "" }),
    fill = (d) => {
      if (!d) return;
      box.replaceChildren(
        h(
          "a",
          {
            class: "lpc",
            href: url.href,
            ...(own
              ? {}
              : {
                  target: "_blank",
                  rel: "noopener noreferrer nofollow",
                  onclick: (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    askLeave(url);
                  },
                }),
          },
          (d.i && /^[a-f0-9]{16}$/.test(d.i)) || (own && d.iu && /^\?ogp?=[A-Za-z0-9_]{1,20}&v=[a-f0-9]{8}$/.test(d.iu))
            ? h("img", {
                class: "lpi",
                src: d.i && /^[a-f0-9]{16}$/.test(d.i) ? "?lpi=" + d.i : d.iu,
                alt: "",
                loading: "lazy",
                onerror: (e) => e.target.remove(),
                onload: (e) => {
                  const l = e.target.closest(".mlist");
                  if (l && l.dataset.stick === "1") l.scrollTop = l.scrollHeight;
                },
              })
            : null,
          h("small", { class: "lps" }, d.s || url.host),
          h("b", { class: "lpt" }, d.t),
          d.d ? h("span", { class: "lpd" }, d.d) : null,
        ),
      );
      box.hidden = false;
      const l = box.closest(".mlist");
      if (l && l.dataset.stick === "1") l.scrollTop = l.scrollHeight;
    };
  if (LPC.has(url.href)) fill(LPC.get(url.href));
  else lpGet(url.href).then(fill);
  return box;
};
/* A post sent in chat (its link on its own) is drawn as the post itself: who, the photo or text post, the marks and comments, tap to open. If the post can't be loaded for you (deleted, or you may not see it) the plain link and its preview show instead. */
const spk = (txt) => {
  const m = String(txt || "")
    .trim()
    .match(/^https?:\/\/([^\/\s]+)\/(?:[^\s?#]*\/)?p\/(\d{1,12})\/?$/);
  return m && m[1] === location.host ? m[2] : 0;
};
const SPC = new Map();
const spGet = (id) => {
  const c = SPC.get(id);
  if (c && Date.now() - c.t < 60000) return c.p;
  const pr = api("feed", null, "&id=" + id).then((r) => (r.posts && r.posts[0]) || null).catch(() => null);
  SPC.set(id, { t: Date.now(), p: pr });
  return pr;
};
function spCard(txt, x) {
  const id = spk(txt),
    box = h("div", { class: "spc sk", role: "link", tabindex: "0", "aria-label": "Shared post" }, h("i", { class: "sk l" }), h("i", { class: "sk img" }));
  const stick = () => {
    const l = box.closest(".mlist");
    if (l && l.dataset.stick === "1") l.scrollTop = l.scrollHeight;
  };
  spGet(id).then((p) => {
    if (!box.isConnected && !p) return;
    if (!p) {
      box.classList.remove("sk");
      box.classList.add("priv");
      box.removeAttribute("role");
      box.removeAttribute("tabindex");
      box.setAttribute("aria-label", "Private post");
      rc(box, ic("eyeoff", 24), h("div", { class: "spvt" }, h("b", {}, "This post is private"), h("small", {}, "You can\u2019t open it (private or removed)")));
      return;
    }
    const mine = !!+p.own,
      anon = +p.anon,
      mm = !!(anon && mine && M && M.mask),
      who = anon ? (mine ? (mm ? M.mask.name : dn(p)) : "Masque") : dn(p),
      im = p.imgs && p.imgs.length ? p.imgs : p.img ? [p.img] : [],
      go = () => (location.hash = "#/p/" + p.id);
    let media = null;
    if (im.length) {
      media = h(
        "div",
        { class: "spm" + (+p.sens ? " sens" : "") },
        +p.sens ? h("div", { class: "spx" }, h("b", {}, "Sensitive photo"), h("small", {}, "Open the post to view")) : h("img", { src: "?img=" + im[0], alt: (p.alts && p.alts[0]) || "Photo by " + who, loading: "lazy", draggable: "false", onload: stick }),
        im.length > 1 ? h("span", { class: "spn" }, "1/" + im.length) : null,
      );
    } else if (p.cap || p.aq) {
      const tp = h("div", { class: "tpost spt", "data-bg": p.bg || "0" });
      tbRender(tp, p.cap || p.aq, p.ed, +p.hg, p.id);
      media = tp;
    }
    box.classList.remove("sk");
    rc(
      box,
      h(
        "div",
        { class: "sph" },
        anon ? av({}, 26) : av(p, 26),
        h("b", {}, who),
        p.anon || +p.mk ? h("span", { class: "lmst", title: "Masque post" }, lmAv(18)) : null,
        h("small", {}, ago(p.ts)),
      ),
      p.aq && im.length ? h("div", { class: "spq" }, p.aq) : null,
      media,
      im.length && p.cap ? h("p", { class: "spp" }, String(p.cap).replace(/\s+/g, " ").slice(0, 140)) : null,
      h("div", { class: "spf" }, h("span", {}, ic("comment", 14), " " + (+p.cc || 0)), h("span", { class: "spo" }, "Open post")),
    );
    box.onclick = (e) => {
      if (e.target.closest("a")) return;
      go();
    };
    box.onkeydown = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        go();
      }
    };
    stick();
  });
  return box;
}
const ago = (t) => {
  const m = (Date.now() / 1000 - t) / 60;
  return m < 1
    ? "now"
    : m < 60
      ? Math.floor(m) + "m"
      : m < 1440
        ? Math.floor(m / 60) + "h"
        : Math.floor(m / 1440) + "d";
};
const $ = (s) => document.querySelector(s);
/* edit-style motion helpers: kin() splits text into letters, big() is a giant page title that wipes in once per page */
const slam = (t, host) => {
  const e = h("div", { class: "slam" + (host ? "" : " g"), "aria-hidden": "true" }, h("span", {}, t));
  (host || document.body).append(e);
  setTimeout(() => e.remove(), 1150);
};
const kin = (s, o = 0) =>
  [...s].map((c, i) => h("span", { class: "k", style: "--i:" + (i + o), "aria-hidden": "true" }, c));
const big = (t, x) =>
  h("h2", { class: "big" + (SHOWN === location.hash ? " still" : "") + (x ? " " + x : "") }, h("span", {}, t));
const rc = (e, ...k) => e.replaceChildren(...k.flat(Infinity).filter((c) => c != null));
const IC = {
  eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  comment:
    '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H11l-4.5 4v-4A2.5 2.5 0 0 1 4 13.5z"/><path d="M8 8.5h8M8 11.5h5"/>',
  e_posts:
    '<path d="M2.5 8.5c3-1.8 6-2.2 9.5-.9 3.5-1.3 6.5-.9 9.5.9 0 5.2-2 9.5-5.8 9.5-1.9 0-2.6-1.6-3.7-1.6s-1.8 1.6-3.7 1.6C4.5 18 2.5 13.7 2.5 8.5z"/><ellipse cx="8" cy="11" rx="2" ry="1.3"/><ellipse cx="16" cy="11" rx="2" ry="1.3"/><path d="M10 14.2h4" opacity=".0"/>',
  e_pair:
    '<g transform="translate(5.5 1) scale(.66)" opacity=".55"><path d="M2.5 8.5c3-1.8 6-2.2 9.5-.9 3.5-1.3 6.5-.9 9.5.9 0 5.2-2 9.5-5.8 9.5-1.9 0-2.6-1.6-3.7-1.6s-1.8 1.6-3.7 1.6C4.5 18 2.5 13.7 2.5 8.5z"/></g><g transform="translate(0 6.2) scale(.72)"><path d="M2.5 8.5c3-1.8 6-2.2 9.5-.9 3.5-1.3 6.5-.9 9.5.9 0 5.2-2 9.5-5.8 9.5-1.9 0-2.6-1.6-3.7-1.6s-1.8 1.6-3.7 1.6C4.5 18 2.5 13.7 2.5 8.5z"/><ellipse cx="8" cy="11" rx="2" ry="1.3"/><ellipse cx="16" cy="11" rx="2" ry="1.3"/></g>',
  e_chat:
    '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.6-.8L3 21l1.5-4.6A8.4 8.4 0 1 1 21 11.5z"/><ellipse cx="9" cy="11" rx="1.3" ry=".9"/><ellipse cx="15" cy="11" rx="1.3" ry=".9"/>',
  e_bell:
    '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/><path d="M9.2 10.2l2 2 3.6-3.8"/>',
  e_search:
    '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/><ellipse cx="8.6" cy="10.5" rx="1.3" ry=".9"/><ellipse cx="13.4" cy="10.5" rx="1.3" ry=".9"/>',
  e_oops:
    '<path d="M2.5 8.5c3-1.8 6-2.2 9.5-.9 3.5-1.3 6.5-.9 9.5.9 0 5.2-2 9.5-5.8 9.5-1.9 0-2.6-1.6-3.7-1.6s-1.8 1.6-3.7 1.6C4.5 18 2.5 13.7 2.5 8.5z"/><path d="M6.4 9.9l3.2 2.2M9.6 9.9l-3.2 2.2M14.4 9.9l3.2 2.2M17.6 9.9l-3.2 2.2"/>',
  e_lock:
    '<rect x="4" y="11" width="16" height="10.5" rx="2.5"/><path d="M8 11V7.5a4 4 0 0 1 8 0V11"/><circle cx="12" cy="16.2" r="1.2"/>',
  e_shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2.2 2.2L15.4 10"/>',
  mask: '<path d="M2.5 8.5c3-1.8 6-2.2 9.5-.9 3.5-1.3 6.5-.9 9.5.9 0 5.2-2 9.5-5.8 9.5-1.9 0-2.6-1.6-3.7-1.6s-1.8 1.6-3.7 1.6C4.5 18 2.5 13.7 2.5 8.5z"/><ellipse cx="8" cy="11" rx="2" ry="1.3"/><ellipse cx="16" cy="11" rx="2" ry="1.3"/>',
  camera:
    '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
  pencil: '<path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/>',
  chat: '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/>',
  users:
    '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  bell: '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
  back: '<path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/>',
  image:
    '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  close: '<path d="M18 6L6 18"/><path d="M6 6l12 12"/>',
  think:
    '<path transform="translate(3.5 1) scale(.7)" d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/><circle cx="12" cy="18.6" r="1.5"/><circle cx="11" cy="22.3" r=".85"/><circle class="dot" cx="8.6" cy="9" r=".9"/><circle class="dot" cx="12" cy="9" r=".9"/><circle class="dot" cx="15.4" cy="9" r=".9"/>',
  reply: '<polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/>',
  gift: '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13M5 12v8a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-8M7.5 8a2.5 2.5 0 0 1 0-5C10 3 12 8 12 8s2-5 4.5-5a2.5 2.5 0 0 1 0 5"/>',
  star: '<path d="M12 3.2l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.7 6.8 19.4l1-5.9L3.5 9.4l5.9-.8z"/>',
  pin: '<path d="M12 17v5"/><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3z"/>',
  more: '<circle cx="5" cy="12" r="1.7" fill="currentColor"/><circle cx="12" cy="12" r="1.7" fill="currentColor"/><circle cx="19" cy="12" r="1.7" fill="currentColor"/>',
  home: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>',
  plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
  sliders:
    '<path d="M4 21v-7"/><path d="M4 10V3"/><path d="M12 21v-9"/><path d="M12 8V3"/><path d="M20 21v-5"/><path d="M20 12V3"/><path d="M1 14h6"/><path d="M9 8h6"/><path d="M17 16h6"/>',
};
IC.bookmark = '<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>';
IC.friends = IC.users;
IC.clip =
  '<path d="M21.4 11.1l-9.2 9.2a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5"/>';
IC.share = '<path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7"/><path d="M16 6l-4-4-4 4"/><path d="M12 2v13"/>';
IC.crown = '<path d="M3 8l4.5 4L12 5l4.5 7L21 8l-1.8 10.5H4.8z"/><path d="M5 21h14"/>';
IC.chev = '<path d="M6 9l6 6 6-6"/>';
IC.lock = IC.e_lock;
IC.eyeoff =
  '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><path d="M1 1l22 22"/>';
IC.shield = IC.e_shield;
IC.ask = '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>';
IC.settings =
  '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>';
IC.trash =
  '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/>';
IC.bellx =
  '<path d="M13.73 21a2 2 0 0 1-3.46 0"/><path d="M18.63 13A17.9 17.9 0 0 1 18 8"/><path d="M6.26 6.26A5.86 5.86 0 0 0 6 8c0 7-3 9-3 9h14"/><path d="M18 8a6 6 0 0 0-9.33-5"/><path d="M1 1l22 22"/>';
/* long-press (or right-click / the menu key) on an element runs fn; the click that follows a long press is swallowed so the chat does not open */
function lpress(el, fn, skip) {
  let tm = 0,
    x = 0,
    y = 0,
    fired = 0;
  const stop = () => {
    clearTimeout(tm);
    tm = 0;
  };
  const no = (e) => !!skip && e.target instanceof Element && !!e.target.closest(skip);
  el.addEventListener("pointerdown", (e) => {
    if (e.button > 0 || no(e)) return;
    fired = 0;
    x = e.clientX;
    y = e.clientY;
    stop();
    tm = setTimeout(() => {
      tm = 0;
      fired = 1;
      try {
        navigator.vibrate && navigator.vibrate(12);
      } catch (_) {}
      fn();
    }, 480);
  });
  el.addEventListener("pointermove", (e) => {
    if (tm && Math.hypot(e.clientX - x, e.clientY - y) > 10) stop();
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((t) => el.addEventListener(t, stop));
  el.addEventListener("pointerup", () => setTimeout(() => (fired = 0), 450));
  el.addEventListener(
    "click",
    (e) => {
      if (fired) {
        fired = 0;
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    },
    true,
  );
  el.addEventListener("contextmenu", (e) => {
    if (no(e)) return;
    e.preventDefault();
    if (tm) stop();
    else if (fired) return;
    fired = 1;
    fn();
  });
}
IC.gift = '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13M5 12v8a1 1 0 001 1h12a1 1 0 001-1v-8M7.5 8a2.5 2.5 0 010-5C11 3 12 8 12 8s1-5 4.5-5a2.5 2.5 0 010 5"/>';
const ic = (n, s = 22) => {
  const e = h("span", { class: "ico" });
  e.innerHTML = `<svg viewBox="0 0 24 24" width="${s}" height="${s}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IC[n]}</svg>`;
  return e;
};
const EM = {
  image: "e_posts",
  users: "e_pair",
  chat: "e_chat",
  bell: "e_bell",
  search: "e_search",
  close: "e_oops",
  lock: "e_lock",
  shield: "e_shield",
};
const emp = (i, t, m, a) =>
  h(
    "div",
    { class: "empty" },
    h("div", { class: "escene" }, h("span", { class: "eico" + (i === "close" ? " bad" : "") }, ic(EM[i] || i, 28)), i === "close" ? null : h("span", { class: "emk", "aria-hidden": "true" }, lmIcon(26))),
    h("b", {}, t),
    m ? h("p", {}, m) : null,
    a || null,
  );
/* full-screen photo viewer: shows the whole image fitted to the screen; tap the image to switch to fit-width (tall images then scroll); Esc, X or tapping outside closes */
function view(src, alt, opt) {
  let closed = false,
    st = 0;
  const prev = document.activeElement,
    v = h("div", { class: "lb", role: "dialog", "aria-modal": "true", "aria-label": "Photo" }),
    im = h("img", { src, alt: alt || "", title: "Tap to zoom" }),
    close = () => {
      if (closed) return;
      closed = true;
      document.removeEventListener("keydown", key);
      document.documentElement.classList.remove("nolock");
      if (prev && prev.focus) prev.focus();
      if (matchMedia("(prefers-reduced-motion:reduce)").matches || !v.animate) {
        v.remove();
        return;
      }
      v.style.pointerEvents = "none";
      im.animate([{ scale: "1" }, { scale: ".9" }], {
        duration: 200,
        easing: "cubic-bezier(.4,0,1,1)",
        fill: "forwards",
      });
      v.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: "ease-in", fill: "forwards" }).onfinish =
        () => v.remove();
    },
    key = (e) => {
      if (e.key === "Escape") close();
      else if (e.key === "ArrowLeft") {
        e.preventDefault();
        go(-1);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        go(1);
      }
    },
    x = h("button", { class: "lbx", "aria-label": "Close", onclick: close }, ic("close", 22));
  v.onclick = (e) => {
    if (e.target === v) close();
  };
  /* pinch / double-tap / drag zoom handled here so the page itself never zooms */
  let sc = 1,
    tx = 0,
    ty = 0,
    dt = null;
  const P = new Map();
  let d0 = 0,
    s0 = 1,
    moved = 0,
    lastTap = 0;
  const lim = () => {
    const r = im.getBoundingClientRect(),
      w = r.width / sc,
      hh = r.height / sc,
      mx = Math.max(0, (w * sc - innerWidth) / 2),
      my = Math.max(0, (hh * sc - innerHeight) / 2);
    tx = Math.max(-mx, Math.min(mx, tx));
    ty = Math.max(-my, Math.min(my, ty));
  };
  const ap = () => {
    if (sc <= 1) {
      sc = 1;
      tx = ty = 0;
    } else lim();
    im.style.transform = `translate(${tx}px,${ty}px) scale(${sc})`;
    v.classList.toggle("zoom", sc > 1);
  };
  const zoomTo = (n) => {
    sc = Math.max(1, Math.min(5, n));
    ap();
  };
  /* several photos (opt.list=[{src,alt}], opt.i=start): arrow keys, swipe and side buttons step through them */
  const L = opt && opt.list && opt.list.length > 1 ? opt.list : null;
  let k = L ? Math.max(0, Math.min(L.length - 1, opt.i || 0)) : 0,
    gx = 0,
    gy = 0,
    tok = 0,
    an = null;
  const cnt = L ? h("span", { class: "lbn", "aria-live": "polite" }) : null,
    pv = L
      ? h(
          "button",
          { type: "button", class: "lbp", "aria-label": "Previous photo", onclick: () => go(-1) },
          ic("back", 22),
        )
      : null,
    nx = L
      ? h(
          "button",
          { type: "button", class: "lbp lbnx", "aria-label": "Next photo", onclick: () => go(1) },
          ic("back", 22),
        )
      : null;
  const dsc = h("div", { class: "lbc", hidden: "", "aria-live": "polite" }),
    setD = (t) => {
      dsc.replaceChildren();
      dsc.hidden = !t;
      if (!t) return;
      dsc.append(h("span", { class: "lbk" }, "Description"), h("p", {}, t));
      if (!matchMedia("(prefers-reduced-motion:reduce)").matches) {
        dsc.style.animation = "none";
        void dsc.offsetWidth;
        dsc.style.animation = "";
      }
    };
  const rm = matchMedia("(prefers-reduced-motion:reduce)").matches,
    fly = (a, b, ms) => {
      if (an) an.cancel();
      an = rm ? null : im.animate(a, { duration: ms, easing: "cubic-bezier(.2,.8,.2,1)" });
      return an;
    };
  const mark = () => {
    if (!L) return;
    cnt.textContent = k + 1 + " / " + L.length;
    pv.hidden = k === 0;
    nx.hidden = k === L.length - 1;
    [L[k - 1], L[k + 1]].forEach((o) => {
      if (o) new Image().src = o.src;
    });
    setD(L[k].desc);
  };
  function go(d) {
    if (!L) return;
    const j = k + d;
    if (j < 0 || j >= L.length) {
      ap();
      fly([{ transform: "translateX(" + -d * 28 + "px)" }, { transform: "none" }], 0, 260);
      return;
    }
    const my = ++tok,
      it = L[j],
      pre = new Image();
    pre.src = it.src;
    sc = 1;
    tx = ty = 0;
    gx = gy = 0;
    (pre.decode ? pre.decode() : Promise.resolve())
      .catch(() => {})
      .then(() => {
        if (my !== tok) return;
        k = j;
        im.src = it.src;
        im.alt = it.alt || "";
        ap();
        mark();
        fly(
          [
            { transform: "translateX(" + d * 70 + "px)", opacity: 0 },
            { transform: "none", opacity: 1 },
          ],
          0,
          240,
        );
        if (opt.on) opt.on(k);
      });
  }
  im.draggable = false;
  im.title = "";
  v.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".lbx,.lbp,.lbc")) return;
    if (!P.size) {
      dt = e.target;
      gx = gy = 0;
    }
    P.set(e.pointerId, { x: e.clientX, y: e.clientY });
    moved = 0;
    if (P.size === 2) {
      gx = gy = 0;
      const [a, b] = [...P.values()];
      d0 = Math.hypot(a.x - b.x, a.y - b.y);
      s0 = sc;
    }
    try {
      v.setPointerCapture(e.pointerId);
    } catch (_) {}
  });
  v.addEventListener("pointermove", (e) => {
    const p = P.get(e.pointerId);
    if (!p) return;
    const dx = e.clientX - p.x,
      dy = e.clientY - p.y;
    moved += Math.abs(dx) + Math.abs(dy);
    p.x = e.clientX;
    p.y = e.clientY;
    if (P.size === 2) {
      const [a, b] = [...P.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (d0) zoomTo((s0 * d) / d0);
    } else if (P.size === 1 && sc > 1) {
      tx += dx;
      ty += dy;
      ap();
    } else if (P.size === 1 && L) {
      gx += dx;
      gy += dy;
      if (Math.abs(gx) > Math.abs(gy)) {
        if (an) an.cancel();
        im.style.transform = "translateX(" + gx * 0.9 + "px)";
      }
    }
  });
  const up = (e) => {
    const had = P.delete(e.pointerId);
    if (!had) return;
    if (P.size === 1) {
      const [a] = [...P.values()];
      d0 = 0;
    }
    if (P.size === 0 && L && sc === 1 && Math.abs(gx) >= 8 && Math.abs(gx) > Math.abs(gy)) {
      const far = Math.abs(gx) > Math.min(80, innerWidth * 0.2),
        dx = gx;
      gx = gy = 0;
      if (e.type === "pointerup" && far) go(dx < 0 ? 1 : -1);
      else {
        const f = dx * 0.9;
        im.style.transform = "";
        fly([{ transform: "translateX(" + f + "px)" }, { transform: "none" }], 0, 200);
      }
      return;
    }
    if (P.size === 0 && moved < 8 && e.type === "pointerup") {
      const t = Date.now();
      if (dt === im) {
        if (t - lastTap < 320) {
          if (!rm) {
            im.style.transition = "transform .26s cubic-bezier(.2,.8,.2,1)";
            clearTimeout(st);
            st = setTimeout(() => {
              im.style.transition = "";
            }, 300);
          }
          zoomTo(sc > 1 ? 1 : 2.5);
          lastTap = 0;
        } else lastTap = t;
      } else if (dt === v) close();
    }
  };
  v.addEventListener("pointerup", up);
  v.addEventListener("pointercancel", up);
  v.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      zoomTo(sc * (e.deltaY < 0 ? 1.15 : 1 / 1.15));
    },
    { passive: false },
  );
  ["gesturestart", "gesturechange", "gestureend"].forEach((n) => v.addEventListener(n, (e) => e.preventDefault()));
  v.onclick = null;
  v.append(im, x, dsc);
  if (L) {
    v.append(cnt, pv, nx);
    mark();
  } else setD(opt && opt.desc);
  document.body.append(v);
  document.documentElement.classList.add("nolock");
  document.addEventListener("keydown", key);
  x.focus();
  if (!rm)
    im.animate(
      [
        { scale: ".9", opacity: 0 },
        { scale: "1", opacity: 1 },
      ],
      { duration: 280, easing: "cubic-bezier(.2,.8,.2,1)" },
    );
}
/* make an element open the photo viewer (used for profile avatar and cover) */
const zoomable = (el, src, label) => {
  el.classList.add("zoomable");
  el.removeAttribute("aria-hidden");
  el.setAttribute("tabindex", "0");
  el.setAttribute("role", "button");
  el.setAttribute("aria-label", "View " + label);
  el.onclick = (e) => {
    if (e.target.closest(".pen")) return;
    if (el.classList.contains("cover") && e.target.closest(".pmv")) return;
    view(src, label);
  };
  el.onkeydown = (e) => {
    if (e.target === el && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      view(src, label);
    }
  };
  return el;
};
/* expiration picker (New post): a bottom sheet with a draggable slider (1 minute up to 30 days) and +1 min / +5 min / +1 h / +1 day buttons; Never clears it */
const EXMAX = 2592000,
  exfmt = (s) => {
    if (!s) return "Never";
    const d = Math.floor(s / 86400),
      hr = Math.floor((s % 86400) / 3600),
      mi = Math.floor((s % 3600) / 60),
      o = [];
    if (d) o.push(d + (d === 1 ? " day" : " days"));
    if (hr) o.push(hr + (hr === 1 ? " hour" : " hours"));
    if (mi) o.push(mi + (mi === 1 ? " minute" : " minutes"));
    return o.join(" ") || "1 minute";
  },
  exsn = (v) => {
    const s = 60 * Math.pow(EXMAX / 60, (v - 1) / 99);
    return Math.min(
      EXMAX,
      s < 3600 ? Math.round(s / 60) * 60 : s < 86400 ? Math.round(s / 300) * 300 : Math.round(s / 3600) * 3600,
    );
  },
  exinv = (s) => (s ? Math.max(1, Math.min(100, Math.round(1 + (99 * Math.log(s / 60)) / Math.log(EXMAX / 60)))) : 0);
function expPicker(cur, onSet) {
  sheet("Disappears after", (close) => {
    let v = cur || 0;
    const out = h("p", { class: "exout", role: "status", "aria-live": "polite" }),
      sl = h("input", {
        type: "range",
        min: 0,
        max: 100,
        step: 1,
        class: "exsl",
        "aria-label": "Drag to choose how long the post stays",
      }),
      paint = (fromSl) => {
        out.textContent = v ? "Gone after " + exfmt(v) : "Never. It stays until you delete it.";
        if (!fromSl) sl.value = exinv(v);
        onSet(v);
      },
      add = (n, l) =>
        h(
          "button",
          {
            type: "button",
            class: "ghost exadd",
            onclick: () => {
              v = Math.min(EXMAX, v + n);
              paint();
            },
          },
          l,
        );
    sl.value = exinv(v);
    sl.oninput = () => {
      const x = +sl.value;
      v = x ? exsn(x) : 0;
      paint(true);
    };
    paint(true);
    return h(
      "div",
      { class: "form" },
      out,
      sl,
      h("div", { class: "exends", "aria-hidden": "true" }, h("small", {}, "Never"), h("small", {}, "30 days")),
      h("div", { class: "exbtns" }, add(60, "+1 min"), add(300, "+5 min"), add(3600, "+1 h"), add(86400, "+1 day")),
      h(
        "div",
        { class: "exfoot" },
        h(
          "button",
          {
            type: "button",
            class: "ghost",
            onclick: () => {
              v = 0;
              paint();
            },
          },
          "Never",
        ),
        h("button", { type: "button", class: "btn", onclick: close }, "Done"),
      ),
    );
  });
}
/* Leave animation: play it, then remove. Resolves callers immediately; the element is click-proof while it fades. */
const RM = matchMedia("(prefers-reduced-motion: reduce)");
function vout(v) {
  if (!v.isConnected || v.dataset.out) return;
  v.dataset.out = "1";
  v.classList.add("out");
  v.style.pointerEvents = "none";
  setTimeout(() => v.remove(), RM.matches ? 0 : 230);
}
const GUARD = [
  "New post",
  "Edit post",
  "Edit profile",
  "Edit banner",
  "Edit post layout",
  "Edit Masque",
  "Create your Masque",
  "Edit group",
  "New group",
];
function sheet(title, body) {
  const v = h("div", { class: "veil" }),
    close = () => vout(v),
    dirty = new Set(),
    guard = GUARD.includes(title),
    /* closing with the X or by tapping outside asks first when a form in this sheet has unsaved edits; the sheet's own close (after a save) never asks */
    asking = { on: 0 },
    tryClose = async () => {
      if (asking.on) return;
      if (guard && dirty.size && !(v.safe && v.safe())) {
        asking.on = 1;
        const ok = await cbox("Discard changes? You have edits that haven't been saved.");
        asking.on = 0;
        if (!ok) return;
      }
      if (v.saved && dirty.size && v.saved()) slam("Draft saved");
      close();
    },
    mark = (e) => dirty.add((e.target.closest && e.target.closest("form")) || v);
  v.addEventListener("input", mark);
  v.addEventListener("change", mark);
  v.addEventListener("mqdirty", mark);
  v.addEventListener("mqsaved", (e) => dirty.delete((e.target.closest && e.target.closest("form")) || v));
  v.addEventListener("click", (e) => {
    if (e.target.closest && e.target.closest(".gp")) dirty.add(v);
  });
  v.onclick = (e) => {
    if (e.target === v) tryClose();
  };
  const PFS = ["Edit profile", "Edit Masque", "Create your Masque", "Edit group"],
    FULLS = ["New post", "Edit post", ...PFS],
    full = FULLS.includes(title);
  v.append(
    h(
      "div",
      {
        class: "sheet" + (full ? " full" : "") + (!PFS.includes(title) && full ? " fp" : ""),
        role: "dialog",
        "aria-label": title,
      },
      h("h2", {}, title, h("button", { "aria-label": "Close", onclick: tryClose }, ic("close", 18))),
      body(close, v),
    ),
  );
  document.body.append(v);
  const sh = v.firstChild,
    vv = window.visualViewport;
  if (full && vv) {
    const fit = () => {
      if (!sh.isConnected) {
        vv.removeEventListener("resize", fit);
        vv.removeEventListener("scroll", fit);
        return;
      }
      if (matchMedia("(max-width:599px)").matches) {
        sh.style.height = vv.height + "px";
        sh.style.top = vv.offsetTop + "px";
      } else {
        sh.style.height = sh.style.top = "";
      }
    };
    vv.addEventListener("resize", fit);
    vv.addEventListener("scroll", fit);
    fit();
  } else if (vv) {
  /* short sheets (Questions, Edit mask, Report...) sit on the bottom edge on phones and lift above the on-screen keyboard instead of being covered by it */
    const fit = () => {
      if (!sh.isConnected) {
        vv.removeEventListener("resize", fit);
        vv.removeEventListener("scroll", fit);
        return;
      }
      if (matchMedia("(max-width:599px)").matches) {
        v.style.paddingBottom = Math.max(0, window.innerHeight - vv.height - vv.offsetTop) + "px";
        sh.style.maxHeight = Math.round(vv.height * 0.92) + "px";
      } else {
        v.style.paddingBottom = sh.style.maxHeight = "";
      }
    };
    vv.addEventListener("resize", fit);
    vv.addEventListener("scroll", fit);
    fit();
  }
}
function cbox(msg) {
  return new Promise((res) => {
    const i = msg.indexOf("? "),
      t = i > 0 ? msg.slice(0, i + 1) : msg,
      d = i > 0 ? msg.slice(i + 2) : "",
      lnk = /^Leave Masque\?/.test(msg),
      lab = lnk
        ? "Open link"
        : /^Remove/.test(msg)
        ? "Remove"
        : /^Block/.test(msg)
          ? "Block"
          : /^Delete/.test(msg)
            ? "Delete"
            : /^Leave/.test(msg)
              ? "Leave"
              : /^Discard/.test(msg)
                ? "Discard"
                : /^Sign out\?/.test(msg)
                  ? "Sign out"
                  : /^Send as /.test(msg)
                    ? "Send"
                    : "Confirm",
      prev = document.activeElement;
    const v = h("div", { class: "veil cb" }),
      done = (r) => {
        document.removeEventListener("keydown", key, true);
        vout(v);
        if (prev && prev.focus)
          try {
            prev.focus();
          } catch (e) {}
        res(r);
      },
      key = (e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          done(false);
        }
      };
    const no = h("button", { class: "ghost", type: "button", onclick: () => done(false) }, "Cancel"),
      yes = h("button", { class: lnk || /^Send as /.test(msg) ? "btn" : "btn danger", type: "button", onclick: () => done(true) }, lab);
    v.onclick = (e) => {
      if (e.target === v) done(false);
    };
    document.addEventListener("keydown", key, true);
    v.append(
      h(
        "div",
        { class: "cbox", role: "alertdialog", "aria-modal": "true", "aria-label": t },
        h("h3", {}, t),
        d ? h("p", { class: "hint" }, d) : null,
        h("div", { class: "cbtn" }, no, yes),
      ),
    );
    /* phones: drop the keyboard first and keep the box inside the visible area, so Cancel / Discard are never covered */
    try {
      if (prev && prev.blur) prev.blur();
    } catch (e) {}
    const vv = window.visualViewport,
      fit = () => {
        if (!v.isConnected) {
          if (vv) vv.removeEventListener("resize", fit);
          return;
        }
        v.style.paddingBottom = "calc(20px + " + (vv ? Math.max(0, innerHeight - vv.height - vv.offsetTop) : 0) + "px)";
      };
    document.body.append(v);
    if (vv) {
      vv.addEventListener("resize", fit);
      fit();
    }
    no.focus();
  });
}
function cur() {
  const x = location.hash || "#/";
  return x === "#/" || x.startsWith("#/p/") || x.startsWith("#/d/")
    ? "home"
    : /^#\/(x|s\/|t\/)/.test(x)
      ? "x"
      : x.startsWith("#/m") || x.startsWith("#/g/") || x.startsWith("#/gj/")
        ? "m"
        : x === "#/f"
          ? "f"
          : x === "#/n"
            ? "n"
            : x.startsWith("#/settings")
              ? "set"
              : x.startsWith("#/u/") && dec(x.slice(4)).toLowerCase() === M.name.toLowerCase()
                ? "me"
                : "";
}
function navBtn(id, icon, label, go, badge, cls) {
  const b = h(
    "button",
    { class: "nv" + (cls ? " " + cls : ""), onclick: go, ...(cur() === id ? { "aria-current": "page" } : {}) },
    typeof icon === "string" ? ic(icon, 24) : icon,
    h("span", { class: "nl" }, label),
  );
  if (badge) b.append(h("span", { class: "badge", "data-b": badge, hidden: "" }));
  if (id === "me") {
    navHold(b);
    if (M.mask) navMe(b);
  }
  return b;
}
const to = (u) => () => (location.hash = u);
/* Home: from anywhere it goes home; when you are already home it refreshes the feed and scrolls back up */
const goHome = () => {
  if (!location.hash || location.hash === "#/") {
    window.scrollTo({ top: 0, behavior: "smooth" });
    route();
  } else location.hash = "#/";
};
function rail() {
  return h(
    "nav",
    { class: "rail", "aria-label": "Main" },
    navBtn("home", "home", "Home", goHome),
    navBtn("x", "search", "Explore", to("#/x")),
    navBtn("m", "chat", "Messages", to("#/m"), "m"),
    navBtn("f", "users", "Friends", to("#/f"), "f"),
    navBtn("n", "bell", "Notifications", to("#/n"), "n"),
    navBtn("me", av(M, 26), "Profile", to("#/u/" + M.name)),
    navBtn("set", "sliders", "Settings", to("#/settings")),
    h("button", { class: "btn full", onclick: newPost }, "+ New post"),
  );
}
let DMX = null;
function tabbar() {
  const nb = (id, icon, label, go) => {
    const b = navBtn(id, icon, label, go);
    b.setAttribute("aria-label", label);
    return b;
  };
  const dock = h("nav", { class: "dock", "aria-label": "Main" }),
    mk = h(
      "button",
      { class: "mk", "aria-label": "Open menu", "aria-expanded": "false", "aria-haspopup": "true" },
      ic("mask", 34),
      h("span", { class: "badge", "data-b": "mn", hidden: "" }),
    );
  const key = (e) => {
    if (e.key === "Escape") {
      shut();
      mk.focus();
    }
  };
  function shut(quiet) {
    dock.classList.remove("open");
    mk.setAttribute("aria-expanded", "false");
    mk.setAttribute("aria-label", "Open menu");
    document.removeEventListener("keydown", key);
  }
  let held = false,
    holdT = 0,
    hot = null,
    swallow = false;
  const hit = (x, y) => {
    let best = null,
      bd = 46;
    for (const f of dock.querySelectorAll(".fi")) {
      const r = f.querySelector(".fc").getBoundingClientRect(),
        d = Math.hypot(x - (r.left + r.width / 2), y - (r.top + r.height / 2));
      if (d < bd) {
        bd = d;
        best = f;
      }
    }
    return best;
  };
  const setHot = (f) => {
    if (f === hot) return;
    hot && hot.classList.remove("hot");
    hot = f;
    f && f.classList.add("hot");
    if (f && navigator.vibrate)
      try {
        navigator.vibrate(8);
      } catch (e) {}
  };
  const openIt = () => {
    dock.classList.add("open");
    mk.setAttribute("aria-expanded", "true");
    mk.setAttribute("aria-label", "Close menu");
    document.addEventListener("keydown", key);
  };
  mk.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button) return;
    if (dock.classList.contains("open")) return;
    held = false;
    clearTimeout(holdT);
    holdT = setTimeout(() => {
      held = true;
      openIt();
      try {
        mk.setPointerCapture(e.pointerId);
      } catch (_) {}
      if (navigator.vibrate)
        try {
          navigator.vibrate(12);
        } catch (_) {}
    }, 260);
  });
  mk.addEventListener("pointermove", (e) => {
    if (held) setHot(hit(e.clientX, e.clientY));
  });
  const endHold = (e) => {
    clearTimeout(holdT);
    if (!held) return;
    const f = e.type === "pointerup" ? hit(e.clientX, e.clientY) : null;
    held = false;
    swallow = true;
    setTimeout(() => (swallow = false), 350);
    if (f) {
      setHot(null);
      f.click();
    } else {
      setHot(null);
      shut();
    }
  };
  mk.addEventListener("pointerup", endHold);
  mk.addEventListener("pointercancel", endHold);
  mk.addEventListener("contextmenu", (e) => e.preventDefault());
  mk.onclick = () => {
    if (swallow) return;
    if (dock.classList.contains("open")) return shut();
    dock.classList.add("open");
    mk.setAttribute("aria-expanded", "true");
    mk.setAttribute("aria-label", "Close menu");
    document.addEventListener("keydown", key);
  };
  const fi = (label, icon, x, y, go, b) => {
    const c = h("span", { class: "fc" }, ic(icon, 22));
    if (b) c.append(h("span", { class: "badge", "data-b": b, hidden: "" }));
    return h(
      "button",
      {
        class: "fi",
        style: "--x:" + x + "px;--y:" + y + "px",
        "aria-label": label,
        onclick: () => {
          shut(1);
          go();
        },
      },
      c,
      h("span", { class: "fl" }, label),
    );
  };
  /* the active tab is shown by a small bar under its icon; it glides from the tab you were on to the new one (the dock is rebuilt on every page, so the last position is remembered in DMX) */
  const mark = h("i", { class: "dmark", "aria-hidden": "true" });
  requestAnimationFrame(() => {
    const a = dock.querySelector('.dpill .nv[aria-current="page"]');
    if (!a || !a.offsetWidth) {
      DMX = null;
      return;
    }
    const x = Math.round(a.offsetLeft + a.offsetWidth / 2 - 9),
      from = DMX;
    DMX = x;
    mark.style.transform = "translateX(" + x + "px)";
    mark.classList.add("on");
    if (from != null && from !== x && mark.animate && !matchMedia("(prefers-reduced-motion:reduce)").matches)
      mark.animate([{ transform: "translateX(" + from + "px)" }, { transform: "translateX(" + x + "px)" }], { duration: 280, easing: "cubic-bezier(.2,.9,.3,1)" });
  });
  dock.append(
    h("div", { class: "dscrim", onclick: shut }),
    h(
      "div",
      { class: "dpill" },
      nb("home", "home", "Home", goHome),
      nb("x", "search", "Explore", to("#/x")),
      h("span", { class: "dgap", "aria-hidden": "true" }),
      nb("f", "users", "Friends", to("#/f")),
      nb("me", av(M, 26), "Profile", to("#/u/" + M.name)),
      mark,
    ),
    h(
      "div",
      { class: "dmk" },
      h(
        "div",
        { class: "fan" },
        fi("Post", "plus", -84, -62, newPost),
        fi("Chat", "chat", 0, -98, to("#/m"), "m"),
        fi("Alerts", "bell", 84, -62, to("#/n"), "n"),
      ),
      mk,
    ),
  );
  return dock;
}
function collapse(el, sx) {
  return new Promise((r) => {
    if (!el || !el.isConnected || matchMedia("(prefers-reduced-motion:reduce)").matches || !el.animate) {
      r();
      return;
    }
    const h0 = el.offsetHeight,
      mb = getComputedStyle(el).marginBottom;
    el.style.overflow = "hidden";
    el.style.pointerEvents = "none";
    el.animate(
      [
        { height: h0 + "px", opacity: 1, marginBottom: mb, transform: "none" },
        {
          height: "0px",
          opacity: 0,
          marginBottom: "0px",
          paddingTop: "0px",
          paddingBottom: "0px",
          transform: "translateX(" + (sx || 0) + "px)",
        },
      ],
      { duration: 280, easing: "cubic-bezier(.4,0,.2,1)", fill: "forwards" },
    ).onfinish = () => r();
  });
}
const FT = {};
let INBX = null,
  NPREV = null,
  FNEW = null,
  FPOP = 0;
function setN(el, v, up) {
  const was = el.textContent;
  el.textContent = v;
  if (was === String(v) || matchMedia("(prefers-reduced-motion:reduce)").matches || !el.animate) return;
  el.animate(
    [
      { transform: "translateY(" + (up ? 9 : -9) + "px)", opacity: 0 },
      { transform: "none", opacity: 1 },
    ],
    { duration: 240, easing: "cubic-bezier(.2,.8,.2,1)" },
  );
}
function badgeSet(x, v) {
  const rm = matchMedia("(prefers-reduced-motion:reduce)").matches,
    had = !x.hidden && x.textContent !== "";
  if (x._a) {
    x._a.onfinish = null;
    x._a.cancel();
    x._a = null;
  }
  if (!v) {
    if (!had || rm || !x.animate) {
      x.hidden = true;
      x.textContent = "";
      return;
    }
    x._a = x.animate(
      [
        { transform: "scale(1)", opacity: 1 },
        { transform: "scale(0)", opacity: 0 },
      ],
      { duration: 180, easing: "ease-in" },
    );
    x._a.onfinish = () => {
      x._a = null;
      x.hidden = true;
      x.textContent = "";
    };
    return;
  }
  const was = x.textContent;
  x.textContent = v;
  x.hidden = false;
  if (had && String(v) !== was && !rm && x.animate)
    x.animate([{ transform: "scale(1.45)" }, { transform: "none" }], {
      duration: 300,
      easing: "cubic-bezier(.2,1.6,.4,1)",
    });
}
async function rowFx(row, fx, b) {
  if (matchMedia("(prefers-reduced-motion:reduce)").matches || !row.animate) return;
  if (fx === "acc") {
    if (b) b.textContent = "Accepted";
    try {
      await row.animate(
        [
          { transform: "scale(1)" },
          { transform: "scale(1.035)", backgroundColor: "var(--tint2)", offset: 0.4 },
          { transform: "scale(1)", backgroundColor: "var(--tint2)" },
        ],
        { duration: 440, easing: "cubic-bezier(.2,.8,.2,1)" },
      ).finished;
    } catch (e) {}
  } else await collapse(row, -48);
}
function swap(el, d) {
  if (matchMedia("(prefers-reduced-motion:reduce)").matches) return;
  el.style.setProperty("--d", d);
  el.classList.remove("tswap");
  void el.offsetWidth;
  el.classList.add("tswap");
}
function shell(main, bare) {
  const go = SHOWN !== location.hash,
    first = !shell.seen;
  shell.seen = 1;
  $("#app").replaceChildren(
    ...[
      h(
        "header",
        {},
        h(
          "div",
          { class: "w" },
          h(
            "button",
            { class: "logo" + (first ? " intro kt" : ""), "aria-label": "Home", onclick: goHome },
            first ? [kin("Mas"), h("i", {}, kin("que", 3))] : ["Mas", h("i", {}, "que")],
          ),
          h(
            "button",
            { class: "ghost msgb mob", "aria-label": "Messages", onclick: to("#/m") },
            ic("chat"),
            h("span", { class: "badge", "data-b": "m", hidden: "" }),
          ),
        ),
      ),
      h(
        "main",
        {},
        h(
          "div",
          { class: "w cols" },
          rail(),
          h("div", { class: "feed" + (go ? " go" : "") }, susBanner(), mtBanner(), main),
        ),
      ),
      bare ? null : tabbar(),
    ].filter(Boolean),
  );
  /* phones: the top bar (logo + messages) is only on the Home feed; every other page has its own title, the dock has Home and Chat, and pages without a dock keep the bar */
  document.documentElement.classList.toggle("nohdr", !bare && !!location.hash && location.hash !== "#/");
  if (go) {
    document
      .querySelectorAll(".feed>.chat,.feed>.card,.feed .chip,.feed .ilist>.chat")
      .forEach((c, i) => c.style.setProperty("--s", Math.min(i, 8)));
    document.querySelectorAll('.nv[aria-current="page"]').forEach((b) => b.classList.add("navpop"));
  }
  api("unread")
    .then((r) => {
      for (const [k, v] of [
        ["m", r.n],
        ["f", r.r],
        ["n", r.o],
        ["mn", r.n + r.o],
      ])
        document.querySelectorAll('[data-b="' + k + '"]').forEach((x) => {
          badgeSet(x, v);
          /* gold while a new gift is waiting among the unseen notifications; back to red once the notifications were looked at */
          x.classList.toggle("gold", !!(r.og && v && (k === "n" || k === "mn")));
        });
      tabCount((r.n || 0) + (r.o || 0));
    })
    .catch(() => {});
}
/* unread count in the tab title, e.g. "(2) Masque", and on the app icon where the browser allows it */
let TAB_BASE = null,
  TABN = 0;
/* tab title per screen, e.g. "Masque - Home". Keeps the unread count in front: "(2) Masque - Home" */
function setTitle(base) {
  try {
    TAB_BASE = base;
    document.title = (TABN ? "(" + (TABN > 99 ? "99+" : TABN) + ") " : "") + base;
  } catch (_) {}
}
function titleFor(h1) {
  const t = h1 || "#/";
  let m;
  if (t === "#/" || /^#\/d\//.test(t)) return "Masque - Home";
  if ((m = t.match(/^#\/u\/(\w+)/))) return M && String(m[1]).toLowerCase() === String(M.name).toLowerCase() ? "Masque - Profile" : "Masque - @" + m[1];
  if (/^#\/p\//.test(t)) return "Masque - Post";
  if (/^#\/t\//.test(t)) return "Masque - #" + t.slice(4).split(/[/?]/)[0];
  if (/^#\/s\//.test(t)) return "Masque - Search";
  if (t === "#/x") return "Masque - Explore";
  if (t === "#/m") return "Masque - Messages";
  if (/^#\/m\//.test(t)) return "Masque - Chat";
  if (/^#\/g\//.test(t)) return "Masque - Group";
  if (t === "#/o") return "Masque - Rooms";
  if (/^#\/o\//.test(t)) return "Masque - Room";
  if (/^#\/gj\//.test(t)) return "Masque - Join group";
  if (t === "#/f") return "Masque - Friends";
  if (t === "#/n") return "Masque - Notifications";
  if (t === "#/saved") return "Masque - Saved";
  if (t.startsWith("#/settings")) return "Masque - Settings";
  if (/^#\/k\//.test(t)) return "Masque - Masque";
  if (t === "#/r") return "Masque - Reports";
  if (t === "#/w") return "Masque - Words";
  if (t === "#/dash") return "Masque - Dashboard";
  if (t === "#/ausers") return "Masque - People";
  if (t === "#/aposts") return "Masque - Posts";
  if (t === "#/acomments") return "Masque - Comments";
  return "Masque - Home";
}
/* once a page has its data, swap the generic title for a specific one (h0 = the hash the page was opened on, so a slow load never retitles a page you already left) */
function refineTitle(h0, sub) {
  try {
    if (sub && location.hash === h0) setTitle("Masque - " + sub);
  } catch (_) {}
}
function postTitle(p) {
  try {
    if (!/^#\/p\//.test(location.hash)) return;
    const who = +p.anon ? "Masque" : dn(p),
      cap = String(p.cap || "").replace(/\s+/g, " ").trim();
    setTitle("Masque - " + (cap ? who + ": " + (cap.length > 40 ? cap.slice(0, 40) + "\u2026" : cap) : who + "\u2019s post"));
  } catch (_) {}
}
function tabCount(n) {
  try {
    n = Math.max(0, n | 0);
    TABN = n;
    const clean = document.title.replace(/^\(\d+\+?\)\s+/, "");
    if (TAB_BASE === null || clean !== TAB_BASE) TAB_BASE = clean;
    document.title = (n ? "(" + (n > 99 ? "99+" : n) + ") " : "") + TAB_BASE;
    if (navigator.setAppBadge) (n ? navigator.setAppBadge(n) : navigator.clearAppBadge()).catch(() => {});
  } catch (_) {}
}
/* auth */
function pwField(ph, ac) {
  const i = h("input", { type: "password", placeholder: ph, autocomplete: ac }),
    b = h("button", { type: "button", "aria-label": "Show password" }, "Show");
  b.onclick = () => {
    const t = i.type === "password";
    i.type = t ? "text" : "password";
    b.textContent = t ? "Hide" : "Show";
    b.setAttribute("aria-label", t ? "Hide password" : "Show password");
  };
  return { i, el: h("div", { class: "pw" }, i, b) };
}
/* recovery code: shown once after sign-up / reset / regenerate */
function rcBody(code, done) {
  const cb = h("input", { type: "checkbox", style: "width:auto" }),
    go = h("button", { class: "btn full", type: "button", onclick: done }, "Continue"),
    cp = h("button", { class: "ghost", type: "button" }, "Copy"),
    sv = h("button", { class: "ghost", type: "button" }, "Save as file");
  go.disabled = true;
  cb.onchange = () => {
    go.disabled = !cb.checked;
  };
  cp.onclick = async () => {
    try {
      await navigator.clipboard.writeText(code);
      cp.textContent = "Copied";
    } catch (e) {
      cp.textContent = "Copy failed";
    }
    setTimeout(() => {
      cp.textContent = "Copy";
    }, 1800);
  };
  sv.onclick = () => {
    const a = h("a", {
      href: URL.createObjectURL(
        new Blob(
          [
            "Masque recovery code\n" +
              code +
              "\n\nKeep this private. With your username it resets your password if you forget it, so anyone who has it can take over your account.\n",
          ],
          { type: "text/plain" },
        ),
      ),
      download: "masque-recovery-code.txt",
    });
    document.body.append(a);
    a.click();
    a.remove();
  };
  return h(
    "div",
    { class: "form" },
    h(
      "p",
      { class: "sub" },
      MAILOK
        ? "This code resets a forgotten password. You can also add a recovery email in Settings. We can't show the code again. Each code works once."
        : "There's no email on Masque, so this code is the only way to reset a forgotten password. We can't show it again. Each code works once.",
    ),
    h("code", { class: "rcode", "aria-label": "Recovery code" }, code),
    h("div", { class: "row" }, cp, sv),
    h("label", { class: "chk" }, cb, " I saved my recovery code somewhere safe"),
    go,
  );
}
function showRC(code, title, next) {
  $("#app").replaceChildren(
    h(
      "div",
      { class: "auth" },
      h("h1", { class: "logo", "aria-label": "Masque" }, "Mas", h("i", {}, "que")),
      h("div", { class: "card" }, h("h3", {}, title), rcBody(code, next)),
    ),
  );
}
function recoverView() {
  const err = h("p", { class: "err", role: "alert" }),
    n = h("input", { placeholder: "Username", autocomplete: "username", autocapitalize: "none", maxlength: 20 }),
    code = h("input", {
      placeholder: "XXXX-XXXX-XXXX-XXXX",
      autocomplete: "off",
      autocapitalize: "characters",
      spellcheck: "false",
      maxlength: 24,
      "aria-label": "Recovery code",
    }),
    pw = pwField("New password (8+ characters)", "new-password"),
    btn = h("button", { class: "btn full", type: "submit" }, "Reset password");
  const f = h(
    "form",
    {
      class: "form",
      onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";
        btn.disabled = true;
        try {
          const rs = await api("recover", fd({ name: n.value, code: code.value, pw: pw.i.value }));
          M = rs.me;
          showRC(rs.rc, "Password reset. Here is your new recovery code", route);
        } catch (x) {
          err.textContent = x.e || "Something went wrong.";
          btn.disabled = false;
        }
      },
    },
    h("label", { class: "f" }, "Username", n),
    h("label", { class: "f" }, "Recovery code", code),
    h("label", { class: "f" }, "New password", pw.el),
    err,
    btn,
    MAILOK
      ? h("button", { type: "button", class: "lnk", onclick: mailReqView }, "Email me a reset link instead")
      : null,
    h("button", { type: "button", class: "lnk", onclick: () => auth("in") }, "Back to sign in"),
  );
  $("#app").replaceChildren(
    h(
      "div",
      { class: "auth" },
      h("h1", { class: "logo", "aria-label": "Masque" }, "Mas", h("i", {}, "que")),
      h("p", { class: "sub" }, "Reset your password with the recovery code you saved when you signed up."),
      h("div", { class: "card" }, f),
    ),
  );
}
/* recovery email: small card screen, ask-for-a-link screen, handling of the links in the emails, and the Settings card */
function simpleCard(title, ...kids) {
  $("#app").replaceChildren(
    h(
      "div",
      { class: "auth" },
      h("h1", { class: "logo", "aria-label": "Masque" }, "Mas", h("i", {}, "que")),
      h("div", { class: "card" }, h("h3", {}, title), ...kids),
    ),
  );
}
function mailReqView() {
  const err = h("p", { class: "err", role: "alert" }),
    n = h("input", { placeholder: "Username", autocomplete: "username", autocapitalize: "none", maxlength: 20 }),
    btn = h("button", { class: "btn full", type: "submit" }, "Email me a reset link");
  const f = h(
    "form",
    {
      class: "form",
      onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";
        btn.disabled = true;
        try {
          await api("mailreq", fd({ name: n.value }));
          simpleCard(
            "Check your email",
            h(
              "p",
              { class: "sub" },
              "If that account has a recovery email, a reset link is on its way. It works for 30 minutes. Check your spam folder too.",
            ),
            h("button", { class: "btn full", type: "button", onclick: () => auth("in") }, "Back to sign in"),
          );
        } catch (x) {
          err.textContent = x.e || "Something went wrong.";
          btn.disabled = false;
        }
      },
    },
    h("label", { class: "f" }, "Username", n),
    err,
    btn,
    h("button", { type: "button", class: "lnk", onclick: recoverView }, "Use my recovery code instead"),
  );
  $("#app").replaceChildren(
    h(
      "div",
      { class: "auth" },
      h("h1", { class: "logo", "aria-label": "Masque" }, "Mas", h("i", {}, "que")),
      h("p", { class: "sub" }, "We'll send a reset link to the recovery email on your account."),
      h("div", { class: "card" }, f),
    ),
  );
}
async function mailLink() {
  const { k, t } = MLINK;
  MLINK = null;
  const go = h("button", { class: "btn full", type: "button", onclick: () => route() }, "Continue");
  if (k === "mv") {
    try {
      await api("mailverify", fd({ t }));
      try {
        M = (await api("me")).me;
      } catch (e) {}
      simpleCard(
        "Recovery email confirmed",
        h("p", { class: "sub" }, "If you ever forget your password, we can email a reset link to this address."),
        go,
      );
    } catch (x) {
      simpleCard("Link not valid", h("p", { class: "err" }, x.e || "Something went wrong."), go);
    }
    return;
  }
  const err = h("p", { class: "err", role: "alert" }),
    pw = pwField("New password (8+ characters)", "new-password"),
    btn = h("button", { class: "btn full", type: "submit" }, "Set new password");
  simpleCard(
    "Choose a new password",
    h(
      "form",
      {
        class: "form",
        onsubmit: async (e) => {
          e.preventDefault();
          err.textContent = "";
          btn.disabled = true;
          try {
            const rs = await api("mailreset", fd({ t, pw: pw.i.value }));
            M = rs.me;
            route();
          } catch (x) {
            err.textContent = x.e || "Something went wrong.";
            btn.disabled = false;
          }
        },
      },
      h("label", { class: "f" }, "New password", pw.el),
      err,
      btn,
    ),
  );
}
function mailCard() {
  if (!MAILOK) return h("div", { hidden: "hidden" });
  const em = h("input", {
      type: "email",
      placeholder: "you@example.com",
      "aria-label": "Recovery email",
      autocomplete: "email",
      maxlength: 120,
    }),
    pw = pwField("Current password", "current-password"),
    err = h("p", { class: "err", role: "alert" }),
    ok = h("p", { class: "hint", role: "status" }),
    b = h("button", { type: "button", class: "ghost" }, M.hasmail ? "Change email" : "Add recovery email");
  b.onclick = async () => {
    err.textContent = "";
    ok.textContent = "";
    if (!em.value.trim() || !pw.i.value) {
      err.textContent = "Enter your email and your current password.";
      return;
    }
    b.disabled = true;
    try {
      await api("mailset", fd({ mail: em.value, pw: pw.i.value }));
      ok.textContent = "Check your inbox. Open the link we sent within 1 hour to confirm this address.";
      pw.i.value = "";
      em.value = "";
    } catch (x) {
      err.textContent = x.e || "Could not send the email.";
    }
    b.disabled = false;
  };
  const rm = M.hasmail
    ? h(
        "button",
        {
          type: "button",
          class: "ghost",
          onclick: async () => {
            err.textContent = "";
            ok.textContent = "";
            if (!pw.i.value) {
              err.textContent = "Enter your current password first.";
              return;
            }
            if (
              !(await cbox(
                "Remove your recovery email? You will only be able to reset a forgotten password with your recovery code.",
              ))
            )
              return;
            try {
              const rs = await api("mailrm", fd({ pw: pw.i.value }));
              M = rs.me;
              pw.i.value = "";
              settings();
            } catch (x) {
              err.textContent = x.e || "Could not remove it.";
            }
          },
        },
        "Remove email",
      )
    : null;
  return h(
    "div",
    { class: "card" },
    h("h3", {}, "Recovery email"),
    h(
      "p",
      { class: "hint" },
      M.hasmail
        ? "Reset links go to " +
            M.mailm +
            ". We keep it encrypted and only use it for password resets and security notices."
        : "Optional. If you forget your password, we can email you a reset link. We keep it encrypted and only use it for resets and security notices.",
    ),
    h("div", { class: "form", style: "margin-top:10px" }, em, pw.el, err, ok, b, rm),
  );
}
function rcCard() {
  const pw = pwField("Current password", "current-password"),
    err = h("p", { class: "err", role: "alert" }),
    b = h("button", { type: "button", class: "ghost" }, M.hasrc ? "Make a new code" : "Make a recovery code");
  b.onclick = async () => {
    err.textContent = "";
    if (!pw.i.value) {
      err.textContent = "Enter your current password first.";
      return;
    }
    if (M.hasrc && !(await cbox("Replace your recovery code? The old one will stop working."))) return;
    b.disabled = true;
    try {
      const rs = await api("newrc", fd({ pw: pw.i.value }));
      M = rs.me;
      pw.i.value = "";
      sheet("Your recovery code", (close) =>
        rcBody(rs.code || rs.rc, () => {
          close();
          settings();
        }),
      );
    } catch (x) {
      err.textContent = x.e || "Could not make a code.";
    }
    b.disabled = false;
  };
  return h(
    "div",
    { class: "card" },
    h("h3", {}, "Recovery code"),
    h(
      "p",
      { class: "hint" },
      M.hasrc
        ? "You have a recovery code. We can't show it again, so if you lost it, make a new one."
        : "You don't have one yet, so a forgotten password can't be reset. Make one now and keep it somewhere safe.",
    ),
    h("div", { class: "form", style: "margin-top:10px" }, pw.el, err, b),
  );
}
const susBanner = () =>
  M && M.sus > Date.now() / 1000
    ? h(
        "div",
        { class: "sbanner", role: "status" },
        h(
          "span",
          {},
          M.sus >= 2e9
            ? "Your account is banned. You can read, but not post or send anything."
            : "Your account is suspended until " +
                new Date(M.sus * 1000).toLocaleDateString(undefined, {
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                }) +
                ". You can read, but not post or send anything.",
        ),
        h("button", { type: "button", class: "ghost sapp", onclick: () => appealSheet() }, "Appeal"),
      )
    : null;
/* people a new account might add (server action "suggest"): a short list with an Add button each. Used by the first-run welcome and the Home welcome card. */
function sugList(max, onNone) {
  const box = h("div", { class: "obpeople" }, h("p", { class: "hint" }, "Loading\u2026"));
  api("suggest")
    .then((r) => {
      const L = (r.list || []).slice(0, max);
      if (!L.length) {
        box.replaceChildren(h("p", { class: "hint" }, "No one to suggest yet. You can find people any time from Friends."));
        if (onNone) onNone();
        return;
      }
      box.replaceChildren(
        ...L.map((u) => {
          const b = h("button", { type: "button", class: "ghost obadd" }, "Add");
          b.onclick = async () => {
            b.disabled = true;
            try {
              await api("fadd", fd({ to: u.name }));
              b.textContent = "Requested";
            } catch (e) {
              b.disabled = false;
              b.textContent = (e && e.e) || "Try again";
            }
          };
          return h(
            "div",
            { class: "obp" },
            h("a", { class: "obpl", href: "#/u/" + u.name }, av(u, 40), h("span", {}, h("b", {}, dn(u)), h("small", { class: "hint" }, "@" + u.name))),
            b,
          );
        }),
      );
    })
    .catch(() => box.replaceChildren(h("p", { class: "hint" }, "Couldn't load suggestions. You can find people later from Friends.")));
  return box;
}
/* first-run welcome after signing up (shown once): 1) make a Masque 2) follow a few tags 3) quick tips 4) answer today's prompt. Every step can be skipped. */
function onboard(step = 1) {
  if (!M) return;
  const N = 5;
  sheet("Welcome to Masque", (close) => {
    const dots = h("p", { class: "hint obstep" }, "Step " + step + " of " + N),
      skip = (lbl) =>
        h(
          "button",
          {
            type: "button",
            class: "ghost",
            onclick: () => {
              close();
              setTimeout(() => (step < N ? onboard(step + 1) : route()), 240);
            },
          },
          lbl || "Skip",
        ),
      wrap = (t, d, ...r) => h("div", { class: "form obx" }, dots, h("h3", {}, t), h("p", { class: "hint" }, d), ...r);
    if (step === 1)
      return wrap(
        "Make a Masque",
        "A Masque is a second name and picture you can post and comment as. Nobody is shown that it belongs to you. You can always do this later.",
        h(
          "button",
          {
            type: "button",
            class: "btn full",
            onclick: () => {
              close();
              setTimeout(() => maskSheet(() => onboard(2)), 240);
            },
          },
          "Create my Masque",
        ),
        skip(),
      );
    if (step === 2) {
      const box = h("div", { class: "obtags" }, h("p", { class: "hint" }, "Loading\u2026"));
      api("tags")
        .then((r) => {
          const L = (r.tags || []).slice(0, 10);
          box.replaceChildren(
            ...(L.length
              ? L.map((t) => {
                  const b = h("button", { type: "button", class: "chip", "aria-pressed": "false" }, "#" + t.tag);
                  b.onclick = async () => {
                    b.disabled = true;
                    try {
                      const x = await api("tagfollow", fd({ tag: t.tag }));
                      b.setAttribute("aria-pressed", String(!!+x.tf));
                      b.classList.toggle("on", !!+x.tf);
                    } catch (e) {}
                    b.disabled = false;
                  };
                  return b;
                })
              : [h("p", { class: "hint" }, "No popular tags yet. You can follow tags any time from Explore.")]),
          );
        })
        .catch(() =>
          box.replaceChildren(h("p", { class: "hint" }, "Couldn't load tags. You can follow them later from Explore.")),
        );
      return wrap(
        "Follow a few tags",
        "Posts that use tags you follow show up for you. Tap to follow or unfollow.",
        box,
        h(
          "button",
          {
            type: "button",
            class: "btn full",
            onclick: () => {
              close();
              setTimeout(() => onboard(3), 240);
            },
          },
          "Next",
        ),
      );
    }
    if (step === 3)
      return wrap(
        "Add a few people",
        "Friends make your feed and chats come alive. Tap Add to send a request; they choose whether to accept.",
        sugList(6),
        h(
          "button",
          {
            type: "button",
            class: "btn full",
            onclick: () => {
              close();
              setTimeout(() => onboard(4), 240);
            },
          },
          "Next",
        ),
      );
    if (step === 4) {
      const T = [
        [
          "The mask button",
          "Tap the round mask at the bottom for Post, Chat and Alerts. On a phone you can also hold it and slide to one.",
        ],
        [
          "Your Masque",
          "Post, comment and chat as your Masque. Nobody is shown it is you, and revealing it is always your choice.",
        ],
        [
          "You choose who sees a post",
          "Set each post to Everyone, Friends or Only me, and make it disappear after a time you pick.",
        ],
        [
          "Anonymous questions",
          "People can ask you things from your profile without you seeing who. Turn it off any time in Settings.",
        ],
      ];
      const li = ([t, d]) => h("li", {}, h("b", {}, t), h("span", { class: "hint" }, d)),
        ul = h("ul", { class: "obtips" }, ...T.map(li)),
        ev = () => {
          if (UNL && UNL.ev && +UNL.ev.on)
            ul.append(li(["Castle Night", "A limited-time look for your profile. Find it in Edit profile."]));
        };
      if (UNL) ev();
      else unlLoad().then(ev);
      return wrap(
        "A few quick tips",
        "Everything you need to start. You can ignore all of it.",
        ul,
        h(
          "button",
          {
            type: "button",
            class: "btn full",
            onclick: () => {
              close();
              setTimeout(() => onboard(5), 240);
            },
          },
          "Got it",
        ),
      );
    }
    const q = h("p", { class: "pq obq" }, "\u2026");
    let pr = null;
    const go = h("button", { type: "button", class: "btn full", disabled: true }, "Answer it");
    api("prompt")
      .then((r) => {
        pr = r;
        q.textContent = r.text;
        go.disabled = !!+r.done;
      })
      .catch(() => {
        q.textContent = "Today's prompt is not available right now.";
      });
    go.onclick = () => {
      close();
      setTimeout(() => {
        route();
        if (pr) newPost({ day: pr.day, text: pr.text });
      }, 240);
    };
    return wrap(
      "Say hello",
      "Every day there is a prompt anyone can answer. It's an easy first post.",
      q,
      go,
      skip("Maybe later"),
    );
  });
}
function auth(tab = "in") {
  const first = !auth.seen;
  auth.seen = 1;
  const up = tab === "up",
    label = up ? "Create account" : "Sign in",
    err = h("p", { class: "err", role: "alert" }),
    n = h("input", {
      placeholder: "e.g. nightowl_42",
      autocomplete: "username",
      autocapitalize: "none",
      maxlength: 20,
    }),
    pw = pwField("Password", up ? "new-password" : "current-password"),
    hint = h("span", { class: "hint" }, "At least 8 characters."),
    btn = h("button", { class: "btn full", type: "submit" }, label);
  pw.i.oninput = () => hint.classList.toggle("ok", pw.i.value.length >= 8);
  const f = h(
    "form",
    {
      class: "form",
      onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";
        btn.disabled = true;
        btn.textContent = "Please wait…";
        try {
          const rs = await api(up ? "signup" : "login", fd({ name: n.value, pw: pw.i.value }));
          M = rs.me;
          if (up && rs.rc)
            showRC(rs.rc, "Save your recovery code", async () => {
              await route();
              onboard();
            });
          else route();
        } catch (x) {
          err.textContent = x.e || "Something went wrong.";
          btn.disabled = false;
          btn.textContent = label;
        }
      },
    },
    h(
      "label",
      { class: "f" },
      "Username",
      n,
      up
        ? h(
            "span",
            { class: "hint" },
            "3 to 20 letters, numbers or _. You can add a display name later in Edit profile.",
          )
        : null,
    ),
    h("label", { class: "f" }, "Password", pw.el, up ? hint : null),
    err,
    btn,
    up ? null : h("button", { type: "button", class: "lnk", onclick: recoverView }, "Forgot password?"),
  );
  const tabs = h("div", { class: "tabs", role: "tablist" });
  [
    ["in", "Sign in"],
    ["up", "Sign up"],
  ].forEach(([k, l]) =>
    tabs.append(h("button", { role: "tab", "aria-selected": tab === k, onclick: () => auth(k) }, l)),
  );
  $("#app").replaceChildren(
    h(
      "div",
      { class: "auth" + (first ? " intro" : "") },
      h("h1", { class: "logo kt", "aria-label": "Masque" }, kin("Mas"), h("i", {}, kin("que", 3))),
      h("p", { class: "sub" }, "Be anyone you want. No real names, ever."),
      h("div", { class: "card" }, tabs, f),
      h(
        "p",
        { class: "hint", style: "margin-top:14px" },
        up
          ? "No email needed. You'll get a recovery code after signing up: it's the only way to reset a forgotten password."
          : "New here? Choose Sign up.",
      ),
      h(
        "ul",
        { class: "pitch", "aria-label": "About Masque" },
        ...[
          ["Be anyone", "Make a Masque: a character with its own name and avatar, and post as it whenever you like."],
          [
            "No real names",
            MAILOK
              ? "No phone number, no real name. An email is optional and only used to reset your password."
              : "No email, no phone number. Just a username and a recovery code.",
          ],
          ["Post your way", "Photos, big poster-style text, polls and anonymous questions."],
          ["Stay in control", "Friends-only and only-me posts, posts that disappear, mute and block."],
        ].map(([t, d], i) => h("li", { style: "--i:" + i }, h("b", {}, t), h("span", {}, d))),
      ),
      h(
        "p",
        { class: "hint fine" },
        up ? "By signing up you agree to the " : "Masque is a place to play with identity. Read the ",
        h("a", { href: "?page=terms" }, "Terms"),
        up ? " and " : " and ",
        h("a", { href: "?page=privacy" }, "Privacy"),
        up ? ". Be kind, and don't pretend to be a real person to hurt them." : " pages.",
      ),
    ),
  );
  if (!first) swap(f, up ? 1 : -1);
}
/* views */
const SIGIL =
  '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path class="d core" d="M12 7.5L16 12L12 16.5L8 12Z"/><path class="d bl" d="M12 1L13.1 5.6L12 7.5L10.9 5.6Z"/><path class="d bl" d="M12 23L13.1 18.4L12 16.5L10.9 18.4Z"/><path class="hn" d="M8 12Q4.5 10.5 2 5.5"/><path class="hn" d="M8 12Q4.5 13.5 2 18.5"/><path class="hn" d="M16 12Q19.5 10.5 22 5.5"/><path class="hn" d="M16 12Q19.5 13.5 22 18.5"/></svg>';
const DOWN =
  '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 9l7 7 7-7"/></svg>';
/* "(edited)" on a post: tap it to see what the text said before. Without a post id (the Edit preview) it is plain text. */
function edtBtn(pid, lead) {
  if (!pid) return h("small", { class: "edt" }, lead + "(edited)");
  return h(
    "button",
    {
      type: "button",
      class: "edt edtb",
      title: "See earlier versions",
      "aria-label": "Edited. See earlier versions",
      onclick: (e) => {
        e.stopPropagation();
        editHist(pid);
      },
    },
    lead + "(edited)",
  );
}
function editHist(pid) {
  sheet("Edit history", (close) => {
    const box = h("div", { class: "form" }, h("p", { class: "hint" }, "Loading\u2026")),
      fmt = (t) => {
        const d = new Date(t * 1000),
          y = d.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined;
        return d.toLocaleString(undefined, { month: "short", day: "numeric", year: y, hour: "numeric", minute: "2-digit" });
      },
      item = (lab, t, cap, cur) =>
        h(
          "div",
          { class: "ehv" + (cur ? " cur" : "") },
          h("div", { class: "ehh" }, h("b", {}, lab), h("small", { class: "hint" }, fmt(t))),
          h("p", { class: "ehc" }, cap || "(no text)"),
        );
    api("pedhist", null, "&id=" + encodeURIComponent(pid))
      .then((r) => {
        const vs = r.v || [],
          kids = [item("Current version", r.cur.ts, r.cur.cap, 1)];
        if (vs.length) {
          vs.forEach((x) => kids.push(item(+x.ts === +r.ts0 ? "Original" : "Earlier version", x.ts, x.cap, 0)));
          kids.unshift(h("p", { class: "hint" }, "Newest first. Only the text is kept, not photos."));
        } else
          kids.push(
            h(
              "p",
              { class: "hint" },
              "No earlier text versions. The post was edited before history was kept, or only its photos or settings changed.",
            ),
          );
        if (+r.own && vs.length)
          kids.push(
            h(
              "button",
              {
                type: "button",
                class: "ghost",
                style: "margin-top:6px",
                onclick: async () => {
                  if (!(await cbox("Remove all earlier versions of this post? This can't be undone."))) return;
                  try {
                    await api("pedclear", fd({ id: pid }));
                    close();
                  } catch (e) {
                    box.append(h("p", { class: "err", role: "alert" }, (e && e.e) || "Could not remove them."));
                  }
                },
              },
              "Remove earlier versions",
            ),
          );
        rc(box, ...kids);
      })
      .catch((e) => rc(box, h("p", { class: "err", role: "alert" }, (e && e.e) || "Could not load the history.")));
    return box;
  });
}
function tbRender(tp, cap, ed, hg, pid) {
  const t = String(cap || "").trim(),
    m = t.match(/^(\S+)\s*([\s\S]*)$/);
  if (!m) {
    tp.classList.remove("huge");
    rc(tp);
    return;
  }
  /* "Huge text": a short text post is drawn as poster text that fills the card (same look as the profile grid tiles) */
  const bl = hg ? bigLines(t) : null;
  if (bl) {
    tp.classList.add("huge");
    rc(
      tp,
      h("span", { class: "gtb", "aria-hidden": "true" }, ...bl.map((x) => h("div", {}, x))),
      h("span", { style: "position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)" }, t),
      +ed ? edtBtn(pid, "") : null,
    );
    if (!tp._ro) {
      tp._ro = 1;
      if (window.ResizeObserver) new ResizeObserver(() => fitBig(tp)).observe(tp);
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => fitBig(tp));
    }
    requestAnimationFrame(() => fitBig(tp));
    return;
  }
  tp.classList.remove("huge");
  const w = m[1],
    n = [...w].length,
    fs = n <= 5 ? 4.4 : n <= 8 ? 3.3 : n <= 12 ? 2.4 : 1.7;
  rc(
    tp,
    h("div", { class: "tbig", style: "font-size:" + fs + "rem" }, linkify(w)),
    m[2] ? h("div", { class: "tsm" }, linkify(m[2])) : null,
    +ed ? edtBtn(pid, "") : null,
  );
}
const BGS = ["Soft", "Sunset", "Ocean", "Forest", "Grape", "Ink", "Paper", "Candy"];
/* Post views. A post counts as seen once most of it has been on screen for about a second (feed cards) or it has stayed open for a moment (live view). Each person counts once per post, your own posts do not count, and only the number is shown, never who looked. Sightings are sent in small batches. */
const VSEEN = new Set(),
  VQ = new Set();
let VT = 0;
function vfmt(n) {
  n = +n || 0;
  if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
  if (n >= 1e4) return Math.round(n / 1e3) + "K";
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
  return String(n);
}
function viewFlush() {
  clearTimeout(VT);
  VT = 0;
  if (!VQ.size || !M) return;
  const ids = [...VQ].slice(0, 12);
  ids.forEach((i) => VQ.delete(i));
  api("view", fd({ ids: ids.join(",") })).catch(() => {});
  if (VQ.size) VT = setTimeout(viewFlush, 1500);
}
/* true the first time this page session sees the post; the caller then bumps the shown number if this person had not been counted before */
function viewSeen(p) {
  if (!M || !p || +p.own || VSEEN.has(+p.id)) return false;
  VSEEN.add(+p.id);
  VQ.add(+p.id);
  if (!VT) VT = setTimeout(viewFlush, 4000);
  return true;
}
function viewBump(p, chip) {
  if (viewSeen(p) && !+p.vm) {
    p.vm = 1;
    p.vw = (+p.vw || 0) + 1;
    if (chip) chip.paint();
  }
}
addEventListener("visibilitychange", () => {
  if (document.hidden) viewFlush();
});
addEventListener("pagehide", viewFlush);
function vchip(p, cls) {
  const n = h("span", {}),
    c = h("span", { class: cls || "vwc", role: "img", hidden: "" }, ic("eye", 16), n);
  c.paint = () => {
    const k = +p.vw || 0;
    c.hidden = false;
    n.textContent = vfmt(k);
    c.setAttribute("aria-label", k + (k === 1 ? " view" : " views"));
    c.title = k + (k === 1 ? " view" : " views");
  };
  c.paint();
  return c;
}
const VIO =
  "IntersectionObserver" in window
    ? new IntersectionObserver(
        (es) =>
          es.forEach((e) => {
            const el = e.target,
              on = e.isIntersecting && (e.intersectionRatio >= 0.6 || e.intersectionRect.height >= innerHeight * 0.55);
            if (on && !el._vt) {
              el._vt = setTimeout(() => {
                el._vt = 0;
                if (el.isConnected && !document.hidden && el._vp) {
                  viewBump(el._vp, el._vc);
                  VIO.unobserve(el);
                }
              }, 1000);
            } else if (!on && el._vt) {
              clearTimeout(el._vt);
              el._vt = 0;
            }
          }),
        { threshold: [0.25, 0.6] },
      )
    : null;
function watchView(el, p, chip) {
  if (!VIO || !M || +p.own || VSEEN.has(+p.id)) return;
  el._vp = p;
  el._vc = chip;
  VIO.observe(el);
}
function card(p, open) {
  p.anon = +p.anon;
  const mine = !!+p.own,
    mm = !!(p.anon && mine && M && M.mask),
    who = p.anon ? (mine ? (mm ? M.mask.name : dn(p)) : "Masque") : dn(p);
  p.me = +p.me;
  p.n = +p.n;
  p.imgs = p.imgs && p.imgs.length ? p.imgs : p.img ? [p.img] : [];
  const lb = h("button", {
      class: "sig" + (p.me ? " on" : ""),
      "aria-pressed": !!p.me,
      "aria-label": "Mark with your sigil",
    }),
    cnt = h("span", {}, p.n),
    ico = h("span", { class: "ico" });
  ico.innerHTML = SIGIL;
  lb.append(ico, cnt);
  likeSw(lb);
  lb.onclick = async () => {
    try {
      await api("like", fd({ id: p.id, as: ASM && M.mask ? "mask" : null }));
      p.me = +!p.me;
      p.n += p.me ? 1 : -1;
      setN(cnt, p.n, p.me);
      if (p.me && +p.dv) {
        p.dv = 0;
        if (dvb) {
          dvb.classList.remove("on");
          dvb.setAttribute("aria-pressed", "false");
        }
      }
      lb.classList.toggle("on", !!p.me);
      lb.setAttribute("aria-pressed", !!p.me);
      ico.classList.remove("pop", "unp");
      void ico.offsetWidth;
      if (p.me) {
        ico.classList.add("pop");
        slam("Marked", art);
        laugh(art);
        buzz(lb);
      } else ico.classList.add("unp");
    } catch (x) {
      alert((x && x.e) || "Could not like.");
    }
  };
  const dvb =
    +p.mk && !mine
      ? h("button", {
          class: "sig dn" + (+p.dv ? " on" : ""),
          "aria-pressed": String(!!+p.dv),
          "aria-label": "Downvote this Masque post",
          title: "Downvote: takes a point off this Masque. Nobody is told who did it.",
        })
      : null;
  if (dvb) {
    const di = h("span", { class: "ico" });
    di.innerHTML = DOWN;
    dvb.append(di);
    dvb.onclick = async () => {
      try {
        await api("dislike", fd({ id: p.id }));
        p.dv = +!+p.dv;
        if (p.dv && +p.me) {
          p.me = 0;
          p.n = Math.max(0, +p.n - 1);
          setN(cnt, p.n, false);
          lb.classList.remove("on");
          lb.setAttribute("aria-pressed", "false");
        }
        dvb.classList.toggle("on", !!p.dv);
        di.classList.remove("dpop", "unp");
        void di.offsetWidth;
        di.classList.add(p.dv ? "dpop" : "unp");
        dvb.setAttribute("aria-pressed", String(!!p.dv));
      } catch (x) {
        alert((x && x.e) || "Could not downvote.");
      }
    };
  }
  p.cc = +p.cc;
  const cb = h("button", { "aria-expanded": "false", class: "cbt", title: "Comments" }),
    cl = () => {
      cb.replaceChildren(ic("comment", 18), ...(p.cc ? [h("span", {}, p.cc)] : []));
      cb.setAttribute("aria-label", "Comments" + (p.cc ? ", " + p.cc : ""));
    },
    panel = h("div", { class: "cmts", hidden: "" });
  cl();
  cb.onclick = () => {
    const o = panel.hidden;
    panel.hidden = !o;
    cb.setAttribute("aria-expanded", o);
    if (o) {
      comments(p, panel, cl);
      laugh(art);
    }
  };
  if (open) {
    panel.hidden = false;
    cb.setAttribute("aria-expanded", "true");
    comments(p, panel, cl);
  }
  const lk = shBtn(p, 18);
  const sv = h(
    "button",
    {
      class: "sav" + (+p.sv ? " on" : ""),
      "aria-pressed": String(!!+p.sv),
      "aria-label": +p.sv ? "Unsave post" : "Save post",
      title: +p.sv ? "Saved" : "Save for later",
    },
    ic("bookmark", 18),
  );
  sv.onclick = async () => {
    sv.disabled = true;
    try {
      const r = await api("save", fd({ id: p.id }));
      p.sv = +r.on;
      sv.classList.toggle("on", !!p.sv);
      sv.setAttribute("aria-pressed", String(!!p.sv));
      sv.setAttribute("aria-label", p.sv ? "Unsave post" : "Save post");
      sv.title = p.sv ? "Saved" : "Save for later";
      sv.classList.remove("pop");
      void sv.offsetWidth;
      if (p.sv) sv.classList.add("pop");
    } catch (x) {
      alert((x && x.e) || "Could not save.");
    }
    sv.disabled = false;
  };
  const vc = vchip(p),
    bar = h("div", { class: "bar" }, lb, dvb, cb, sv, lk, vc),
    capEl = h("p", { class: "cap" }),
    tp = p.img || (p.aq && !+p.pd) ? null : h("div", { class: "tpost", "data-bg": p.bg || "0" }),
    setCap = () => {
      if (tp) {
        capEl.hidden = true;
        tp.hidden = !p.cap;
        tbRender(tp, p.cap, p.ed, +p.hg, p.id);
      } else {
        capEl.hidden = !p.cap;
        rc(capEl, h("b", {}, who), linkify(p.cap), +p.ed ? edtBtn(p.id, " ") : null);
      }
    };
  setCap();
  const more = h(
    "button",
    {
      class: "more",
      "aria-label": "Post options",
      "aria-haspopup": "dialog",
      title: "More",
      onclick: () => postMenu(p, mine, setCap),
    },
    ic("more", 20),
  );
  /* double-tap (or double-click) a photo to mark the post; it only ever marks, never unmarks, and a sigil bursts out where you tapped */
  const dbl = (e) => {
    const r = art.getBoundingClientRect(),
      b = h("span", {
        class: "dtl",
        "aria-hidden": "true",
        style:
          "left:" +
          ((e && e.clientX != null ? e.clientX : r.left + r.width / 2) - r.left) +
          "px;top:" +
          ((e && e.clientY != null ? e.clientY : r.top + r.height / 2) - r.top) +
          "px",
      });
    b.innerHTML = SIGIL;
    art.append(b);
    setTimeout(() => b.remove(), 900);
    laugh(art);
    if (!p.me) lb.onclick();
  };
  const ptg = p.anon && !mine ? "" : mm ? "#/k/" + M.mask.name : "#/" + (+p.mk ? "k" : "u") + "/" + p.name,
    pav = () => {
      const a = p.anon ? (mine ? av(mm ? { avatar: M.mask.avatar } : p, 36) : av({}, 36)) : av(p, 36);
      if (ptg) {
        a.style.cursor = "pointer";
        a.setAttribute("role", "link");
        a.setAttribute("tabindex", "0");
        a.setAttribute("aria-label", "View profile of " + who);
        a.onclick = () => (location.hash = ptg);
        a.onkeydown = (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            location.hash = ptg;
          }
        };
      }
      return a;
    };
  const gEl = sensGal(p, gal(p.imgs, who, dbl, p.alts));
  const art = h(
    "article",
    { class: "post", "data-pid": p.id },
    h(
      "div",
      { class: "ph" },
      pav(),
      h(
        "b",
        p.anon && !mine
          ? { class: "anon" }
          : { onclick: () => (location.hash = mm ? "#/k/" + M.mask.name : "#/" + (+p.mk ? "k" : "u") + "/" + p.name) },
        who,
      ),
      p.anon && mine
        ? h("span", { class: "anontag", title: "Only you can see this was you" }, "Masque to others")
        : null,
      +p.pinned ? h("span", { class: "anontag", title: "Pinned to the profile" }, "Pinned") : null,
      +p.qp ? h("span", { class: "anontag", title: "Pinned answer" }, "Pinned") : null,
      +p.vis
        ? h(
            "span",
            {
              class: "anontag",
              title: +p.vis === 2 ? "Only you can see this post" : "Only your friends can see this post",
            },
            +p.vis === 2 ? "Only me" : "Friends",
          )
        : null,
      +p.hold
        ? h(
            "span",
            {
              class: "anontag",
              title: "Held back by the word filter. Only the author and admins can see it until an admin approves it.",
            },
            mine ? "Waiting for review" : "Held for review",
          )
        : null,
      +p.exp > 0 ? h("span", { class: "anontag", title: "This post deletes itself" }, "Gone in " + left(p.exp)) : null,
      h("small", { style: "cursor:pointer", onclick: () => (location.hash = "#/p/" + p.id) }, ago(p.ts)),
      p.anon || +p.mk ? h("span", { class: "lmst", title: "Masque post" }, lmAv(26)) : null,
      more,
    ),
    p.aq
      ? h(
          "div",
          { class: "qa" },
          h("small", {}, +p.pd > 0 ? "Prompt of the day" : "Anonymous question"),
          h("p", {}, p.aq),
        )
      : null,
    gEl,
    tp,
    bar,
    capEl,
    pollEl(p),
    panel,
  );
  /* tap the free space of a post (caption, header gaps, empty bar space, text posts) to open it. Photos, buttons, links, names, polls, comments and the like keep their own taps; selecting text does not open it. Not on the post's own page. */
  if (!open) {
    art.classList.add("tapopen");
    art.addEventListener("click", (e) => {
      const t = e.target;
      if (!(t instanceof Element) || e.defaultPrevented) return;
      if (t.closest("button,a,img,video,input,textarea,select,label,summary,b,small,[role=button],[contenteditable],form")) return;
      if ((gEl && gEl.contains(t)) || (panel && panel.contains && panel.contains(t))) return;
      const sel = window.getSelection && window.getSelection();
      if (sel && String(sel).length) return;
      location.hash = "#/p/" + p.id;
    });
  }
  watchView(art, p, vc);
  lpress(art, () => postHold(p, mine, setCap, { like: () => lb.onclick(), save: () => sv.onclick(), comments: () => cb.click() }), 'button,a,input,textarea,select,video,audio,label,form,.cmts,[class*="poll"]');
  return art;
}
/* sensitive photos: blurred (and not clickable) until the viewer taps; nothing is remembered, so it blurs again next time */
function sensGal(p, g) {
  if (!g || !+p.sens) return g;
  g.inert = true;
  const w = h("div", { class: "sens" }, g),
    by = +p.sens === 2 ? "A moderator marked this photo as sensitive" : "Marked as sensitive by the author";
  const b = h(
    "button",
    { type: "button", class: "sensov", "aria-label": "Sensitive photo. " + by + ". Tap to view" },
    h("b", {}, "Sensitive photo"),
    h("small", {}, by),
    h("span", { class: "sensgo" }, "Tap to view"),
  );
  b.onclick = () => {
    if (b.classList.contains("out")) return;
    g.inert = false;
    w.classList.add("shown");
    b.classList.add("out"); /* fades away while the photo un-blurs; removed once the fade ends */
    setTimeout(() => b.remove(), 500);
  };
  w.append(b);
  return w;
}
/* photo descriptions (alt text): a small "+ ALT" pill on each composer thumbnail opens this sheet */
function altSheet(it, done) {
  sheet("Photo description", (close) => {
    const t = h("textarea", {
        rows: 4,
        maxlength: 200,
        placeholder: "Describe what's in this photo…",
        "aria-label": "Photo description",
      }),
      c = h("p", { class: "hint cnt" }),
      sv = h("button", { class: "btn full", type: "button" }, "Save"),
      upd = () => {
        c.textContent = t.value.length + " / 200";
      };
    t.value = it.alt || "";
    t.oninput = upd;
    upd();
    sv.onclick = () => {
      it.alt = t.value.replace(/\s+/g, " ").trim();
      close();
      done();
    };
    return h(
      "div",
      { class: "form" },
      h("img", { class: "altprev", src: it.url, alt: "" }),
      h(
        "p",
        { class: "hint" },
        'Say what\'s in the photo, like "two dogs asleep on a grey couch". Screen readers read it out loud, and it shows under the photo in full view.',
      ),
      t,
      c,
      sv,
    );
  });
}
const altBtn = (it, i, redraw) =>
  h(
    "button",
    {
      type: "button",
      class: "palt-btn" + (it.alt ? " on" : ""),
      "aria-label": (it.alt ? "Edit description for photo " : "Add description for photo ") + (i + 1),
      onclick: () => altSheet(it, redraw),
    },
    it.alt ? "ALT \u2713" : "+ ALT",
  );
/* post photos: one photo is a plain image; 2+ become a "print stack" (a pile of photo prints: swipe the top one away or press Next, tap it to open the viewer at that photo, double-tap likes) */
function gal(L, who, onlike, A) {
  let tm = 0;
  const dd = (i) => (A && A[i]) || "";
  const tap = (e, i) => {
      if (!onlike) return open(i);
      if (tm) {
        clearTimeout(tm);
        tm = 0;
        onlike(e);
      } else
        tm = setTimeout(() => {
          tm = 0;
          open(i);
        }, 260);
    },
    open = (i) =>
      L.length > 1
        ? view("?img=" + L[i], "Photo " + (i + 1) + " of " + L.length + " by " + who, {
            list: L.map((q, j) => ({
              src: "?img=" + q,
              alt: dd(j) || "Photo " + (j + 1) + " of " + L.length + " by " + who,
              desc: dd(j),
            })),
            i,
          })
        : view("?img=" + L[i], dd(i) || "Photo by " + who, { desc: dd(i) }),
    one = (s, i) =>
      h("img", {
        class: "pimg",
        src: "?img=" + s,
        alt: dd(i) || (L.length > 1 ? "Photo " + (i + 1) + " of " + L.length : "Photo") + " by " + who,
        loading: "lazy",
        draggable: "false",
        tabindex: "0",
        role: "button",
        "aria-label": "View full photo",
        onload: (e) => e.target.classList.add("ld"),
        onerror: (e) => e.target.classList.add("ld"),
        onclick: (e) => tap(e, i),
        onkeydown: (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            open(i);
          }
        },
      });
  if (L.length < 2) return L.length ? one(L[0], 0) : null;
  const n = L.length,
    order = L.map((_, i) => i),
    calm = () => matchMedia("(prefers-reduced-motion:reduce)").matches;
  let busy = false,
    drag = -1,
    sx = 0,
    sy = 0,
    dx = 0,
    moved = false,
    t0 = 0;
  const cards = L.map((s, i) => {
      const c = h(
        "div",
        {
          class: "psc",
          tabindex: "-1",
          role: "button",
          "aria-label":
            "Photo " + (i + 1) + " of " + n + " by " + who + ". Press Enter to view full size, arrow keys to flip.",
        },
        h(
          "div",
          { class: "psi" },
          h("img", {
            src: "?img=" + s,
            alt: dd(i) || "Photo " + (i + 1) + " of " + n + " by " + who,
            loading: "lazy",
            draggable: "false",
          }),
        ),
        h(
          "div",
          { class: "psf", "aria-hidden": "true" },
          h("span", {}, "NO. " + String(i + 1).padStart(2, "0")),
          dd(i) ? h("span", { class: "psa" }, "ALT") : null,
        ),
      );
      c.onpointerdown = (e) => {
        if (order[0] !== i || busy || (e.pointerType === "mouse" && e.button !== 0)) return;
        drag = i;
        sx = e.clientX;
        sy = e.clientY;
        dx = 0;
        moved = false;
        t0 = Date.now();
        c.classList.add("drag");
        try {
          c.setPointerCapture(e.pointerId);
        } catch (_) {}
      };
      c.onpointermove = (e) => {
        if (drag !== i) return;
        dx = e.clientX - sx;
        const dy = e.clientY - sy;
        if (!moved && Math.abs(dx) > 8 && Math.abs(dx) > Math.abs(dy)) moved = true;
        if (moved) c.style.transform = "translate(" + dx + "px," + dy * 0.12 + "px) rotate(" + dx / 16 + "deg)";
      };
      c.onpointerup = (e) => {
        if (drag !== i) return;
        drag = -1;
        c.classList.remove("drag");
        if (moved) {
          const v = Math.abs(dx) / Math.max(1, Date.now() - t0);
          if (Math.abs(dx) > 70 || v > 0.5) fly(dx < 0 ? -1 : 1);
          else c.style.transform = "";
        } else tap(e, i);
      };
      c.onpointercancel = () => {
        if (drag !== i) return;
        drag = -1;
        c.classList.remove("drag");
        c.style.transform = "";
      };
      c.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open(i);
        } else if (e.key === "ArrowRight") {
          e.preventDefault();
          fly(-1);
        } else if (e.key === "ArrowLeft") {
          e.preventDefault();
          fly(1);
        }
      };
      return c;
    }),
    stage = h("div", { class: "pstk-st" }, ...cards),
    cnt = h("span", { class: "pstk-n", "aria-live": "polite" }),
    dots = h("span", { class: "pstk-dots", "aria-hidden": "true" }, ...L.map(() => h("i", {}))),
    nx = h(
      "button",
      { type: "button", class: "pstk-next", "aria-label": "Next photo", onclick: () => fly(-1) },
      "Next \u203a",
    ),
    wrap = h(
      "div",
      {
        class: "pstk",
        role: "group",
        "aria-label": n + " photos by " + who + ", stacked like prints. Swipe the top one away or press Next.",
      },
      stage,
      h("div", { class: "pstk-bar" }, cnt, dots, nx),
    );
  const paint = () => {
    order.forEach((ci, d) => {
      const c = cards[ci];
      c.dataset.d = Math.min(d, 4);
      c.style.zIndex = n - d;
      c.tabIndex = d === 0 ? 0 : -1;
      c.inert = d > 0;
    });
    cnt.textContent = String(order[0] + 1).padStart(2, "0") + " / " + String(n).padStart(2, "0");
    [...dots.children].forEach((x, j) => x.classList.toggle("on", j === order[0]));
  };
  function fly(dir) {
    if (busy) return;
    busy = true;
    const c = cards[order[0]],
      foc = document.activeElement === c;
    c.classList.add("fly");
    c.style.transform = "translate(" + dir * 125 + "%,-6%) rotate(" + dir * 18 + "deg)";
    c.style.opacity = "0";
    setTimeout(
      () => {
        order.push(order.shift());
        c.classList.add("snap");
        c.style.transform = "";
        c.style.opacity = "";
        paint();
        void c.offsetWidth;
        c.classList.remove("snap", "fly");
        busy = false;
        if (foc) cards[order[0]].focus({ preventScroll: true });
      },
      calm() ? 0 : 260,
    );
  }
  paint();
  return wrap;
}
function postRows(p, mine, setCap, close) {
    const row = (label, fn, cls) =>
      h(
        "button",
        {
          type: "button",
          class: "ghost mrow2" + (cls ? " " + cls : ""),
          onclick: () => {
            close();
            fn();
          },
        },
        label,
      );
    return [
      ...(mine
        ? [
            row("Edit post", () => editPost(p, setCap)),
            ...(p.aq && !+p.pd && !+p.mk
              ? [
                  row(+p.qp ? "Unpin answer" : "Pin answer to top", async () => {
                    try {
                      await api("qpin", fd({ id: p.id, on: +p.qp ? 0 : 1 }));
                      route();
                    } catch (x) {
                      alert(x.e || "Could not pin.");
                    }
                  }),
                ]
              : []),
            ...(!p.anon && !+p.mk && !+p.hold
              ? [
                  row(+M.pin === +p.id ? "Unpin from profile" : "Pin to profile", async () => {
                    try {
                      const on = +M.pin !== +p.id;
                      await api("pin", fd({ id: p.id, on: on ? 1 : 0 }));
                      M.pin = on ? p.id : 0;
                      route();
                    } catch (x) {
                      alert(x.e || "Could not pin.");
                    }
                  }),
                ]
              : []),
            ...(p.anon
              ? [
                  row("Reveal myself", async () => {
                    if (
                      await cbox(
                        "Reveal yourself on this post? Your name and photo will show on it and on your comments here, and it will appear on your profile. This can't be undone.",
                      )
                    ) {
                      try {
                        await api("unmask", fd({ id: p.id, confirm: 1 }));
                        route();
                      } catch (x) {
                        alert(x.e || "Could not reveal.");
                      }
                    }
                  }),
                ]
              : []),
            row(
              "Delete post",
              async () => {
                if (await cbox("Delete this post?")) {
                  try {
                    await api("del", fd({ id: p.id }));
                    if (location.hash.startsWith("#/p/")) location.hash = "#/";
                    else {
                      await collapse(document.querySelector('.post[data-pid="' + p.id + '"]'));
                      route();
                    }
                  } catch (x) {
                    alert(x.e || "Could not delete.");
                  }
                }
              },
              "dng",
            ),
          ]
        : [
            row("Report post", () => reportSheet("post", p.id)),
            ...(M.admin
              ? [
                  row(
                    "Delete post (admin)",
                    async () => {
                      if (await cbox("Delete this post? You are deleting someone else\u2019s post as an admin. It is written to the admin log.")) {
                        try {
                          await api("del", fd({ id: p.id }));
                          if (location.hash.startsWith("#/p/")) location.hash = "#/";
                          else {
                            await collapse(document.querySelector('.post[data-pid="' + p.id + '"]'));
                            route();
                          }
                        } catch (x) {
                          alert(x.e || "Could not delete.");
                        }
                      }
                    },
                    "dng",
                  ),
                ]
              : []),
          ]),
    ];
}
function postMenu(p, mine, setCap) {
  sheet("Post options", (close) => h("div", { class: "form" }, ...postRows(p, mine, setCap, close)));
}
/* ===================== Sending posts to friends and groups =====================
   The share button on a post (feed card and the full-screen viewer): tap opens "Send to" with your friends and groups, hold shows your most recent chats right above the button, slide your finger (or mouse) onto one and let go to send it. A post goes out as its link, so the chat shows the same preview card as any Masque link. Whoever you sent to last comes first, in both places. */
const SHK = "mq-shr1";
const shRecent = () => {
  try {
    const a = JSON.parse(localStorage.getItem(SHK) || "[]");
    return Array.isArray(a) ? a.filter((x) => x && (x.k === "u" || x.k === "g") && x.id != null).slice(0, 12) : [];
  } catch (e) {
    return [];
  }
};
const shNote = (t) => {
  try {
    const a = shRecent().filter((x) => !(x.k === t.k && String(x.id).toLowerCase() === String(t.id).toLowerCase()));
    a.unshift({ k: t.k, id: t.id });
    localStorage.setItem(SHK, JSON.stringify(a.slice(0, 12)));
    if (SHC) shSort(SHC);
  } catch (e) {}
};
const shSort = (all) => {
  const rec = shRecent(),
    pos = (t) => {
      const i = rec.findIndex((r) => r.k === t.k && String(r.id).toLowerCase() === String(t.id).toLowerCase());
      return i < 0 ? 99 : i;
    };
  all.sort((a, b) => pos(a) - pos(b) || b.ts - a.ts || String(a.name).toLowerCase().localeCompare(String(b.name).toLowerCase()));
  return all;
};
let SHC = null,
  SHT = 0,
  SHP = null;
/* friends and groups you can send to: most recently sent-to first, then most recently chatted, then the rest A to Z */
const shTargets = (force) => {
  if (!force && SHC && Date.now() - SHT < 60000) return Promise.resolve(SHC);
  if (SHP) return SHP;
  SHP = Promise.all([
    api("friends").then((r) => r.list || []).catch(() => []),
    api("inbox").then((r) => r.chats || []).catch(() => []),
    api("ginbox").then((r) => r.groups || []).catch(() => []),
  ])
    .then(([fr, ch, gr]) => {
      const last = new Map();
      ch.forEach((c) => {
        if (!+c.ms && !+c.mk) last.set(String(c.name).toLowerCase(), +c.ts || 0);
      });
      const us = fr.filter((x) => +x.st === 1).map((x) => ({ k: "u", id: x.name, name: x.nick || x.name, handle: x.name, avatar: x.avatar, ts: last.get(String(x.name).toLowerCase()) || 0 })),
        gs = gr.map((g) => ({ k: "g", id: g.id, name: g.name, avatar: g.avatar, ts: +g.ts || 0 }));
      SHC = shSort([...us, ...gs]);
      SHT = Date.now();
      return SHC;
    })
    .finally(() => {
      SHP = null;
    });
  return SHP;
};
const shLink = (p) => location.origin + BASE + "p/" + p.id;
const shAv = (t, n) => (t.k === "g" ? gva(t, n) : av({ avatar: t.avatar }, n));
async function shSend(t, p) {
  if (+p.vis === 2) throw { e: "This post is set to Only me, so nobody else can open it. Change who can see it first." };
  const d = new FormData();
  d.append("txt", shLink(p));
  if (t.k === "g") {
    d.append("gid", t.id);
    await api("gsend", d);
  } else {
    d.append("to", t.id);
    await api("send", d);
  }
  shNote(t);
  try {
    SFX.play("send");
  } catch (e) {}
}
async function shCopy(p) {
  const l = shLink(p);
  try {
    await navigator.clipboard.writeText(l);
    slam("Link copied");
  } catch (e) {
    prompt("Copy this link", l);
  }
}
function shareSheet(p) {
  if (+p.vis === 2) {
    sheet("Only you can see this post", () =>
      h(
        "div",
        { class: "form shf" },
        h("p", { class: "hint" }, "This post is set to Only me, so a link to it won\u2019t open for anyone else. To share it, edit the post and change it to Friends or Everyone first."),
      ),
    );
    return;
  }
  sheet("Send to", (close) => {
    const sel = new Map(),
      key = (t) => t.k + ":" + t.id,
      err = h("p", { class: "err", role: "alert" }),
      grid = h("div", { class: "shg" }, h("p", { class: "hint shn" }, "Loading\u2026")),
      q = h("input", { type: "search", class: "shsr", placeholder: "Search friends and groups", "aria-label": "Search friends and groups", autocomplete: "off" }),
      go = h("button", { class: "btn full", type: "button", disabled: "" }, "Send");
    let all = [];
    const paintGo = () => {
      go.disabled = !sel.size;
      go.textContent = sel.size ? "Send to " + sel.size : "Send";
    };
    const draw = () => {
      const s = q.value.trim().toLowerCase(),
        l = s ? all.filter((t) => (t.name + " " + (t.handle || "")).toLowerCase().includes(s)) : all;
      rc(
        grid,
        l.length
          ? l.map((t) => {
              const on = sel.has(key(t)),
                b = h("button", { type: "button", class: "sht" + (on ? " on" : ""), "aria-pressed": String(on) }, h("span", { class: "sha" }, shAv(t, 54), h("i", { class: "shk" }, ic("check", 14))), h("b", {}, t.name), t.k === "g" ? h("small", {}, "Group") : null);
              b.onclick = () => {
                if (sel.has(key(t))) sel.delete(key(t));
                else sel.set(key(t), t);
                b.classList.toggle("on", sel.has(key(t)));
                b.setAttribute("aria-pressed", String(sel.has(key(t))));
                paintGo();
              };
              return b;
            })
          : [h("p", { class: "hint shn" }, all.length ? "No match." : "No friends or groups to send to yet. Add friends or start a group, or copy the link below.")],
      );
    };
    q.oninput = draw;
    shTargets().then((l) => {
      all = l;
      draw();
    });
    go.onclick = async () => {
      err.textContent = "";
      go.disabled = true;
      const bad = [];
      for (const t of [...sel.values()]) {
        try {
          await shSend(t, p);
          sel.delete(key(t));
        } catch (x) {
          bad.push(t.name + ": " + ((x && x.e) || "could not send"));
        }
      }
      if (!bad.length) {
        close();
        slam("Sent");
        return;
      }
      err.textContent = bad.join(". ");
      draw();
      paintGo();
    };
    return h(
      "div",
      { class: "form shf" },
      +p.vis === 1 ? h("p", { class: "hint" }, "Friends-only post: the link only opens for your friends.") : null,
      q,
      grid,
      err,
      go,
      h(
        "div",
        { class: "shr" },
        h("button", { type: "button", class: "ghost", onclick: () => shCopy(p) }, ic("link", 16), " Copy link"),
        navigator.share
          ? h(
              "button",
              {
                type: "button",
                class: "ghost",
                onclick: async () => {
                  try {
                    await navigator.share({ title: "Post on Masque", url: shLink(p) });
                  } catch (e) {}
                },
              },
              ic("share", 16),
              " Share elsewhere",
            )
          : null,
      ),
    );
  });
}
/* the share button: tap = the sheet, hold = your latest chats pop up above it; slide onto one and let go to send */
function shBtn(p, size, cls) {
  const b = h("button", { type: "button", class: "shb" + (cls ? " " + cls : ""), "aria-label": "Send post", "aria-haspopup": "dialog", title: "Send to friends. Hold for your latest chats" }, ic("share", size));
  let t = 0,
    fired = 0,
    down = 0,
    sx = 0,
    sy = 0,
    pop = null,
    hot = null,
    tops = [];
  const closePop = () => {
    const k = pop;
    pop = null;
    hot = null;
    if (!k) return;
    k.classList.add("out");
    setTimeout(() => k.remove(), 170);
  };
  const setHot = (el) => {
    if (hot === el) return;
    if (hot) hot.classList.remove("hot");
    hot = el;
    if (el) {
      el.classList.add("hot");
      try {
        navigator.vibrate && navigator.vibrate(6);
      } catch (e) {}
    }
  };
  const open = async () => {
    t = 0;
    fired = 1;
    try {
      navigator.vibrate && navigator.vibrate(12);
    } catch (e) {}
    let list = [];
    try {
      list = await shTargets();
    } catch (e) {}
    if (!b.isConnected) return;
    if (!down || !list.length) {
      down = 0;
      shareSheet(p);
      return;
    }
    tops = list.slice(0, innerWidth < 440 ? 4 : 5);
    pop = h(
      "div",
      { class: "shq", role: "menu", "aria-label": "Send to" },
      h("small", {}, "Slide to a chat and let go"),
      h(
        "div",
        { class: "shqr" },
        ...tops.map((x, i) => h("div", { class: "shqt", role: "menuitem", "data-i": String(i), style: "--d:" + i * 40 + "ms" }, shAv(x, 52), h("b", {}, x.name))),
        h("div", { class: "shqt more", role: "menuitem", "data-more": "1", style: "--d:" + tops.length * 40 + "ms" }, h("span", { class: "shqm" }, ic("more", 22)), h("b", {}, "More")),
      ),
    );
    document.body.append(pop);
    const r = b.getBoundingClientRect(),
      w = pop.offsetWidth,
      ph = pop.offsetHeight;
    let top = r.top - ph - 12;
    if (top < 8) top = Math.min(innerHeight - ph - 8, r.bottom + 12);
    pop.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.right - w)) + "px";
    pop.style.top = top + "px";
  };
  const hit = (e) => {
    const el = document.elementFromPoint(e.clientX, e.clientY);
    return el && el.closest ? el.closest(".shq .shqt") : null;
  };
  b.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button) return;
    fired = 0;
    down = 1;
    sx = e.clientX;
    sy = e.clientY;
    clearTimeout(t);
    shTargets().catch(() => {});
    try {
      b.setPointerCapture(e.pointerId);
    } catch (x) {}
    t = setTimeout(open, 340);
  });
  b.addEventListener("pointermove", (e) => {
    if (t && Math.hypot(e.clientX - sx, e.clientY - sy) > 12) {
      clearTimeout(t);
      t = 0;
    }
    if (pop) setHot(hit(e));
  });
  const up = (e, cancel) => {
    clearTimeout(t);
    t = 0;
    down = 0;
    if (!pop) return;
    const k = cancel ? null : hit(e) || hot;
    if (!k) {
      closePop();
      return;
    }
    if (k.dataset.more) {
      closePop();
      shareSheet(p);
      return;
    }
    const to = tops[+k.dataset.i];
    pop.classList.add("pick");
    k.classList.add("hot", "go");
    const k0 = pop;
    shSend(to, p).then(
      () => {
        k.classList.add("done");
        k.lastChild.textContent = "Sent";
        setTimeout(() => {
          if (pop === k0) closePop();
        }, 800);
      },
      (x) => {
        closePop();
        alert((x && x.e) || "Could not send.");
      },
    );
  };
  b.addEventListener("pointerup", (e) => up(e, false));
  b.addEventListener("pointercancel", (e) => up(e, true));
  b.addEventListener("contextmenu", (e) => e.preventDefault());
  b.addEventListener(
    "click",
    (e) => {
      if (fired) {
        fired = 0;
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    },
    true,
  );
  b.addEventListener("click", () => shareSheet(p));
  return b;
}
/* hold (or right-click) a post anywhere: quick actions plus everything from its "..." menu. a = { like, save, comments } so the post on screen updates too. */
async function postHold(p0, mine, setCap, a) {
  let p = p0;
  if (p.me === undefined || p.sv === undefined) {
    try {
      const r = await api("feed", null, "&id=" + p0.id);
      if (r.posts && r.posts[0]) p = r.posts[0];
    } catch (e) {}
  }
  const anon = +p.anon,
    mm = !!(anon && mine && M && M.mask),
    who = anon ? (mine ? (mm ? M.mask.name : dn(p)) : "Masque") : dn(p),
    ptg = anon && !mine ? "" : mm ? "#/k/" + M.mask.name : "#/" + (+p.mk ? "k" : "u") + "/" + p.name;
  sheet("Post", (close) => {
    const done = (fn) => () => {
      close();
      fn();
    };
    const sg = h("span", { class: "ico" });
    sg.innerHTML = SIGIL.replace('width="22" height="22"', 'width="24" height="24"');
    const q = (label, icon, fn, on) => h("button", { type: "button", class: "phb" + (on ? " on" : ""), onclick: done(fn) }, icon, h("b", {}, label)),
      row = (label, icon, fn) => h("button", { type: "button", class: "ghost mrow2 phr", onclick: done(fn) }, icon, h("span", {}, label)),
      like = async () => {
        if (a && a.like) return a.like();
        try {
          await api("like", fd({ id: p.id, as: ASM && M.mask ? "mask" : null }));
        } catch (x) {
          alert((x && x.e) || "Could not like.");
        }
      },
      save = async () => {
        if (a && a.save) return a.save();
        try {
          const r = await api("save", fd({ id: p.id }));
          slam(+r.on ? "Saved" : "Removed");
        } catch (x) {
          alert((x && x.e) || "Could not save.");
        }
      },
      here = location.hash === "#/p/" + p.id;
    return h(
      "div",
      { class: "form phf" },
      h("p", { class: "hint phs" }, who + (p.cap ? ": " + String(p.cap).replace(/\s+/g, " ").slice(0, 90) : "")),
      h(
        "div",
        { class: "phq" },
        q("Send", ic("share", 24), () => shareSheet(p)),
        q(+p.me ? "Unmark" : "Mark", sg, like, +p.me),
        q(+p.sv ? "Unsave" : "Save", ic("bookmark", 24), save, +p.sv),
        q("Comments", ic("comment", 24), () => (a && a.comments ? a.comments() : (location.hash = "#/p/" + p.id))),
      ),
      row("Copy link", ic("link", 18), () => shCopy(p)),
      navigator.share
        ? row("Share outside Masque", ic("share", 18), async () => {
            if (+p.vis === 2) {
              alert("This post is set to Only me, so a link to it won\u2019t open for anyone else.");
              return;
            }
            try {
              await navigator.share({ title: "Post on Masque", url: shLink(p) });
            } catch (e) {}
          })
        : null,
      p.cap
        ? row("Copy text", ic("clip", 18), async () => {
            try {
              await navigator.clipboard.writeText(String(p.cap));
              slam("Copied");
            } catch (e) {
              prompt("Copy this text", String(p.cap));
            }
          })
        : null,
      here ? null : row("Open post", ic("eye", 18), () => (location.hash = "#/p/" + p.id)),
      ptg ? row("View " + (mm ? "Masque" : "profile"), ic("users", 18), () => (location.hash = ptg)) : null,
      ...postRows(p, mine, setCap || (() => {}), close),
    );
  });
}
async function comments(p, panel, cl) {
  const list = h("div", { class: "clist" }),
    err = h("p", { class: "err", role: "alert" }),
    inp = h("input", { placeholder: "Add a comment…", maxlength: 300, "aria-label": "Add a comment" }),
    go = h("button", { class: "btn", type: "submit" }, "Send");
  go.disabled = true;
  inp.addEventListener("input", () => {
    go.disabled = !inp.value.trim();
  });
  const f = h(
    "form",
    {
      class: "cform",
      onsubmit: async (e) => {
        e.preventDefault();
        if (!inp.value.trim()) return;
        go.disabled = true;
        err.textContent = "";
        try {
          await api("comment", fd({ pid: p.id, txt: inp.value, as: ASM && M.mask ? "mask" : null }));
          inp.value = "";
          await load();
          list.scrollTop = list.scrollHeight;
          laugh(list.closest(".post"));
        } catch (x) {
          err.textContent = x.e || "Could not send.";
        }
        go.disabled = !inp.value.trim();
        inp.focus();
      },
    },
    maskSw(p, inp, "Comment"),
    inp,
    go,
  );
  panel.replaceChildren(list, err, f);
  mentionPick(inp, mentionPeople);
  async function load() {
    let r;
    try {
      r = await api("comments", null, "&pid=" + p.id);
    } catch (x) {
      list.replaceChildren(h("p", { class: "hint" }, x.e || "Could not load comments."));
      return;
    }
    p.cc = r.comments.length;
    cl();
    const kids = {};
    r.comments.forEach((c) => {
      if (+c.par) (kids[c.par] ??= []).push(c);
    });
    const tops = r.comments.filter((c) => !+c.par),
      SN = load.sn || (load.sn = new Set()),
      ini = !SN.size;
    list.replaceChildren(
      ...(tops.length
        ? tops.map((c, ti) => {
            const reps = h("div", { class: "rep" }),
              wrap = h("div", { class: "cthread" }),
              ask = (x) => replyForm(c, wrap, +x.par && !+x.mine ? "@" + x.name + " " : "");
            (kids[c.id] || []).forEach((k) => {
              const e = cmt(k, r.owner, load, ask);
              if (!ini && !SN.has(+k.id) && SN.has(+c.id)) e.classList.add("enter");
              reps.append(e);
            });
            wrap.append(cmt(c, r.owner, load, ask));
            if (reps.children.length) {
              wrap.classList.add("hasrep");
              const nrp = reps.children.length,
                tg = h(
                  "button",
                  { type: "button", class: "rtog", "aria-expanded": "true" },
                  "Hide replies (" + nrp + ")",
                );
              tg.onclick = () => {
                const hd = (reps.hidden = !reps.hidden);
                tg.textContent = (hd ? "Show" : "Hide") + " replies (" + nrp + ")";
                tg.setAttribute("aria-expanded", String(!hd));
                wrap.classList.toggle("collapsed", hd);
              };
              wrap.append(tg, reps);
            }
            if (!SN.has(+c.id)) {
              wrap.classList.add("enter");
              if (ini) wrap.style.setProperty("--i", Math.min(ti, 6));
            }
            return wrap;
          })
        : [h("p", { class: "hint" }, "No comments yet.")]),
    );
    r.comments.forEach((c) => SN.add(+c.id));
    if (+r.hid)
      list.append(
        h(
          "p",
          { class: "hint muted-note" },
          r.hid +
            (r.hid == 1 ? " comment is" : " comments are") +
            " hidden by your mutes. You can change this in Settings.",
        ),
      );
  }
  function replyForm(c, box, pre) {
    const old = box.querySelector(".rf");
    if (old) {
      const o = old.querySelector("input");
      o.value = pre || o.value;
      o.focus();
      return;
    }
    const i = h("input", { placeholder: "Write a reply…", maxlength: 300, "aria-label": "Reply", value: pre || "" }),
      e2 = h("p", { class: "err", role: "alert" }),
      b = h("button", { class: "btn", type: "submit" }, "Send"),
      f2 = h(
        "form",
        {
          class: "cform rf",
          onsubmit: async (e) => {
            e.preventDefault();
            if (!i.value.trim()) return;
            b.disabled = true;
            e2.textContent = "";
            try {
              await api("comment", fd({ pid: p.id, txt: i.value, par: c.id, as: ASM && M.mask ? "mask" : null }));
              await load();
            } catch (x) {
              e2.textContent = x.e || "Could not send.";
              b.disabled = false;
            }
          },
        },
        maskSw(p, i, "Reply"),
        i,
        b,
        h(
          "button",
          {
            class: "ghost",
            type: "button",
            onclick: () => {
              f2.remove();
              e2.remove();
            },
          },
          "Cancel",
        ),
      );
    box.append(f2, e2);
    mentionPick(i, mentionPeople);
    i.focus({ preventScroll: true });
    i.setSelectionRange(i.value.length, i.value.length);
    /* keep the reply row clear of the bottom dock (the dock also tucks away while you type, see style.css) */
    requestAnimationFrame(() => f2.scrollIntoView({ block: "center", behavior: "auto" }));
  }
  await load();
}
function cmt(c, owner, reload, onReply) {
  const body = h("div", { class: "ct" }),
    pl = +c.mk ? "#/k/" + c.name : c.name ? "#/u/" + c.name : "",
    show = () => {
      rc(
        body,
        h(
          "div",
          { class: "cn" },
          h(
            "b",
            pl
              ? {
                  class: "lnk",
                  role: "link",
                  tabindex: "0",
                  onclick: () => (location.hash = pl),
                  onkeydown: (e) => {
                    if (e.key === "Enter") location.hash = pl;
                  },
                }
              : {},
            dn(c) || "Masque",
          ),
          !c.name || +c.mk ? h("span", { class: "cmlm", title: "Masque" }, lmIcon(13)) : null,
        ),
        h("p", { class: "ctx" }, linkify(c.txt), +c.ed ? h("small", { class: "edt" }, " (edited)") : null),
      );
    };
  show();
  const acts = h("span", { class: "ca" }),
    lk = h("button", {
      class: "clk" + (+c.lk ? " on" : ""),
      "aria-pressed": !!+c.lk,
      "aria-label": "Mark comment with your sigil",
    }),
    lc = h("span", {}, +c.n || ""),
    li = h("span", { class: "ico" });
  li.innerHTML = SIGIL.replace('width="22" height="22"', 'width="15" height="15"');
  lk.append(li, lc);
  likeSw(lk);
  lk.onclick = async () => {
    try {
      await api("clike", fd({ id: c.id, as: ASM && M.mask ? "mask" : null }));
      c.lk = +!+c.lk;
      c.n = (+c.n || 0) + (c.lk ? 1 : -1);
      setN(lc, c.n || "", c.lk);
      li.classList.remove("pop", "unp");
      void li.offsetWidth;
      li.classList.add(c.lk ? "pop" : "unp");
      lk.classList.toggle("on", !!c.lk);
      lk.setAttribute("aria-pressed", !!c.lk);
      if (c.lk && +c.dv) {
        c.dv = 0;
        const d0 = acts.querySelector(".dn");
        if (d0) {
          d0.classList.remove("on");
          d0.setAttribute("aria-pressed", "false");
        }
      }
    } catch (e) {}
  };
  acts.append(lk);
  if (+c.mk && !+c.mine) {
    const dv = h("button", {
        class: "clk dn" + (+c.dv ? " on" : ""),
        "aria-pressed": String(!!+c.dv),
        "aria-label": "Downvote this Masque comment",
        title: "Downvote: takes a point off this Masque. Nobody is told who did it.",
      }),
      di = h("span", { class: "ico" });
    di.innerHTML = DOWN.replace('width="22" height="22"', 'width="15" height="15"');
    dv.append(di);
    dv.onclick = async () => {
      try {
        await api("cdislike", fd({ id: c.id }));
        c.dv = +!+c.dv;
        if (c.dv && +c.lk) {
          c.lk = 0;
          c.n = Math.max(0, (+c.n || 0) - 1);
          setN(lc, c.n || "", false);
          lk.classList.remove("on");
          lk.setAttribute("aria-pressed", "false");
        }
        dv.classList.toggle("on", !!c.dv);
        di.classList.remove("dpop", "unp");
        void di.offsetWidth;
        di.classList.add(c.dv ? "dpop" : "unp");
        dv.setAttribute("aria-pressed", String(!!c.dv));
      } catch (x) {
        alert((x && x.e) || "Could not downvote.");
      }
    };
    acts.append(dv);
  }
  if (onReply) acts.append(h("button", { onclick: () => onReply(c) }, "Reply"));
  const cav = av(c, 28);
  if (pl) {
    cav.style.cursor = "pointer";
    cav.onclick = () => (location.hash = pl);
  }
  const bub = h("div", { class: "cbub" }, body),
    row = h(
      "div",
      { class: "cm" },
      cav,
      h(
        "div",
        { class: "cb" },
        bub,
        h(
          "div",
          { class: "cmeta" },
          h(
            "small",
            { class: "hint" },
            ago(c.ts) +
              (+c.hold
                ? +c.mine
                  ? " \u00b7 Waiting for review (only you and admins can see it)"
                  : " \u00b7 Held for review"
                : ""),
          ),
          acts,
        ),
      ),
    );
  const editIt = () => {
      const i = h("input", { value: c.txt, maxlength: 300, "aria-label": "Edit comment" }),
        e2 = h("span", { class: "err" });
      const save = async () => {
        try {
          const r = await api("editc", fd({ id: c.id, txt: i.value }));
          c.txt = r.txt;
          c.ed = r.ed;
          bub.hidden = false;
          f2.remove();
          show();
        } catch (x) {
          e2.textContent = x.e || "Could not save.";
        }
      };
      const f2 = h(
        "form",
        {
          class: "cform",
          onsubmit: (e) => {
            e.preventDefault();
            save();
          },
        },
        i,
        h("button", { class: "btn", type: "submit" }, "Save"),
        h(
          "button",
          {
            class: "ghost",
            type: "button",
            onclick: () => {
              bub.hidden = false;
              f2.remove();
            },
          },
          "Cancel",
        ),
      );
      bub.hidden = true;
      bub.after(f2);
      i.focus();
    },
    delIt = async () => {
      if (await cbox("Delete this comment?")) {
        try {
          await api("delc", fd({ id: c.id }));
        } catch (x) {
          alert((x && x.e) || "Could not delete.");
          return;
        }
        await collapse(row);
        reload();
      }
    };
  /* edit / report / delete live behind a three-dot button on the comment */
  const items = [];
  if (+c.mine) items.push(["Edit", editIt]);
  if (!+c.mine) items.push(["Report", () => reportSheet("comment", c.id)]);
  if (owner && !+c.mine)
    items.push([
      "Mute this person",
      async () => {
        if (
          await cbox(
            "Mute " +
              (dn(c) || "this person") +
              "? Their comments on your posts will be hidden from you, and you won\u2019t get notifications from them. They are not told. You can undo this in Settings.",
          )
        ) {
          try {
            await api("mutec", fd({ id: c.id }));
            await collapse(row);
            reload();
          } catch (x) {
            alert((x && x.e) || "Could not mute.");
          }
        }
      },
    ]);
  if (+c.mine || owner || M.admin) items.push([+c.mine || owner ? "Delete" : "Delete (admin)", delIt, "dng"]);
  bub.append(
    h(
      "button",
      {
        type: "button",
        class: "cmore",
        "aria-label": "Comment options",
        "aria-haspopup": "dialog",
        title: "More",
        onclick: () =>
          sheet("Comment options", (close) =>
            h(
              "div",
              { class: "form" },
              ...items.map(([l, fn, kc]) =>
                h(
                  "button",
                  {
                    type: "button",
                    class: "ghost mrow2" + (kc ? " " + kc : ""),
                    onclick: () => {
                      close();
                      fn();
                    },
                  },
                  l,
                ),
              ),
            ),
          ),
      },
      ic("more", 18),
    ),
  );
  return row;
}
/* drag a photo thumbnail onto another to reorder (shared by New post and Edit post); mv(from,to) changes the list, rd() redraws */
function pdrag(t, i, grid, mv, rd) {
  let sx = 0,
    sy = 0,
    on = false,
    id = null,
    over = -1;
  const kids = () => [...grid.children],
    hit = (x, y) => {
      let r = -1;
      kids().forEach((k, j) => {
        if (j === i) return;
        const b = k.getBoundingClientRect();
        if (x >= b.left && x <= b.right && y >= b.top && y <= b.bottom) r = j;
      });
      return r;
    };
  t.addEventListener("pointerdown", (e) => {
    if (e.target.closest("button") || (e.pointerType === "mouse" && e.button)) return;
    id = e.pointerId;
    sx = e.clientX;
    sy = e.clientY;
    on = false;
    over = -1;
    try {
      t.setPointerCapture(id);
    } catch (_) {}
  });
  t.addEventListener("pointermove", (e) => {
    if (e.pointerId !== id) return;
    const dx = e.clientX - sx,
      dy = e.clientY - sy;
    if (!on) {
      if (Math.hypot(dx, dy) < 8) return;
      on = true;
      t.classList.add("drag");
    }
    t.style.transform = "translate(" + dx + "px," + dy + "px) scale(1.06)";
    const o = hit(e.clientX, e.clientY);
    if (o !== over) {
      kids().forEach((k, j) => k.classList.toggle("over", j === o));
      over = o;
    }
  });
  const end = (e) => {
    if (e.pointerId !== id) return;
    id = null;
    if (!on) return;
    on = false;
    t.classList.remove("drag");
    t.style.transform = "";
    kids().forEach((k) => k.classList.remove("over"));
    if (e.type === "pointerup" && over > -1 && over !== i) {
      mv(i, over);
    }
    rd();
  };
  t.addEventListener("pointerup", end);
  t.addEventListener("pointercancel", end);
  t.addEventListener("contextmenu", (e) => {
    if (on) e.preventDefault();
  });
}
function editPost(p, done) {
  sheet("Edit post", (close) => {
    const oldV = +p.vis || 0,
      VP = visPick(oldV),
      MAXI = 10,
      had = p.imgs && p.imgs.length ? p.imgs : p.img ? [p.img] : [],
      orig = had.join("|");
    if (p.anon || +p.mk) VP.noFriends(true);
    let L = had.map((n, i) => ({ name: n, url: "?img=" + n, alt: (p.alts && p.alts[i]) || "" })),
      Q = Promise.resolve();
    const origA = L.map((x) => x.alt).join("\u0001");
    const cap = h("textarea", { rows: 4, maxlength: 300, "aria-label": "Caption" }),
      cnt = h("p", { class: "hint cnt" }),
      err = h("p", { class: "err", role: "alert" }),
      btn = h("button", { class: "btn full", type: "submit" }, "Save");
    cap.value = p.cap || "";
    const upd = () => {
      cnt.textContent = cap.value.length + " / 300";
      cnt.classList.toggle("warn", cap.value.length >= 270);
      btn.disabled = !L.length && !cap.value.trim();
      sbox.hidden = !L.length;
    };
    const oldS = +p.sens || 0,
      sn = h("input", { type: "checkbox" }),
      sbox = h(
        "div",
        {},
        oldS === 2
          ? h("p", { class: "hint" }, "A moderator marked this photo as sensitive. It stays blurred.")
          : h(
              "label",
              { class: "chk anonrow" },
              sn,
              h(
                "span",
                {},
                h("b", {}, "Sensitive photo"),
                h("small", { class: "hint" }, "Blurs the photo until someone taps it."),
              ),
            ),
      );
    sn.checked = oldS === 1;
    cap.oninput = upd;
    mentionPick(cap, mentionPeople, true);
    /* photo manager (only for posts that have photos): add, remove, drag to reorder, tap "Set cover" to move one to the front */
    const grid = h("div", { class: "pgrid pedit", hidden: "" }),
      inp = h("input", { type: "file", accept: "image/*", multiple: "", hidden: "", "aria-label": "Photos" }),
      z = h("button", { type: "button", class: "drop" }, "");
    const qprep = (f) => {
      const rd = readable(f);
      rd.catch(() => {});
      const q = Q.then(async () => shrink(await rd));
      Q = q.catch(() => {});
      return q;
    };
    const gone = (it) => {
      if (it.blob) URL.revokeObjectURL(it.url);
    };
    const draw = () => {
      grid.replaceChildren(
        ...L.map((it, i) => {
          const t = h(
            "div",
            {
              class: "pthumb",
              role: "group",
              "aria-label": "Photo " + (i + 1) + " of " + L.length + ". Drag to reorder.",
            },
            h("img", { src: it.url, alt: "Photo " + (i + 1) }),
            i === 0
              ? h("span", { class: "pcov" }, "Cover")
              : h(
                  "button",
                  {
                    type: "button",
                    class: "pset",
                    "aria-label": "Make photo " + (i + 1) + " the cover",
                    onclick: () => {
                      L.unshift(L.splice(i, 1)[0]);
                      draw();
                    },
                  },
                  "Set cover",
                ),
            altBtn(it, i, draw),
            h(
              "button",
              {
                type: "button",
                "aria-label": "Remove photo " + (i + 1),
                onclick: () => {
                  gone(it);
                  L.splice(i, 1);
                  draw();
                  upd();
                },
              },
              ic("close", 14),
            ),
          );
          pdrag(t, i, grid, (x, y) => L.splice(y, 0, L.splice(x, 1)[0]), draw);
          return t;
        }),
      );
      grid.hidden = !L.length;
      z.hidden = !had.length;
      z.disabled = L.length >= MAXI;
      z.textContent =
        L.length >= MAXI ? "Photo limit reached (" + MAXI + ")" : "Add photos (" + L.length + " / " + MAXI + ")";
    };
    const add = (fs) => {
      err.textContent = "";
      for (const f of fs) {
        if (!f.type.startsWith("image/")) continue;
        if (L.length >= MAXI) {
          err.textContent = "Up to " + MAXI + " photos per post.";
          break;
        }
        if (f.size > IMGMAX) {
          err.textContent = "Image must be under " + IMGMB + " MB.";
          continue;
        }
        const pr = qprep(f),
          it = { url: URL.createObjectURL(f), blob: 1, p: pr, name: "" };
        L.push(it);
        pr.catch((x) => {
          const k = L.indexOf(it);
          if (k > -1) {
            gone(it);
            L.splice(k, 1);
            draw();
            upd();
          }
          err.textContent = (x && x.e) || "Could not read that photo. Pick it again.";
        });
      }
      draw();
      upd();
    };
    z.onclick = () => inp.click();
    inp.onchange = () => {
      add([...inp.files]);
      inp.value = "";
    };
    z.ondragover = (e) => {
      e.preventDefault();
      z.classList.add("hot");
    };
    z.ondragleave = () => z.classList.remove("hot");
    z.ondrop = (e) => {
      e.preventDefault();
      z.classList.remove("hot");
      add([...e.dataTransfer.files]);
    };
    draw();
    upd();
    return h(
      "form",
      {
        class: "form",
        onsubmit: async (e) => {
          e.preventDefault();
          btn.disabled = true;
          const d = fd({ id: p.id, cap: cap.value, vis: VP.get() }),
            changed =
              had.length && (L.map((x) => x.name).join("|") !== orig || L.map((x) => x.alt).join("\u0001") !== origA);
          try {
            if (changed) {
              const names = [];
              for (let i = 0; i < L.length; i++) {
                const it = L[i];
                if (!it.name) {
                  btn.textContent = "Uploading " + (i + 1) + " / " + L.length + "…";
                  const f = await it.p,
                    u = new FormData();
                  u.append("img", f);
                  it.name = (await api("pup", u)).img;
                }
                names.push(it.name);
              }
              d.append("imgs", JSON.stringify(names));
              const am = {};
              L.forEach((it) => {
                if (it.alt && it.name) am[it.name] = it.alt;
              });
              d.append("alts", JSON.stringify(am));
            }
            if (oldS !== 2 && had.length) d.append("sens", sn.checked ? "1" : "0");
            btn.textContent = "Saving…";
            const r = await api("edit", d);
            p.cap = r.cap;
            p.ed = r.ed;
            p.sens = +r.sens || 0;
            p.vis = +r.vis || 0;
            if (r.imgs || p.sens !== oldS || p.vis !== oldV) {
              if (r.imgs) {
                p.imgs = r.imgs;
                p.img = r.imgs[0] || "";
                p.alts = r.alts || [];
              }
              L.forEach(gone);
              close();
              route();
              return;
            }
            done();
            close();
          } catch (x) {
            err.textContent = x.e || "Could not save.";
            btn.textContent = "Save";
            upd();
          }
        },
      },
      had.length ? h("p", { class: "hint pehint" }, "Drag photos to reorder them. The first one is the cover.") : null,
      grid,
      h("div", {}, z, inp),
      sbox,
      cap,
      cnt,
      VP.el,
      err,
      btn,
    );
  });
}
function tabsBar(sel, pick) {
  const t = h("div", { class: "tabs", role: "tablist" }),
    ind = h("i", { class: "tind", "aria-hidden": "true" }),
    TB = [
      ["foryou", "For you"],
      ["friends", "Friends"],
      ["following", "Following"],
    ];
  ind.style.width = 100 / TB.length + "%";
  TB.forEach(([k, l]) => t.append(h("button", { role: "tab", "aria-selected": sel === k, onclick: () => pick(k) }, l)));
  t.append(ind);
  t.ind = ind;
  return t;
}
/* a Grid-layout tile: the first photo (or the text for a text post). Tap opens the post, where likes and comments are. */
/* Grid tiles of short text-only posts: the words become huge poster-style lines (like PNEUMO / NOULTRA / MICRO). Long words are cut into pieces of at most 7 letters, one piece per line. Each line is made as wide as the tile allows but never taller than 30% of the tile, and the whole stack is shrunk if it would not fit. Longer posts keep the normal small text. */
const BIGMAX = 7,
  FCV = document.createElement("canvas").getContext("2d");
function bigLines(cap) {
  const w = String(cap || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!w.length || w.length > 4 || [...w.join("")].length > 28) return null;
  const L = [];
  for (const x of w) {
    const c = [...x],
      n = Math.ceil(c.length / BIGMAX),
      z = Math.ceil(c.length / n);
    for (let i = 0; i < c.length; i += z) L.push(c.slice(i, i + z).join(""));
  }
  return L.length > 5 ? null : L;
}
function fitBig(t) {
  const s = t.querySelector(".gtb");
  if (!s) return;
  const cs = getComputedStyle(t),
    W = t.clientWidth - (parseFloat(cs.paddingLeft) || 0) - (parseFloat(cs.paddingRight) || 0),
    H = t.clientHeight - (parseFloat(cs.paddingTop) || 0) - (parseFloat(cs.paddingBottom) || 0);
  if (!(W > 0) || !(H > 0)) return;
  FCV.font = "900 100px " + getComputedStyle(s).fontFamily;
  const rows = [...s.children],
    sz = rows.map((r) =>
      Math.min(H * 0.3, (W * 0.84) / Math.max(0.1, FCV.measureText(r.textContent.toUpperCase()).width / 100)),
    ),
    k = Math.min(1, (H * 0.84) / sz.reduce((a, b) => a + b * 0.92, 0));
  rows.forEach((r, i) => (r.style.fontSize = sz[i] * k + "px"));
}
function tile(p) {
  const im = p.imgs && p.imgs.length ? p.imgs : p.img ? [p.img] : [],
    sens = +p.sens && im.length,
    t = h("button", {
      type: "button",
      class: "gt",
      "data-pid": p.id,
      "aria-label": p.cap ? p.cap.slice(0, 80) : "Photo post",
      onclick: () => (location.hash = "#/p/" + p.id),
    });
  lpress(t, () => postHold(p, !!+p.own, null, null));
  if (im.length && !sens)
    t.append(h("img", { src: "?img=" + im[0], alt: (p.alts && p.alts[0]) || "", loading: "lazy", draggable: "false" }));
  else {
    if (!im.length && !sens && +p.bg > 0) t.dataset.bg = p.bg;
    const bl = !im.length && !sens ? bigLines(p.cap) : null;
    if (bl) {
      t.classList.add("gb");
      t.append(h("span", { class: "gtb", "aria-hidden": "true" }, ...bl.map((x) => h("div", {}, x))));
      if (window.ResizeObserver) new ResizeObserver(() => fitBig(t)).observe(t);
      else requestAnimationFrame(() => fitBig(t));
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => fitBig(t));
    } else t.append(h("span", { class: "gtt" }, sens ? "Sensitive photo" : p.cap || ""));
  }
  if (im.length > 1 && !sens) t.append(h("i", { class: "gtm", "aria-hidden": "true" }, "+" + (im.length - 1)));
  if (+p.pinned) t.append(h("i", { class: "gtp" }, "Pinned"));
  else if (+p.hold) t.append(h("i", { class: "gtp" }, "In review"));
  return t;
}
/* one card per prompt day: the question, who answered, and a button to open the thread (#/d/<day>) that lists every answer */
function threadCard(t) {
  const today = Math.floor(Date.now() / 864e5),
    lab = +t.day === today ? "Today" : +t.day === today - 1 ? "Yesterday" : "2 days ago",
    open = () => {
      location.hash = "#/d/" + t.day;
    },
    cnt = +t.n + (+t.n === 1 ? " answer" : " answers");
  const art = h(
    "article",
    {
      class: "post thread",
      role: "link",
      tabindex: "0",
      "aria-label": "Prompt of the day thread: " + t.text + ". " + cnt + ".",
      onclick: (e) => {
        if (!e.target.closest("button")) open();
      },
      onkeydown: (e) => {
        if (e.key === "Enter" && e.target === art) open();
      },
    },
    h("div", { class: "ph" }, h("b", {}, "Prompt of the day"), h("small", { class: "hint" }, lab)),
    h("div", { class: "qa" }, h("small", {}, "Thread \u00b7 " + cnt), h("p", {}, t.text)),
    h(
      "div",
      { class: "throw" },
      h("div", { class: "thfaces", "aria-hidden": "true" }, ...(t.who || []).map((w) => av(w, 28))),
      h("span", { class: "hint thc" }, cnt),
      h("button", { class: "ghost", type: "button", onclick: open }, "Read answers"),
      +t.day === today && !+t.done
        ? h("button", { class: "btn", type: "button", onclick: () => newPost({ day: t.day, text: t.text }) }, "Answer")
        : null,
    ),
  );
  return art;
}
function feedBox(q, r, empty, lay) {
  if (!r.posts.length && !(r.threads && r.threads.length)) return empty;
  const box = h("div", lay === "big" ? { class: "pbc" } : {}),
    btn = h("button", { class: "ghost", style: "width:100%;margin-bottom:14px" }, "Load more"),
    play = SHOWN !== location.hash,
    G = lay === "grid" ? h("div", { class: "pgl" }) : null;
  let last = 0;
  if (G) box.append(G);
  box.append(btn);
  let nb = 0;
  const shownIds = new Set();
  const add = (x) => {
    /* the "For you" order can shift a little between two pages: never show the same post twice, and keep the page cursor moving */
    if (x.posts.length) last = x.posts[x.posts.length - 1].id;
    x = { ...x, posts: x.posts.filter((p) => !shownIds.has(+p.id) && shownIds.add(+p.id)) };
    const more = nb++ > 0,
      top = FT[q];
    x.posts.forEach((p, i) => {
      const c = G ? tile(p) : card(p);
      if (play || more || (!more && top && +p.id > top)) {
        c.classList.add("cut");
        c.style.setProperty("--i", Math.min(i, 5));
      }
      (G || box).insertBefore(c, G ? null : btn);
      last = p.id;
    });
    if (!more && x.posts.length) FT[q] = Math.max(top || 0, ...x.posts.map((p) => +p.id));
    btn.hidden = !x.more;
    /* prompt-of-the-day threads: one card per day, dropped at a steady pseudo-random spot among the first posts (like any other post) */
    if (!more && !G && x.threads && x.threads.length) {
      const ts = [...x.threads].reverse();
      ts.forEach((t) => {
        const kids = [...box.children].filter((el) => el !== btn),
          n = Math.min(kids.length, 6),
          sp = ((+t.day * 2654435761 + (+M.id || 0) * 40503) >>> 0) % (n + 1),
          c = threadCard(t);
        if (play) c.classList.add("cut");
        box.insertBefore(c, kids[sp] || btn);
      });
    }
  };
  add(r);
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      add(await api("feed", null, q + "&before=" + last));
    } catch (e) {}
    btn.disabled = false;
  };
  return box;
}
/* Home "New posts" pill. Every 30 s while the page is open (and when you come back to the tab) it asks how many posts arrived in the feed you are looking at since it was loaded. Tapping the pill goes to the top and reloads, the same as pull-to-refresh, and the new posts slide in. Only one pill exists at a time; it removes itself when you leave Home. */
let NPILL = null;
function newPill(anchor, getQ) {
  if (NPILL) NPILL.stop();
  let tm = 0,
    seq = 0;
  const txt = h("span", {}),
    pill = h(
      "button",
      { type: "button", class: "npill", hidden: "", "aria-live": "polite", "aria-label": "Show new posts" },
      ic("back", 16),
      txt,
    ),
    hide = () => {
      pill.hidden = true;
    },
    check = async () => {
      if (!anchor.isConnected) return stop();
      if (document.hidden) return;
      const f = getQ(),
        my = ++seq;
      try {
        const r = await api("feed", null, f + "&cnt=1&after=" + (FT[f] || 0));
        if (my !== seq || !anchor.isConnected) return;
        const n = +r.n || 0;
        if (!n) return hide();
        txt.textContent = (n > 20 ? "20+" : n) + (n === 1 ? " new post" : " new posts");
        pill.setAttribute("aria-label", "Show " + txt.textContent);
        pill.hidden = false;
      } catch (e) {}
    },
    vis = () => {
      if (!document.hidden) check();
    },
    stop = () => {
      clearInterval(tm);
      document.removeEventListener("visibilitychange", vis);
      pill.remove();
      if (NPILL && NPILL.pill === pill) NPILL = null;
    };
  pill.onclick = () => {
    hide();
    seq++;
    scrollTo({ top: 0, behavior: "auto" });
    Promise.resolve()
      .then(() => route())
      .catch(() => {});
  };
  tm = setInterval(check, 30000);
  document.addEventListener("visibilitychange", vis);
  document.body.append(pill);
  NPILL = {
    pill,
    stop,
    tab: () => {
      hide();
      check();
    },
  };
}
/* Home: a short welcome for accounts under a week old. Explains the idea in two lines, suggests a few people, and goes away for good when dismissed. */
function welcomeCard() {
  if (!M || !+M.newish) return null;
  const k = "mq-welcome-" + M.name;
  try {
    if (localStorage.getItem(k)) return null;
  } catch (_) {}
  const box = h("section", { class: "wcard", "aria-label": "Welcome to Masque" }),
    x = h("button", { type: "button", class: "ghost wcx", "aria-label": "Hide this welcome", title: "Hide" }, "\u00d7");
  x.onclick = () => {
    try {
      localStorage.setItem(k, "1");
    } catch (_) {}
    box.remove();
  };
  box.append(
    x,
    h("h3", {}, "Welcome to Masque"),
    h(
      "p",
      { class: "hint" },
      "Post, comment and chat as yourself or as a Masque, a second name and face nobody is shown is you. Add a few people and your feed fills up.",
    ),
    sugList(4, () => {}),
    h(
      "div",
      { class: "row" },
      h("button", { type: "button", class: "btn", onclick: () => newPost() }, "Make my first post"),
      h("button", { type: "button", class: "ghost", onclick: () => (location.hash = "#/f") }, "Find people"),
    ),
  );
  return box;
}
async function home() {
  const [rfy, rf, rl, pr, hr] = await Promise.all([
    api("feed", null, "&fy=1"),
    api("feed", null, "&f=1"),
    api("feed", null, "&fl=1").catch(() => ({ posts: [] })),
    api("prompt").catch(() => null),
    api("here").catch(() => ({ list: [] })),
  ]);
  const mkEmpty = (fr) =>
    fr === 2
      ? emp(
          "users",
          "You're not following anyone yet",
          "Follow people from their public profile and their posts will show up here.",
          h("button", { class: "ghost", onclick: () => (location.hash = "#/x") }, "Find people"),
        )
      : fr
      ? emp(
          "users",
          "Your feed is quiet",
          "Posts from you and your friends will show up here.",
          h("button", { class: "ghost", onclick: () => (location.hash = "#/f") }, "Find friends"),
        )
      : emp(
          "image",
          "Nothing here yet",
          "Be the first to share something.",
          h("button", { class: "btn", onclick: () => newPost() }, "New post"),
        );
  if (FEED === "all") FEED = "foryou";
  const keys = ["foryou", "friends", "following"],
    pfy = h("section", { class: "pane", role: "tabpanel" }, feedBox("&fy=1", rfy, mkEmpty(0))),
    pf = h("section", { class: "pane", role: "tabpanel" }, feedBox("&f=1", rf, mkEmpty(1))),
    pl = h("section", { class: "pane", role: "tabpanel" }, feedBox("&fl=1", rl, mkEmpty(2))),
    pager = h("div", { class: "pager" }, pfy, pf, pl);
  let idx = Math.max(0, keys.indexOf(FEED)),
    tabs;
  const paint = (p) => {
    tabs.ind.style.transform = "translateX(" + p * 100 + "%)";
    const i = Math.round(p);
    [...tabs.querySelectorAll("[role=tab]")].forEach((b, j) => b.setAttribute("aria-selected", j === i));
  };
  const go = (i) => {
    idx = i;
    FEED = keys[i];
    if (NPILL) NPILL.tab();
    pager.scrollTo({
      left: i * pager.clientWidth,
      behavior: matchMedia("(prefers-reduced-motion:reduce)").matches ? "auto" : "smooth",
    });
  };
  tabs = tabsBar(FEED, (k) => go(keys.indexOf(k)));
  let raf = 0,
    tm = 0,
    moving = false,
    y0 = 0,
    cur = idx;
  const pos = { foryou: 0, friends: 0, following: 0 },
    panes = [pfy, pf, pl],
    rest = () => panes.forEach((n, j) => n.classList.toggle("off", j !== cur));
  const settle = () => {
    moving = false;
    const w = pager.clientWidth || 1,
      i = Math.round(pager.scrollLeft / w);
    pos[keys[cur]] = y0;
    const moved = i !== cur;
    cur = i;
    idx = i;
    FEED = keys[i];
    rest();
    window.scrollTo(0, pos[keys[i]]);
    if (moved && NPILL) NPILL.tab();
  };
  pager.addEventListener(
    "scroll",
    () => {
      if (!moving) {
        moving = true;
        y0 = window.scrollY;
        panes.forEach((n) => n.classList.remove("off"));
      }
      clearTimeout(tm);
      tm = setTimeout(settle, 120);
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const w = pager.clientWidth || 1,
          p = Math.max(0, Math.min(keys.length - 1, pager.scrollLeft / w));
        paint(p);
      });
    },
    { passive: true },
  );
  const wc = welcomeCard();
  shell([wc || nudgeCard(), hereRow(hr.list || []), ticker(rf.posts || [], pr), pr ? pcard(pr) : null, tabs, pager]);
  const w = pager.clientWidth;
  pager.style.scrollBehavior = "auto";
  pager.scrollLeft = idx * w;
  paint(idx);
  pager.style.scrollBehavior = "";
  rest();
  newPill(pager, () => ["&fy=1", "&f=1", "&fl=1"][idx] || "");
}
/* Home top: "Here now" (friends who are online) and a small headline ticker of what friends just did */
function hereSheet(u) {
  sheet(dn(u), (close) =>
    h(
      "div",
      { class: "form" },
      h(
        "div",
        { class: "here-q" },
        avw(av(u, 56), u.st, 0, u.name),
        h(
          "div",
          {},
          h("b", {}, dn(u)),
          h("small", { class: "hint" }, "@" + u.name + " \u00b7 " + (ST[u.st] || "Online")),
          sbub(u.sx, "in full"),
        ),
      ),
      h(
        "div",
        { class: "row" },
        h(
          "button",
          {
            class: "btn",
            type: "button",
            onclick: () => {
              close();
              location.hash = "#/m/" + u.name;
            },
          },
          "Message",
        ),
        h(
          "button",
          {
            class: "ghost",
            type: "button",
            onclick: () => {
              close();
              location.hash = "#/u/" + u.name;
            },
          },
          "Profile",
        ),
      ),
    ),
  );
}
function hereRow(list) {
  const box = h("section", { class: "here", "aria-label": "Friends online now" });
  const draw = (L) =>
    rc(
      box,
      h(
        "div",
        { class: "here-h" },
        h("span", { class: "here-t" }, h("i", { class: "here-dot", "aria-hidden": "true" }), "Here now"),
        h("span", { class: "here-c" }, L.length ? String(L.length) : ""),
      ),
      L.length
        ? h(
            "div",
            { class: "here-l" + (L.some((u) => u.sx) ? " has-sb" : ""), role: "list" },
            ...L.map((u) =>
              h(
                "button",
                {
                  type: "button",
                  class: "here-u",
                  role: "listitem",
                  "aria-label": dn(u) + ", " + (ST[u.st] || "Online") + ". Open quick actions",
                  onclick: () => hereSheet(u),
                },
                avw(av(u, 46), u.st, 0, u.name, u.sx),
                h("span", { class: "here-n" }, dn(u)),
              ),
            ),
          )
        : h("p", { class: "here-e" }, "Nobody\u2019s around right now."),
    );
  draw(list);
  const tm = setInterval(async () => {
    if (!box.isConnected) {
      clearInterval(tm);
      return;
    }
    if (document.hidden) return;
    try {
      draw((await api("here")).list || []);
    } catch (e) {}
  }, 30000);
  return box;
}
function ticker(posts, pr) {
  const C = [];
  if (pr && !+pr.done) C.push({ t: "Prompt: open today", go: "#/d/" + pr.day, hot: 1 });
  posts
    .filter((p) => !+p.own && !+p.hold)
    .slice(0, 8)
    .forEach((p) =>
      C.push({
        t:
          (+p.anon ? "New Masque post" : dn(p) + (+p.pd > 0 ? " answered the prompt" : " posted")) +
          " \u00b7 " +
          ago(p.ts),
        go: "#/p/" + p.id,
      }),
    );
  if (!C.length) return null;
  const chip = (c) =>
      h(
        "button",
        {
          type: "button",
          class: "tk-c" + (c.hot ? " hot" : ""),
          onclick: () => {
            location.hash = c.go;
          },
        },
        c.t,
      ),
    run = (dup) =>
      h("div", dup ? { class: "tk-run dup", "aria-hidden": "true", inert: "" } : { class: "tk-run" }, ...C.map(chip)),
    tr = h("div", { class: "tk-track" }, run(0), run(1));
  tr.style.setProperty("--d", Math.max(14, C.length * 6) + "s");
  return h("section", { class: "tk", "aria-label": "What your friends just did" }, tr);
}
/* ---- Chat streaks: a small flame with the day count on a chat. Direct chat: both of you wrote that day. Group: enough different members wrote (the server decides).
   The flame can be hidden per chat on this device (chat options). It shows from 2 days, and counts down the last 3 hours when today has not counted yet. ---- */
const CS_KEY = "mq-cs-off";
const csOffSet = () => {
  try {
    return new Set(JSON.parse(localStorage.getItem(CS_KEY) || "[]"));
  } catch (_) {
    return new Set();
  }
};
const csIsOff = (k) => csOffSet().has(k);
const csSetOff = (k, on) => {
  try {
    const s = csOffSet();
    on ? s.add(k) : s.delete(k);
    localStorage.setItem(CS_KEY, JSON.stringify([...s].slice(-200)));
  } catch (_) {}
};
const csFlame = () => {
  const e = document.createElement("span");
  e.className = "csf";
  e.setAttribute("aria-hidden", "true");
  e.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14"><path d="M12 2c.8 3.6 5.2 5.6 5.2 10.6a5.2 5.2 0 0 1-10.4 0c0-2 .9-3.4 2.1-4.4.1 2 1 3 2.1 3.2C10.4 8.6 10.6 5 12 2z" fill="currentColor"/></svg>';
  return e;
};
/* cs = {n, dn, lf, tc, nd}; key = "d<name>[/k]" or "g<id>"; returns null when there is nothing to show */
const csChip = (cs, key) => {
  const n = +(cs && cs.n) || 0;
  if (n < 2 || csIsOff(key)) return null;
  const risk = !+cs.dn && +cs.lf > 0 && +cs.lf <= 10800,
    hrs = Math.max(1, Math.ceil(+cs.lf / 3600)),
    grp = key[0] === "g",
    who = grp ? (+cs.nd || 2) + " different members" : "both of you",
    tr = typeof strTier === "function" ? strTier(n) : 1,
    tip =
      n + "-day chat streak" + (tr >= 3 ? " (" + STRN[tr] + ")" : "") + ". It grows each day " + who + " write." +
      (+cs.dn ? " Today counts." : risk ? " Ends in about " + hrs + "h." : grp && +cs.nd ? " " + (+cs.tc || 0) + "/" + cs.nd + " have written today." : " Today still needs a message.");
  return h(
    "span",
    { class: "cschip t" + tr + (risk ? " risk" : "") + (+cs.dn ? " done" : ""), role: "img", "aria-label": tip, title: tip },
    csFlame(),
    h("b", {}, String(n)),
    risk ? h("small", {}, hrs + "h") : null,
  );
};
/* the open chat's flame in its header; the chat's own redraws call csUpd with fresh numbers */
let CSX = {};
/* Streak went up (the day count grew since this chat was last shown, live or while you were away): the flame pops, embers rise, the number rolls up and the new day count slams across the screen.
   Once per new count. "Last shown" is remembered per chat on this device; the first time a chat is shown it is only recorded, never celebrated. */
const CS_SEEN = "mq-cs-seen";
const csSeenMap = () => {
  try {
    const o = JSON.parse(localStorage.getItem(CS_SEEN) || "{}");
    return o && typeof o === "object" ? o : {};
  } catch (_) {
    return {};
  }
};
const csSeenSet = (k, n) => {
  try {
    const o = csSeenMap();
    delete o[k];
    o[k] = n;
    const ks = Object.keys(o);
    ks.slice(0, Math.max(0, ks.length - 200)).forEach((x) => delete o[x]);
    localStorage.setItem(CS_SEEN, JSON.stringify(o));
  } catch (_) {}
};
function csCelebrate(chip, from, to) {
  if (matchMedia("(prefers-reduced-motion:reduce)").matches) return;
  const b = chip.querySelector("b"),
    em = [],
    big = typeof strTier === "function" && strTier(to) > strTier(from); /* crossed into a new flame tier (3, 7, 14, 30, 100 days): bigger burst */
  chip.classList.add("csup");
  if (big) chip.classList.add("csbig");
  if (b) {
    b.textContent = String(from);
    setTimeout(() => b.isConnected && setN(b, to, 1), 380);
  }
  const ne = big ? 20 : 8;
  for (let i = 0; i < ne; i++) {
    const e = h("span", { class: "cse", "aria-hidden": "true" });
    e.style.setProperty("--dx", Math.round((Math.random() - 0.5) * (big ? 84 : 44)) + "px");
    e.style.setProperty("--dy", -Math.round(26 + Math.random() * (big ? 48 : 26)) + "px");
    e.style.setProperty("--dl", (i * (big ? 0.04 : 0.05)).toFixed(2) + "s");
    e.style.setProperty("--sz", 3 + Math.round(Math.random() * 3) + "px");
    em.push(e);
  }
  chip.append(...em);
  setTimeout(() => slam(String(to)), 180);
  setTimeout(() => {
    chip.classList.remove("csup", "csbig");
    em.forEach((e) => e.remove());
  }, big ? 2200 : 1500);
}
const csUpd = (cs) => {
  CSX.cs = cs;
  if (!CSX.el) return;
  if (CSX.busy && Date.now() < CSX.busy && cs && +cs.n === CSX.bn) return;
  const c = csChip(cs, CSX.key);
  CSX.el.replaceChildren(...(c ? [c] : []));
  if (!cs || !CSX.key) return;
  const n = +cs.n || 0,
    o = csSeenMap(),
    k = CSX.key;
  if (c && +cs.dn && k in o && n > +o[k]) {
    CSX.busy = Date.now() + 2300;
    CSX.bn = n;
    csCelebrate(c, Math.max(1, +o[k]), n);
  }
  if (o[k] !== n) csSeenSet(k, n);
};
const csHere = (el, key, cs) => {
  CSX = { el, key, cs };
  csUpd(cs);
};
/* chat options row: hide or show the flame on this device */
const csRow = (row, key) =>
  row(csIsOff(key) ? "Show streak flame" : "Hide streak flame", "star", () => {
    csSetOff(key, !csIsOff(key));
    csUpd(CSX.cs);
  });
/* ---- Prompt streak: a flame that grows with the streak (see strTier), a 7-day row, a countdown while it is at risk, and the next goal ----
   The server (`prompt` action) sends: streak (days in a row), wk (last 7 days, oldest first, 1 = answered), best, day (today's day number). The "streak day" is the same UTC day the prompt changes on. */
const STRN = ["No streak yet", "Spark", "Kindled", "Blazing", "Wildfire", "Blue flame", "Eternal"],
  STRM = [3, 7, 14, 30, 60, 100, 365],
  strTier = (n) => (n >= 100 ? 6 : n >= 30 ? 5 : n >= 14 ? 4 : n >= 7 ? 3 : n >= 3 ? 2 : n >= 1 ? 1 : 0),
  strFlame = () =>
    '<svg viewBox="0 0 64 80" aria-hidden="true" focusable="false"><path class="f1" d="M32 3C36 18 54 28 55 50C56 68 45 78 32 78C19 78 8 68 9 50C10 40 16 34 20 26C22 32 24 36 28 36C26 24 28 12 32 3Z"/><path class="f2" d="M32 28C35 38 46 44 46 58C46 69 40 75 32 75C24 75 18 69 18 58C18 50 23 46 26 40C28 44 29 46 31 46C30 40 30 34 32 28Z"/><path class="f3" d="M32 50C35 56 40 59 40 66C40 72 36 75 32 75C28 75 24 72 24 66C24 60 29 57 32 50Z"/><path class="fe" d="M20 60Q25 55 30.5 61Q25 64 20 60ZM44 60Q39 55 33.5 61Q39 64 44 60Z"/></svg>',
  strIcon = (cls, svg) => {
    const e = h("span", { class: cls, "aria-hidden": "true" });
    e.innerHTML = svg;
    return e;
  },
  strLeft = (pr) => {
    const ms = (+pr.day + 1) * 86400000 - Date.now();
    if (ms <= 0) return "Today is almost over";
    const hh = Math.floor(ms / 3600000),
      mm = Math.floor((ms % 3600000) / 60000);
    return (hh > 0 ? hh + "h " + mm + "m" : Math.max(1, mm) + "m") + " left to keep it";
  };
/* works out everything the streak visuals need and remembers the last streak you saw (to celebrate a new day) */
function strInfo(pr) {
  const n = +pr.streak || 0,
    wk =
      Array.isArray(pr.wk) && pr.wk.length === 7
        ? pr.wk.map(Number)
        : Array.from({ length: 7 }, (_, i) => {
            const back = 6 - i,
              end = +pr.done ? 0 : 1;
            return n > 0 && back >= end && back < end + n ? 1 : 0;
          }),
    kept = wk[6] === 1,
    key = "mq-sk" + (typeof M !== "undefined" && M && M.name ? M.name : "");
  let prev = 0;
  try {
    prev = +localStorage.getItem(key) || 0;
  } catch (e) {}
  const up = kept && n !== prev && (n > prev ? prev > 0 || n === 1 : n === 1);
  if (kept && n !== prev)
    try {
      localStorage.setItem(key, String(n));
    } catch (e) {}
  /* a milestone day just kept (7, 30, 100): the server adds a one-time Sigil bonus, worked out from your best streak */
  const hit = up ? (pr.ms || []).find((z) => +z[0] === n) : null;
  return { n, t: strTier(n), wk, kept, risk: n > 0 && !kept, up, prev, best: Math.max(+pr.best || 0, n), icy: !!+pr.icy && n > 0, hit: hit ? +hit[1] : 0 };
}
const SNOWF =
  '<svg viewBox="0 0 24 24"><path d="M12 3v18M4.2 7.5l15.6 9M19.8 7.5l-15.6 9M9.5 4.6L12 6.8l2.5-2.2M9.5 19.4L12 17.2l2.5 2.2"/></svg>';
const strChip = (si) =>
  si.n > 0
    ? h("span", { class: "skchip sk" + si.t + (si.icy ? " icy" : "") + (si.risk ? " risk" : "") + (si.up ? " bump" : ""), title: si.n + "-day streak" }, strIcon("skm", strFlame()), h("b", {}, si.n))
    : null;
/* the small flame next to someone's avatar on their profile (you and your friends see it) */
const strProfileChip = (sk) => {
  const n = +(sk && sk.n) || 0;
  if (n < 1) return null;
  const el = h("span", { class: "skchip pf sk" + strTier(n) + (+sk.icy ? " icy" : ""), role: "img", "aria-label": n + "-day streak" + (+sk.icy ? ", frozen" : ""), title: n + "-day prompt streak" + (+sk.icy ? " (frozen)" : "") }, strIcon("skm", strFlame()), h("b", {}, n));
  return el;
};
/* "Save your streak": shown when 1 to 3 days were missed right after a streak of 3 or more. Costs Sigils (price from the server); the missed days turn icy and the chain carries on. */
function strFreeze(pr) {
  const z = pr.fz,
    bal = +pr.bal || 0,
    price = +z.price,
    can = bal >= price,
    out = h("p", { class: "hint skfzerr", role: "alert", hidden: "" }),
    b = h(
      "button",
      { type: "button", class: "btn skfzb", disabled: !can },
      strIcon("skfzi", SNOWF),
      price ? "Save it for " + price + " Sigils" : "Save it (free for admins)",
    );
  b.onclick = async () => {
    b.disabled = true;
    out.hidden = true;
    try {
      await api("sfreeze", fd({}));
      route();
    } catch (e) {
      out.textContent = (e && e.e) || "Could not save the streak.";
      out.hidden = false;
      b.disabled = !can;
    }
  };
  return h(
    "div",
    { class: "skfz" },
    h(
      "div",
      {},
      h("b", {}, z.n === 1 ? "You missed a day" : "You missed " + z.n + " days"),
      h("p", { class: "hint" }, "Freeze " + (z.n === 1 ? "it" : "them") + " to keep your " + z.was + "-day streak" + (+z.after > +z.was ? " (back to " + z.after + ")" : "") + ". You have " + bal + " Sigils." + (can ? "" : " " + (price - bal) + " more needed.")),
    ),
    b,
    out,
  );
}
function strBlock(pr, si) {
  const n = si.n,
    next = STRM.find((x) => x > n),
    nb = (pr.ms || []).find((z) => +z[0] === next),
    base = [...STRM].reverse().find((x) => x <= n) || 0,
    pct = next ? Math.max(4, Math.round(((n - base) / (next - base)) * 100)) : 100,
    num = h("b", {}, String(si.up && !RM.matches ? si.prev : n)),
    sub = h(
      "p",
      { class: "sksub" },
      n === 0
        ? "Answer today\u2019s prompt to light your streak."
        : si.hit
          ? n + "-day milestone! +" + si.hit + " Sigils added."
          : si.kept
            ? "Kept for today. See you tomorrow."
            : si.icy
              ? "Frozen day saved it. " + strLeft(pr)
              : strLeft(pr),
    ),
    ems = si.t >= 2 ? [[-12, "1.9s", "0s"], [9, "2.3s", ".5s"], [-3, "2.1s", "1.1s"], [14, "1.7s", "1.5s"]].concat(si.t >= 4 ? [[-16, "2.4s", ".8s"], [4, "1.8s", "1.9s"]] : []) : [],
    el = h(
      "div",
      { class: "skb sk" + si.t + (si.icy ? " icy" : "") + (si.hit ? " hit" : "") + (si.risk ? " risk" : "") + (si.kept ? " kept" : "") + (si.up ? " up" : ""), role: "group", "aria-label": n + "-day prompt streak" },
      h("div", { class: "skfl" }, strIcon("skfs", strFlame()), ...ems.map((z) => h("i", { class: "skem", style: "--x:" + z[0] + "px;--d:" + z[1] + ";--l:" + z[2] })), ),
      h(
        "div",
        { class: "skmain" },
        h("small", { class: "skt" }, STRN[si.t]),
        h("div", { class: "sknum" }, num, h("span", {}, n === 1 ? "day streak" : "day streak")),
        sub,
      ),
      h(
        "div",
        { class: "skwk", role: "list", "aria-label": "Last 7 days" },
        ...si.wk.map((v, i) => {
          const L = "SMTWTFS"[new Date((+pr.day - 6 + i) * 86400000).getUTCDay()];
          return h(
            "div",
            { class: "skd" + (+v === 1 ? " on" : +v === 2 ? " ice" : "") + (i === 6 ? " today" : ""), role: "listitem", "aria-label": (i === 6 ? "Today" : L) + (+v === 1 ? ": answered" : +v === 2 ? ": frozen, streak saved" : ": not answered") },
            h("small", {}, i === 6 ? "Today" : L),
            h("i", {}, +v === 1 ? strIcon("skc", '<svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>') : +v === 2 ? strIcon("skc", SNOWF) : null),
          );
        }),
      ),
      pr.fz ? strFreeze(pr) : null,
      h(
        "div",
        { class: "skpr" },
        h("div", { class: "skbar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(pct) }, h("i", { style: "width:" + pct + "%" })),
        h(
          "div",
          { class: "skfoot" },
          h("span", {}, next ? next - n + (next - n === 1 ? " more day" : " more days") + " to a " + next + "-day streak" + (nb ? " (+" + nb[1] + " Sigils)" : "") : "Legend. Keep it burning."),
          h("span", { class: "skbest" }, "Best " + si.best),
        ),
      ),
    );
  /* a new day was kept: the number rolls up to the new total */
  if (si.up && !RM.matches) {
    const from = si.prev,
      to = n,
      steps = Math.min(12, Math.abs(to - from) || 1);
    let i = 0;
    setTimeout(() => {
      const iv = setInterval(() => {
        i++;
        num.textContent = String(Math.round(from + ((to - from) * i) / steps));
        if (i >= steps) clearInterval(iv);
      }, 60);
    }, 450);
  }
  /* while it is at risk the countdown ticks; stops when the card leaves the page */
  if (si.risk) {
    const iv = setInterval(() => {
      if (!el.isConnected) clearInterval(iv);
      else sub.textContent = strLeft(pr);
    }, 30000);
  }
  return el;
}
/* Home prompt card: a slim row (streak chip + "4-day streak" + time left) stands in for the full streak block; tap it to open the full block (week + progress), tap the block to close it again. A fresh milestone or a new day kept starts open so the celebration shows. */
function skCompact(el, si, pr) {
  let x = false;
  try {
    x = sessionStorage.getItem("mq-skx") === "1";
  } catch (e) {}
  if (si.up || si.hit) x = true;
  const n = si.n,
    top = n === 0 ? "Light your streak" : n + "-day streak",
    sub = n === 0 ? "Answer today\u2019s prompt" : si.kept ? "Kept for today" : si.icy ? "A frozen day saved it" : strLeft(pr),
    row = h(
      "button",
      { type: "button", class: "skrow sk" + si.t + (si.icy ? " icy" : "") + (si.risk ? " risk" : ""), "aria-expanded": "false" },
      strChip(si) || h("span", { class: "skzero", "aria-hidden": "true" }, strIcon("skm", strFlame())),
      h("span", { class: "skrt" }, h("b", {}, top), h("small", {}, sub)),
      h("span", { class: "skmini", "aria-hidden": "true" }, ...si.wk.map((v, i) => h("i", { class: (+v === 1 ? "on" : +v === 2 ? "ice" : "") + (i === 6 ? " today" : "") }))),
      h("span", { class: "skrc", "aria-hidden": "true" }),
    ),
    wrap = h("div", { class: "skwrap" }, row, el);
  el.classList.add("skx");
  el.tabIndex = 0;
  el.setAttribute("role", "button");
  el.setAttribute("aria-label", n + "-day prompt streak. Tap to collapse.");
  const set = (o) => {
    row.hidden = o;
    el.hidden = !o;
    row.setAttribute("aria-expanded", String(o));
    try {
      sessionStorage.setItem("mq-skx", o ? "1" : "0");
    } catch (e) {}
  };
  row.onclick = () => set(true);
  el.addEventListener("click", (ev) => {
    if (ev.target.closest("button,a,input")) return;
    set(false);
  });
  el.addEventListener("keydown", (ev) => {
    if ((ev.key === "Enter" || ev.key === " ") && ev.target === el) {
      ev.preventDefault();
      set(false);
    }
  });
  set(x);
  return wrap;
}
/* Streak went up: a full-screen moment. The flame pops in the middle of the screen, embers rise, and the number counts up to the new total. Tap anywhere to skip; it also closes by itself. Skipped when the person asked for reduced motion (the card still shows the change). */
let SKSEEN = "";
function strCelebrate(si) {
  const mark = (typeof M !== "undefined" && M ? M.name : "") + ":" + si.n;
  if (RM.matches || SKSEEN === mark) return;
  SKSEEN = mark;
  document.getElementById("skov")?.remove();
  const n = si.n,
    from = n > si.prev ? si.prev : 0,
    steps = Math.min(10, Math.max(1, n - from)),
    num = h("b", {}, String(from)),
    ps = Array.from({ length: 16 }, (_, i) => h("i", { class: "skov-p", style: "--x:" + Math.round((Math.random() - 0.5) * 190) + "px;--h:" + (150 + Math.round(Math.random() * 130)) + "px;--d:" + (1.6 + Math.random() * 1.4).toFixed(2) + "s;--l:" + (Math.random() * 1.6).toFixed(2) + "s;--s:" + (4 + Math.round(Math.random() * 5)) + "px" })),
    sub = h("p", { class: "skov-sub" }, si.hit ? n + "-day milestone! +" + si.hit + " Sigils added." : n === 1 ? "Your streak is lit. Come back tomorrow." : "Come back tomorrow to keep it burning."),
    el = h(
      "div",
      { id: "skov", class: "skov sk" + si.t + (si.icy ? " icy" : ""), role: "status", "aria-live": "polite", "aria-label": n + "-day prompt streak" },
      h(
        "div",
        { class: "skov-in" },
        h("div", { class: "skov-fl" }, h("i", { class: "skov-glow" }), strIcon("skfs", strFlame()), ...ps, h("i", { class: "skov-ring" }), h("i", { class: "skov-ring r2" })),
        h("div", { class: "skov-num" }, num),
        h("div", { class: "skov-lab" }, n === 1 ? "day streak" : "day streak"),
        h("small", { class: "skov-tier" }, STRN[si.t]),
        sub,
        h("small", { class: "skov-tap" }, "Tap to continue"),
      ),
    );
  let gone = false;
  const timers = [],
    close = () => {
      if (gone) return;
      gone = true;
      timers.forEach(clearTimeout);
      removeEventListener("hashchange", close);
      el.classList.add("out");
      setTimeout(() => el.remove(), 300);
    };
  el.onclick = close;
  addEventListener("hashchange", close);
  document.body.append(el);
  let i = 0;
  timers.push(
    setTimeout(() => {
      const iv = setInterval(() => {
        if (gone) return clearInterval(iv);
        i++;
        num.textContent = String(Math.round(from + ((n - from) * i) / steps));
        num.classList.remove("tick");
        void num.offsetWidth;
        num.classList.add("tick");
        if (navigator.vibrate)
          try {
            navigator.vibrate(i >= steps ? [14, 50, 22] : 6);
          } catch (e) {}
        if (i >= steps) {
          clearInterval(iv);
          el.classList.add("done");
          timers.push(setTimeout(close, 2300));
        }
      }, 120);
      timers.push(iv);
    }, 800),
  );
}
const pcard = (pr) => {
  const si = strInfo(pr);
  if (si.up) setTimeout(() => strCelebrate(si), 350);
  let open = false;
  try {
    open = sessionStorage.getItem("mq-pd") === "1";
  } catch (e) {}
  const body = h(
      "div",
      { class: "pdbody" },
      h(
        "div",
        { class: "pdin" },
        skCompact(strBlock(pr, si), si, pr),
        h("div", { class: "pdq" }, h("small", { class: "pdk" }, "Today\u2019s prompt"), h("p", { class: "pq" }, pr.text)),
        h(
          "div",
          { class: "row" },
          +pr.done
            ? h("button", { class: "ghost pddone", type: "button", disabled: "" }, ic("check", 16), "You answered")
            : h("button", { class: "btn", type: "button", onclick: () => newPost(pr) }, "Answer"),
        ),
        h(
          "div",
          { class: "pdlinks" },
          h(
            "button",
            { class: "ghost pdlink", type: "button", onclick: () => (location.hash = "#/d/" + pr.day) },
            "See answers",
            +pr.n ? h("i", { class: "pdn" }, String(pr.n)) : null,
          ),
          h("button", { class: "ghost pdlink", type: "button", onclick: () => (location.hash = "#/h/1") }, "Worth reading"),
          h("button", { class: "ghost pdlink", type: "button", onclick: () => (location.hash = "#/h/7") }, "This week"),
        ),
      ),
    ),
    st = +pr.done ? "Answered" : "Open today",
    btn = h(
      "button",
      { type: "button", class: "pdbtn", "aria-expanded": "false" },
      h("span", { class: "pdl" }, ic("ask", 18), h("b", {}, "Prompt of the day")),
      h(
        "span",
        { class: "pdm" + (+pr.done ? "" : " new") },
        +pr.done ? null : h("i", { class: "pnew", "aria-hidden": "true" }),
        st,
        strChip(si),
      ),
      h("span", { class: "pdc", "aria-hidden": "true" }, ic("chev", 18)),
    ),
    card = h("div", { class: "card pcard" + (open ? " open" : "") }, btn, body);
  const set = (o) => {
    open = o;
    card.classList.toggle("open", o);
    btn.setAttribute("aria-expanded", String(o));
    body.inert = !o;
    try {
      sessionStorage.setItem("mq-pd", o ? "1" : "0");
    } catch (e) {}
  };
  btn.onclick = () => set(!open);
  set(open);
  return card;
};
async function hl(span) {
  let d = 0;
  try {
    d = (await api("prompt")).day - 1;
  } catch (e) {}
  if (!d) {
    shell(emp("search", "Nothing yet", "Try again in a moment."));
    return;
  }
  await results(
    +span === 7 ? "Answers worth reading this week" : "Yesterday's answers worth reading",
    "&top=" + d + "&span=" + (+span === 7 ? 7 : 1),
  );
}
async function saved() {
  const q = "&sv=1",
    r = await api("feed", null, q);
  shell([
    big("Saved", "sm"),
    h(
      "button",
      { class: "ghost", style: "margin-bottom:14px", onclick: () => (location.hash = "#/u/" + M.name) },
      "\u2190 Profile",
    ),
    feedBox(
      q,
      r,
      emp(
        "bookmark",
        "Nothing saved yet",
        "Tap the bookmark on a post to keep it here. Only you can see what you save.",
      ),
    ),
  ]);
}
/* Masque rooms: temporary themed chat rooms (1, 6 or 24 hours) that only Masques can talk in. Everything said in a room is deleted when it closes. */
const RTH = {
  midnight: "Midnight",
  rain: "Rain",
  neon: "Neon",
  castle: "Castle",
  sunrise: "Sunrise",
  void: "Void",
};
const rleft = (s) => {
  s = Math.max(0, Math.floor(s));
  const d = Math.floor(s / 3600),
    m = Math.floor((s % 3600) / 60);
  return d ? d + "h " + m + "m" : m ? m + "m" : s + "s";
};
async function rooms() {
  const r = await api("rlist"),
    off = r.now - Date.now() / 1000,
    mk = () => {
      if (!M.mask) return maskSheet(() => route());
      sheet("Open a room", (close) => {
        const nm = h("input", { type: "text", maxlength: 40, placeholder: "Room name, e.g. 3am thoughts", "aria-label": "Room name" }),
          err = h("p", { class: "err", role: "alert" });
        let th = "midnight",
          hrs = 24;
        const chips = (items, cur, set, cls) => {
            const box = h("div", { class: "rmchips" });
            items.forEach(([k, l]) => {
              const b = h("button", { type: "button", class: "chip " + (cls || ""), "data-k": k, "aria-pressed": String(k === cur) }, l);
              b.onclick = () => {
                set(k);
                [...box.children].forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
              };
              box.append(b);
            });
            return box;
          },
          go = h("button", { class: "btn", type: "button" }, "Open room");
        go.onclick = async () => {
          err.textContent = "";
          if (!nm.value.trim()) return (err.textContent = "Give the room a name.");
          go.disabled = true;
          try {
            const x = await api("rcreate", fd({ name: nm.value, theme: th, hrs }));
            close();
            location.hash = "#/o/" + x.id;
          } catch (e) {
            err.textContent = (e && e.e) || "Could not open the room.";
            go.disabled = false;
          }
        };
        return h(
          "div",
          { class: "form" },
          h("label", {}, "Name", nm),
          h("label", {}, "Theme"),
          chips(Object.entries(RTH), th, (k) => (th = k), "rmth"),
          h("label", {}, "Closes after"),
          chips([["1", "1 hour"], ["6", "6 hours"], ["24", "24 hours"]], "24", (k) => (hrs = +k)),
          h("p", { class: "hint" }, "You will chat as " + M.mask.name + ". When the room closes, every message in it is deleted."),
          err,
          go,
        );
      });
    };
  shell([
    big("Rooms", "sm"),
    h("button", { class: "ghost", style: "margin-bottom:14px", onclick: () => (location.hash = "#/m") }, "← Messages"),
    h("p", { class: "hint", style: "margin:0 0 12px" }, "Temporary chat rooms. Only Masques talk in them, nobody sees your real profile, and each room disappears when its time is up."),
    h("button", { class: "btn", style: "width:100%;margin-bottom:14px", onclick: mk }, M.mask ? "Open a room" : "Create your Masque to open a room"),
    ...(r.rooms.length
      ? r.rooms.map((x) =>
          h(
            "button",
            { class: "chat rmrow", "data-th": x.theme, onclick: () => (location.hash = "#/o/" + x.id) },
            h("span", { class: "rmdot", "aria-hidden": "true" }),
            h(
              "div",
              { class: "cx" },
              h("b", {}, x.name),
              h("span", { class: "hint" }, RTH[x.theme] + " · " + (+x.here ? x.here + " here" : "empty") + " · closes in " + rleft(x.exp - (Date.now() / 1000 + off))),
            ),
          ),
        )
      : [emp("users", "No rooms open", "Open the first one and pick a theme.")]),
  ]);
}
async function roomPage(id) {
  const h0 = location.hash;
  let r;
  try {
    r = await api("rthread", null, "&id=" + id);
  } catch (e) {
    shell(emp("lock", "This room has closed", "Rooms close by themselves and everything in them is deleted.", h("button", { class: "btn", onclick: () => (location.hash = "#/o") }, "All rooms")));
    return;
  }
  refineTitle(h0, r.room.name);
  const off = r.now - Date.now() / 1000,
    exp = +r.room.exp,
    list = h("div", { class: "mlist rmlist", role: "log", "aria-live": "polite" }),
    hereEl = h("div", { class: "rmhere", "aria-label": "Here now" }),
    sub = h("small", { class: "hint" }),
    err = h("p", { class: "err", role: "alert" }),
    inp = h("input", { type: "text", maxlength: 300, enterkeyhint: "send", autocomplete: "off", placeholder: r.has ? "Say something as " + M.mask.name + "…" : "", "aria-label": "Message" }),
    send = h("button", { class: "btn", type: "submit" }, "Send");
  let last = 0,
    first = true,
    over = false,
    nHere = 0;
  const paintSub = () => (sub.textContent = nHere + " here · closes in " + rleft(exp - (Date.now() / 1000 + off))),
    paintHere = (L) => {
      nHere = L.length;
      hereEl.replaceChildren(...L.slice(0, 12).map((u) => h("span", { class: "rmh", title: u.name }, av(u.avatar ? { avatar: u.avatar } : { mk: 1 }, 22), h("small", {}, u.name))));
      paintSub();
    },
    row = (m) => {
      const mine = !!+m.mine,
        canDel = mine || +r.room.own || (M && M.admin),
        e = h(
          "div",
          { class: "rmm" + (mine ? " mine" : ""), "data-mid": m.id },
          mine ? null : av(m.avatar ? { avatar: m.avatar } : { mk: 1 }, 30),
          h("div", { class: "rmb" }, mine ? null : h("small", { class: "rmn" }, m.name), h("span", { class: "rmt" }, m.txt)),
        );
      /* vote cluster: mark / downvote (counts toward that Masque's reputation, nobody sees who voted) and report. Your own messages only show how many marks they got. */
      const upN = h("b", {}),
        ub = h("button", { type: "button", class: "rmv-b up", "aria-label": "Mark this message", title: "Mark: adds a point to their Masque" }),
        db = h("button", { type: "button", class: "rmv-b dn", "aria-label": "Downvote this message", title: "Downvote: takes a point off their Masque. Nobody is told who did it." }),
        rp = h("button", { type: "button", class: "rmv-b rp", "aria-label": "Report this message", title: "Report" }, "Report"),
        bar = h("div", { class: "rmvote" });
      ub.innerHTML = DOWN;
      db.innerHTML = DOWN;
      ub.append(upN);
      m.up = +m.up || 0;
      m.mv = +m.mv || 0;
      e._paint = (up, mv) => {
        m.up = +up || 0;
        m.mv = +mv || 0;
        upN.textContent = m.up ? String(m.up) : "";
        ub.classList.toggle("on", m.mv === 1);
        db.classList.toggle("on", m.mv === -1);
        ub.setAttribute("aria-pressed", String(m.mv === 1));
        db.setAttribute("aria-pressed", String(m.mv === -1));
        if (mine && !dl) bar.hidden = !m.up;
      };
      const vote = async (v) => {
        try {
          const x = await api("rvote", fd({ id: m.id, v: m.mv === v ? 0 : v }));
          e._paint(x.up, x.mv);
        } catch (z) {
          err.textContent = (z && z.e) || "Could not vote.";
        }
      };
      ub.onclick = () => vote(1);
      db.onclick = () => vote(-1);
      rp.onclick = () => reportSheet("mask", m.name, null, "Room \u201c" + r.room.name.slice(0, 30) + "\u201d: \u201c" + String(m.txt).slice(0, 100) + "\u201d ");
      const dl = canDel ? h("button", { type: "button", class: "rmv-b rp", "aria-label": "Delete message", title: "Delete" }, "Delete") : null;
      if (dl)
        dl.onclick = async () => {
          try {
            await api("rdelmsg", fd({ id: m.id }));
            e.remove();
          } catch (z) {
            err.textContent = (z && z.e) || "Could not delete.";
          }
        };
      if (mine) {
        ub.disabled = true;
        bar.append(ub);
      } else if (r.has) bar.append(ub, db, rp);
      else bar.append(rp);
      if (dl) bar.append(dl);
      const bb = e.querySelector(".rmb"),
        col = h("div", { class: "rmc" });
      bb.replaceWith(col);
      col.append(bb, bar);
      e._paint(m.up, m.mv);
      return e;
    },
    add = (ms) => {
      const stick = first || list.scrollHeight - list.scrollTop - list.clientHeight < 140;
      let n = 0;
      ms.forEach((m) => {
        if (+m.id <= last) return;
        last = +m.id;
        list.append(row(m));
        n++;
      });
      if (!last && first) list.append(h("p", { class: "hint rmempty" }, "Nobody has said anything yet. Be first."));
      if (n) list.querySelector(".rmempty")?.remove();
      if (stick) list.scrollTop = list.scrollHeight;
      first = false;
    },
    closed = () => {
      over = true;
      clearInterval(POLL);
      list.append(h("p", { class: "hint rmempty" }, "This room has closed. Everything said here is gone."));
      list.scrollTop = list.scrollHeight;
      inp.disabled = true;
      send.disabled = true;
      sub.textContent = "Closed";
    },
    tick = async () => {
      if (document.hidden || over || !list.isConnected) return;
      try {
        const x = await api("rthread", null, "&id=" + id + "&after=" + last);
        paintHere(x.here || []);
        add(x.msgs || []);
        /* sync: drop messages that were deleted, refresh counts and your own votes */
        const lv = x.live || [],
          byId = new Map(lv.map((z) => [+z.id, z])),
          lo = lv.length >= 80 ? Math.min(...lv.map((z) => +z.id)) : 0;
        list.querySelectorAll(".rmm[data-mid]").forEach((el) => {
          const id2 = +el.dataset.mid,
            z = byId.get(id2);
          if (z) el._paint && el._paint(z.up, z.mv);
          else if (id2 >= lo) el.remove();
        });
      } catch (e) {
        if (e && (e.s === 404 || /closed/.test(e.e || ""))) closed();
      }
    };
  add(r.msgs || []);
  paintHere(r.here || []);
  clearInterval(POLL);
  POLL = setInterval(tick, 3000);
  const form = r.has
    ? h(
        "form",
        {
          class: "cform rmform",
          onsubmit: async (e) => {
            e.preventDefault();
            const t = inp.value.trim();
            if (!t || over) return;
            send.disabled = true;
            err.textContent = "";
            try {
              await api("rsend", fd({ id, txt: t }));
              inp.value = "";
              SFX.play("send");
              await tick();
            } catch (x) {
              err.textContent = (x && x.e) || "Could not send.";
              if (x && x.s === 404) closed();
            }
            if (!over) send.disabled = false;
            inp.focus();
          },
        },
        inp,
        send,
      )
    : h("div", { class: "cform" }, h("button", { class: "btn", type: "button", style: "width:100%", onclick: () => maskSheet(() => route()) }, "Create your Masque to talk"));
  const close = +r.room.own || (M && M.admin)
    ? h(
        "button",
        {
          type: "button",
          class: "ghost ibtn",
          style: "margin-left:auto;flex:none",
          onclick: async () => {
            if (!(await cbox("Close this room now? Everything in it is deleted."))) return;
            try {
              await api("rclose", fd({ id }));
              location.hash = "#/o";
            } catch (x) {
              err.textContent = (x && x.e) || "Could not close the room.";
            }
          },
        },
        "Close",
      )
    : null;
  shell(
    h(
      "div",
      { class: "tcard rmv", "data-th": r.room.theme },
      h(
        "div",
        { class: "th" },
        h("button", { class: "ghost", onclick: () => (location.hash = "#/o"), "aria-label": "Back to rooms" }, ic("back", 18)),
        h("div", { class: "gtitle", style: "min-width:0" }, h("b", {}, r.room.name), sub),
        close,
      ),
      hereEl,
      list,
      err,
      form,
    ),
    true,
  );
  list.scrollTop = list.scrollHeight;
}
async function pday(d) {
  let t = "Prompt of the day";
  try {
    const p = await api("prompt");
    if (+p.day === +d) t = p.text;
  } catch (e) {}
  await results(t, "&pd=" + d);
}
async function postPageClassic(id) {
  const { posts } = await api("feed", null, "&id=" + id);
  if (posts.length) postTitle(posts[0]);
  shell(
    posts.length
      ? [
          (() => {
            const r = (/^#\/p\//.test(REF || "") && PCTX && PCTX.from) || REF || "",
              lab = /^#\/u\//.test(r)
                ? "Profile"
                : /^#\/k\//.test(r)
                  ? "Masque"
                  : r === "#/saved"
                    ? "Saved"
                    : /^#\/d\//.test(r)
                      ? "Prompt"
                      : /^#\/h\//.test(r)
                        ? "Worth reading"
                        : r && r !== "#/" && !/^#\/p\//.test(r)
                          ? "Back"
                          : "Home",
              to = lab === "Home" ? "#/" : r;
            return h(
              "button",
              {
                class: "ghost",
                style: "margin-bottom:10px",
                onclick: () => {
                  location.hash = to;
                },
              },
              ic("back", 16),
              lab,
            );
          })(),
          card(posts[0], true),
          matchMedia("(pointer:fine)").matches ? postPager(posts[0]) : nextStream(posts[0]),
        ]
      : emp("close", "Post not found", "It was deleted or isn't available to you."),
  );
}
/* Live view: opening a post (#/p/ID) shows it full screen like a live stream. The author, caption, close and menu sit at the top, the photo or text fills the middle, the like / comments / save / link buttons stack on the right, and the bottom has a see-through comment box with your picture beside it (hold it to switch between you and your Masque, same as everywhere else). Comments float up from the bottom as they arrive and fade out; the full list opens from the comment button. Double-tap anywhere on the post to mark it. Set REELS to false to bring the old post page back. */
const REELS = true;
/* Where you tapped to open a post is remembered for a moment, so the viewer can grow out of that card when it opens and shrink back toward it when it closes. */
let RLO = null;
addEventListener(
  "pointerdown",
  (e) => {
    const t = e.target;
    if (!(t instanceof Element) || t.closest(".rl")) return;
    let n = t,
      r = null;
    for (let i = 0; n && i < 8 && n !== document.body; i++, n = n.parentElement) {
      const b = n.getBoundingClientRect();
      if (b.width >= 56 && b.height >= 56) {
        r = b;
        break;
      }
    }
    RLO = r ? { t: performance.now(), top: r.top, left: r.left, right: r.right, bottom: r.bottom } : null;
  },
  true,
);
function rlOrigin(el) {
  const W = innerWidth,
    H = innerHeight,
    o = RLO && performance.now() - RLO.t < 2500 ? RLO : null;
  RLO = null;
  let t = H * 0.32,
    b = H * 0.32,
    l = W * 0.3,
    r = W * 0.3;
  if (o) {
    const ct = Math.max(0, o.top),
      cl = Math.max(0, o.left),
      cr = Math.max(0, W - o.right),
      cb = Math.max(0, H - o.bottom),
      w = W - cl - cr,
      hh = H - ct - cb;
    if (w >= 56 && hh >= 56 && w * hh < W * H * 0.8) {
      t = ct;
      l = cl;
      r = cr;
      b = cb;
    }
  }
  const left0 = (W - Math.min(520, W)) / 2;
  el.style.cssText += "--ct:" + t + "px;--cr:" + r + "px;--cb:" + b + "px;--cl:" + l + "px;--ox:" + (l + (W - l - r) / 2 - left0) + "px;--oy:" + (t + (H - t - b) / 2) + "px;";
}
/* anim: the viewer is closing, so it shrinks back and fades instead of vanishing. Without it everything is removed at once (a new post is opening, or the screen is changing for good). */
function reelOff(anim) {
  const go = !!anim && !matchMedia("(prefers-reduced-motion:reduce)").matches;
  document.querySelectorAll(".rl").forEach((r) => {
    if (r._off) r._off();
    r._off = null;
    if (go) {
      if (!r.classList.contains("rlgone")) {
        r.classList.add("rlgone");
        setTimeout(() => r.remove(), 330);
      }
    } else r.remove();
  });
  document.querySelectorAll(".rlbk").forEach((b) => {
    if (go) {
      b.classList.add("gone");
      setTimeout(() => b.remove(), 330);
    } else b.remove();
  });
  document.documentElement.classList.remove("rlon");
}
async function postPage(id) {
  if (!REELS) return postPageClassic(id);
  const { posts } = await api("feed", null, "&id=" + id);
  if (!posts.length) {
    shell(emp("close", "Post not found", "It was deleted or isn't available to you."));
    return;
  }
  const cx = streamCtx(),
    r = (/^#\/p\//.test(REF || "") && PCTX && PCTX.from) || REF || "",
    to = !r || r === "#/" || /^#\/p\//.test(r) ? "#/" : r;
  shell(h("div"));
  reelView(posts[0], to, cx);
}
/* dir: 1 = came from swiping up (next post), -1 = swiping down (previous). The old screen slides away and this one slides in. */
function lightBg(bg) {
  const b = String(bg || "0");
  if (b === "6" || b === "7") return true;
  if (b !== "0") return false;
  const m = getComputedStyle(document.documentElement).getPropertyValue("--tint").trim().match(/^#([0-9a-f]{6})$/i);
  if (!m) return true;
  const n = parseInt(m[1], 16);
  return (n >> 16 & 255) * 0.299 + (n >> 8 & 255) * 0.587 + (n & 255) * 0.114 > 150;
}
/* PC (wide window with a mouse): comments open as a panel docked beside the post instead of a sheet over it, and it stays open while you move between posts. */
let RLCS = 0;
const rlDock = () => matchMedia("(min-width:1100px) and (pointer:fine)").matches;
function reelView(p, to, cx, dir, from) {
  const old = document.querySelector(".rl:not(.rlgone)");
  if (old && dir) {
    if (old._off) old._off();
    old.classList.add(dir > 0 ? "outu" : "outd");
    setTimeout(() => old.remove(), 340);
  } else {
    RLCS = 0;
    reelOff();
  }
  p.anon = +p.anon;
  p.me = +p.me;
  postTitle(p);
  p.n = +p.n;
  p.cc = +p.cc;
  p.imgs = p.imgs && p.imgs.length ? p.imgs : p.img ? [p.img] : [];
  const mine = !!+p.own,
    mm = !!(p.anon && mine && M && M.mask),
    who = p.anon ? (mine ? (mm ? M.mask.name : dn(p)) : "Masque") : dn(p),
    ptg = p.anon && !mine ? "" : mm ? "#/k/" + M.mask.name : "#/" + (+p.mk ? "k" : "u") + "/" + p.name,
    calm = () => matchMedia("(prefers-reduced-motion:reduce)").matches,
    isText = !p.imgs.length && !(p.aq && !+p.pd);
  let root,
    stage,
    sheetEl,
    slideGo = null,
    off0 = false;
  /* ---------- like (button and double-tap) ---------- */
  const lcnt = h("span", {}, p.n || ""),
    lico = h("span", { class: "ico" }),
    lb = h("button", { type: "button", class: "rlb" + (p.me ? " on" : ""), "aria-pressed": String(!!p.me), "aria-label": "Mark with your sigil" });
  lico.innerHTML = SIGIL.replace('width="22" height="22"', 'width="28" height="28"');
  lb.append(lico, lcnt);
  likeSw(lb);
  const dvb = +p.mk && !mine ? h("button", { type: "button", class: "rlb dn" + (+p.dv ? " on" : ""), "aria-pressed": String(!!+p.dv), "aria-label": "Downvote this Masque post", title: "Downvote: takes a point off this Masque. Nobody is told who did it." }) : null;
  const doLike = async () => {
    try {
      await api("like", fd({ id: p.id, as: ASM && M.mask ? "mask" : null }));
      p.me = +!p.me;
      p.n += p.me ? 1 : -1;
      setN(lcnt, p.n || "", p.me);
      if (p.me && +p.dv) {
        p.dv = 0;
        if (dvb) {
          dvb.classList.remove("on");
          dvb.setAttribute("aria-pressed", "false");
        }
      }
      lb.classList.toggle("on", !!p.me);
      lb.setAttribute("aria-pressed", String(!!p.me));
      lico.classList.remove("pop", "unp");
      void lico.offsetWidth;
      if (p.me) {
        lico.classList.add("pop");
        slam("Marked", root.firstChild);
        laugh(root);
        buzz(lb);
      } else lico.classList.add("unp");
    } catch (x) {
      alert((x && x.e) || "Could not like.");
    }
  };
  lb.onclick = doLike;
  if (dvb) {
    const di = h("span", { class: "ico" });
    di.innerHTML = DOWN.replace('width="22" height="22"', 'width="26" height="26"');
    dvb.append(di);
    dvb.onclick = async () => {
      try {
        await api("dislike", fd({ id: p.id }));
        p.dv = +!+p.dv;
        if (p.dv && +p.me) {
          p.me = 0;
          p.n = Math.max(0, p.n - 1);
          setN(lcnt, p.n || "", false);
          lb.classList.remove("on");
          lb.setAttribute("aria-pressed", "false");
        }
        dvb.classList.toggle("on", !!p.dv);
        dvb.setAttribute("aria-pressed", String(!!p.dv));
        di.classList.remove("dpop", "unp");
        void di.offsetWidth;
        di.classList.add(p.dv ? "dpop" : "unp");
      } catch (x) {
        alert((x && x.e) || "Could not downvote.");
      }
    };
  }
  /* double-tap / double-click: a sigil bursts where you tapped; it only ever marks, never unmarks */
  const burst = (x, y) => {
    const b = h("span", { class: "dtl", "aria-hidden": "true", style: "left:" + x + "px;top:" + y + "px" });
    b.innerHTML = SIGIL;
    root.append(b);
    setTimeout(() => b.remove(), 900);
    laugh(root);
    if (!p.me) doLike();
  };
  /* ---------- save / link / comments buttons ---------- */
  p.sv = +p.sv;
  const sv = h("button", { type: "button", class: "rlb" + (p.sv ? " on" : ""), "aria-pressed": String(!!p.sv), "aria-label": p.sv ? "Unsave post" : "Save post" }, ic("bookmark", 26));
  sv.onclick = async () => {
    sv.disabled = true;
    try {
      const r = await api("save", fd({ id: p.id }));
      p.sv = +r.on;
      sv.classList.toggle("on", !!p.sv);
      sv.setAttribute("aria-pressed", String(!!p.sv));
      sv.setAttribute("aria-label", p.sv ? "Unsave post" : "Save post");
      sv.classList.remove("pop");
      void sv.offsetWidth;
      if (p.sv) sv.classList.add("pop");
    } catch (x) {
      alert((x && x.e) || "Could not save.");
    }
    sv.disabled = false;
  };
  const lk = shBtn(p, 26, "rlb");
  const cb = h("button", { type: "button", class: "rlb", "aria-label": "Comments", "aria-expanded": "false" });
  const cl = () => {
    cb.replaceChildren(ic("comment", 26), ...(p.cc ? [h("span", {}, p.cc)] : []));
    cb.setAttribute("aria-label", "Comments" + (p.cc ? ", " + p.cc : ""));
  };
  cl();
  /* ---------- the full comment list (a sheet inside the viewer) ---------- */
  const openSheet = () => {
    if (sheetEl) return;
    const panel = h("div", { class: "cmts" });
    sheetEl = h(
      "div",
      { class: "rlsheet", role: "dialog", "aria-label": "Comments" },
      h("div", { class: "rlsh" }, h("b", {}, "Comments"), h("button", { type: "button", class: "rlx", "aria-label": "Close comments", onclick: closeSheet }, ic("close", 20))),
      panel,
    );
    root.append(sheetEl);
    root.classList.add("cs");
    if (rlDock()) RLCS = 1;
    paintNav();
    cb.setAttribute("aria-expanded", "true");
    comments(p, panel, cl);
    void sheetEl.offsetWidth;
    sheetEl.classList.add("in");
  };
  const closeSheet = () => {
    if (!sheetEl) return;
    const s = sheetEl;
    sheetEl = null;
    root.classList.remove("cs");
    RLCS = 0;
    paintNav();
    cb.setAttribute("aria-expanded", "false");
    s.classList.remove("in");
    setTimeout(() => s.remove(), calm() ? 0 : 260);
  };
  cb.onclick = () => (sheetEl ? closeSheet() : openSheet());
  /* ---------- top: author, tags, caption, close ---------- */
  const meta = () => {
    const bits = [ago(p.ts)];
    if (+p.vis) bits.push(+p.vis === 2 ? "Only me" : "Friends");
    if (+p.pinned || +p.qp) bits.push("Pinned");
    if (+p.exp > 0) bits.push("Gone in " + left(p.exp));
    if (+p.hold) bits.push(mine ? "Waiting for review" : "Held for review");
    return bits.join(" \u00b7 ");
  };
  const pav = (() => {
    const a = p.anon ? (mine ? av(mm ? { avatar: M.mask.avatar } : p, 40) : av({}, 40)) : av(p, 40);
    if (ptg) {
      a.style.cursor = "pointer";
      a.setAttribute("role", "link");
      a.setAttribute("tabindex", "0");
      a.setAttribute("aria-label", "View profile of " + who);
      a.onclick = () => (location.hash = ptg);
      a.onkeydown = (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          location.hash = ptg;
        }
      };
    }
    return a;
  })();
  const capEl = h("p", { class: "rlcap" }),
    paintCap = () => {
      if (isText) {
        capEl.hidden = true;
        return;
      }
      capEl.hidden = !p.cap;
      rc(capEl, linkify(p.cap || ""), +p.ed ? edtBtn(p.id, " ") : null);
    };
  capEl.onclick = (e) => {
    if (e.target.closest("a,button")) return;
    capEl.classList.toggle("open");
  };
  paintCap();
  const more = h("button", { type: "button", class: "rlx", "aria-label": "Post options", "aria-haspopup": "dialog", onclick: () => postMenu(p, mine, () => { paintCap(); paintText(); }) }, ic("more", 22)),
    closeB = h("button", { type: "button", class: "rlx rlclose", "aria-label": "Close", onclick: () => (location.hash = to) }, ic("close", 24));
  const dots = p.imgs.length > 1 ? h("div", { class: "rldots", "aria-hidden": "true" }, ...p.imgs.map(() => h("i", {}))) : null;
  const top = h(
    "div",
    { class: "rltop" },
    dots,
    h(
      "div",
      { class: "rlhd" },
      pav,
      h(
        "div",
        { class: "rlwho" },
        h("b", ptg ? { onclick: () => (location.hash = ptg) } : {}, who, p.anon && mine ? h("span", { class: "rltag", title: "Only you can see this was you" }, "Masque to others") : null, p.anon || +p.mk ? h("span", { class: "lmst", title: "Masque post" }, lmAv(22)) : null),
        h("small", {}, meta()),
      ),
      more,
      closeB,
    ),
    p.aq ? h("div", { class: "rlq" }, h("small", {}, +p.pd > 0 ? "Prompt of the day" : "Anonymous question"), h("p", {}, p.aq)) : null,
    capEl,
  );
  /* ---------- middle: photos, or the text post, plus a poll ---------- */
  let tp = null,
    light = false;
  const paintText = () => {
    if (tp) {
      tp.hidden = !p.cap;
      tbRender(tp, p.cap, p.ed, +p.hg, p.id);
    }
  };
  if (p.imgs.length) {
    const track = h("div", { class: "rltrack" }, ...p.imgs.map((s, i) => h("div", { class: "rlsl" }, h("img", { class: "rlimg", src: "?img=" + s, alt: (p.alts && p.alts[i]) || (p.imgs.length > 1 ? "Photo " + (i + 1) + " of " + p.imgs.length : "Photo") + " by " + who, draggable: "false" }))));
    stage = h("div", { class: "rlst" }, h("div", { class: "rlbg", style: "background-image:url(?img=" + p.imgs[0] + ")" }), track);
    if (dots) {
      /* The white bars fill up one photo at a time, and when one is full the row scrolls to the next photo by itself. Holding the photo, opening comments or a menu, typing, or switching tabs pauses it. Swiping, dragging with the mouse or the left / right arrow keys move on by hand and restart the bar. The last photo just fills and stays. */
      const n = p.imgs.length,
        SLIDE_MS = 5000,
        segs = [...dots.children],
        width = () => Math.max(1, track.clientWidth);
      let idx = 0,
        el = -350,
        lastT = 0,
        raf = 0,
        held = 0,
        heldT = 0,
        animEnd = 0,
        snapT = 0,
        dragged = 0,
        md = null;
      const paint = () => segs.forEach((d, j) => d.style.setProperty("--p", j < idx ? 1 : j > idx ? 0 : calm() ? 1 : Math.max(0, Math.min(1, el / SLIDE_MS))));
      const blocked = () => {
        if (held && performance.now() - heldT < 20000) return true;
        if (document.hidden || sheetEl || (stage && stage.inert)) return true;
        const a = document.activeElement;
        if (a && root && root.contains(a) && /^(INPUT|TEXTAREA)$/.test(a.tagName)) return true;
        const im = track.children[idx] && track.children[idx].firstChild;
        if (im && im.complete === false) return true;
        return !!document.querySelector(".veil,.lb,dialog[open],.modal");
      };
      const kick = () => {
        if (raf || calm() || off0) return;
        lastT = 0;
        raf = requestAnimationFrame(tick);
      };
      const tick = (t) => {
        raf = 0;
        if (off0 || !root || !root.isConnected) return;
        const dt = lastT ? Math.min(100, t - lastT) : 0;
        lastT = t;
        if (!blocked()) {
          el += dt;
          if (el >= SLIDE_MS) {
            if (idx < n - 1) {
              goTo(idx + 1, true);
              return;
            }
            el = SLIDE_MS;
            segs[idx].style.setProperty("--p", 1);
            return;
          }
          segs[idx].style.setProperty("--p", Math.max(0, el / SLIDE_MS));
        }
        raf = requestAnimationFrame(tick);
      };
      const goTo = (i, smooth) => {
        i = Math.max(0, Math.min(n - 1, i));
        if (i !== idx) el = 0;
        idx = i;
        animEnd = performance.now() + (smooth ? 600 : 0);
        track.scrollTo({ left: i * width(), behavior: smooth ? "smooth" : "auto" });
        paint();
        kick();
      };
      slideGo = (d) => goTo(idx + d, true);
      const sync = () => {
        if (performance.now() < animEnd) return;
        const i = Math.max(0, Math.min(n - 1, Math.round(track.scrollLeft / width())));
        if (i !== idx) {
          idx = i;
          el = 0;
          paint();
          kick();
        }
      };
      track.addEventListener("scroll", sync, { passive: true });
      /* mouse: drag the photos sideways like a finger would (touch and trackpads already scroll the row on their own) */
      track.addEventListener("pointerdown", (e) => {
        if (e.pointerType !== "mouse" || e.button || e.target.closest("button,a")) return;
        clearTimeout(snapT);
        md = { x: e.clientX, sl: track.scrollLeft, t: performance.now(), id: e.pointerId, on: false, dx: 0 };
      });
      track.addEventListener("pointermove", (e) => {
        if (!md || e.pointerId !== md.id) return;
        if (!(e.buttons & 1)) return endDrag(e);
        const dx = e.clientX - md.x;
        if (!md.on) {
          if (Math.abs(dx) < 5) return;
          md.on = true;
          try {
            track.setPointerCapture(e.pointerId);
          } catch (x) {}
          track.style.scrollSnapType = "none";
          track.classList.add("drag");
        }
        md.dx = dx;
        track.scrollLeft = md.sl - dx;
      });
      const endDrag = (e) => {
        if (!md || (e && e.pointerId !== md.id)) return;
        const d = md;
        md = null;
        if (!d.on) return;
        dragged = performance.now();
        const w = width(),
          v = Math.abs(d.dx) / Math.max(1, performance.now() - d.t);
        let i = Math.round((d.sl - d.dx) / w);
        if (Math.abs(d.dx) > 40 && v > 0.35) i = Math.round(d.sl / w) + (d.dx < 0 ? 1 : -1);
        track.classList.remove("drag");
        goTo(i, true);
        snapT = setTimeout(() => (track.style.scrollSnapType = ""), 520);
      };
      track.addEventListener("pointerup", endDrag);
      track.addEventListener("pointercancel", endDrag);
      /* a drag that ends over a photo should not also count as a tap on it */
      track.addEventListener(
        "click",
        (e) => {
          if (performance.now() - dragged < 250) {
            e.stopPropagation();
            e.preventDefault();
          }
        },
        true,
      );
      /* hold to pause */
      stage.addEventListener("pointerdown", (e) => {
        if (e.target instanceof Element && e.target.closest("button,a,input")) return;
        held = 1;
        heldT = performance.now();
      });
      const rel = () => (held = 0);
      ["pointerup", "pointercancel", "lostpointercapture"].forEach((k) => stage.addEventListener(k, rel));
      paint();
      setTimeout(kick, 0);
    }
  } else {
    tp = isText ? h("div", { class: "tpost rltp", "data-bg": p.bg || "0" }) : null;
    /* light text-post backgrounds (and the default one in a light theme) get dark controls so nothing washes out */
    light = !!tp && lightBg(p.bg);
    stage = h("div", { class: "rlst" + (isText ? " txt" : "") }, tp);
    paintText();
    if (tp) {
      const chk = () => tp.classList.toggle("scr", tp.scrollHeight > tp.clientHeight + 24);
      requestAnimationFrame(() => requestAnimationFrame(chk));
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(chk);
      setTimeout(chk, 400);
      if (window.ResizeObserver) new ResizeObserver(chk).observe(tp);
    }
  }
  const pl = pollEl(p);
  if (pl) stage.append(h("div", { class: "rlpoll" }, pl));
  let sensBtn = null;
  if (+p.sens) {
    stage.inert = true;
    const sb = h("button", { type: "button", class: "rlsens", "aria-label": "Sensitive photo. Tap to view" }, h("b", {}, "Sensitive photo"), h("small", {}, +p.sens === 2 ? "A moderator marked this photo as sensitive" : "Marked as sensitive by the author"), h("span", {}, "Tap to view"));
    sb.onclick = () => {
      if (sb.classList.contains("out")) return;
      stage.inert = false;
      stage.classList.add("shown");
      sb.classList.add("out");
      setTimeout(() => sb.remove(), 500);
    };
    sensBtn = sb;
  }
  /* ---------- flying comments ---------- */
  const fly = h("div", { class: "rlfy", "aria-hidden": "true" });
  const seen = new Set();
  let first = true;
  const bubble = (c) => {
    if (sheetEl || off0) return;
    const nm = dn(c) || "Masque",
      el = h("div", { class: "rlc" }, av(c, 28), h("div", {}, h("b", {}, nm), h("span", {}, c.txt)));
    const kids = [...fly.children],
      before = kids.map((k) => k.getBoundingClientRect().top);
    el.style.rotate = (Math.random() * 2.4 - 1.2).toFixed(2) + "deg";
    fly.append(el);
    while (fly.children.length > 7) fly.firstChild.remove();
    if (calm()) {
      setTimeout(() => el.remove(), 6500);
      return;
    }
    kids.forEach((k, i) => {
      if (!k.isConnected) return;
      const d = before[i] - k.getBoundingClientRect().top;
      if (d) k.animate([{ transform: "translateY(" + d + "px)" }, { transform: "none" }], { duration: 380, easing: "cubic-bezier(.2,.9,.3,1)" });
    });
    el.animate(
      [
        { transform: "translateY(34px) scale(.9)", opacity: 0 },
        { transform: "none", opacity: 1 },
      ],
      { duration: 380, easing: "cubic-bezier(.2,1.2,.3,1)" },
    );
    const a = el.animate([{ opacity: 1 }, { opacity: 1, offset: 0.55 }, { opacity: 0 }], { duration: 9000, fill: "forwards" });
    a.onfinish = () => el.remove();
  };
  let queue = [],
    qt = 0;
  const pump = () => {
    if (qt || !queue.length) return;
    bubble(queue.shift());
    qt = setTimeout(
      () => {
        qt = 0;
        pump();
      },
      queue.length > 4 ? 260 : 650,
    );
  };
  const load = async () => {
    if (off0 || document.hidden) return;
    let r;
    try {
      r = await api("comments", null, "&pid=" + p.id);
    } catch (x) {
      return;
    }
    p.cc = r.comments.length;
    cl();
    const fresh = r.comments.filter((c) => !seen.has(+c.id));
    r.comments.forEach((c) => seen.add(+c.id));
    /* on opening, replay the latest few so the post feels alive; later only what is new */
    queue.push(...(first ? fresh.slice(-6) : fresh.slice(-8)));
    first = false;
    pump();
  };
  const timer = setInterval(() => {
    if (!root.isConnected) return clearInterval(timer);
    load();
  }, 5000);
  /* ---------- bottom: see-through comment box with your picture ---------- */
  const inp = h("input", { placeholder: "Add a comment\u2026", maxlength: 300, "aria-label": "Add a comment" }),
    go = h("button", { class: "rlsend", type: "submit", "aria-label": "Send comment" }, "Send"),
    err = h("p", { class: "rlerr", role: "alert" });
  go.disabled = true;
  inp.addEventListener("input", () => {
    go.disabled = !inp.value.trim();
  });
  const sw = maskSw(p, inp, "Comment") || av(M, 34);
  const form = h(
    "form",
    {
      class: "cform rlform",
      onsubmit: async (e) => {
        e.preventDefault();
        const t = inp.value.trim();
        if (!t) return;
        go.disabled = true;
        err.textContent = "";
        try {
          await api("comment", fd({ pid: p.id, txt: t, as: ASM && M.mask ? "mask" : null }));
          inp.value = "";
          await load();
        } catch (x) {
          err.textContent = x.e || "Could not send.";
        }
        go.disabled = !inp.value.trim();
        inp.focus({ preventScroll: true });
      },
    },
    sw,
    inp,
    go,
  );
  mentionPick(inp, mentionPeople);
  const vcr = vchip(p, "rlvw"),
    rail = h("div", { class: "rlrail" }, lb, dvb, cb, sv, lk, vcr),
    bot = h("div", { class: "rlbot" }, err, form);
  /* ---------- next / previous post (swipe up or down, wheel, arrow keys, J / K) ---------- */
  let paintNav = () => {};
  const nb = { next: null, prev: null, ok: 0, okp: 0 };
  let want = 0,
    wantT = 0;
  /* a swipe that came before the neighbouring post finished loading is remembered for a moment and done as soon as it arrives */
  const pending = () => {
    if (!want || performance.now() > wantT) return;
    const d = want;
    want = 0;
    setTimeout(() => goNav(d), Math.max(0, navLock - performance.now()) + 20);
  };
  const warm = (x) => {
    const m = x && ((x.imgs && x.imgs[0]) || x.img);
    if (m) {
      try {
        new Image().src = "?img=" + m;
      } catch (e) {}
    }
  };
  if (cx) {
    /* a failed request (weak signal) is tried again instead of being taken for "end of feed" */
    const look = (ex, set, tries) =>
      api("feed", null, cx.q + ex)
        .then((r) => set((r.posts || [])[0] || null))
        .catch(() => {
          if (tries > 0 && !off0) setTimeout(() => look(ex, set, tries - 1), 1200);
        });
    /* the post we just swiped away from is already known: it is the neighbour on the other side */
    if (dir < 0 && from) {
      nb.next = from;
      nb.ok = 1;
    } else
      look(
        "&before=" + p.id,
        (x) => {
          nb.next = x;
          nb.ok = 1;
          if (x) {
            warm(x);
            showHint();
          }
          pending();
          paintNav();
        },
        2,
      );
    if (dir > 0 && from) {
      nb.prev = from;
      nb.okp = 1;
    } else
      look(
        "&newer=" + p.id,
        (x) => {
          nb.prev = x;
          nb.okp = 1;
          pending();
          paintNav();
        },
        2,
      );
  }
  let navLock = performance.now() + (dir ? 380 : 450),
    endT = 0;
  const goNav = (d) => {
    const now = performance.now();
    if (now < navLock || !root.isConnected || off0 || (sheetEl && !rlDock())) return;
    if (document.querySelector(".veil,.lb,dialog[open],.modal")) return;
    const x = d > 0 ? nb.next : nb.prev;
    if (!x) {
      if (cx && !(d > 0 ? nb.ok : nb.okp)) {
        want = d;
        wantT = now + 2500;
        return;
      }
      if (d > 0 && nb.ok) {
        navLock = now + 700;
        clearTimeout(endT);
        const e = h("div", { class: "rlend" }, "You\u2019re all caught up");
        root.firstChild.append(e);
        endT = setTimeout(() => e.remove(), 1600);
      }
      return;
    }
    navLock = now + 450;
    dropHint();
    try {
      localStorage.setItem("mq-rlh2", "3");
    } catch (e) {}
    try {
      history.replaceState(null, "", "#/p/" + x.id);
      CURH = location.hash;
    } catch (e) {}
    reelView(x, to, cx, d, p);
  };
  /* "swipe up" tip: only shown when there is a next post, and only the first few times on this device. It goes away when you touch the screen or move on, and never comes back once you have swiped to another post. */
  let hint = null;
  const dropHint = () => {
    if (!hint) return;
    const k = hint;
    hint = null;
    k.classList.add("out");
    setTimeout(() => k.remove(), 260);
  };
  const showHint = () => {
    if (dir || hint || off0 || !root || !root.isConnected || sheetEl) return;
    let n = 0;
    try {
      n = +localStorage.getItem("mq-rlh2") || 0;
    } catch (e) {}
    if (n >= 3) return;
    try {
      localStorage.setItem("mq-rlh2", String(n + 1));
    } catch (e) {}
    const touch = matchMedia("(pointer:coarse)").matches;
    hint = h("div", { class: "rlhint", "aria-hidden": "true" }, h("div", { class: "rlhp" }, ic("chev", 18), h("span", {}, touch ? "Swipe up for next" : "Scroll or press J for next")));
    root.firstChild.append(hint);
    setTimeout(dropHint, 4400);
  };
  /* ---------- assemble ---------- */
  root = h("div", { class: "rl nolock" + (light ? " lt" : "") + (dir ? (dir > 0 ? " inu" : " ind") : ""), role: "dialog", "aria-modal": "true", "aria-label": "Post by " + who }, h("div", { class: "rlin" }, stage, top, fly, rail, bot));
  if (sensBtn) root.firstChild.append(sensBtn);
  /* PC: previous / next buttons beside the post, so it is clear you can move up and down (phones never show them, see the CSS) */
  if (cx) {
    const nbtn = (k, label, d) => h("button", { type: "button", class: "rlnb " + k, title: label, "aria-label": label, onclick: () => goNav(d) }, ic("chev", 22)),
      bu = nbtn("up", "Previous post (\u2191 or K)", -1),
      bd = nbtn("dn", "Next post (\u2193 or J)", 1);
    root.append(h("div", { class: "rlnav" }, bu, bd));
    paintNav = () => {
      const lock = !!sheetEl && !rlDock();
      bu.disabled = lock || !!(nb.okp && !nb.prev);
      bd.disabled = lock || !!(nb.ok && !nb.next);
    };
    paintNav();
  }
  /* double-tap on the post area (not on buttons, the poll, the box or the sheet) */
  let lt = 0,
    lx = 0,
    ly = 0,
    dx = 0,
    dy = 0;
  let swp = false,
    st0 = 0;
  root.addEventListener("pointerdown", (e) => {
    dropHint();
    dx = e.clientX;
    dy = e.clientY;
    st0 = Date.now();
    const sc = e.target instanceof Element && e.target.closest(".rltp.scr");
    swp = e.pointerType === "pen" && e.target instanceof Element && !e.target.closest("button,a,input,form,.rlsheet,.rlpoll,.rlsens,.rlcap.open") && (!sc || sc.scrollHeight <= sc.clientHeight + 24);
  });
  /* swipe up / down for the next / previous post. Uses touch events for the whole screen: pointer events are cancelled the moment the browser starts a pan (the photo row pans sideways), which made swipes fail now and then. A long post scrolls first; a swipe that started at its top or bottom edge and did not move it hands over to the next / previous post. */
  let tsc = null,
    tsy = 0,
    tsx = 0,
    tst = 0,
    tsTop = 0,
    tok = false;
  root.addEventListener(
    "touchstart",
    (e) => {
      tok = false;
      tsc = null;
      if (e.touches.length !== 1 || !(e.target instanceof Element)) return;
      if (e.target.closest("button,a,input,textarea,.rlsheet,.rlpoll,.rlsens,.rlcap.open")) return;
      const t = e.touches[0],
        sc = e.target.closest(".rltp.scr");
      tok = true;
      tsc = sc;
      tsy = t.clientY;
      tsx = t.clientX;
      tst = Date.now();
      tsTop = sc ? sc.scrollTop : 0;
    },
    { passive: true },
  );
  root.addEventListener(
    "touchcancel",
    () => {
      tok = false;
      tsc = null;
    },
    { passive: true },
  );
  root.addEventListener(
    "touchend",
    (e) => {
      const sc = tsc,
        ok = tok;
      tsc = null;
      tok = false;
      if (!ok || e.touches.length || !e.changedTouches.length) return;
      const t = e.changedTouches[0],
        mx = t.clientX - tsx,
        my = t.clientY - tsy,
        v = Math.abs(my) / Math.max(1, Date.now() - tst);
      if (!(Math.abs(my) > 36 && Math.abs(my) > Math.abs(mx) * 1.2 && (Math.abs(my) > 64 || v > 0.3))) return;
      if (sc) {
        const atTop = tsTop <= 1,
          atEnd = tsTop >= sc.scrollHeight - sc.clientHeight - 1;
        if (Math.abs(sc.scrollTop - tsTop) >= 2 || !((my < 0 && atEnd) || (my > 0 && atTop))) return;
      }
      lt = 0;
      goNav(my < 0 ? 1 : -1);
    },
    { passive: true },
  );
  root.addEventListener("pointerup", (e) => {
    if (e.pointerType === "mouse" && e.button) return;
    if (swp) {
      swp = false;
      const mx = e.clientX - dx,
        my = e.clientY - dy,
        v = Math.abs(my) / Math.max(1, Date.now() - st0);
      if (Math.abs(my) > 24 && Math.abs(my) > Math.abs(mx) * 1.5 && (Math.abs(my) > 80 || v > 0.45)) {
        lt = 0;
        goNav(my < 0 ? 1 : -1);
        return;
      }
    }
    if (!(e.target instanceof Element) || e.target.closest("button,a,input,form,.rlpoll,.rlsheet,.rlsens,.rltop,.rlbot,.rlrail,.rlcap,.rlq")) return;
    if (Math.hypot(e.clientX - dx, e.clientY - dy) > 12) return;
    const now = Date.now();
    if (now - lt < 320 && Math.hypot(e.clientX - lx, e.clientY - ly) < 70) {
      lt = 0;
      burst(e.clientX, e.clientY);
    } else {
      lt = now;
      lx = e.clientX;
      ly = e.clientY;
    }
  });
  const key = (e) => {
    if (!root.isConnected) return;
    if (e.ctrlKey || e.metaKey || e.altKey || document.querySelector(".veil,.lb,dialog[open],.modal")) return;
    if (e.key === "Escape") {
      if (sheetEl) closeSheet();
      else location.hash = to;
      return;
    }
    if (e.target instanceof Element && e.target.closest("input,textarea,select,[contenteditable]")) return;
    if (e.key === "ArrowDown" || e.key === "j" || e.key === "J") {
      e.preventDefault();
      goNav(1);
    } else if (e.key === "ArrowUp" || e.key === "k" || e.key === "K") {
      e.preventDefault();
      goNav(-1);
    } else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && slideGo && !sheetEl) {
      e.preventDefault();
      slideGo(e.key === "ArrowRight" ? 1 : -1);
    }
  };
  let wacc = 0,
    wt = 0;
  root.addEventListener(
    "wheel",
    (e) => {
      if (e.ctrlKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
      if (e.target instanceof Element && e.target.closest(".rlsheet,.rlpoll,.rlcap.open,input")) return;
      const sc = e.target instanceof Element && e.target.closest(".rltp.scr");
      if (sc) {
        const room = e.deltaY > 0 ? sc.scrollHeight - sc.clientHeight - sc.scrollTop : sc.scrollTop;
        if (room > 1) {
          wacc = 0;
          return;
        }
      }
      const n = performance.now();
      if (n - wt > 350) wacc = 0;
      wt = n;
      wacc += e.deltaY;
      if (Math.abs(wacc) >= 70) {
        const d = wacc > 0 ? 1 : -1;
        wacc = 0;
        goNav(d);
      }
    },
    { passive: true },
  );
  addEventListener("keydown", key);
  /* counts as a view once it has stayed open for a moment (swiping straight past does not count) */
  const vt = setTimeout(() => {
    if (root.isConnected && !off0 && !document.hidden) viewBump(p, vcr);
  }, dir ? 900 : 1200);
  root._off = () => {
    off0 = true;
    clearTimeout(vt);
    clearInterval(timer);
    clearTimeout(qt);
    removeEventListener("keydown", key);
  };
  /* a solid layer under the sliding screens, so the page behind (and its nav) never shows through the gap while posts swap */
  if (!document.querySelector(".rlbk:not(.gone)")) document.body.append(h("div", { class: "rlbk", "aria-hidden": "true" }));
  lpress(stage, () => postHold(p, mine, () => { paintCap(); paintText(); }, { like: () => lb.onclick(), save: () => sv.onclick(), comments: () => openSheet() }), "button,a,input,textarea,.rlpoll,.rlsens");
  if (!dir) rlOrigin(root);
  document.body.append(root);
  document.documentElement.classList.add("rlon");
  load();
  if (RLCS && dir && rlDock()) openSheet();
}
/* Keep scrolling on a post's page: below the post, the posts that come next in the feed you opened it from (Home tab, a profile, a tag, Saved, a Masque or a prompt day) keep loading, drawn exactly like the Home cards. It continues from the opened post, so what follows is the same order the list had. Opening a post from inside the stream keeps the same list. */
let PCTX = null;
function streamCtx() {
  const r = REF || "",
    fixed = (q, lab) => (PCTX = { q, lab, from: r });
  let m;
  if (/^#\/p\//.test(r) && PCTX) return PCTX;
  if ((m = r.match(/^#\/u\/(\w+)/))) return fixed("&u=" + encodeURIComponent(m[1]), "More from this profile");
  if ((m = r.match(/^#\/k\/(\w+)/))) return fixed("&k=" + encodeURIComponent(m[1]), "More from this Masque");
  if ((m = r.match(/^#\/t\/(\w+)/))) return fixed("&t=" + encodeURIComponent(m[1]), "More in #" + m[1].toLowerCase());
  if ((m = r.match(/^#\/d\/(\d+)/))) return fixed("&pd=" + m[1], "More answers");
  if (r === "#/saved") return fixed("&sv=1", "More saved posts");
  if ((m = r.match(/^#\/s\/(.+)/))) return fixed("&s=" + encodeURIComponent(dec(m[1])), "More results");
  return FEED === "foryou"
    ? fixed("&fy=1", "Next for you")
    : FEED === "friends"
    ? fixed("&f=1", "Next in Friends")
    : FEED === "following"
      ? fixed("&fl=1", "Next in Following")
      : fixed("", "Next in Home");
}
/* PC: flick the wheel a little at the bottom of a post for the next one, at the top for the previous one (or use the two buttons, or J / K). Short posts that fit the screen page straight away. Swaps the page in place so Back still leaves the whole run at once. Phones keep the endless list instead. */
function postPager(cur) {
  const cx = streamCtx(),
    nav = { prev: null, next: null },
    go = (id) => {
      if (!id) return;
      lock = performance.now() + 900;
      scrollTo(0, 0);
      location.replace("#/p/" + id);
    },
    mk = (dir, label, key) => {
      const b = h("button", { type: "button", class: "pgb " + dir, disabled: "", "aria-label": label, title: label + " (" + key + ")", onclick: () => go(nav[dir]) }, ic("chev", 18));
      return b;
    },
    pb = mk("prev", "Previous post", "K"),
    nb = mk("next", "Next post", "J"),
    hint = h("p", { class: "hint pghint" }, "Scroll down for the next post, up for the previous one"),
    box = h("div", { class: "pager2", "aria-label": cx.lab }, hint, h("div", { class: "pgbs" }, pb, nb));
  let lock = performance.now() + 500,
    acc = 0,
    accT = 0,
    lastNot = 0;
  requestAnimationFrame(() => scrollTo(0, 0));
  setTimeout(() => scrollTo(0, 0), 80);
  const q = (ex) => api("feed", null, cx.q + ex).then((r) => r.posts || []).catch(() => []);
  q("&newer=" + cur.id).then((r) => {
    if (r[0]) {
      nav.prev = r[0].id;
      pb.disabled = false;
    }
  });
  q("&before=" + cur.id).then((r) => {
    if (r[0]) {
      nav.next = r[0].id;
      nb.disabled = false;
    }
    hint.hidden = !r[0];
  });
  const busy = () => !!document.querySelector(".sheet,.veil,.lb,.gftv,.mqrev,.overlay,.viewer,dialog[open],.modal");
  const wheel = (e) => {
    if (!box.isConnected) return off();
    const now = performance.now();
    if (e.ctrlKey || e.deltaX && Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
    if (busy() || (e.target instanceof Element && e.target.closest("textarea,input,select,[contenteditable],.sheet,.veil,.lb"))) return;
    if (now < lock) {
      lock = Math.max(lock, now + 150);
      return;
    }
    const el = document.scrollingElement || document.documentElement,
      top = el.scrollTop <= 2,
      bot = el.scrollTop + innerHeight >= el.scrollHeight - 2,
      dir = e.deltaY > 0 ? "down" : "up",
      edge = dir === "down" ? bot : top;
    if (!edge) {
      lastNot = now; /* still scrolling inside the post: do not page until it has rested at the edge for a moment */
      acc = 0;
      return;
    }
    if (now - lastNot < 250) return;
    if (now - accT > 350) acc = 0;
    accT = now;
    acc += Math.abs(e.deltaY);
    if (acc >= 70) {
      acc = 0;
      const id = dir === "down" ? nav.next : nav.prev;
      if (id) go(id);
      else lock = now + 300;
    }
  };
  const key = (e) => {
    if (!box.isConnected) return off();
    if (e.ctrlKey || e.metaKey || e.altKey || busy() || (e.target instanceof Element && e.target.closest("input,textarea,select,[contenteditable]"))) return;
    if (e.key === "j" || e.key === "J") go(nav.next);
    else if (e.key === "k" || e.key === "K") go(nav.prev);
  };
  const off = () => {
    removeEventListener("wheel", wheel);
    removeEventListener("keydown", key);
  };
  addEventListener("wheel", wheel, { passive: true });
  addEventListener("keydown", key);
  return box;
}
function nextStream(first) {
  const cx = streamCtx(),
    box = h("section", { class: "nstream", "aria-label": cx.lab }),
    list = h("div", { class: "nslist" }),
    end = h("p", { class: "hint nsend", hidden: "" }, "You’re all caught up."),
    sent = h("div", { class: "nssent", "aria-hidden": "true" }),
    seen = new Set([String(first.id)]);
  box.append(h("div", { class: "nshead" }, h("span", {}, cx.lab), ic("chev", 14)), list, sent, end);
  let last = first.id,
    busy = false,
    done = false,
    io = null;
  const load = async () => {
    if (busy || done) return;
    if (!box.isConnected) return io && io.disconnect();
    busy = true;
    box.classList.add("busy");
    try {
      const r = await api("feed", null, cx.q + "&before=" + last);
      if (!box.isConnected) return;
      r.posts.forEach((p, i) => {
        last = p.id;
        if (seen.has(String(p.id))) return;
        seen.add(String(p.id));
        const c = card(p);
        c.classList.add("cut");
        c.style.setProperty("--i", Math.min(i, 5));
        list.append(c);
      });
      if (!r.more || !r.posts.length) {
        done = true;
        end.hidden = !list.children.length;
        if (io) io.disconnect();
      }
    } catch (e) {
      /* offline or an error: stop for now, scrolling up and down again retries */
    }
    busy = false;
    box.classList.remove("busy");
    /* the sentinel can still be on screen after a short batch: look again */
    if (!done && io && sent.isConnected) {
      io.unobserve(sent);
      io.observe(sent);
    }
  };
  if ("IntersectionObserver" in window) {
    io = new IntersectionObserver(
      (es) => {
        if (es.some((e) => e.isIntersecting)) load();
      },
      { rootMargin: "900px 0px" },
    );
    requestAnimationFrame(() => sent.isConnected && io.observe(sent));
  } else {
    const more = h("button", { class: "ghost", type: "button", style: "width:100%;margin-bottom:14px", onclick: load }, "Load more");
    box.insertBefore(more, end);
  }
  return box;
}
/* profile content: "Posts" (normal posts) and "Questions" (answers to anonymous questions) as two tabs */
function profTabs(name, u, pr) {
  const tb = h("div", { class: "tabs ptabs", role: "tablist" }),
    body = h("div"),
    enc = encodeURIComponent(name);
  let cur = "";
  const pick = async (k) => {
    if (k === cur) return;
    const was = cur;
    cur = k;
    [...tb.children].forEach((b) => b.setAttribute("aria-selected", String(b.dataset.k === k)));
    if (k === "p")
      body.replaceChildren(
        feedBox("&u=" + enc, pr, emp("image", "No posts yet", "When they post, you will see it here."), u.tpl),
      );
    else {
      body.replaceChildren(h("p", { class: "hint" }, "Loading\u2026"));
      let r;
      try {
        r = await api("feed", null, "&u=" + enc + "&tab=q");
      } catch (e) {
        if (cur === k) body.replaceChildren(emp("lock", "Unavailable", "Could not load answers."));
        return;
      }
      if (cur !== k) return;
      {
        const bx = feedBox(
          "&u=" + enc + "&tab=q",
          r,
          emp("ask", "No answered questions yet", "Anonymous questions they answer will show up here."),
        );
        bx.classList.add("qtab");
        body.replaceChildren(bx);
      }
    }
    if (was) swap(body, k === "q" ? 1 : -1);
  };
  [
    ["p", "Posts", u.posts],
    ["q", "Answered", u.qs],
  ].forEach(([k, l, n]) =>
    tb.append(
      h(
        "button",
        { role: "tab", "data-k": k, "aria-selected": "false", onclick: () => pick(k) },
        l,
        n == null ? null : h("small", { class: "tcnt" }, " " + n),
      ),
    ),
  );
  pick("p");
  const mine = u.name.toLowerCase() === M.name.toLowerCase();
  return h(
    "div",
    {},
    mine
      ? h(
          "div",
          { class: "ptrow" },
          tb,
          h(
            "button",
            {
              type: "button",
              class: "lpen",
              "aria-label": "Edit post layout",
              title: "Edit post layout",
              onclick: () => editProfile(u, "layout"),
            },
            ic("pencil", 18),
          ),
        )
      : tb,
    body,
  );
}
/* status line: a few words under the bio ("studying", "on a break") that clears itself 24 hours after it was set */
function statusLine(u, mine) {
  return null; /* an empty status on your own profile is now a ghost bubble over your avatar (see pbub) */
  if (u.status || !mine) return null;
  return h(
    "button",
    { type: "button", class: "pstatus mine nost", "aria-label": "Set a status", onclick: () => statusTextSheet(u) },
    h("i", { "aria-hidden": "true" }),
    "Set a status",
  );
}
/* status text: up to STMAX characters, with a live counter that warns near the limit and flashes when you hit it */
const STMAX = 100;
function statusTextSheet(u) {
  sheet("Status", (close) => {
    const inp = h("input", { type: "text", maxlength: STMAX, placeholder: "What are you up to?", "aria-label": "Status" }),
      msg = h("p", { class: "hint", role: "status" }),
      cnt = h("small", { class: "hint cnt stcnt", "aria-live": "polite" }),
      bar = h("i", { class: "stbar", "aria-hidden": "true" }),
      meter = h("div", { class: "stmeter" }, bar),
      upd = () => {
        const n = inp.value.length,
          left = STMAX - n;
        cnt.textContent = n >= STMAX ? "Limit reached \u00b7 " + n + " / " + STMAX : n + " / " + STMAX;
        cnt.classList.toggle("near", n >= STMAX * 0.8 && n < STMAX);
        cnt.classList.toggle("full", n >= STMAX);
        meter.classList.toggle("near", n >= STMAX * 0.8 && n < STMAX);
        meter.classList.toggle("full", n >= STMAX);
        bar.style.width = Math.min(100, (n / STMAX) * 100) + "%";
        cnt.setAttribute("aria-label", left > 0 ? left + " characters left" : "Character limit reached");
      },
      flash = () => {
        cnt.classList.remove("hit");
        meter.classList.remove("hit");
        void cnt.offsetWidth;
        cnt.classList.add("hit");
        meter.classList.add("hit");
      },
      save = async (v) => {
        msg.className = "hint";
        msg.textContent = "";
        try {
          const r = await api("setstatus", fd({ txt: v }));
          u.status = r.status;
          u.stleft = r.stleft;
          M.status = r.status;
          close();
          route();
        } catch (x) {
          msg.className = "err";
          msg.textContent = (x && x.e) || "Could not save.";
        }
      };
    inp.value = u.status || "";
    inp.addEventListener("input", upd);
    /* typing or pasting more than fits: the box quietly drops it, so flash the counter to show why */
    inp.addEventListener("beforeinput", (e) => {
      if (e.inputType && e.inputType.startsWith("insert") && inp.value.length >= STMAX && inp.selectionStart === inp.selectionEnd) flash();
    });
    inp.addEventListener("paste", () => {
      const before = inp.value;
      setTimeout(() => {
        if (inp.value.length >= STMAX && inp.value !== before) flash();
      }, 0);
    });
    upd();
    return h(
      "form",
      { class: "form", onsubmit: (e) => { e.preventDefault(); save(inp.value.trim()); } },
      h(
        "p",
        { class: "hint" },
        "Shows as a little chat bubble on your avatar. " +
          (u.status ? "Clears itself in about " + Math.max(1, Math.ceil((+u.stleft || 0) / 3600)) + "h." : "It clears itself after 24 hours."),
      ),
      inp,
      h("div", { class: "stfoot" }, meter, cnt),
      h("div", { class: "row", style: "flex-wrap:wrap;gap:6px" }, ...["Studying", "On a break", "Busy", "Gaming", "Out and about", "Sleeping", "Bored"].map((t) => h("button", { type: "button", class: "chip", onclick: () => { inp.value = t; inp.focus(); upd(); } }, t))),
      msg,
      h("div", { class: "row", style: "gap:10px" }, u.status ? h("button", { type: "button", class: "ghost", onclick: () => save("") }, "Clear") : null, h("button", { type: "submit", class: "btn", style: "flex:1" }, "Save")),
    );
  });
}
/* profile layouts: "card" moves the name block onto the banner; the sticky bar (on unless turned off) shows a small avatar + name once the header has scrolled away */
function profLayoutFx(u, cv) {
  try {
    if (profLayoutFx.off) profLayoutFx.off();
    profLayoutFx.off = null;
    const feed = document.querySelector(".feed"),
      me = feed && feed.querySelector(":scope > .me:not(.mrow)");
    if (!feed || !me) return;
    if (document.documentElement.dataset.pl === "card" && cv && cv.isConnected) {
      me.classList.add("pmv");
      cv.append(me);
    }
    let on = true;
    try {
      on = localStorage.getItem("mq-pc") !== "0";
    } catch (e) {}
    if (!on || !("IntersectionObserver" in window)) return;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches,
      bar = h(
        "button",
        {
          type: "button",
          class: "pbar",
          tabindex: "-1",
          "aria-label": "Back to the top of " + dn(u) + "'s profile",
          onclick: () => scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" }),
        },
        av(u, 28),
        h("b", {}, dn(u)),
        h("span", { class: "pbup", "aria-hidden": "true" }, ic("back", 16)),
      ),
      place = () => {
        const r = feed.getBoundingClientRect();
        bar.style.left = r.left + 8 + "px";
        bar.style.width = Math.max(0, r.width - 16) + "px";
      },
      io = new IntersectionObserver(
        ([e]) => {
          const v = !e.isIntersecting && e.boundingClientRect.bottom < 0;
          if (v) place();
          bar.classList.toggle("on", v);
        },
        { threshold: 0 },
      ),
      off = () => {
        io.disconnect();
        removeEventListener("resize", place);
        bar.remove();
      };
    place();
    document.body.append(bar);
    io.observe(me);
    addEventListener("resize", place);
    addEventListener("hashchange", off, { once: true });
    profLayoutFx.off = off;
  } catch (e) {}
}
/* the Experimental switch: game invites + profile designs. Reloads so every screen redraws with the new setting. */
function experimentalCard() {
  const c = h("input", { type: "checkbox", style: "width:auto" }),
    all = M.admin ? h("input", { type: "checkbox", style: "width:auto" }) : null,
    err = h("span", { class: "err", role: "alert" });
  c.checked = !!(+M.xp || +M.xpall);
  /* if the admin switch is on, everybody has it, so the personal switch cannot turn it off */
  c.disabled = !!+M.xpall;
  c.onchange = async () => {
    try {
      M = (await api("setxp", fd({ on: c.checked ? 1 : 0 }))).me;
    } catch (e) {
      c.checked = !c.checked;
      err.textContent = e.e || "Could not save this.";
    }
  };
  if (all) {
    all.checked = !!+M.xpall;
    all.onchange = async () => {
      try {
        M = (await api("xpall", fd({ on: all.checked ? 1 : 0 }))).me;
      } catch (e) {
        all.checked = !all.checked;
        err.textContent = e.e || "Could not save this.";
      }
    };
  }
  return h(
    "div",
    { class: "card" },
    h("h3", {}, "Experimental"),
    h("label", { class: "chk" }, c, " Show experimental features"),
    all ? h("label", { class: "chk", style: "margin-top:10px" }, all, " Admin: turn on for everyone") : null,
    err,
    h(
      "p",
      { class: "hint" },
      "Turns on game invites in chats and the profile layout choices (Compact, Banner card). Off keeps game invites hidden and profiles in the classic layout. Saved to your account, so it follows you to every device.",
    ),
  );
}
function profileLayoutPick() {
  const L = [["", "Compact"], ["card", "Banner card"], ["classic", "Classic"]];
  let cur = "",
    pc = true;
  try {
    cur = localStorage.getItem("mq-pl") || "";
    pc = localStorage.getItem("mq-pc") !== "0";
  } catch (e) {}
  const row = h("div", { class: "row", role: "group", "aria-label": "Profile layout" }),
    set = (k) => {
      try {
        k ? localStorage.setItem("mq-pl", k) : localStorage.removeItem("mq-pl");
      } catch (e) {}
      k ? (document.documentElement.dataset.pl = k) : delete document.documentElement.dataset.pl;
      [...row.children].forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.k === k)));
    };
  L.forEach(([k, l]) => row.append(h("button", { type: "button", class: "ghost", "data-k": k, "aria-pressed": String(cur === k), onclick: () => set(k) }, l)));
  const c = h("input", { type: "checkbox", style: "width:auto" });
  c.checked = pc;
  c.onchange = () => {
    try {
      c.checked ? localStorage.removeItem("mq-pc") : localStorage.setItem("mq-pc", "0");
    } catch (e) {}
  };
  return h(
    "div",
    { class: "setrow" },
    h("b", { style: "display:block;margin-bottom:8px" }, "Profile layout"),
    row,
    h("p", { class: "hint" }, "Compact keeps the top of a profile short. Banner card puts the name and counts on the cover photo. Classic is the original look."),
    h("label", { class: "chk", style: "margin-top:10px" }, c, " Small name bar when you scroll down a profile"),
    h("p", { class: "hint" }, "Saved on this device only."),
  );
}
async function profile(name) {
  const h0 = location.hash;
  let u, pr;
  try {
    [{ u }, pr] = await Promise.all([
      api("user", null, "&u=" + encodeURIComponent(name)),
      api("feed", null, "&u=" + encodeURIComponent(name)),
    ]);
  } catch (e) {
    setPT(null);
    shell(emp("search", "No such account", "Check the spelling and try again."));
    return;
  }
  const mine = u.name.toLowerCase() === M.name.toLowerCase(),
    go = SHOWN !== location.hash;
  setPT(u);
  refineTitle(h0, mine ? "Profile" : u.nick ? u.nick + " (@" + u.name + ")" : "@" + u.name);
  const cv = h("div", { class: "cover" + (u.cover ? "" : " plain") + (go ? " cut2" : "") }, batFlock("f"));
  {
    const f = bfx(u.tcf || "", u.taf || "");
    if (/^\w+$/.test(f)) cv.dataset.cf = f;
  }
  if (mine)
    cv.append(
      h(
        "button",
        {
          class: "pen cpen",
          "aria-label": "Edit cover photo",
          title: "Edit cover photo",
          onclick: () => editProfile(u, "cover"),
        },
        ic("pencil", 16),
      ),
    );
  if (u.cover) {
    const ci = h("div", { class: "cvimg" });
    ci.style.backgroundImage = `url(?img=${u.cover})`;
    ci.style.backgroundPosition = "50% " + (u.cy ?? 50) + "%";
    cv.prepend(ci);
    const im = new Image(),
      on = () => requestAnimationFrame(() => ci.classList.add("on"));
    im.onload = on;
    im.onerror = on;
    im.src = "?img=" + u.cover;
    if (im.complete) on();
    zoomable(cv, "?img=" + u.cover, u.name + "'s cover photo");
  }
  const pav0 = av(u, 92),
    pbub = u.status || !mine
      ? sbub(u.status, "ps", (e) => {
          if (mine) statusTextSheet(u);
          else e.currentTarget.classList.toggle("open");
        })
      : sbub("Set your status", "ps ghost", () => statusTextSheet(u)),
    pav = h("div", { class: "pavw" }, pav0, batFlock("o"), pbub, strProfileChip(u.streak));
  if (u.avatar) zoomable(pav0, "?img=" + u.avatar, u.name + "'s profile photo");
  shell([
    cv,
    h(
      "div",
      { class: "me" + (go ? " intro" : "") },
      mine
        ? h(
            "div",
            { class: "avwrap" },
            pav,
            h(
              "button",
              { class: "pen", "aria-label": "Edit profile", title: "Edit profile", onclick: () => editProfile(u) },
              ic("pencil", 16),
            ),
          )
        : pav,
      h(
        "div",
        {},
        h("h1", { class: "kt", "aria-label": dn(u) }, go ? kin(dn(u)) : dn(u)),
        u.nick ? h("p", { class: "hint" }, "@" + u.name) : null,
        h("p", { class: "pbio", onclick: (e) => e.currentTarget.classList.toggle("open") }, u.bio || "No bio yet."),
        statusLine(u, mine),
        h(
          "p",
          { class: "pstats" },
          h("span", {}, h("b", {}, u.posts), " posts"),
          u.locked
            ? h("span", {}, h("b", {}, u.friends), " friends")
            : h(
                "button",
                {
                  type: "button",
                  class: "pstat",
                  "aria-label": u.friends + " friends. See who they are",
                  onclick: () => (mine ? (location.hash = "#/f") : friendsOf(u)),
                },
                h("b", {}, u.friends),
                " friends",
              ),
          ...(+u.priv
            ? []
            : [
                h(
                  "button",
                  { type: "button", class: "pstat", "aria-label": u.followers + " followers. See who they are", onclick: () => followList(u, "followers") },
                  h("b", {}, u.followers),
                  " followers",
                ),
                h(
                  "button",
                  { type: "button", class: "pstat", "aria-label": "Following " + u.following + ". See who they follow", onclick: () => followList(u, "following") },
                  h("b", {}, u.following),
                  " following",
                ),
              ]),
          +u.priv ? h("span", { class: "pprv" }, ic("lock", 12), "Private") : null,
        ),
      ),
    ),
    mine
      ? h(
          "div",
          { class: "row prow" },
          h(
            "button",
            { class: "ghost", onclick: () => askInbox() },
            ic("ask", 16),
            "Inbox" + (+u.asks ? " (" + u.asks + ")" : ""),
          ),
          h(
            "button",
            {
              class: "ghost ibtn",
              type: "button",
              title: "Saved",
              "aria-label": "Saved",
              onclick: () => (location.hash = "#/saved"),
            },
            ic("bookmark", 18),
          ),
          h(
            "button",
            {
              class: "ghost ibtn",
              type: "button",
              title: "Settings",
              "aria-label": "Settings",
              onclick: () => (location.hash = "#/settings"),
            },
            ic("settings", 18),
          ),
          shareBtn(u),
        )
      : h(
          "div",
          { class: "row orow" },
          ...(u.blocked
            ? [h("button", { class: "ghost", onclick: fcall("unblock", u.name) }, "Unblock " + u.name)]
            : [
                ...friendBtns(u),
                ...followBtn(u),
                h(
                  "button",
                  {
                    class: "ghost msgb",
                    ...(u.dm === "friends" && u.rel !== "friends"
                      ? { disabled: "", title: "Only friends can message this person" }
                      : {}),
                    onclick: () => (location.hash = "#/m/" + u.name),
                  },
                  "Message",
                ),
                h(
                  "button",
                  {
                    type: "button",
                    class: "ghost ibtn",
                    title: "More",
                    "aria-label": "More options",
                    onclick: () => profMore(u),
                  },
                  ic("more", 18),
                ),
              ]),
        ),
    askBox(u),
    +u.locked ? emp("lock", "This account is private", "Become friends to see their posts.") : profTabs(name, u, pr),
  ]);
  profLayoutFx(u, cv);
  if (mine && ASKOPEN) {
    ASKOPEN = false;
    askInbox();
  }
}
/* share a profile: the link is /u/name so link previews (which never see the #) can show who it is; the page then opens #/u/name */
/* the less-used actions on someone else's profile live behind one "..." button so the profile stays quiet */
function profMore(u) {
  sheet("More", (close) => {
    const row = (l, i, fn, cls) =>
      h(
        "button",
        {
          type: "button",
          class: "ghost mrow2" + (cls ? " " + cls : ""),
          onclick: () => {
            close();
            fn();
          },
        },
        ic(i, 16),
        l,
      );
    return h(
      "div",
      { class: "form" },
      row("Share profile", "share", async () => {
        const url = location.origin + BASE + "u/" + encodeURIComponent(u.name);
        if (navigator.share) {
          try {
            await navigator.share({ title: dn(u) + " on Masque", url });
            return;
          } catch (e) {
            if (e && e.name === "AbortError") return;
          }
        }
        try {
          await navigator.clipboard.writeText(url);
          slam("Link copied");
        } catch (e) {
          prompt("Copy this link", url);
        }
      }),
      row("Report", "shield", () => reportSheet("user", u.name)),
      M.admin ? row("Send a gift (admin)", "gift", () => giveSheet(u)) : null,
      M.admin ? row("Give Sigils (admin)", "gift", () => sigilSheet(u.name)) : null,
      row(
        "Block",
        "lock",
        () =>
          fcall(
            "block",
            u.name,
            "Block " + u.name + "? You will not see each other\u2019s posts, comments or messages, and any friendship ends.",
          )(),
        "dng",
      ),
    );
  });
}
/* admin: give (or take back) theme items such as backgrounds, patterns, fonts and frames. A gift works even if the person has not earned it, and it also works for Castle Night items after the event ended. */
const XK = {
    tbg: ["x_void", "x_inferno", "x_cyber", "x_vapor", "x_abyss", "x_gilded", "x_nebula", "x_higan", "x_mardi", "x_moonlit", "x_csig"],
    tbp: ["x_synth", "x_matrix", "x_embers", "x_cosmos", "x_scan", "x_lilies", "x_centi", "x_csigil", "x_cscript"],
    tcd: ["x_crystal", "x_csigc"],
    taf: ["x_nova", "x_hell", "x_voidf", "x_sov", "x_higanf", "x_csigf"],
    tcf: ["x_aurora", "x_fire", "x_voidb", "x_chrome", "x_centib", "x_csigb"],
  },
  /* one-tap packs in the Give items sheet */
  PACKS = {
    "Higanbana pack": [["tbg", "x_higan"], ["tbp", "x_lilies"], ["tbp", "x_centi"], ["taf", "x_higanf"], ["tcf", "x_centib"]],
    "Cybersigilism pack": [["tbg", "x_csig"], ["tbp", "x_csigil"], ["tbp", "x_cscript"], ["tcd", "x_csigc"], ["taf", "x_csigf"], ["tcf", "x_csigb"]],
  },
  GL = () => ({ tbg: PBG, tbp: PBP, tcd: PCD, tfn: PFN, tas: PAS, taf: PAF, tcf: PBF }),
  GIVEN = { tbg: "Background", tbp: "Pattern", tcd: "Card", tfn: "Font", tas: "Avatar shape", taf: "Avatar frame", tcf: "Banner frame" };
/* admin: give (or take back, with a minus) Sigils. The name can be yours. */
/* admin: see the admins and moderators, make someone a moderator, or take it away again */
function staffSheet() {
  sheet("Moderators", (close) => {
    const box = h("div", { class: "form" }),
      msg = h("p", { class: "hint", role: "status" }),
      who = h("input", { type: "text", maxlength: 20, placeholder: "Username", "aria-label": "Username", autocapitalize: "off", autocomplete: "off" }),
      set = async (name, role) => {
        msg.className = "hint";
        msg.textContent = "";
        try {
          await api("setrole", fd({ name, role }));
          who.value = "";
          await load();
        } catch (x) {
          msg.className = "err";
          msg.textContent = (x && x.e) || "Could not do that.";
        }
      },
      person = (u, canRemove) =>
        h("div", { class: "row", style: "justify-content:space-between;align-items:center" }, h("span", {}, "@" + u.name), canRemove ? h("button", { type: "button", class: "ghost", onclick: () => set(u.name, "user") }, "Remove") : h("span", { class: "hint" }, "admin")),
      load = async () => {
        let r;
        try {
          r = await api("staff");
        } catch (x) {
          box.replaceChildren(h("p", { class: "err" }, (x && x.e) || "Could not load."));
          return;
        }
        box.replaceChildren(
          h("p", { class: "hint" }, "Moderators can work the reports queue, answer appeals and suspend accounts for up to 30 days. They cannot ban, delete accounts or change site settings."),
          h("b", {}, "Admins"),
          ...r.admins.map((u) => person(u, false)),
          h("b", {}, "Moderators"),
          ...(r.mods.length ? r.mods.map((u) => person(u, true)) : [h("p", { class: "hint" }, "No moderators yet.")]),
          who,
          h("button", { type: "button", class: "btn full", onclick: () => who.value.trim() && set(who.value.trim(), "mod") }, "Make moderator"),
          msg,
        );
      };
    load();
    return box;
  });
}
function sigilSheet(name) {
  sheet("Give Sigils", (close) => {
    const who = h("input", { type: "text", value: name || M.name, maxlength: 20, "aria-label": "Username", autocapitalize: "off", autocomplete: "off" }),
      amt = h("input", { type: "number", inputmode: "numeric", step: "1", placeholder: "Amount", "aria-label": "Amount of Sigils" }),
      msg = h("p", { class: "hint", role: "status" }),
      go = h("button", { type: "submit", class: "btn full" }, "Give Sigils");
    return h(
      "form",
      {
        class: "form",
        onsubmit: async (e) => {
          e.preventDefault();
          go.disabled = true;
          msg.className = "hint";
          msg.textContent = "";
          try {
            const r = await api("sgive", fd({ u: who.value.trim(), n: String(parseInt(amt.value, 10) || 0) }));
            if (r.name.toLowerCase() === M.name.toLowerCase()) await unlLoad();
            msg.textContent = "Done. @" + r.name + " now has " + r.bal + " Sigils.";
            amt.value = "";
            if (location.hash.startsWith("#/settings")) route();
          } catch (x) {
            msg.className = "err";
            msg.textContent = (x && x.e) || "Could not give Sigils.";
          }
          go.disabled = false;
        },
      },
      h("p", { class: "hint" }, "Gives Sigils to anyone, including yourself. Use a minus to take some back."),
      who,
      amt,
      h("div", { class: "row", style: "flex-wrap:wrap;gap:6px" }, ...[50, 100, 500, 1000].map((n) => h("button", { type: "button", class: "chip", onclick: () => { amt.value = n; } }, "+" + n))),
      msg,
      go,
    );
  });
}
async function giveSheet(u) {
  let gr = [];
  try {
    if (!UNL) UNL = await api("unl");
    gr = (await api("agrants", null, "&u=" + encodeURIComponent(u.name))).gr;
  } catch (x) {
    alert((x && x.e) || "Could not load.");
    return;
  }
  sheet("Send a gift", () => {
    const sel = new Set(),
      paints = [],
      msg = h("input", { type: "text", maxlength: 140, placeholder: "Add a note (optional)", "aria-label": "Gift note" }),
      st = h("p", { class: "hint", role: "status" }),
      send = h("button", { type: "button", class: "btn full" }),
      upd = () => {
        send.disabled = !sel.size;
        send.textContent = sel.size ? "Send gift (" + sel.size + (sel.size === 1 ? " item)" : " items)") : "Pick something to send";
        paints.forEach((f) => f());
      },
      wrap = h(
        "div",
        { class: "form gvs" },
        h("p", { class: "hint" }, "Tick everything you want to put in the box, then send it. @" + u.name + " gets a notification and opens it like a present. Gifts skip the unlock requirements."),
      );
    Object.entries(PACKS).forEach(([nm, items]) => {
      const pb = h("button", { type: "button", class: "ghost" }, "\u2605 Add the " + nm);
      pb.onclick = () => {
        items.forEach(([k, id]) => !gr.includes(k + ":" + id) && sel.add(k + ":" + id));
        upd();
      };
      wrap.append(pb);
    });
    Object.keys(GIVEN).forEach((k) => {
      const ids = [...new Set([...Object.keys((UNL.req || {})[k] || {}), ...(EVK[k] || []), ...(XK[k] || [])])];
      if (!ids.length) return;
      const lab = (id) => ((GL()[k] || []).find((a) => a[0] === id) || [0, id])[1];
      wrap.append(
        h("h3", { class: "vt" }, GIVEN[k]),
        h(
          "div",
          { class: "row", style: "flex-wrap:wrap;gap:6px" },
          ...ids.map((id) => {
            const key = k + ":" + id,
              b = h("button", { type: "button", class: "ghost" }, (/^x_/.test(id) ? "\u2605 " : "") + lab(id));
            const paint = () => {
              const has = gr.includes(key);
              b.classList.toggle("gvh", has);
              b.setAttribute("aria-pressed", String(sel.has(key)));
              b.title = has ? "Already gifted. Tap to take it back." : "";
              if (has) b.dataset.has = "\u2713";
              else delete b.dataset.has;
            };
            b.onclick = async () => {
              if (gr.includes(key)) {
                if (!(await cbox("Take back " + lab(id) + " from @" + u.name + "?"))) return;
                b.disabled = true;
                try {
                  gr = (await api("agive", fd({ u: u.name, k, id, on: 0 }))).gr;
                } catch (x) {
                  alert((x && x.e) || "Could not save.");
                }
                b.disabled = false;
              } else sel.has(key) ? sel.delete(key) : sel.add(key);
              upd();
            };
            paints.push(paint);
            return b;
          }),
        ),
      );
    });
    send.onclick = async () => {
      send.disabled = true;
      st.className = "hint";
      st.textContent = "";
      try {
        const r = await api("agift", fd({ u: u.name, items: [...sel].join(","), msg: msg.value }));
        gr = r.gr;
        sel.clear();
        msg.value = "";
        upd();
        st.className = "hint ok";
        st.textContent = "Gift sent (" + r.n + (r.n === 1 ? " item" : " items") + ").";
      } catch (x) {
        st.className = "err";
        st.textContent = (x && x.e) || "Could not send.";
        send.disabled = !sel.size;
      }
    };
    wrap.append(h("div", { class: "gvsend" }, h("label", { class: "f" }, "Note", msg), send, st));
    upd();
    return wrap;
  });
}
function shareBtn(u) {
  const url = location.origin + BASE + "u/" + encodeURIComponent(u.name),
    b = h(
      "button",
      { class: "ghost ibtn shbtn", type: "button", title: "Share profile", "aria-label": "Share profile" },
      ic("share", 18),
    ),
    lab = (t) => {
      b.replaceChildren(ic("check", 18));
      b.title = "Link copied";
      setTimeout(() => {
        b.replaceChildren(ic("share", 18));
        b.title = "Share profile";
      }, 1500);
    };
  b.onclick = async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title: dn(u) + " on Masque", url });
        return;
      } catch (e) {
        if (e && e.name === "AbortError") return;
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      lab("Copied");
    } catch (e) {
      prompt("Copy this link", url);
    }
  };
  return b;
}
/* sheets */
/* who can see a post: Everyone / Friends / Only me. Friends is off for Masque posts (it would show whose Masque it is). */
function visPick(init, onpick) {
  let v = +init || 0,
    fr = true;
  const row = h("div", { class: "vis", role: "radiogroup", "aria-label": "Who can see this post" }),
    defs = [
      [0, "Everyone", "Anyone who can see your profile"],
      [1, "Friends", "Only your friends"],
      [2, "Only me", "Only you, like a private note"],
    ],
    bs = defs.map(([k, l, t]) =>
      h("button", { type: "button", class: "vbtn", role: "radio", title: t, onclick: () => set(k, 1) }, l),
    ),
    paint = () =>
      bs.forEach((b, i) => {
        b.setAttribute("aria-checked", String(i === v));
        b.disabled = i === 1 && !fr;
        b.title = i === 1 && !fr ? "Not available for Masque posts" : defs[i][2];
      }),
    set = (k, u) => {
      if (k === 1 && !fr) return;
      v = k;
      paint();
      if (u && onpick) onpick(v);
    };
  row.append(...bs);
  paint();
  return {
    el: h("div", { class: "visrow" }, h("small", { class: "hint" }, "Who can see this"), row),
    get: () => v,
    set: (k) => set(k, 0),
    noFriends: (b) => {
      fr = !b;
      if (b && v === 1) {
        v = 0;
        if (onpick) onpick(0);
      }
      paint();
    },
  };
}
function newPost(pr) {
  if (!pr || typeof pr.text !== "string") pr = null;
  sheet("New post", (close, veil) => {
    let L = [],
      bg = 0,
      hg_ = true,
      tprev = null,
      swrow = null,
      Q = Promise.resolve();
    const MAXI = 10;
    const grid = h("div", { class: "pgrid pedit", hidden: "" }),
      hint = h("p", { class: "hint pehint", hidden: "" }, "Drag photos to reorder them. The first one is the cover."),
      cap = h("textarea", { rows: 3, maxlength: 300, placeholder: "Write a caption…", "aria-label": "Caption" }),
      cnt = h("p", { class: "hint cnt" }, "0 / 300"),
      err = h("p", { class: "err", role: "alert" }),
      btn = h("button", { class: "btn full", type: "submit" }, "Share");
    const upd = () => {
      try {
        hgRow.hidden = !!L.length;
      } catch (e) {}
      btn.disabled = !L.length && !cap.value.trim();
      cnt.textContent = cap.value.length + " / 300";
      cnt.classList.toggle("warn", cap.value.length >= 270);
      if (tprev) {
        tprev.hidden = !!L.length;
        swrow.hidden = !!L.length;
        if (!L.length) {
          const e = !cap.value.trim();
          tprev.classList.toggle("empty", e);
          tbRender(tprev, e ? "Big first word, then the smaller rest" : cap.value, 0, hg_ && !e);
        }
      }
    };
    upd();
    cap.oninput = upd;
    mentionPick(cap, mentionPeople, true);
    const VP = visPick(0, () => sv()),
      tipEl = h("p", { class: "hint opttip", role: "status", hidden: "" }),
      showTip = (t) => {
        tipEl.textContent = t;
        tipEl.hidden = !t;
      },
      OPT = (inp, label, tip) => {
        const l = h("label", { class: "opt", title: tip }, inp, h("span", {}, label));
        inp.addEventListener("change", () => {
          l.classList.toggle("on", inp.checked);
          showTip(inp.checked ? tip : "");
        });
        return l;
      };
    const an = h("input", { type: "checkbox" }),
      anRow = OPT(
        an,
        [lmIcon(16), "Masque"],
        M.mask
          ? "Posts as your Masque: its name and photo show to everyone, with the laughing mask on the post. Other people are not shown that it is you."
          : "Create your Masque: a second profile that posts under its own name and photo, with the laughing mask on every post.",
      ),
      hgc = h("input", { type: "checkbox", checked: "" }),
      hgRow = OPT(
        hgc,
        "Huge text",
        "Short text posts (up to 4 words) show as big poster text in List and Big card. Turn it off for the normal look.",
      ),
      hk0 =
        ((hgc.checked = true),
        hgRow.classList.add("on"),
        hgc.addEventListener("change", () => {
          hg_ = hgc.checked;
          upd();
        })),
      sn = h("input", { type: "checkbox" }),
      guard = an.addEventListener("change", () => {
        if (!M.mask && an.checked) {
          an.checked = false;
          anRow.classList.remove("on");
          showTip("");
          maskSheet(() => {
            an.checked = true;
            anRow.classList.add("on");
            showTip(
              "Posts as your Masque: its name and photo show to everyone, with the laughing mask on the post. Other people are not shown that it is you.",
            );
          });
        }
      }),
      snRow = OPT(sn, "Sensitive photo", "Blurs the photo until someone taps it."),
      mk0 = an.addEventListener("change", () => VP.noFriends(an.checked)),
      inp = h("input", { type: "file", accept: "image/*", multiple: "", hidden: "", "aria-label": "Photos" }),
      z = h("button", { type: "button", class: "drop" }, "Add photos (up to " + MAXI + ")");
    snRow.hidden = true;
    /* start reading each picked photo right away (phones can lose access to a file later), but shrink them one at a time so ten photos never fill the phone's memory */
    const qprep = (f) => {
      const rd = readable(f);
      rd.catch(() => {});
      const p = Q.then(async () => shrink(await rd));
      Q = p.catch(() => {});
      return p;
    };
    const draw = () => {
      grid.replaceChildren(
        ...L.map((it, i) => {
          const t = h(
            "div",
            {
              class: "pthumb",
              role: "group",
              "aria-label": "Photo " + (i + 1) + " of " + L.length + (L.length > 1 ? ". Drag to reorder." : ""),
            },
            h("img", { src: it.url, alt: "Photo " + (i + 1) }),
            i === 0
              ? L.length > 1
                ? h("span", { class: "pcov" }, "Cover")
                : null
              : h(
                  "button",
                  {
                    type: "button",
                    class: "pset",
                    "aria-label": "Make photo " + (i + 1) + " the cover",
                    onclick: () => {
                      L.unshift(L.splice(i, 1)[0]);
                      draw();
                    },
                  },
                  "Set cover",
                ),
            altBtn(it, i, draw),
            h(
              "button",
              {
                type: "button",
                "aria-label": "Remove photo " + (i + 1),
                onclick: () => {
                  URL.revokeObjectURL(it.url);
                  L.splice(i, 1);
                  draw();
                  upd();
                },
              },
              ic("close", 14),
            ),
          );
          if (L.length > 1) pdrag(t, i, grid, (x, y) => L.splice(y, 0, L.splice(x, 1)[0]), draw);
          return t;
        }),
      );
      hint.hidden = L.length < 2;
      grid.hidden = !L.length;
      snRow.hidden = !L.length;
      z.disabled = L.length >= MAXI;
      z.textContent = !L.length
        ? "Add photos (up to " + MAXI + ")"
        : L.length >= MAXI
          ? "Photo limit reached (" + MAXI + ")"
          : "Add more photos (" + L.length + " / " + MAXI + ")";
    };
    const add = (fs) => {
      err.textContent = "";
      for (const f of fs) {
        if (!f.type.startsWith("image/")) continue;
        if (L.length >= MAXI) {
          err.textContent = "Up to " + MAXI + " photos per post.";
          break;
        }
        if (f.size > IMGMAX) {
          err.textContent = "Image must be under " + IMGMB + " MB.";
          continue;
        }
        const p = qprep(f),
          it = { url: URL.createObjectURL(f), p, name: "" };
        L.push(it);
        p.catch((x) => {
          const k = L.indexOf(it);
          if (k > -1) {
            URL.revokeObjectURL(it.url);
            L.splice(k, 1);
            draw();
            upd();
          }
          err.textContent = (x && x.e) || "Could not read that photo. Pick it again.";
        });
      }
      draw();
      upd();
    };
    z.onclick = () => inp.click();
    inp.onchange = () => {
      add([...inp.files]);
      inp.value = "";
    };
    z.ondragover = (e) => {
      e.preventDefault();
      z.classList.add("hot");
    };
    z.ondragleave = () => z.classList.remove("hot");
    z.ondrop = (e) => {
      e.preventDefault();
      z.classList.remove("hot");
      add([...e.dataTransfer.files]);
    };
    const pOn = h("input", { type: "checkbox" }),
      pIn = [0, 1, 2, 3].map((i) =>
        h("input", { placeholder: "Option " + (i + 1), maxlength: 40, "aria-label": "Poll option " + (i + 1) }),
      ),
      pEnd = h(
        "select",
        { class: "pend", "aria-label": "How long the poll stays open" },
        ...[
          [0, "Open: no end"],
          [3600, "Closes in 1 hour"],
          [21600, "Closes in 6 hours"],
          [86400, "Closes in 24 hours"],
          [259200, "Closes in 3 days"],
          [604800, "Closes in 7 days"],
        ].map(([v, t]) => h("option", { value: String(v) }, t)),
      ),
      pMulti = h("input", { type: "checkbox" }),
      pMultiRow = h("label", { class: "pmulti" }, pMulti, h("span", {}, "Allow picking several answers")),
      pBox = h("div", { class: "pollform", hidden: "" }, ...pIn, pEnd, pMultiRow),
      pRow = OPT(
        pOn,
        "Poll",
        "2 to 4 options (last two optional). Your caption is the question. Votes are never tied to anyone.",
      ),
      pf = () => {
        pBox.hidden = !pOn.checked;
      };
    pOn.onchange = pf;
    const exTip = "The post, its photos and comments are deleted for good after this time.";
    let exs = 0;
    const exRow = h(
      "button",
      {
        type: "button",
        class: "opt exopt",
        "aria-pressed": "false",
        "aria-label": "Disappears after: never. Tap to change.",
        title: "Choose when this post disappears",
      },
      "Expires: Never",
    );
    const setEx = (n) => {
      exs = n;
      exRow.textContent = "Expires: " + exfmt(exs);
      exRow.setAttribute("aria-pressed", exs ? "true" : "false");
      exRow.setAttribute("aria-label", "Disappears after: " + exfmt(exs).toLowerCase() + ". Tap to change.");
    };
    exRow.onclick = () =>
      expPicker(exs, (n) => {
        setEx(n);
        showTip(exs ? exTip : "The post stays until you delete it.");
        sv();
      });
    tprev = h("div", { class: "tpost pv", "data-bg": "0", "aria-label": "Post preview" });
    swrow = h(
      "div",
      { class: "bgs", role: "radiogroup", "aria-label": "Background" },
      ...BGS.map((n, i) =>
        h("button", {
          type: "button",
          class: "tpost sw",
          role: "radio",
          "aria-label": n,
          title: n,
          "aria-checked": i === 0,
          "data-bg": i,
          onclick: () => {
            bg = i;
            tprev.setAttribute("data-bg", i);
            [...swrow.children].forEach((b, j) => b.setAttribute("aria-checked", j === i));
            sv();
          },
        }),
      ),
    );
    upd();
    /* drafts: the caption and options are kept on this device as you type (photos are not), and come back next time you open New post */
    const DK = pr ? null : "mq-draft-" + M.name,
      clr = () => {
        if (DK)
          try {
            localStorage.removeItem(DK);
          } catch (e) {}
      },
      note = h(
        "p",
        { class: "hint draftnote", hidden: "" },
        "Draft restored. ",
        h(
          "button",
          {
            type: "button",
            class: "lnk",
            onclick: () => {
              cap.value = "";
              pOn.checked = false;
              pf();
              pIn.forEach((x) => (x.value = ""));
              pEnd.value = "0";
              pMulti.checked = false;
              if (exs) setEx(0);
              an.checked = false;
              anRow.classList.remove("on");
              showTip("");
              if (swrow.children[0]) swrow.children[0].click();
              upd();
              clr();
              note.hidden = true;
            },
          },
          "Discard draft",
        ),
      );
    let has = 0;
    const sv = () => {
      if (!DK) return;
      const d = {
          cap: cap.value,
          bg,
          as: an.checked ? 1 : 0,
          po: pOn.checked ? pIn.map((x) => x.value) : 0,
          ex: exs,
          vis: VP.get(),
        },
        empty = !d.cap.trim() && !d.as && !d.ex && !d.vis && bg === 0 && (!d.po || !d.po.some((x) => x.trim()));
      try {
        if (empty) {
          localStorage.removeItem(DK);
          has = 0;
        } else {
          localStorage.setItem(DK, JSON.stringify(d));
          has = 1;
        }
      } catch (e) {}
    };
    veil.addEventListener("input", sv);
    veil.addEventListener("change", sv);
    veil.safe = () => !!DK && !L.length;
    veil.saved = () => has && !L.length;
    if (DK) {
      let d = null;
      try {
        d = JSON.parse(localStorage.getItem(DK) || "null");
      } catch (e) {}
      if (d && typeof d === "object") {
        cap.value = String(d.cap || "").slice(0, 300);
        if (+d.bg > 0 && swrow.children[+d.bg]) swrow.children[+d.bg].click();
        if (+d.as && M.mask) {
          an.checked = true;
          anRow.classList.add("on");
        }
        VP.set(+d.vis || 0);
        if (an.checked) VP.noFriends(true);
        if (Array.isArray(d.po)) {
          pOn.checked = true;
          pf();
          pIn.forEach((x, i) => (x.value = String(d.po[i] || "").slice(0, 40)));
        }
        if (+d.ex > 0) setEx(+d.ex);
        upd();
        sv();
        has = 1;
        note.hidden = false;
      }
    }
    return h(
      "form",
      {
        class: "form",
        onsubmit: async (e) => {
          e.preventDefault();
          btn.disabled = true;
          const d = new FormData();
          d.append("cap", cap.value);
          if (an.checked && M.mask && VP.get() === 1) {
            err.textContent = "Masque posts can\u2019t be friends-only. Pick Everyone or Only me.";
            btn.disabled = false;
            return;
          }
          if (an.checked && M.mask) d.append("as", "mask");
          if (VP.get()) d.append("vis", String(VP.get()));
          if (sn.checked && L.length) d.append("sens", "1");
          if (!L.length && !hgc.checked) d.append("hg", "0");
          if (pr) d.append("pd", "1");
          if (exs) d.append("exp", String(exs));
          if (pOn.checked) {
            const ops = pIn.map((x) => x.value.trim()).filter(Boolean);
            if (L.length) {
              err.textContent = "A poll can't have photos.";
              btn.disabled = false;
              return;
            }
            if (ops.length < 2) {
              err.textContent = "Give at least 2 poll options.";
              btn.disabled = false;
              return;
            }
            if (!cap.value.trim()) {
              err.textContent = "Write the question for your poll in the caption.";
              btn.disabled = false;
              return;
            }
            d.append("poll", JSON.stringify(ops));
            if (+pEnd.value) d.append("pend", pEnd.value);
            if (pMulti.checked) d.append("pmulti", "1");
          }
          if (!L.length) d.append("bg", String(bg));
          try {
            const names = [];
            for (let i = 0; i < L.length; i++) {
              const it = L[i];
              btn.textContent = L.length > 1 ? "Uploading " + (i + 1) + " / " + L.length + "…" : "Sharing…";
              if (!it.name) {
                const f = await it.p,
                  u = new FormData();
                u.append("img", f);
                it.name = (await api("pup", u)).img;
              }
              names.push(it.name);
            }
            if (names.length) {
              d.append("imgs", JSON.stringify(names));
              const am = {};
              L.forEach((it) => {
                if (it.alt && it.name) am[it.name] = it.alt;
              });
              if (Object.keys(am).length) d.append("alts", JSON.stringify(am));
            }
            btn.textContent = "Sharing…";
            const rs = await api("post", d);
            clr();
            close();
            if (rs.hold)
              alert(
                "Thanks! Your post is waiting for review. Only you and the admins can see it until an admin approves it.",
              );
            else slam("Posted");
            route();
          } catch (x) {
            err.textContent = x.e || "Could not post.";
            btn.textContent = "Share";
            upd();
          }
        },
      },
      h("div", { class: "row" }, h("div", {}, z, inp)),
      pr
        ? h("div", { class: "qa", style: "margin:0" }, h("small", {}, "Prompt of the day"), h("p", {}, pr.text))
        : null,
      note,
      grid,
      hint,
      tprev,
      swrow,
      cap,
      cnt,
      h(
        "div",
        { class: "opts", role: "group", "aria-label": "Post options" },
        anRow,
        pr ? null : pRow,
        snRow,
        hgRow,
        exRow,
      ),
      VP.el,
      tipEl,
      pr ? null : pBox,
      err,
      btn,
    );
  });
}
function drop(label, onfile, idle) {
  const i = h("input", { type: "file", accept: "image/*", "aria-label": label, hidden: "" }),
    z = h("button", { type: "button", class: "drop" }, idle || label + ": click or drop an image");
  const go = (f) => {
    if (f && f.type.startsWith("image/") && onfile(f)) {
      const nm = f.name.length > 24 ? f.name.slice(0, 12) + "…" + f.name.slice(-10) : f.name;
      z.textContent = idle ? "Selected: " + nm : label + ": " + nm;
      z.dispatchEvent(new Event("mqdirty", { bubbles: true }));
    }
  };
  z.onclick = () => i.click();
  i.onchange = () => {
    go(i.files[0]);
    i.value = "";
  };
  z.ondragover = (e) => {
    e.preventDefault();
    z.classList.add("hot");
  };
  z.ondragleave = () => z.classList.remove("hot");
  z.ondrop = (e) => {
    e.preventDefault();
    z.classList.remove("hot");
    go(e.dataTransfer.files[0]);
  };
  return h("div", {}, z, i);
}
const pform = (title, hint, onsave, ...kids) => {
  const st = h("p", { class: "hint", role: "alert" }),
    btn = h("button", { class: "btn full", type: "submit" }, "Save " + title.toLowerCase());
  const say = (t, bad) => {
    st.className = bad ? "err" : "hint";
    st.textContent = t;
  };
  btn.disabled = true;
  const f = h(
    "form",
    {
      class: "form pform",
      onsubmit: async (e) => {
        e.preventDefault();
        btn.disabled = true;
        say("");
        let ok = 0;
        try {
          await onsave();
          say("Saved.");
          ok = 1;
          f.dispatchEvent(new Event("mqsaved", { bubbles: true }));
          route();
        } catch (x) {
          if (x && x.cancel) say("");
          else say((x && x.e) || "Could not save.", 1);
        }
        btn.disabled = !!ok;
      },
    },
    h("h3", {}, title),
    hint ? h("p", { class: "sub" }, hint) : null,
    ...kids,
    st,
    btn,
  );
  f.say = say;
  f.save = onsave;
  f.isDirty = () => !btn.disabled;
  f.markSaved = () => {
    f._other = false;
    btn.disabled = true;
    f.dispatchEvent(new Event("mqsaved", { bubbles: true }));
  };
  f.touch = () => {
    const gs = [...f.querySelectorAll("[role=radiogroup][data-o]")];
    if (!PICKING) f._other = true;
    if (PICKING && !f._other && gs.length && gs.every((r) => r.dataset.v === r.dataset.o)) {
      btn.disabled = true;
      f.dispatchEvent(new Event("mqsaved", { bubbles: true }));
      return;
    }
    btn.disabled = false;
    if (st.textContent === "Saved.") say("");
    f.dispatchEvent(new Event("mqdirty", { bubbles: true }));
  };
  return f;
};
const pbig = (f, say) => {
  if (f.size > IMGMAX) {
    say("Image must be under " + IMGMB + " MB.", 1);
    return false;
  }
  say("");
  return true;
};
/* start reading+shrinking right away: phones can lose access to a picked file if a second one is picked before the first is read */
const pprep = (f, max, say) => {
  const p = shrink(f, max);
  p.catch((x) => say((x && x.e) || "Could not read that photo. Pick it again.", 1));
  return p;
};
/* A picture card (preview, Change photo, Remove photo) in the same layout as Edit profile. save(photoPromise|null, remove) does the upload. */
function picForm(title, hint, src, fallback, save) {
  let avF = null,
    rm = 0;
  const pav = h("div"),
    set = (u) => pav.replaceChildren(u ? av({ src: u }, 88) : fallback(88));
  set(src);
  const f = pform(
    title,
    hint,
    async () => {
      if (!avF && !rm) throw { e: "Pick a photo or tap Remove photo first." };
      await save(avF, rm);
      avF = null;
      rm = 0;
    },
    h(
      "div",
      { class: "picrow" },
      pav,
      h(
        "div",
        { class: "picact" },
        drop(
          title,
          (file) => {
            if (pbig(file, f.say)) {
              avF = pprep(file, 800, f.say);
              rm = 0;
              set(URL.createObjectURL(file));
              f.touch();
            }
          },
          "Change photo",
        ),
        h(
          "button",
          {
            type: "button",
            class: "ghost rm",
            onclick: async () => {
              if (!(await cbox("Remove the picture? It will be deleted when you tap Save."))) return;
              avF = null;
              rm = 1;
              set("");
              f.touch();
            },
          },
          "Remove photo",
        ),
      ),
    ),
  );
  return f;
}
/* a bio box with the 0 / 160 counter, as in Edit profile */
function bioBox(val, ph, label) {
  const b = h("textarea", { rows: 3, maxlength: 160, placeholder: ph, "aria-label": label }),
    c = h("span", { class: "hint cnt" });
  b.value = val || "";
  const u = () => {
    c.textContent = b.value.length + " / 160";
  };
  b.addEventListener("input", u);
  u();
  return [b, h("label", { class: "f" }, label, b, c)];
}
/* profile theme presets: [id, label]. The ids must match the lists in the `profile` case of index.php and the [data-pbg|pcd|pfn] rules in style.css. */
const PBG = [
    ["", "Default"],
    ["nightfall", "Blood moon"],
    ["sage", "Sage"],
    ["sky", "Sky"],
    ["rose", "Rose"],
    ["sand", "Sand"],
    ["lilac", "Lilac"],
    ["sunset", "Sunset"],
    ["ocean", "Ocean"],
    ["aurora", "Aurora"],
    ["peach", "Peach"],
    ["midnight", "Midnight"],
    ["mint", "Mint"],
    ["slate", "Slate"],
    ["dusk", "Dusk"],
    ["forest", "Forest"],
    ["coral", "Coral"],
    ["lemon", "Lemon"],
    ["berry", "Berry"],
    ["cocoa", "Cocoa"],
    ["ice", "Ice"],
    ["ember", "Ember"],
    ["sakura", "Sakura"],
    ["moss", "Moss"],
    ["noir", "Noir"],
    ["x_void", "Void"],
    ["x_inferno", "Inferno"],
    ["x_cyber", "Cyberpunk"],
    ["x_vapor", "Vaporwave"],
    ["x_abyss", "Abyss"],
    ["x_gilded", "Gilded"],
    ["x_nebula", "Nebula"],
    ["x_higan", "Higanbana"],
    ["x_mardi", "Masquerade"],
    ["x_moonlit", "Moonlit"],
    ["x_csig", "Cybersigil"],
  ],
  PBP = [
    ["", "None"],
    ["castle", "Castle"],
    ["castlepaint", "Castle (painted)"],
    ["grid", "Grid"],
    ["graph", "Graph paper"],
    ["dots", "Dots"],
    ["fdots", "Fading dots"],
    ["fgrid", "Fading grid"],
    ["lines", "Notebook"],
    ["diag", "Stripes"],
    ["hatch", "Crosshatch"],
    ["check", "Checkers"],
    ["zig", "Zigzag"],
    ["diamonds", "Diamonds"],
    ["rings", "Rings"],
    ["polka", "Polka"],
    ["stars", "Starry"],
    ["spot", "Spotlight"],
    ["fstripes", "Fading stripes"],
    ["drift", "Drifting stars"],
    ["snowfall", "Snowfall"],
    ["flow", "Aurora flow"],
    ["scroll", "Scrolling grid"],
    ["twinkle", "Twinkle"],
    ["fireflies", "Fireflies"],
    ["x_synth", "Synthwave"],
    ["x_matrix", "Code rain"],
    ["x_embers", "Rising embers"],
    ["x_cosmos", "Cosmos"],
    ["x_scan", "CRT"],
    ["x_lilies", "Spider lilies"],
    ["x_centi", "Centipedes"],
    ["x_csigil", "Sigil crosses"],
    ["x_cscript", "Thorn script"],
  ],
  PCD = [
    ["", "Classic"],
    ["flat", "Flat"],
    ["glass", "Glass"],
    ["x_crystal", "Crystal"],
    ["x_csigc", "Sigil brackets"],
    ["outline", "Outlined"],
  ],
  PAS = [
    ["", "Circle"],
    ["squircle", "Squircle"],
    ["hex", "Hexagon"],
    ["octagon", "Octagon"],
    ["diamond", "Diamond"],
    ["shield", "Shield"],
    ["pixel", "Pixel"],
  ],
  PAF = [
    ["", "None"],
    ["bats", "Bats"],
    ["batmono", "Shadow bat"],
    ["batpaint", "Painted bats"],
    ["ring", "Ring"],
    ["rainbow", "Rainbow"],
    ["dash", "Dashed"],
    ["glow", "Glow"],
    ["gold", "Gold"],
    ["royal", "Royal"],
    ["emerald", "Emerald"],
    ["ruby", "Ruby"],
    ["neon", "Neon"],
    ["pixel", "Pixel"],
    ["prism", "Prism"],
    ["ember", "Ember"],
    ["snow", "Snow"],
    ["sakura", "Sakura"],
    ["shimmer", "Shimmer"],
    ["thorns", "Thorns"],
    ["x_nova", "Nova"],
    ["x_hell", "Hellfire"],
    ["x_voidf", "Voidglass"],
    ["x_sov", "Sovereign"],
    ["x_higanf", "Red lily"],
    ["x_csigf", "Sigil blade"],
  ],
  PBF = [
    ["", "None"],
    ["match", "Match avatar"],
    ["bats", "Bats"],
    ["batmono", "Shadow bats"],
    ["batpaint", "Painted bats"],
    ["line", "Line"],
    ["gold", "Gold"],
    ["royal", "Royal"],
    ["neon", "Neon"],
    ["pixel", "Pixel"],
    ["chains", "Chains"],
    ["snow", "Snow"],
    ["sakura", "Sakura"],
    ["shimmer", "Shimmer"],
    ["thorns", "Thorns"],
    ["x_aurora", "Aurora"],
    ["x_fire", "Wildfire"],
    ["x_voidb", "Void"],
    ["x_chrome", "Chrome"],
    ["x_centib", "Centipede"],
    ["x_csigb", "Sigil thorns"],
  ],
  PPL = [
    ["", "List"],
    ["grid", "Grid"],
    ["big", "Big card"],
  ],
  PFN = [
    ["", "Default"],
    ["serif", "Serif"],
    ["elegant", "Elegant"],
    ["mono", "Mono"],
    ["round", "Rounded"],
    ["hand", "Handwritten"],
  ];
/* one row of single-choice buttons. attr (like "data-pbg") is copied onto each button so the stylesheet can paint it (a color swatch, or the label in its own font). */
/* Unlockables: UNL comes from the server (api "unl"): your stats, what each option needs, and whether you are an admin. Locked options get a lock and say what they need when tapped. */
let UNL = null;
const LKR = [];
/* Limited-time set "Castle Night": which option of each setting belongs to it. The server (CASTLE_END in index.php) decides when it ends; UNL.ev says if it is still on. Options of an ended event stay hidden unless you already have them equipped. */
const EVK = {
    tbg: ["nightfall", "ashen"],
    tbp: ["castle", "castlebw", "castlepaint"],
    taf: ["bats", "batmono", "batpaint"],
    tcf: ["bats", "batmono", "batpaint"],
  },
  EVS = {
    color: { tbg: "nightfall", tbp: "castle", taf: "bats", tcf: "bats" },
    paint: { tbg: "nightfall", tbp: "castlepaint", taf: "batpaint", tcf: "batpaint" },
    mono: { tbg: "ashen", tbp: "castlebw", taf: "batmono", tcf: "batmono" },
  };
/* a little bat (wings flap in CSS). Used for the Bats avatar and banner frames; the elements only show up under data-paf=bats / data-cf=bats. */
const BATP =
    "M19 8.5C16 4 9 1.8 1 3.2C3.2 5 3.6 7 3.4 9.4C5 8.2 6.8 8.4 8 10.2C9.4 8.8 11.2 9 12.4 11C14 9.6 16 10 17.6 12.2L19 11z",
  BAT =
    '<svg class="bat" viewBox="0 0 40 20" aria-hidden="true"><g class="wg"><path d="' +
    BATP +
    '"/></g><g transform="matrix(-1 0 0 1 40 0)"><g class="wg"><path d="' +
    BATP +
    '"/></g></g><ellipse cx="20" cy="10.2" rx="1.9" ry="3.5"/><path d="M18.2 7.6l.5-4 1.3 1.8 1.3-1.8.5 4z"/><g class="ey"><circle cx="19.2" cy="7.9" r=".62"/><circle cx="20.8" cy="7.9" r=".62"/></g></svg>',
  BATS = {
    o: [
      [-16, 6, 0, 24, 0, 0.34],
      [-6, 8.5, 130, 19, 1, 0.4],
      [-26, 11, 250, 28, 0, 0.37],
    ],
    f: [
      [14, 9, -1, 30, 0, 0.34, 8],
      [36, 12.5, -6, 22, 1, 0.4, 60],
      [58, 8, -4, 36, 0, 0.31, 30],
      [24, 16, -11, 19, 1, 0.42, 80],
      [70, 10.5, -8, 26, 0, 0.36, 45],
    ],
  };
const BMW = "M26 11.5C22 4.5 12 2.5 1 7Q5 10.5 7 15.5Q9.5 13 14 18.5Q15.5 15.5 20 19.8Q22 17.2 26.5 17.5Z",
  BMB = "M26 11.5L7 15.5M26 11.5L14 18.5M26 11.5L20 19.8M26 11.5L3.5 8.5",
  BATM =
    '<svg class="bat m" viewBox="0 0 60 30" aria-hidden="true"><g class="wg2"><path d="' +
    BMW +
    '"/></g><g transform="matrix(-1 0 0 1 60 0)"><g class="wg2"><path d="' +
    BMW +
    '"/></g></g><path d="M27.4 12.5Q30 24.5 32.6 12.5L31.4 10.4L28.6 10.4Z"/><path d="M28.6 18.5L30 24L31.4 18.5Z"/><path d="M27.3 9.4L26.6 1.6L29.4 5.6L30 4.6L30.6 5.6L33.4 1.6L32.7 9.4Q30 12.6 27.3 9.4Z"/><path class="fg" d="M29 11.3l.4 1.5l.4-1.5ZM30.2 11.3l.4 1.5l.4-1.5Z"/><g class="ey"><path d="M28.1 8.1l1.6.5l-.2.9l-1.5-.4ZM31.9 8.1l-1.6.5l.2.9l1.5-.4Z"/></g></svg>',
  BAT2 = BAT.replace('class="bat"', 'class="bat c"') + BATM;
function batFlock(k) {
  const w = h("span", { class: "bflock", "aria-hidden": "true" });
  w.innerHTML =
    k === "o"
      ? '<i class="mist"></i><i class="pb" style="--fl:.9s">' +
        BAT2 +
        "</i>" +
        BATS.o
          .map(
            ([i, t, a, sz, rv, fl]) =>
              '<i class="o' +
              (rv ? " rv" : "") +
              '" style="--i:' +
              i +
              "px;--t:" +
              t +
              "s;--a:" +
              a +
              "deg;--s:" +
              sz +
              "px;--fl:" +
              fl +
              's">' +
              BAT2 +
              "</i>",
          )
          .join("")
      : '<i class="sh" style="--fl:1.1s">' +
        BAT2 +
        "</i>" +
        BATS.f
          .map(
            ([y, t, d, sz, rv, fl, x], n) =>
              '<i class="f' +
              (rv ? " rv" : "") +
              '" style="--y:' +
              y +
              "%;--t:" +
              t +
              "s;--d:" +
              d +
              "s;--x:" +
              x +
              "%;--s:" +
              sz +
              "px;--fl:" +
              fl +
              "s;--b:" +
              (1.5 + n * 0.3) +
              's">' +
              BAT2 +
              "</i>",
          )
          .join("");
  return w;
}
async function unlLoad() {
  try {
    UNL = await api("unl");
  } catch (e) {}
}
/* true while a pick() button is being handled, so a form can tell "picked something" from "typed or changed a photo" */
let PICKING = false;
function pick(label, list, cur, attr, onpick, cls, lk) {
  let v = cur || "";
  const orig = v,
    row = h("div", { class: cls, role: "radiogroup", "aria-label": label }),
    sw = cls === "sws",
    note = h("p", { class: "hint lknote", role: "status", hidden: "" }),
    lockOf = (k) => {
      if (!lk || !k || !UNL || UNL.admin) return null;
      if ((UNL.gr || []).includes(lk + ":" + k)) return null;
      const q = (UNL.req[lk] || {})[k];
      if (!q || k === orig) return null;
      const have = +(UNL.st[q.s] || 0);
      return have >= q.n ? null : { t: q.t, have, n: q.n, s: q.s };
    },
    bs = list.map(([k, l]) => {
      const b = h(
        "button",
        {
          type: "button",
          class: sw ? "sw" : "opt",
          role: "radio",
          title: l,
          "aria-label": l,
          onclick: () => {
            if (k === v) return; /* tapping what is already picked changes nothing, so it should not light up Save */
            const q = lockOf(k);
            if (q) {
              note.textContent = q.s === "shop" ? q.t + " (Settings > Marketplace)." : "Locked: " + q.t + " (" + q.have + "/" + q.n + ").";
              note.hidden = false;
              return;
            }
            note.hidden = true;
            v = k;
            row.dataset.v = k;
            paint();
            PICKING = true;
            try {
              onpick(k);
            } finally {
              PICKING = false;
            }
          },
        },
        sw ? null : l,
      );
      if (attr && k) b.setAttribute(attr, k);
      return b;
    }),
    paint = () =>
      bs.forEach((b, i) => {
        b.setAttribute("aria-checked", String(list[i][0] === v));
        /* admin exclusives (ids starting x_): only shown to admins, people an admin gave them to, and whoever already has one equipped */
        if (lk && /^x_/.test(list[i][0])) {
          b.classList.add("xad");
          b.hidden = !UNL || (!UNL.admin && !(UNL.gr || []).includes(lk + ":" + list[i][0]) && list[i][0] !== orig);
        }
        const ev = lk && EVK[lk] && EVK[lk].includes(list[i][0]);
        if (ev) {
          b.classList.add("ltd");
          b.hidden = !UNL || (!UNL.admin && !(UNL.ev && +UNL.ev.on) && list[i][0] !== orig && !(UNL.gr || []).includes(lk + ":" + list[i][0]));
        }
        const q = lockOf(list[i][0]);
        b.classList.toggle("lk", !!q);
        b.setAttribute("aria-disabled", String(!!q));
        b.title = q ? list[i][1] + " (locked: " + q.t + ")" : list[i][1];
      });
  row.dataset.o = row.dataset.v = orig;
  row.append(...bs);
  paint();
  if (lk) LKR.push(paint);
  return lk ? h("div", {}, row, note) : row;
}
/* show (or clear) a person's theme on the page while their profile is open */
const PTK = { tbg: "pbg", tbp: "pbp", tcd: "pcd", tfn: "pfn", tas: "pas", taf: "paf" };
/* the page background of a profile lives on its own fixed layer so it can fade in when you open a profile and fade out when you leave (or cross-fade into the next profile). The layer carries its own data-pbg / data-pbp, so it keeps its colors while it fades. */
let PBL = null;
function pbgLayer(bg, pat) {
  const old = PBL,
    drop = (l, ms) => {
      l.style.opacity = "";
      l.classList.remove("on");
      setTimeout(() => l.remove(), ms);
    };
  if (!bg && !pat) {
    if (old) drop(old, 900);
    PBL = null;
    return;
  }
  if (old && old.dataset.pbg === (bg || undefined) && old.dataset.pbp === (pat || undefined)) return;
  const L = h("div", { class: "pbgl", "aria-hidden": "true" });
  if (bg) L.dataset.pbg = bg;
  if (pat) L.dataset.pbp = pat;
  document.body.append(L);
  void L.offsetWidth;
  /* add .on from rAF *and* a timer (rAF is paused in background tabs / some capture setups), then pin opacity once the fade is over so an interrupted transition can never leave the background half-faded */
  requestAnimationFrame(() => L.classList.add("on"));
  setTimeout(() => L.classList.add("on"), 60);
  setTimeout(() => {
    if (PBL === L) L.style.opacity = "var(--pbo,1)";
  }, 1000);
  PBL = L;
  if (old) setTimeout(() => old.remove(), 900);
}
function setPT(u) {
  const r = document.documentElement.dataset;
  for (const k in PTK) {
    const v = u && typeof u[k] === "string" && /^\w+$/.test(u[k]) ? u[k] : "";
    v ? (r[PTK[k]] = v) : delete r[PTK[k]];
  }
  pbgLayer(r.pbg, r.pbp);
  pforce();
}
/* Dark-made themes (Blood moon, Ashen, every admin theme, the Castle patterns) are drawn for the dark look: deep colors, light thorns/stars/text. In light mode they used to be washed out into pale copies. Now, while one of them is open on a profile, the whole page switches to the dark look so it is 1:1 with dark mode (nav, buttons, cards and header all dark and readable), and goes back to your own light/dark choice when you leave the profile. Pastel themes (Sage, Rose, Sky...) keep following your choice. */
function pforce() {
  const r = document.documentElement.dataset,
    dm = (v) => /^x_/.test(v || "") || v === "nightfall" || v === "ashen",
    dk = dm(r.pbg) || /^x_/.test(r.pbp || "") || /^castle/.test(r.pbp || "");
  let pref = "auto";
  try {
    pref = localStorage.getItem("mq-theme") || "auto";
  } catch (e) {}
  const light = pref === "light" || (pref === "auto" && !(window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches));
  if (dk && light) {
    r.theme = "dark";
    r.pforce = "1";
  } else if (r.pforce) {
    delete r.pforce;
    pref === "auto" ? delete r.theme : (r.theme = pref);
  }
}
function editProfile(u, only) {
  sheet(only === "cover" ? "Edit banner" : only === "layout" ? "Edit post layout" : "Edit profile", (close, veil) => {
    LKR.length = 0;
    unlLoad().then(() => {
      LKR.forEach((f) => f());
      try {
        unlSum();
      } catch (e) {}
    });
    /* Edit profile = picture + details (bio, display name, username). Edit banner (pencil on the banner) = banner only. Each one saves on its own and only sends its own fields. */
    const form = pform,
      big = pbig,
      prep = pprep;

    /* 1. profile picture */
    let avF = null,
      rmA = 0;
    const pav = h("div"),
      setAv = (src) => pav.replaceChildren(av({ src }, 84));
    setAv(u.avatar ? "?img=" + u.avatar : "");
    const fa = form(
      "Profile picture",
      "Shown on your profile, posts and chats.",
      async () => {
        if (!avF && !rmA) throw { e: "Pick a photo or tap Remove picture first." };
        const d = new FormData();
        if (avF) d.append("avatar", await avF);
        else d.append("noavatar", "1");
        M = (await api("profile", d)).me;
        avF = null;
        rmA = 0;
      },
      h(
        "div",
        { class: "picrow" },
        pav,
        h(
          "div",
          { class: "picact" },
          drop(
            "Profile picture",
            (f) => {
              if (big(f, fa.say)) {
                avF = prep(f, 800, fa.say);
                rmA = 0;
                setAv(URL.createObjectURL(f));
                fa.touch();
              }
            },
            "Change photo",
          ),
          h(
            "button",
            {
              type: "button",
              class: "ghost rm",
              onclick: async () => {
                if (!(await cbox("Remove your profile picture? It will be deleted when you tap Save."))) return;
                avF = null;
                rmA = 1;
                setAv("");
                fa.touch();
              },
            },
            "Remove photo",
          ),
        ),
      ),
    );

    /* 2. banner (cover photo + vertical position) */
    let cy = +u.cy || 50,
      cvF = null,
      rmC = 0,
      y0 = null;
    const pcv = h("div", {
      class: "cover",
      title: "Drag to reposition",
      style: "cursor:ns-resize;touch-action:none;height:150px",
    });
    const setCv = (url) => {
      pcv.style.backgroundImage = url ? `url(${url})` : "";
      pcv.classList.toggle("plain", !url);
      pcv.style.backgroundPosition = "50% " + cy + "%";
    };
    setCv(u.cover ? "?img=" + u.cover : "");
    pcv.onpointerdown = (e) => {
      y0 = e.clientY;
      pcv.setPointerCapture(e.pointerId);
    };
    pcv.onpointermove = (e) => {
      if (y0 == null) return;
      fb.touch();
      cy = Math.max(0, Math.min(100, cy - ((e.clientY - y0) / pcv.clientHeight) * 100));
      y0 = e.clientY;
      pcv.style.backgroundPosition = "50% " + cy + "%";
    };
    pcv.onpointerup = () => (y0 = null);
    const fb = form(
      "Banner",
      "The wide photo at the top of your profile.",
      async () => {
        const d = new FormData();
        d.append("cy", Math.round(cy));
        if (cvF) d.append("cover", await cvF);
        else if (rmC) d.append("nocover", "1");
        M = (await api("profile", d)).me;
        cvF = null;
        rmC = 0;
      },
      h("div", { class: "cvwrap" }, pcv, h("span", { class: "cvhint" }, "Drag to reposition")),
      h(
        "div",
        { class: "actrow" },
        drop(
          "Banner",
          (f) => {
            if (big(f, fb.say)) {
              cvF = prep(f, undefined, fb.say);
              rmC = 0;
              setCv(URL.createObjectURL(f));
              fb.touch();
            }
          },
          "Change banner",
        ),
        h(
          "button",
          {
            type: "button",
            class: "ghost rm",
            onclick: async () => {
              if (!(await cbox("Remove your banner? It will be deleted when you tap Save."))) return;
              cvF = null;
              rmC = 1;
              setCv("");
              fb.touch();
            },
          },
          "Remove banner",
        ),
      ),
    );

    /* 2a. banner frame: a separate border drawn inside the banner's own edge (same rounded corners). The preview is a small copy of the banner. */
    let bf_ = u.tcf || "",
      af_ = u.taf || "";
    const bpv = h(
        "div",
        { class: "cover" + (u.cover ? "" : " plain"), "aria-hidden": "true", style: "height:100px" },
        batFlock("f"),
      ),
      bdraw = () => {
        const f = bfx(bf_, af_);
        f ? (bpv.dataset.cf = f) : delete bpv.dataset.cf;
      };
    if (u.cover) {
      bpv.style.backgroundImage = `url(?img=${u.cover})`;
      bpv.style.backgroundPosition = "50% " + cy + "%";
    }
    bdraw();
    const fbs = form(
      "Banner style",
      "A frame around your banner. It stays inside the banner's edge.",
      async () => {
        M = (await api("profile", fd({ tcf: bf_ }))).me;
        u.tcf = bf_;
      },
      bpv,
      h("p", { class: "tlab" }, "Frame"),
      pick(
        "Banner frame",
        PBF,
        bf_,
        "data-cf",
        (v) => {
          bf_ = v;
          bdraw();
          fbs.touch();
        },
        "opts",
        "tcf",
      ),
    );

    /* 2b. avatar shape and frame. The preview (.apv) uses the same data-pas / data-paf attributes as a real profile page. */
    let as_ = u.tas || "";
    const apv = h(
        "div",
        { class: "apv", "aria-hidden": "true" },
        h("div", { class: "pavw" }, av({ src: u.avatar ? "?img=" + u.avatar : "" }, 84), batFlock("o")),
      ),
      adraw = () => {
        as_ ? (apv.dataset.pas = as_) : delete apv.dataset.pas;
        af_ ? (apv.dataset.paf = af_) : delete apv.dataset.paf;
      };
    adraw();
    const fs = form(
      "Avatar style",
      "Shown to everyone who opens your profile.",
      async () => {
        M = (await api("profile", fd({ tas: as_, taf: af_ }))).me;
        u.tas = as_;
        u.taf = af_;
      },
      apv,
      h("p", { class: "tlab" }, "Shape"),
      pick(
        "Shape",
        PAS,
        as_,
        null,
        (v) => {
          as_ = v;
          adraw();
          fs.touch();
        },
        "opts",
        "tas",
      ),
      h("p", { class: "tlab" }, "Frame"),
      pick(
        "Frame",
        PAF,
        af_,
        "data-paf",
        (v) => {
          af_ = v;
          adraw();
          bdraw();
          fs.touch();
        },
        "opts",
        "taf",
      ),
    );

    /* 2c. post layout on your profile. The little preview only illustrates the shape. */
    let tl = u.tpl || "";
    const lpv = h("div", { class: "lpv", "aria-hidden": "true" }, ...[0, 1, 2, 3, 4, 5].map(() => h("i"))),
      ldraw = () => {
        lpv.dataset.l = tl || "list";
      };
    ldraw();
    const fl = form(
      "Post layout",
      "How your posts are laid out on your profile.",
      async () => {
        M = (await api("profile", fd({ tpl: tl }))).me;
        u.tpl = tl;
      },
      lpv,
      pick(
        "Post layout",
        PPL,
        tl,
        null,
        (v) => {
          tl = v;
          ldraw();
          fl.touch();
        },
        "opts",
      ),
      h(
        "p",
        { class: "hint" },
        "List shows full posts. Grid shows photos as small tiles (tap one to open the post). Big card shows larger photos and text.",
      ),
    );

    /* 3. theme: background, card style and font. Everyone who opens your profile sees it. The preview uses the same attributes as the real page. */
    let tb = u.tbg || "",
      tp = u.tbp || "",
      tc = u.tcd || "",
      tf = u.tfn || "";
    const tprev = h(
        "div",
        { class: "tprev", "aria-hidden": "true" },
        h(
          "div",
          { class: "tpost" },
          h("div", { class: "tn" }, h("i"), dn(u)),
          h("p", {}, "This is how your posts will look."),
        ),
      ),
      tdraw = () => {
        for (const [k, v] of [
          ["pbg", tb],
          ["pbp", tp],
          ["pcd", tc],
          ["pfn", tf],
        ])
          v ? (tprev.dataset[k] = v) : delete tprev.dataset[k];
      };
    tdraw();
    const ft = form(
      "Theme",
      "Shown to everyone who opens your profile.",
      async () => {
        M = (await api("profile", fd({ tbg: tb, tbp: tp, tcd: tc, tfn: tf }))).me;
        u.tbg = tb;
        u.tbp = tp;
        u.tcd = tc;
        u.tfn = tf;
      },
      tprev,
      h("button", { type: "button", class: "shpgo", onclick: () => { veil.querySelector(".sheet > h2 button").click(); location.hash = "#/settings/marketplace"; } }, h("span", { class: "shpfseal", "aria-hidden": "true" }, ic("mask", 16)), "Get more in the Marketplace"),
      h("p", { class: "tlab" }, "Background"),
      pick(
        "Background",
        PBG,
        tb,
        "data-pbg",
        (v) => {
          tb = v;
          tdraw();
          ft.touch();
        },
        "sws",
        "tbg",
      ),
      h("p", { class: "tlab" }, "Pattern"),
      pick(
        "Pattern",
        PBP,
        tp,
        "data-pbp",
        (v) => {
          tp = v;
          tdraw();
          ft.touch();
        },
        "opts",
        "tbp",
      ),
      h("p", { class: "tlab" }, "Card style"),
      pick(
        "Card style",
        PCD,
        tc,
        "data-pcdo",
        (v) => {
          tc = v;
          tdraw();
          ft.touch();
        },
        "opts cdopts",
        "tcd",
      ),
      h("p", { class: "hint" }, "Glass looks best with a background color."),
      h("p", { class: "tlab" }, "Font"),
      pick(
        "Font",
        PFN,
        tf,
        "data-pfn",
        (v) => {
          tf = v;
          tdraw();
          ft.touch();
        },
        "opts",
        "tfn",
      ),
    );

    /* 4. details: display name, username, bio. Username + display name share one 7-day timer. */
    const n = h("input", { value: u.name, maxlength: 20, "aria-label": "Username" }),
      nk = h("input", {
        value: u.nick || "",
        maxlength: 24,
        placeholder: "Optional",
        autocomplete: "off",
        "aria-label": "Display name",
      }),
      b = h("textarea", {
        rows: 3,
        maxlength: 160,
        placeholder: "Tell people a little about you",
        "aria-label": "Bio",
      }),
      bcnt = h("span", { class: "hint cnt" });
    b.value = u.bio || "";
    const upc = () => {
      bcnt.textContent = b.value.length + " / 160";
    };
    b.addEventListener("input", upc);
    upc();
    const lockHint = h("p", { class: "hint" });
    const lock = () => {
      const until = (+M.ncts || 0) + 604800,
        on = !M.admin && Date.now() / 1000 < until;
      n.disabled = nk.disabled = on;
      lockHint.hidden = !on;
      lockHint.textContent = on
        ? "You changed your username or display name recently. You can change them again on " +
          new Date(until * 1000).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" }) +
          "."
        : "";
    };
    lock();
    const fd3 = form(
      "Profile details",
      null,
      async () => {
        const un = n.value.trim(),
          kn = nk.value.trim(),
          cN = un !== u.name,
          cK = kn !== (u.nick || "");
        const d = new FormData();
        d.append("name", un);
        d.append("nick", kn);
        d.append("bio", b.value);
        if (cN || cK) {
          const parts = [];
          if (cN) parts.push("change your username to @" + un);
          if (cK) parts.push(kn ? "change your display name to \u201c" + kn + "\u201d" : "remove your display name");
          if (
            !(await cbox(
              "Change your name? You're about to " +
                parts.join(" and ") +
                ". " +
                (M.admin
                  ? cN
                    ? " Admin access follows the username: unless @" +
                      un +
                      " is listed in ADMIN_USERS on the server, this account stops being an admin."
                    : ""
                  : " You won't be able to change your username or display name again for 7 days."),
            ))
          )
            throw { cancel: 1 };
          d.append("confirm", "1");
        }
        M = (await api("profile", d)).me;
        u.name = M.name;
        u.nick = M.nick || "";
        n.value = u.name;
        nk.value = u.nick;
        lock();
      },
      h("label", { class: "f" }, "Bio", b, bcnt),
      h(
        "label",
        { class: "f" },
        "Display name",
        nk,
        h("span", { class: "hint" }, "Optional. Shown instead of your username."),
      ),
      h(
        "label",
        { class: "f" },
        "Username",
        h("div", { class: "atw" }, n),
        h("span", { class: "hint" }, "What you log in with and what people @mention."),
      ),
      lockHint,
      h(
        "p",
        { class: "hint" },
        "You can change your username and display name once every 7 days (changing both counts as one change).",
      ),
    );
    fd3.addEventListener("input", () => fd3.touch());
    const unlBox = h("div", { class: "card unlbox" }),
      unlSum = () => {
        if (!UNL) return;
        const t = UNL.st || {};
        unlBox.replaceChildren(
          h("h3", {}, "Unlockables"),
          h(
            "p",
            { class: "hint" },
            UNL.admin
              ? "You're an admin, so every frame, shape, color and pattern is unlocked for you."
              : "Locked options show a lock. Unlock them by posting, commenting, getting likes, making friends and keeping your daily prompt streak going. Whatever you already use stays yours.",
          ),
          h(
            "p",
            { class: "unls" },
            [
              ["posts", t.p],
              ["comments", t.c],
              ["likes", t.l],
              ["friends", t.f],
              ["best streak", t.s],
              ["days here", t.d],
            ]
              .map(([x, y]) => (y || 0) + " " + x)
              .join(" \u00b7 "),
          ),
          h(
            "button",
            { type: "button", class: "ghost", style: "margin-top:10px", onclick: () => { close(); location.hash = "#/settings/unlockables"; } },
            "See your progress",
          ),
        );
      };
    /* limited-time "Castle Night" card: shows only while the event is on. Pick a look (pixel, painted or black and white), then one tap equips the whole set. */
    const EVL = [
        ["color", "Pixel", "Pixel castle, red bats"],
        ["paint", "Painted", "Painted castle and bats"],
        ["mono", "Shadow bat", "Dark grey scene, shadow bat on your avatar"],
      ],
      evNm = (v) => v || "",
      evOn = (k) => {
        const s = EVS[k];
        return evNm(u.tbg) === s.tbg && evNm(u.tbp) === s.tbp && (u.taf || "") === s.taf && (u.tcf || "") === s.tcf;
      };
    let evSel = "color";
    const evNote = h("p", { class: "evnote", role: "status" }),
      evLeft = h("span", { class: "evleft" }),
      evGoBtn = h(
        "button",
        {
          type: "button",
          class: "btn evgo",
          onclick: async () => {
            evGoBtn.disabled = true;
            evNote.textContent = "";
            try {
              M = (await api("profile", fd(EVS[evSel]))).me;
              close();
              route();
            } catch (x) {
              evNote.textContent = (x && x.e) || "Could not equip it.";
              evGoBtn.disabled = false;
            }
          },
        },
        "Equip this look",
      ),
      evTiles = EVL.map(([k, n, d]) =>
        h(
          "button",
          {
            type: "button",
            class: "evlook",
            role: "radio",
            "data-k": k,
            "aria-checked": "false",
            onclick: () => evPick(k),
          },
          h("span", { class: "evsw", "aria-hidden": "true" }),
          h("b", {}, n),
          h("small", {}, d),
        ),
      ),
      evPick = (k) => {
        evSel = k;
        evBox.dataset.look = k;
        evTiles.forEach((t) => t.setAttribute("aria-checked", t.dataset.k === k ? "true" : "false"));
        const on = evOn(k);
        evGoBtn.disabled = on;
        evGoBtn.textContent = on ? "Equipped" : "Equip this look";
      },
      evBox = h(
        "div",
        { class: "evcard", hidden: "", "data-look": "color" },
        h(
          "div",
          { class: "evhero" },
          h("div", { class: "evart", "aria-hidden": "true" }),
          h("div", { class: "evtop" }, h("span", { class: "evtag" }, "Limited time"), evLeft),
          h("h3", {}, "Castle Night"),
          h("p", { class: "evtxt" }),
        ),
        h(
          "div",
          { class: "evbody" },
          h("div", { class: "evlooks", role: "radiogroup", "aria-label": "Castle Night look" }, ...evTiles),
          evGoBtn,
          h("p", { class: "evfine" }, "You keep it after the event if you leave it equipped."),
          evNote,
        ),
      );
    const evAcc = h("details", { class: "pacc pev", hidden: "" }, h("summary", {}, h("span", {}, "Castle Night \u00b7 limited time")), evBox);
    LKR.push(() => {
      const e = UNL && UNL.ev;
      if (!e || !+e.on) {
        evBox.hidden = true;
        evAcc.hidden = true;
        return;
      }
      evAcc.hidden = false;
      const left = Math.max(1, Math.ceil((e.end * 1000 - Date.now()) / 864e5));
      evBox.querySelector(".evtxt").textContent =
        "A blood-red moon and castle behind your profile, bats around your picture and across your banner. Free until " +
        new Date(e.end * 1000).toLocaleDateString(undefined, { month: "long", day: "numeric" }) +
        ".";
      evLeft.textContent = left + (left === 1 ? " day left" : " days left");
      evBox.hidden = false;
      evPick((EVL.find(([k]) => evOn(k)) || [evSel])[0]);
    });
    /* post layout lives behind the pencil next to the Posts / Questions tabs; unlockables have their own page in Settings */
    const unlLink = h(
      "button",
      { type: "button", class: "unllink", onclick: () => { close(); location.hash = "#/settings/unlockables"; } },
      h("span", {}, "Unlockables"),
      h("small", { class: "hint" }, "See your progress"),
      h("span", { class: "hint", "aria-hidden": "true" }, "\u203a"),
    );
    const shpLink = h(
      "button",
      { type: "button", class: "unllink", onclick: () => { close(); location.hash = "#/settings/marketplace"; } },
      h("span", {}, "Marketplace"),
      h("small", { class: "hint" }, "Spend your Sigils"),
      h("span", { class: "hint", "aria-hidden": "true" }, "\u203a"),
    );
    return pagg(
      close,
      veil,
      only === "cover"
        ? [["Banner", fb, true], ["Banner style", fbs]]
        : only === "layout"
          ? [["Post layout", fl, true]]
          : [["Profile picture", fa, true, true], ["Profile details", fd3, true, true], ["Avatar style", fs], ["Theme", ft]],
      only === "layout" ? [] : [evAcc],
      only === "layout" ? [] : [unlLink, shpLink],
    );
  });
}
/* edit screens: every section is a dropdown, and one bar at the bottom saves (or throws away) all of them at once. specs: [title, pform, open?] or a ready <details>; lead: elements shown above the sections; tail: elements after them */
function pagg(close, veil, specs, lead, tail) {
  const pacc = (title, f, open, pin) => {
    const dot = h("i", { class: "pdot2", hidden: "", "aria-label": "Unsaved changes" }),
      d = h("details", { class: "pacc" }, h("summary", {}, h("span", {}, title), dot), f);
    if (open) d.open = true;
    d.addEventListener("mqdirty", () => (dot.hidden = false));
    d.addEventListener("mqsaved", () => (dot.hidden = true));
    /* opening a normal section closes the others (their changes are kept while closed); the pinned ones stay open together, and the opened one scrolls to the top so you never hunt for it */
    d.addEventListener("toggle", () => {
      if (!d.open || pin) return; /* the two pinned sections (picture + details) open together and never close each other or scroll */
      d.parentElement?.querySelectorAll(":scope > details.pacc[open]").forEach((o) => {
        if (o !== d) o.open = false;
      });
      requestAnimationFrame(() => d.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion:reduce)").matches ? "auto" : "smooth" }));
    });
    f.addEventListener("input", () => {
      if (f.touch) f.touch();
    });
    d.form = f;
    return d;
  };
  const secs = specs.map((x) => (Array.isArray(x) ? pacc(x[0], x[1], x[2], x[3]) : x));
  const forms = secs.map((x) => x.form).filter(Boolean),
    anyDirty = () => forms.some((f) => f.isDirty()),
    sbtn = h("button", { class: "btn", type: "button", disabled: "" }, "Save all changes"),
    sstat = h("p", { class: "hint psstat", role: "alert" }),
    refresh = () => {
      sbtn.disabled = !anyDirty();
      dbtn.textContent = anyDirty() ? "Discard" : "Close";
    };
  secs.forEach((x) => {
    x.addEventListener("mqdirty", refresh);
    x.addEventListener("mqsaved", refresh);
    x.addEventListener("input", () => setTimeout(refresh, 0));
  });
  sbtn.onclick = async () => {
    sbtn.disabled = true;
    sstat.className = "hint psstat";
    sstat.textContent = "";
    for (const f of forms.filter((x) => x.isDirty())) {
      try {
        await f.save();
        f.markSaved();
      } catch (x) {
        if (x && x.cancel) {
          refresh();
          return;
        }
        const sec = secs.find((e) => e.form === f);
        if (sec) sec.open = true;
        sstat.className = "err psstat";
        sstat.textContent = (sec ? sec.querySelector("summary span").textContent + ": " : "") + ((x && x.e) || "Could not save.");
        refresh();
        return;
      }
    }
    close();
    route();
  };
  const dbtn = h(
    "button",
    {
      type: "button",
      class: "ghost",
      onclick: () => veil.querySelector(".sheet > h2 button").click(),
    },
    "Close",
  );
  return h(
    "div",
    { class: "pforms agg" },
    ...(lead || []),
    ...secs,
    ...(tail || []),
    h("div", { class: "psbar" }, sstat, h("div", { class: "psrow" }, dbtn, sbtn)),
  );
}
function pwForm() {
  const o = h("input", {
      type: "password",
      placeholder: "Current password",
      "aria-label": "Current password",
      autocomplete: "current-password",
    }),
    w = h("input", {
      type: "password",
      placeholder: "New password (8+ characters)",
      "aria-label": "New password",
      autocomplete: "new-password",
    }),
    pe = h("p", { class: "err", role: "alert" });
  return h(
    "div",
    { class: "form" },
    o,
    w,
    pe,
    h(
      "button",
      {
        type: "button",
        class: "ghost",
        onclick: async () => {
          try {
            await api("pw", fd({ old: o.value, new: w.value }));
            pe.textContent = "Password changed.";
            o.value = w.value = "";
          } catch (x) {
            pe.textContent = x.e || "Could not change password.";
          }
        },
      },
      "Change password",
    ),
  );
}
/* settings */
function toggle(label, hint, key, on, yes, no) {
  const c = h("input", { type: "checkbox", style: "width:auto" }),
    st = h("small", { class: "hint", role: "status" });
  c.checked = on;
  c.onchange = async () => {
    st.textContent = "";
    try {
      M = (await api("profile", fd({ [key]: c.checked ? yes : no }))).me;
      st.textContent = "Saved.";
    } catch (x) {
      c.checked = !c.checked;
      st.textContent = x.e || "Could not save.";
    }
  };
  return h(
    "div",
    { class: "setrow" },
    h("label", { class: "chk" }, c, " " + label),
    h("p", { class: "hint" }, hint),
    st,
  );
}
let DEFER = null;
addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  DEFER = e;
});
addEventListener("appinstalled", () => {
  DEFER = null;
});
if ("serviceWorker" in navigator)
  addEventListener("load", () => navigator.serviceWorker.register("?sw=1", { scope: "./" }).catch(() => {}));
function installCard() {
  if (matchMedia("(display-mode: standalone)").matches || navigator.standalone) return "";
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent),
    b = DEFER
      ? h(
          "button",
          {
            class: "btn full",
            onclick: async () => {
              DEFER.prompt();
              try {
                await DEFER.userChoice;
              } catch (e) {}
              DEFER = null;
              settings();
            },
          },
          "Install Masque",
        )
      : null;
  return h(
    "div",
    { class: "card" },
    h("h3", {}, "Install Masque"),
    h(
      "p",
      { class: "hint" },
      b
        ? "Add Masque to your home screen so it opens like a normal app."
        : ios
          ? "Tap the Share button, then \u201cAdd to Home Screen\u201d."
          : "Open your browser menu and choose \u201cInstall app\u201d or \u201cAdd to Home Screen\u201d.",
    ),
    b,
  );
}
/* Home nudge: a small dismissible card that gets people to (1) install Masque and (2) turn on notifications. Browsers never let a site do either by itself, so each is made one tap:
   Android/Chrome shows its own install dialog from the button; iPhone has no such thing, so the exact steps are shown; notifications use the browser's own permission prompt from the button. */
function nudgeCard() {
  if (!M) return null;
  const quiet = (k, days) => {
      try {
        return Date.now() - +(localStorage.getItem(k) || 0) < days * 864e5;
      } catch (_) {
        return false;
      }
    },
    mute = (k) => {
      try {
        localStorage.setItem(k, String(Date.now()));
      } catch (_) {}
    },
    installed = matchMedia("(display-mode: standalone)").matches || navigator.standalone,
    ios = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1),
    phone = ios || /android/i.test(navigator.userAgent),
    ik = "mq-nudge-i-" + M.name,
    nk = "mq-nudge-n-" + M.name;
  const wrapC = (k, title, text, ...more) => {
    const box = h("section", { class: "wcard nudge", "aria-label": title }),
      x = h("button", { type: "button", class: "ghost wcx", "aria-label": "Hide", title: "Hide" }, "\u00d7");
    x.onclick = () => {
      mute(k);
      box.remove();
    };
    box.append(x, h("h3", {}, title), h("p", { class: "hint" }, text), ...more);
    return box;
  };
  if (!installed && (phone || DEFER) && !quiet(ik, 14)) {
    if (DEFER) {
      const err = h("p", { class: "err", role: "alert" }),
        b = h("button", { type: "button", class: "btn" }, "Install Masque");
      const box = wrapC(ik, "Install Masque", "Open it like a normal app, and get notifications on your phone.", b, err);
      b.onclick = async () => {
        if (!DEFER) return;
        DEFER.prompt();
        let ch = null;
        try {
          ch = await DEFER.userChoice;
        } catch (_) {}
        DEFER = null;
        if (ch && ch.outcome === "accepted") box.remove();
        else b.hidden = true;
      };
      return box;
    }
    if (ios)
      return wrapC(
        ik,
        "Add Masque to your Home Screen",
        "On iPhone this is also what makes notifications work.",
        h(
          "ol",
          { class: "nsteps" },
          h("li", {}, "Open Masque in Safari."),
          h("li", {}, "Tap the Share button (the square with an arrow pointing up)."),
          h("li", {}, "Scroll down and tap \u201cAdd to Home Screen\u201d, then Add."),
          h("li", {}, "Open Masque from your Home Screen."),
        ),
      );
    return wrapC(
      ik,
      "Install Masque",
      "Open your browser menu (the three dots) and tap \u201cInstall app\u201d or \u201cAdd to Home screen\u201d. It then opens like a normal app and can send notifications.",
    );
  }
  if ((installed || !ios) && PUSHOK() && Notification.permission === "default" && !quiet(nk, 7)) {
    const err = h("p", { class: "err", role: "alert" }),
      b = h("button", { type: "button", class: "btn" }, "Turn on notifications"),
      box = wrapC(nk, "Don't miss anything", "Get a notification when someone messages you, comments or sends a friend request. They never show names, only what happened.", b, err);
    b.onclick = async () => {
      b.disabled = true;
      err.textContent = "";
      try {
        await pushOn();
        box.replaceChildren(h("p", { class: "hint" }, "Notifications are on. You can change what reaches you in Settings."));
        setTimeout(() => box.remove(), 4000);
      } catch (x) {
        err.textContent = (x && x.e) || "Could not turn on notifications.";
        b.disabled = false;
      }
    };
    return box;
  }
  return null;
}
/* notification settings: pick what reaches your bell, turn message pop-ups off, and set quiet hours (no badges or pop-ups; everything is waiting afterwards) */
function notifCard(np) {
  const G = [
    ["sigils", "Sigils", "When someone marks your post or comment"],
    ["replies", "Comments and replies", "On your posts and on your comments"],
    ["mentions", "Mentions", "When someone @mentions you"],
    ["tags", "Tags you follow", "New posts that use a tag you follow"],
    ["friends", "Friend requests", "New requests, and requests that were accepted"],
    ["follows", "New followers", "When someone follows you"],
    ["asks", "Anonymous questions", "New questions, and answers to yours"],
    ["reveals", "Masque reveals", "When a friend tells you a Masque is them"],
    ["streak", "Streak reminders", "A push about 3 hours before your daily prompt streak or a chat streak ends. Quiet hours apply."],
  ];
  const muted = new Set(np.muted || []),
    st = h("small", { class: "hint", role: "status" }),
    hm = (m) => String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0"),
    mn = (v) => {
      const a = (v || "").split(":");
      return a.length < 2 || isNaN(+a[0]) || isNaN(+a[1]) ? null : +a[0] * 60 + +a[1];
    };
  const save = async (d) => {
    st.textContent = "";
    try {
      await api("setnp", fd(Object.assign({ tz: -new Date().getTimezoneOffset() }, d)));
      st.textContent = "Saved.";
      return true;
    } catch (x) {
      st.textContent = x.e || "Could not save.";
      return false;
    }
  };
  const row = (key, t, hint) => {
    const c = h("input", { type: "checkbox", style: "width:auto" });
    c.checked = !muted.has(key);
    c.onchange = async () => {
      c.checked ? muted.delete(key) : muted.add(key);
      if (!(await save({ muted: [...muted].join(",") }))) {
        c.checked ? muted.add(key) : muted.delete(key);
        c.checked = !c.checked;
      }
    };
    return h("div", { class: "setrow" }, h("label", { class: "chk" }, c, " " + t), h("p", { class: "hint" }, hint));
  };
  const pop = h("input", { type: "checkbox", style: "width:auto" }),
    qon = h("input", { type: "checkbox", style: "width:auto" }),
    qf = h("input", { type: "time", value: hm(+np.qfrom), "aria-label": "Quiet hours start" }),
    qt = h("input", { type: "time", value: hm(+np.qto), "aria-label": "Quiet hours end" });
  pop.checked = !!+np.pop;
  qon.checked = !!+np.qon;
  qf.disabled = qt.disabled = !qon.checked;
  pop.onchange = async () => {
    if (!(await save({ pop: pop.checked ? 1 : 0 }))) pop.checked = !pop.checked;
  };
  qon.onchange = async () => {
    qf.disabled = qt.disabled = !qon.checked;
    if (!(await save({ qon: qon.checked ? 1 : 0, qfrom: mn(qf.value) ?? 1320, qto: mn(qt.value) ?? 420 }))) {
      qon.checked = !qon.checked;
      qf.disabled = qt.disabled = !qon.checked;
    }
  };
  const tm = async () => {
    const a = mn(qf.value),
      b = mn(qt.value);
    if (a === null || b === null) return;
    await save({ qfrom: a, qto: b });
  };
  qf.onchange = qt.onchange = tm;
  return h(
    "div",
    { class: "card" },
    h("h3", {}, "Notifications"),
    h(
      "p",
      { class: "hint", style: "margin-bottom:6px" },
      "Choose what shows up in your bell. Turned-off kinds simply never reach you.",
    ),
    ...G.map((g) => row(...g)),
    pushRow(),
    h(
      "div",
      { class: "setrow" },
      h("label", { class: "chk" }, pop, " Message pop-ups"),
      h("p", { class: "hint" }, "The little banner when a message or group message arrives while you are in the app. Also turns message push notifications on or off."),
    ),
    h(
      "div",
      { class: "setrow" },
      h("label", { class: "chk" }, qon, " Quiet hours"),
      h(
        "p",
        { class: "hint" },
        "No badges or pop-ups during these hours. Everything is still waiting for you afterwards.",
      ),
      h("div", { class: "qrow" }, h("span", { class: "hint" }, "From"), qf, h("span", { class: "hint" }, "to"), qt),
    ),
    st,
  );
}
/* Push notifications: the browser's own "turn on notifications" plus a subscription the server can send to. Needs a service worker; on iPhone only works once Masque is added to the Home Screen. */
const PUSHOK = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
async function pushSub() {
  try {
    return PUSHOK() && Notification.permission === "granted" ? await (await navigator.serviceWorker.ready).pushManager.getSubscription() : null;
  } catch (e) {
    return null;
  }
}
/* stop pushes to this browser (used on sign-out, so the next person on a shared device never gets your alerts) */
async function pushOffHere() {
  try {
    const sub = await pushSub();
    if (!sub) return;
    await api("pushoff", fd({ ep: sub.endpoint }));
    await sub.unsubscribe();
  } catch (e) {}
}
async function pushOn() {
  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw { e: "Notifications are blocked for this site. Allow them in your browser's site settings, then try again." };
  const reg = await navigator.serviceWorker.ready,
    key = (await api("pushkey")).key,
    pad = "=".repeat((4 - (key.length % 4)) % 4),
    raw = atob((key + pad).replace(/-/g, "+").replace(/_/g, "/")),
    appKey = Uint8Array.from(raw, (c) => c.charCodeAt(0));
  let sub = await reg.pushManager.getSubscription();
  if (sub) {
    const cur = new Uint8Array(sub.options.applicationServerKey || []);
    if (cur.length !== appKey.length || cur.some((v, i) => v !== appKey[i])) {
      await sub.unsubscribe();
      sub = null;
    }
  }
  sub ||= await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: appKey });
  const j = sub.toJSON();
  await api("pushsub", fd({ ep: sub.endpoint, k: j.keys.p256dh, a: j.keys.auth }));
}
function pushRow() {
  const c = h("input", { type: "checkbox", style: "width:auto" }),
    st = h("p", { class: "hint", role: "status" }),
    test = h("button", { type: "button", class: "ghost", hidden: true }, "Send a test"),
    ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const hint = h(
    "p",
    { class: "hint" },
    "Get a notification on this device when something happens, even when Masque is closed. They never show names, only what happened.",
  );
  if (!PUSHOK()) {
    c.disabled = true;
    st.textContent = ios
      ? "On iPhone and iPad, tap Share, then Add to Home Screen, and open Masque from there. Then you can turn this on."
      : "This browser doesn't support notifications.";
  } else {
    pushSub().then((s) => {
      c.checked = !!s;
      test.hidden = !s;
    });
  }
  c.onchange = async () => {
    st.textContent = "";
    c.disabled = true;
    try {
      if (c.checked) {
        await pushOn();
        st.textContent = "Notifications are on for this device.";
      } else {
        await pushOffHere();
        st.textContent = "Notifications are off for this device.";
      }
    } catch (x) {
      c.checked = !c.checked;
      st.textContent = x.e || "Could not change that.";
    }
    c.disabled = false;
    test.hidden = !c.checked;
  };
  test.onclick = async () => {
    try {
      await api("pushtest", fd({}));
      st.textContent = "Sent. It should arrive in a few seconds.";
    } catch (x) {
      st.textContent = x.e || "Could not send.";
    }
  };
  return h("div", { class: "setrow" }, h("label", { class: "chk" }, c, " Push notifications"), hint, test, st);
}
/* Muted on your posts: people (muted from a comment's menu) and words, both only affect comments on your own posts */
function mutesCard() {
  const box = h("div", { class: "mutes" }),
    st = h("p", { class: "hint", role: "status" }),
    inp = h("input", { placeholder: "Add a word or phrase", maxlength: 30, "aria-label": "Word to mute" }),
    add = h("button", { class: "btn", type: "submit" }, "Mute"),
    chip = (txt, kind, v) =>
      h(
        "span",
        { class: "mchip" },
        txt,
        h(
          "button",
          {
            type: "button",
            "aria-label": "Unmute " + txt,
            onclick: async () => {
              try {
                await api("unmute", fd({ kind, v }));
                await paint();
              } catch (x) {
                st.textContent = x.e || "Could not unmute.";
              }
            },
          },
          ic("close", 12),
        ),
      );
  async function paint() {
    let r;
    try {
      r = await api("mutes");
    } catch (x) {
      rc(box, h("p", { class: "hint" }, "Could not load your mutes."));
      return;
    }
    rc(
      box,
      h(
        "div",
        { class: "mgroup" },
        h("b", {}, "Words"),
        r.words.length
          ? h("div", { class: "mchips" }, ...r.words.map((w) => chip(w, "w", w)))
          : h("p", { class: "hint" }, "None yet."),
      ),
      h(
        "div",
        { class: "mgroup" },
        h("b", {}, "People"),
        r.users.length
          ? h("div", { class: "mchips" }, ...r.users.map((u) => chip(u.name, "u", u.id)))
          : h("p", { class: "hint" }, "None yet. Open the \u22ef menu on a comment on your post to mute someone."),
      ),
    );
  }
  const f = h(
    "form",
    {
      class: "cform",
      onsubmit: async (e) => {
        e.preventDefault();
        const w = inp.value.trim();
        if (!w) return;
        add.disabled = true;
        st.textContent = "";
        try {
          await api("muteword", fd({ w }));
          inp.value = "";
          await paint();
        } catch (x) {
          st.textContent = x.e || "Could not mute.";
        }
        add.disabled = false;
      },
    },
    inp,
    add,
  );
  paint();
  return h(
    "div",
    { class: "card" },
    h("h3", {}, "Muted on your posts"),
    h(
      "p",
      { class: "hint", style: "margin-bottom:10px" },
      "Comments from muted people, or that contain a muted word, are hidden from you on your own posts. Nobody is told. You also won\u2019t get notifications for them.",
    ),
    f,
    st,
    box,
  );
}
/* Where you're signed in: one row per browser; "Sign out" ends that browser's session on its next request */
function devicesCard() {
  const box = h("div", { class: "devs" }),
    st = h("p", { class: "hint", role: "status" });
  async function paint() {
    let r;
    try {
      r = await api("devices");
    } catch (x) {
      rc(box, h("p", { class: "hint" }, "Could not load your devices."));
      return;
    }
    const out = async (id) => {
      st.textContent = "";
      try {
        await api("devout", fd({ id }));
        await paint();
      } catch (x) {
        st.textContent = x.e || "Could not sign out that device.";
      }
    };
    rc(
      box,
      ...r.list.map((d) =>
        h(
          "div",
          { class: "dev" },
          h(
            "div",
            { class: "dinfo" },
            h("b", {}, d.label),
            h(
              "small",
              { class: "hint" },
              d.cur
                ? "This device"
                : "Active " +
                    (ago(d.last) === "now" ? "now" : ago(d.last) + " ago") +
                    " \u00b7 signed in " +
                    new Date(d.ts * 1000).toLocaleDateString(),
            ),
          ),
          d.cur ? null : h("button", { class: "ghost", type: "button", onclick: () => out(d.n) }, "Sign out"),
        ),
      ),
      r.list.length > 1
        ? h(
            "button",
            {
              class: "ghost",
              type: "button",
              style: "margin-top:8px",
              onclick: async () => {
                if (!(await cbox("Sign out all other devices? Anyone using them will have to sign in again."))) return;
                st.textContent = "";
                try {
                  await api("devoutall", fd({}));
                  await paint();
                } catch (x) {
                  st.textContent = x.e || "Could not sign out.";
                }
              },
            },
            "Sign out all other devices",
          )
        : null,
    );
  }
  paint();
  return h(
    "div",
    { class: "card" },
    h("h3", {}, "Where you\u2019re signed in"),
    h(
      "p",
      { class: "hint", style: "margin-bottom:10px" },
      "Each browser or phone you\u2019re signed in on. If you don\u2019t recognise one, sign it out and change your password. We don\u2019t keep IP addresses here.",
    ),
    box,
    st,
  );
}
/* shown for the first day of an account: what is limited and when it lifts */
function newAcctCard() {
  const nl = +(M && M.nl) || 0;
  if (nl <= 0) return null;
  const hrs = Math.max(1, Math.ceil(nl / 3600)),
    lk = nl > 86400 - 3600;
  return h(
    "div",
    { class: "card" },
    h("h3", {}, "New account limits"),
    h(
      "p",
      { class: "hint" },
      "For your first day there are lower limits on posting, commenting, messages, friend requests and questions" +
        (lk ? ", and links are off for your first hour" : "") +
        ". They lift on their own in about " +
        hrs +
        (hrs === 1 ? " hour" : " hours") +
        ".",
    ),
  );
}
/* Settings > Unlockables: what you have, and how far you are from the rest. Uses the same server list as the locks (UNL). */
function progressCard() {
  const U = UNL;
  if (!U) return h("div", { class: "card" }, h("p", { class: "hint" }, "Could not load your progress. Try again in a moment."));
  const CATS = [
      ["tbg", "Backgrounds", PBG],
      ["tbp", "Patterns", PBP],
      ["tcd", "Card styles", PCD],
      ["tfn", "Fonts", PFN],
      ["tas", "Avatar shapes", PAS],
      ["taf", "Avatar frames", PAF],
      ["tcf", "Banner frames", PBF],
    ],
    STN = { p: "posts", c: "comments", l: "likes", f: "friends", s: "best streak", d: "days here" },
    more = (s, k) =>
      s === "p"
        ? k + (k === 1 ? " more post" : " more posts")
        : s === "c"
          ? k + (k === 1 ? " more comment" : " more comments")
          : s === "l"
            ? k + (k === 1 ? " more like" : " more likes")
            : s === "f"
              ? k + (k === 1 ? " more friend" : " more friends")
              : s === "s"
                ? k + (k === 1 ? " more day" : " more days") + " of your prompt streak"
                : k + (k === 1 ? " more day" : " more days") + " on Masque",
    st = U.st || {},
    items = [];
  CATS.forEach(([k, cn, list]) => {
    const req = (U.req || {})[k] || {};
    list.forEach(([id, label]) => {
      const q = req[id];
      if (!q || q.s === "shop") return;
      const have = +(st[q.s] || 0),
        n = +q.n,
        mine = (U.eq || {})[k] === id || (U.gr || []).includes(k + ":" + id),
        done = !!U.admin || mine || have >= n;
      items.push({ k, cn, id, label, s: q.s, n, have, done, left: Math.max(0, n - have), t: q.t });
    });
  });
  const bar = (it) =>
      h("div", { class: "pgbar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": String(it.n), "aria-valuenow": String(Math.min(it.have, it.n)), "aria-label": it.label + ": " + it.have + " of " + it.n },
        h("i", { style: "width:" + Math.round((Math.min(it.have, it.n) / it.n) * 100) + "%" })),
    locked = items.filter((x) => !x.done),
    next = locked
      .slice()
      .sort((a, b) => b.have / b.n - a.have / a.n || a.left - b.left)
      .slice(0, 5),
    got = items.length - locked.length;
  const pv = (it) =>
      it.k === "tbg"
        ? h("span", { class: "sw upv", "data-pbg": it.id, "aria-hidden": "true" })
        : it.k === "tfn"
          ? h("span", { class: "upv upf", "data-pfn": it.id, "aria-hidden": "true" }, "Aa")
          : h("span", { class: "upv upg", "aria-hidden": "true" }, ic(it.done ? "check" : "star", 18)),
    nextRow = (it, i) =>
      h("div", { class: "pgrow pgn" + (i === 0 ? " first" : "") },
        pv(it),
        h("div", { class: "pgbody" },
          h("div", { class: "pgtop" }, h("b", {}, it.label), h("span", { class: "pgtag" }, i === 0 ? "Closest" : it.cn.replace(/s$/, ""))),
          bar(it),
          h("p", { class: "hint" }, more(it.s, it.left) + " (" + Math.min(it.have, it.n) + "/" + it.n + ")"))),
    catBox = ([k, cn]) => {
      const mine = items.filter((x) => x.k === k);
      if (!mine.length) return null;
      const lk = mine.filter((x) => !x.done).sort((a, b) => a.left / a.n - b.left / b.n),
        ok = mine.filter((x) => x.done);
      return h("details", { class: "pacc pgcat" },
        h("summary", {}, h("span", {}, cn), h("small", { class: "hint pgcnt" }, ok.length + " / " + mine.length)),
        h("div", { class: "unl" },
          lk.length ? h("div", { class: "unlk" }, ...lk.map((it) => h("div", { class: "pgrow pgn" }, pv(it), h("div", { class: "pgbody" }, h("div", { class: "pgtop" }, h("b", {}, it.label), h("span", { class: "hint" }, it.have + "/" + it.n)), bar(it), h("p", { class: "hint" }, it.t))))) : null,
          ok.length ? h("div", { class: "unok" }, ...ok.map((it) => h("span", { class: "unchip" }, pv(it), h("b", {}, it.label), ic("check", 14)))) : null));
    },
    pc = Math.round((got / Math.max(1, items.length)) * 100);
  return h("div", {},
    h("div", { class: "card unlbox pgtally" },
      U.admin
        ? h("p", { class: "pgnote" }, "You're an admin, so everything is unlocked for you.")
        : h("div", { class: "pghead" },
            h("div", { class: "pgring", style: "--pgp:" + pc, role: "img", "aria-label": got + " of " + items.length + " unlocked" },
              h("span", { class: "pgbig" }, String(got))),
            h("div", { class: "pgsum" },
              h("b", {}, "of " + items.length + " unlocked"),
              h("span", { class: "hint" }, items.length - got ? items.length - got + " still to earn" : "That's everything"))),
      h("div", { class: "pgtiles" }, ...["p", "c", "l", "f", "s", "d"].map((x) => h("div", {}, h("b", {}, String(st[x] || 0)), h("span", {}, STN[x]))))),
    !U.admin && next.length
      ? h("div", { class: "card" }, h("h3", {}, "Next up"), h("p", { class: "hint" }, "The ones you are closest to."), ...next.map(nextRow))
      : !U.admin
        ? h("div", { class: "card" }, h("h3", {}, "All unlocked"), h("p", { class: "hint" }, "You have every unlockable. Nicely done."))
        : null,
    h("div", { class: "card" }, h("h3", {}, "Everything"), ...CATS.map(catBox).filter(Boolean)));
}
/* Settings > Marketplace: themes you buy with Sigils. Sigils are earned from posting, commenting, likes, friends, prompt streaks and days on Masque; the server works out the balance (earned minus spent). */
const SGL = () => h("span", { class: "sgl", "aria-hidden": "true" }, ic("mask", 14));
function marketCard() {
  const U = UNL;
  if (!U || !U.shop) return h("div", { class: "card" }, h("p", { class: "hint" }, "Could not load the Marketplace. Try again in a moment."));
  const CATS = [
      ["tbg", "Backgrounds", PBG],
      ["tbp", "Patterns", PBP],
      ["taf", "Avatar frames", PAF],
      ["tcf", "Banner frames", PBF],
    ],
    box = h("div", { class: "shp" }),
    owned = (k, id) => !!U.admin || (U.gr || []).includes(k + ":" + id) || (U.eq || {})[k] === id,
    bal = () => +((U.sg || {}).bal || 0),
    pv = (k, id, label) =>
      k === "tbg"
        ? h("span", { class: "sw shppv", "data-pbg": id, "aria-hidden": "true" })
        : k === "tbp"
          ? h("div", { class: "tprev shppv", "data-pbp": id, "aria-hidden": "true" })
          : k === "taf"
            ? h("div", { class: "apv shppv", "data-paf": id, "aria-hidden": "true" }, h("div", { class: "pavw" }, av({ src: "" }, 44)))
            : h("div", { class: "cover plain shppv shpcf", "data-cf": id, "aria-hidden": "true" }),
    tier = (price) => (price >= 280 ? "legend" : price >= 220 ? "epic" : price >= 160 ? "rare" : "common"),
    /* a small copy of your profile (your banner, picture, theme) with the item on it */
    miniProfile = (k, id) => {
      const eq = U.eq || {},
        cur = {};
      ["tbg", "tbp", "tcd", "tfn", "tas", "taf", "tcf"].forEach((z) => (cur[z] = eq[z] || ""));
      cur[k] = id;
      const root = h("div", { class: "tprev shpmp", "aria-hidden": "true" }),
        cv = h("div", { class: "cover" + (M.cover ? "" : " plain") }, batFlock("f")),
        apv = h("div", { class: "apv" }, h("div", { class: "pavw" }, av({ src: M.avatar ? "?img=" + M.avatar : "" }, 64), batFlock("o")));
      [["pbg", "tbg"], ["pbp", "tbp"], ["pcd", "tcd"], ["pfn", "tfn"]].forEach(([d, s]) => cur[s] && /^\w+$/.test(cur[s]) && (root.dataset[d] = cur[s]));
      cur.tas && /^\w+$/.test(cur.tas) && (apv.dataset.pas = cur.tas);
      cur.taf && /^\w+$/.test(cur.taf) && (apv.dataset.paf = cur.taf);
      const f = bfx(cur.tcf, cur.taf);
      if (/^\w+$/.test(f)) cv.dataset.cf = f;
      if (M.cover) {
        cv.style.backgroundImage = `url(?img=${M.cover})`;
        cv.style.backgroundPosition = "50% " + (M.cy ?? 50) + "%";
      }
      root.append(
        cv,
        h("div", { class: "shpmpav" }, apv, h("div", { class: "shpmpn" }, h("span", {}, dn(M)), h("small", {}, "@" + M.name))),
        h("div", { class: "tpost" }, h("div", { class: "tn" }, h("i"), dn(M)), h("p", {}, "This is how your profile will look.")),
      );
      return root;
    },
    /* confirmation: shows the item on your profile first, then buys on the second tap */
    askBuy = (k, id, label, price, go) =>
      sheet("Buy " + label + "?", (close) => {
        const need = price - bal(),
          pick = (eq) => () => (close(), go(eq));
        return h("div", {},
          miniProfile(k, id),
          h("div", { class: "shpbuyin" },
            h("p", { class: "hint" }, "This is a preview with your current look. You have " + bal() + " Sigils."),
            need > 0
              ? h("button", { type: "button", class: "btn", disabled: true }, "Need " + need + " more")
              : h("button", { type: "button", class: "btn", onclick: pick(true) }, h("span", { class: "shpbp" }, SGL(), "Buy & equip " + price)),
            h("div", { class: "row" },
              h("button", { type: "button", class: "ghost", onclick: close }, "Not now"),
              need > 0 ? null : h("button", { type: "button", class: "ghost", onclick: pick(false) }, "Buy only"))));
      }),
    buy = async (k, id, label, price, b, msg, equip) => {
      b.disabled = true;
      msg.textContent = "";
      let eqErr = "";
      try {
        const r = await api("shopbuy", fd({ k, id })),
          was = bal();
        U.gr = r.gr;
        U.sg.bal = r.bal;
        if (equip)
          try {
            M = (await api("profile", fd({ [k]: id }))).me;
            U.eq = { ...(U.eq || {}), [k]: id };
          } catch (y) {
            eqErr = "Bought, but it could not be equipped. Pick it in Edit profile.";
          }
        paint(id, was);
        if (eqErr) slam(eqErr);
        else if (equip) slam(label + " equipped");
      } catch (x) {
        msg.textContent = (x && x.e) || "Could not buy that.";
        b.disabled = false;
      }
    },
    item = (k, id, list, price, bought) => {
      const label = (list.find((z) => z[0] === id) || [id, id])[1],
        have = owned(k, id),
        can = bal() >= price,
        msg = h("p", { class: "err shperr", role: "alert" }),
        b = have
          ? h("span", { class: "shpown" }, ic("check", 14), "Yours")
          : h("button", { type: "button", class: "btn shpbuy" + (can ? "" : " poor"), "aria-label": "Preview " + label + " for " + price + " Sigils", onclick: () => askBuy(k, id, label, price, (eq) => buy(k, id, label, price, b, msg, eq)) }, SGL(), String(price));
      return h("div", { class: "shpitem" + (have ? " own" : "") + (bought === id ? " got" : ""), "data-tier": tier(price) },
        pv(k, id, label),
        h("b", { class: "shpname" }, label),
        have ? h("div", { class: "shpact" }, b) : h("div", { class: "shpact" }, b, can ? null : h("small", { class: "hint" }, price - bal() + " more")),
        msg);
    },
    /* a shelf of things you can afford right now (only when there is something to show) */
    ready = () => {
      const out = [];
      CATS.forEach(([k, cn, list]) => Object.entries(U.shop[k] || {}).forEach(([id, price]) => {
        if (!owned(k, id) && bal() >= +price) out.push([k, id, list, +price]);
      }));
      return out.sort((a, b) => b[3] - a[3]).slice(0, 4);
    },
    paint = (bought, was) => {
      const num = h("span", { class: "shpnum" }, String(was != null ? was : bal())),
        shelf = ready();
      if (was != null) {
        const to = bal(),
          fly = h("span", { class: "shpfly", "aria-hidden": "true" }, "-" + (was - to));
        setTimeout(() => {
          if (matchMedia("(prefers-reduced-motion:reduce)").matches) return (num.textContent = String(to));
          const t0 = performance.now(),
            tick = (t) => {
              const f = Math.min(1, (t - t0) / 700);
              num.textContent = String(Math.round(was + (to - was) * (1 - Math.pow(1 - f, 3))));
              if (f < 1) requestAnimationFrame(tick);
            };
          requestAnimationFrame(tick);
          num.parentElement && num.parentElement.append(fly);
          setTimeout(() => fly.remove(), 1100);
        }, 250);
        if (matchMedia("(prefers-reduced-motion:reduce)").matches) num.textContent = String(to);
      }
      box.replaceChildren(
        ...[
        h("div", { class: "card shphead" },
          h("div", { class: "shpbal" }, h("span", { class: "shpseal" + (was != null ? " stamp" : ""), "aria-hidden": "true" }, ic("mask", 30)), num, h("span", { class: "shpunit" }, "Sigils")),
          h("p", { class: "hint" }, "Earn Sigils by posting (5), commenting (2), getting likes (1), making friends (8), keeping your prompt streak (6 a day, plus a bonus at 7, 30 and 100 days) and just being here (4 a day). Missed a day? Save your streak with a freeze (40 Sigils a day) on the Prompt of the day card.")),
        shelf.length ? h("div", { class: "card shpready" }, h("h3", {}, "You can afford"), h("div", { class: "shpcase", "data-shelf": "ready" }, h("div", { class: "shpgrid" }, ...shelf.map(([k, id, list, price]) => item(k, id, list, price, bought))))) : null,
        ...CATS.map(([k, cn, list]) => {
          const ids = Object.entries(U.shop[k] || {});
          if (!ids.length) return null;
          return h("div", { class: "card" }, h("h3", {}, cn), h("div", { class: "shpcase", "data-shelf": k }, h("div", { class: "shpgrid" }, ...ids.map(([id, price]) => item(k, id, list, +price, bought)))));
        }),
        U.admin ? h("div", { class: "card" }, h("p", { class: "hint" }, "You're an admin, so everything here is already yours."), h("button", { type: "button", class: "ghost", onclick: () => sigilSheet(M.name) }, "Give Sigils")) : null,
      ].filter(Boolean));
    };
  paint();
  return box;
}
async function settings() {
  const sec = (location.hash.split("/")[2] || "").toLowerCase();
  let np = { muted: [], pop: 1, qon: 0, qfrom: 1320, qto: 420 };
  if (sec === "notifications" || !sec)
    try {
      np = await api("np");
    } catch (e) {}
  if (!sec || sec === "unlockables" || sec === "marketplace") await unlLoad();
  const S = {};
  S.privacy = [
    h(
      "div",
      { class: "card" },
      h("h3", {}, "Privacy"),
      toggle(
        "Private account",
        "Only your friends can see your posts. Your name, bio and counts stay visible.",
        "priv",
        !!+M.priv,
        "1",
        "0",
      ),
      toggle(
        "Only friends can message me",
        "Other people will not be able to start a conversation with you.",
        "dm",
        M.dm === "friends",
        "friends",
        "all",
      ),
      toggle(
        "Allow anonymous questions",
        "People can send you questions without a name. You choose which ones to answer publicly.",
        "ask",
        !!+M.askon,
        "1",
        "0",
      ),
      askLine(),
    ),
  ];
  S.notifications = [notifCard(np), mutesCard()];
  S.unlockables = sec === "unlockables" ? [progressCard()] : [];
  S.marketplace = sec === "marketplace" ? [marketCard()] : [];
  S.masque = [
    h(
      "div",
      { class: "card" },
      h("h3", {}, "Second Masque"),
      h(
        "p",
        { class: "hint", style: "margin-bottom:10px" },
        "A second name and picture for posting and commenting. Other people are not shown that it belongs to you; only site admins can see that.",
      ),
      M.mask
        ? h(
            "div",
            { class: "row" },
            h(
              "button",
              { class: "ghost", onclick: () => (location.hash = "#/k/" + M.mask.name) },
              "View " + M.mask.name,
            ),
            h("button", { class: "ghost", onclick: () => maskSheet() }, "Edit Masque"),
          )
        : h("button", { class: "ghost", onclick: () => maskSheet() }, "Create a Masque"),
    ),
  ];
  S.appearance = [
    h("div", { class: "card" }, h("h3", {}, "Appearance"), themePick()),
    XP() ? h("div", { class: "card" }, h("h3", {}, "Profile layout"), profileLayoutPick()) : null,
    experimentalCard(),
    h("div", { class: "card" }, h("h3", {}, "Accessibility"), textSizePick(), motionPick(), soundPick()),
  ].filter(Boolean);
  S.security = [h("div", { class: "card" }, h("h3", {}, "Password"), pwForm()), mailCard(), rcCard(), devicesCard()];
  S.admin = [
    M.mod
      ? h(
          "div",
          { class: "card" },
          h("h3", {}, "Admin"),
          h("button", { class: "ghost", onclick: () => (location.hash = "#/r") }, "Reports"),
          mgBtn("Posts", "#/aposts"),
          mgBtn("Comments", "#/acomments"),
          M.admin ? mgBtn("People (users)", "#/ausers") : null,
          M.admin ? h("button", { class: "ghost", style: "display:block;width:100%;margin-top:8px", onclick: staffSheet }, "Moderators") : null,
          M.admin ? [
          h(
            "button",
            {
              class: "ghost",
              style: "display:block;width:100%;margin-top:8px",
              onclick: () => (location.hash = "#/w"),
            },
            "Blocked words",
          ),
          h(
            "button",
            { class: "ghost", style: "display:block;width:100%;margin-top:8px", onclick: maintSheet },
            "Maintenance mode" + (+MT.on ? " (on)" : ""),
          ),
          h(
            "button",
            { class: "ghost", style: "display:block;width:100%;margin-top:8px", onclick: rfSheet },
            "Force refresh",
          ),
          h(
            "a",
            {
              class: "ghost",
              href: "?a=backup",
              download: "",
              style: "display:block;text-align:center;text-decoration:none;color:inherit;margin-top:8px",
            },
            "Download backup",
          ),
          h(
            "p",
            { class: "hint", style: "margin-top:8px" },
            "The backup is the whole database (accounts, posts, messages) as one file. Photos live in the up/ folder on your server and are not included. Keep the file private.",
          ),
          ] : h("p", { class: "hint", style: "margin-top:8px" }, "You are a moderator: you can work the reports queue, answer appeals and suspend accounts for up to 30 days."),
        )
      : null,
  ];
  S.dashboard = [h("div", { class: "card" }, h("h3", {}, "Dashboard"), h("p", { class: "hint" }, "Your activity, and what needs attention for your role."), h("button", { class: "btn", onclick: () => (location.hash = "#/dash") }, "Open dashboard"))];
  S.account = [
    h(
      "div",
      { class: "card" },
      h("h3", {}, "Account"),
      h(
        "p",
        { class: "hint legal-lnk" },
        h("a", { href: "?page=terms", target: "_blank", rel: "noopener" }, "Terms"),
        " \u00b7 ",
        h("a", { href: "?page=privacy", target: "_blank", rel: "noopener" }, "Privacy"),
      ),
      h(
        "button",
        {
          class: "ghost",
          onclick: async () => {
            if (!(await cbox("Sign out? You'll need to sign in again to use Masque."))) return;
            await pushOffHere();
            await api("logout", fd({}));
            try {
              Object.keys(localStorage)
                .filter((k) => /^mq-(md|gd|pv)-/.test(k))
                .forEach((k) => localStorage.removeItem(k));
            } catch (e) {}
            M = null;
            T = (await api("me")).csrf;
            location.hash = "";
            auth();
          },
        },
        "Sign out",
      ),
    ),
    h("div", { class: "card" }, h("h3", {}, "Delete account"), delForm()),
  ];
  const M0 = [
    ["privacy", "lock", "Privacy", "Private account, who can message you, anonymous questions"],
    ["notifications", "bell", "Notifications", "What reaches your bell, pop-ups, quiet hours, muted words"],
    ["dashboard", "star", "Dashboard", "Your numbers" + (M.mod ? ", the moderation queue" : "") + (M.admin ? " and site overview" : "")],
    ["masque", "mask", "Second Masque", "A second name and picture for posting"],
    ["appearance", "sliders", "Appearance", "Theme, text size, reduce motion"],
    ["unlockables", "star", "Unlockables", "Your progress and what to unlock next"],
    ["marketplace", "gift", "Marketplace", "Spend your Sigils on themes"],
    ["security", "shield", "Security", "Password, recovery code, signed-in devices"],
  ];
  if (M.mod) M0.push(["admin", "settings", M.admin ? "Admin" : "Moderator", M.admin ? "Reports, moderators, blocked words, maintenance, backup" : "Reports and appeals"]);
  M0.push(["account", "users", "Account", "Sign out or delete your account"]);
  const cur = M0.find((r) => r[0] === sec);
  /* the menu is grouped under small labels instead of one long list (Marketplace has its own card above) */
  const SG = [["Your space", ["dashboard", "privacy", "notifications", "masque"]], ["Look and feel", ["appearance", "unlockables"]], ["Account", ["security", "admin", "account"]]],
    setItems = SG.flatMap(([lab, keys]) => {
      const rs = M0.filter((r) => keys.includes(r[0]));
      return rs.length ? [{ lab }, ...rs] : [];
    });
  if (!cur) {
    shell([
      h(
        "button",
        { class: "ghost", style: "margin-bottom:10px", onclick: () => (location.hash = "#/u/" + M.name) },
        ic("back", 16),
        "Profile",
      ),
      big("Settings"),
      h(
        "button",
        { type: "button", class: "setme", onclick: () => (location.hash = "#/u/" + M.name) },
        av(M, 52),
        h("div", { class: "cx" }, h("b", {}, dn(M)), h("span", { class: "hint" }, "@" + M.name + " \u00b7 View profile")),
        h("span", { class: "hint", "aria-hidden": "true" }, "\u203a"),
      ),
      installCard(),
      newAcctCard(),
      h(
        "button",
        { type: "button", class: "shpfeat", onclick: () => (location.hash = "#/settings/marketplace") },
        h("span", { class: "shpfseal", "aria-hidden": "true" }, ic("mask", 24)),
        h("div", { class: "cx" }, h("b", {}, "Marketplace"), h("span", { class: "hint" }, UNL && UNL.sg && !UNL.admin ? UNL.sg.bal + " Sigils to spend on themes, frames and patterns" : "Themes, frames and patterns")),
        h("span", { class: "hint", "aria-hidden": "true" }, "\u203a"),
      ),
      h(
        "div",
        { class: "setmenu" },
        ...setItems.map((r) =>
          r.lab
            ? h("div", { class: "ilab" }, h("b", {}, r.lab))
            : h(
            "button",
            { class: "chat setgo sg-" + r[0], onclick: () => (location.hash = "#/settings/" + r[0]) },
            h("span", { class: "seti", "aria-hidden": "true" }, ic(r[1], 20)),
            h("div", { class: "cx" }, h("b", {}, r[2]), h("span", { class: "hint" }, r[0] === "marketplace" && UNL && UNL.sg && !UNL.admin ? UNL.sg.bal + " Sigils to spend" : r[3])),
            h("span", { class: "hint", "aria-hidden": "true" }, "\u203a"),
          ),
        ),
      ),
    ]);
    return;
  }
  shell([
    h(
      "button",
      { class: "ghost", style: "margin-bottom:10px", onclick: () => (location.hash = "#/settings") },
      ic("back", 16),
      "Settings",
    ),
    big(cur[2]),
    ...S[sec],
  ]);
}
/* messages */
const gva = (g, n) => (g && g.avatar ? av({ src: "?img=" + g.avatar }, n) : gav(n));
const gav = (n) => {
  const d = h("div", { class: "av", "aria-hidden": "true" }, ic("users", Math.round(n * 0.5)));
  d.style.cssText = `width:${n}px;height:${n}px;display:grid;place-items:center;color:#fff;background:linear-gradient(145deg,#a3acb2,#7d878e)`;
  return d;
};
/* the search box on the Messages page keeps its text when the list refreshes by itself (new message, status change) and is cleared when you open the page fresh */
let IQ = "";
async function inbox(keep) {
  const [{ chats, reqs: RQ, inb }, gr, gi] = await Promise.all([
    api("inbox"),
    api("ginbox").catch(() => ({ groups: [] })),
    api("ginv").catch(() => ({ invites: [] })),
  ]);
  const invs = gi.invites || [];
  const all = [...chats.map((c) => ({ ...c, k: "d" })), ...gr.groups.map((c) => ({ ...c, k: "g" }))].sort(
      (a, b) => b.ts - a.ts,
    ),
    has = !!M.mask;
  /* two lists: chats you have as yourself (and groups) under Main, chats you have as your Masque under Masque. It opens on whichever mode you are in. */
  let tab = has ? (keep && ITAB ? ITAB : ASM ? "k" : "m") : "m";
  ITAB = tab;
  if (!keep) IQ = "";
  const side = (c) => (c.k === "d" && +c.ms ? "k" : "m");
  /* groups: one you joined only as your Masque is under Masque; one you are in as yourself is under Main, and also under Masque when your Masque sits in it too */
  const inTab = (c, t) => (c.k === "g" ? (t === "k" ? !!(+c.gp || +c.gk) : !+c.gp) : side(c) === t);
  const ikey = (c) => (c.k === "g" ? "g" + c.id : "d" + c.name + (+c.ms ? "/k" : "")),
    prevI = keep ? INBX : null;
  INBX = {};
  all.forEach((c) => (INBX[ikey(c)] = c.ts + "|" + (+c.un || 0)));
  const row0 = (c) =>
    c.k === "g"
      ? h(
          "button",
          { class: "chat", onclick: () => (location.hash = "#/g/" + c.id) },
          gva(c, 44),
          h(
            "div",
            { class: "cx" },
            h("b", {}, c.name),
            h(
              "span",
              { class: "hint" },
              ...(dprev(c)
                ? [h("b", { class: "drf" }, "Draft: "), dprev(c)]
                : [
                    c.txt || c.img
                      ? (+c.mine ? "You" : c.who) + ": " + (ptx(c.txt) || (isAudN(c.img) ? "Audio" : "Photo"))
                      : "No messages yet",
                  ]),
            ),
          ),
          csChip(c.cs, "g" + c.id),
          h("small", { class: "hint" }, ago(c.ts)),
          +c.un ? h("span", { class: "badge" }, c.un) : null,
        )
      : h(
          "button",
          {
            class: "chat" + (+c.ms ? " asm" : ""),
            onclick: () => (location.hash = "#/m/" + c.name + (+c.ms ? "/k" : "")),
          },
          avw(av(c, 44), c.st, +c.mk || +c.ms, c.name),
          h(
            "div",
            { class: "cx" },
            c.sx && !+c.mk && !+c.ms ? h("span", { class: "cnm" }, h("b", {}, pdn(c)), sbub(c.sx, "in")) : h("b", {}, pdn(c)),
            +c.mk ? h("small", { class: "hint" }, "Masque") : null,
            h(
              "span",
              { class: "hint" },
              ...(dprev(c)
                ? [h("b", { class: "drf" }, "Draft: "), dprev(c)]
                : [(+c.mine ? "You: " : "") + (ptx(c.txt) || (isAudN(c.img) ? "Audio" : "Photo"))]),
            ),
          ),
          csChip(c.cs, "d" + c.name + (+c.ms ? "/k" : "")),
          h("small", { class: "hint" }, ago(c.ts)),
          +c.un ? h("span", { class: "badge" }, c.un) : null,
        );
  /* long-press a chat: mute it, delete it for you only (DMs), or leave it (groups) */
  const chatMenu = (c) => {
    const g = c.k === "g",
      nm = g ? c.name : pdn(c),
      args = () => (g ? { gid: c.id } : { u: c.name, mk: +c.mk ? 1 : 0, as: +c.ms ? 1 : 0 });
    sheet(nm, (close) => {
      const err = h("p", { class: "err", role: "alert" }),
        item = (icon, label, sub, fn, danger) =>
          h(
            "button",
            {
              type: "button",
              class: "chat setgo" + (danger ? " danger" : ""),
              onclick: async () => {
                err.textContent = "";
                try {
                  await fn();
                } catch (x) {
                  err.textContent = (x && x.e) || "Something went wrong. Try again.";
                }
              },
            },
            h("span", { class: "seti", "aria-hidden": "true" }, ic(icon, 20)),
            h("div", { class: "cx" }, h("b", {}, label), sub ? h("span", { class: "hint" }, sub) : null),
          ),
        mu = +c.mu;
      return h(
        "div",
        { class: "setmenu cmenu" },
        item(
          mu ? "bell" : "bellx",
          mu ? "Unmute" : "Mute",
          mu ? "Pop-ups and the unread badge are back on." : "No pop-ups and no unread badge. The chat stays in your list.",
          async () => {
            await api(g ? "gmute" : "cmute", fd({ ...args(), on: mu ? 0 : 1 }));
            close();
            inbox(true);
          },
        ),
        g
          ? item(
              "close",
              "Leave group",
              "You will no longer see its messages.",
              async () => {
                if (!(await cbox("Leave this group? You will no longer see its messages. If you are the last member, the group is deleted."))) return;
                await api("gleave", fd({ gid: c.id }));
                try {
                  localStorage.removeItem(dkG(c.id));
                } catch (e) {}
                close();
                inbox(true);
              },
              1,
            )
          : item(
              "trash",
              "Delete chat",
              "Removed for you only. " + nm + " keeps their copy.",
              async () => {
                if (
                  !(await cbox(
                    "Delete this chat? It is removed for you only. " + nm + " keeps their copy, and it comes back if they message you again.",
                  ))
                )
                  return;
                await api("cdel", fd(args()));
                try {
                  localStorage.removeItem(dkD(c.name, +c.ms));
                } catch (e) {}
                close();
                inbox(true);
              },
              1,
            ),
        err,
      );
    });
  };
  const row = (c) => {
    const e = row0(c);
    if (prevI && prevI[ikey(c)] !== INBX[ikey(c)]) e.classList.add("rnew");
    e.classList.add("lpr");
    if (+c.un && !+c.mu) e.classList.add("unr");
    if (+c.mu) {
      e.classList.add("muted");
      const t = e.querySelector(":scope > small.hint");
      if (t) e.insertBefore(h("span", { class: "mutei", role: "img", "aria-label": "Muted" }, ic("bellx", 14)), t);
    }
    lpress(e, () => chatMenu(c));
    return e;
  };
  /* Home-style section labels: unread chats first, then the rest (only when both exist and nobody is searching) */
  const ilab = (t, n) => h("div", { class: "ilab" }, h("b", {}, t), h("span", {}, String(n)));
  const grouped = (list) => {
    if (IQ.trim()) return list.map(row);
    const u = list.filter((c) => +c.un && !+c.mu),
      r = list.filter((c) => !(+c.un && !+c.mu));
    return u.length && r.length ? [ilab("Unread", u.length), ...u.map(row), ilab("Earlier", r.length), ...r.map(row)] : list.map(row);
  };
  const body = h("div", { class: "ilist" }),
    tb = h("div", { class: "tabs itabs", role: "tablist", "aria-label": "Chats" }),
    cnt = (t) =>
      all.filter((c) => inTab(c, t)).reduce((n, c) => n + (+c.un || 0), 0) + (t === "k" ? (RQ || []).length : 0),
    reqs = RQ || [];
  const rqRow = (r) => {
    const act = async (a) => {
        try {
          await api("mreq", fd({ u: r.name, pm: +r.mk, act: a }));
          inbox(true);
        } catch (e) {
          alert(e.e || "Could not update this request.");
        }
      },
      pv = (ptx(r.txt) || (+r.img ? "\u{1F4F7} Photo" : "")) + (+r.cnt > 1 ? " \u00b7 +" + (r.cnt - 1) + " more" : "");
    return h(
      "div",
      { class: "chat rqrow" },
      h(
        "button",
        {
          type: "button",
          class: "rqopen",
          "aria-label": "Open the request from " + r.name,
          onclick: () => (location.hash = "#/m/" + r.name + "/k"),
        },
        av(r, 44),
        h(
          "div",
          { class: "cx" },
          h("b", {}, r.name),
          +r.mk ? h("small", { class: "hint" }, "Masque") : null,
          h("span", { class: "hint" }, pv),
        ),
      ),
      h(
        "div",
        { class: "rqact" },
        h("button", { type: "button", class: "btn", onclick: () => act("accept") }, "Accept"),
        h("button", { type: "button", class: "ghost", onclick: () => act("ignore") }, "Ignore"),
      ),
    );
  };
  const invRow = (v) => {
    const act = async (a) => {
      try {
        const x = await api("gacc", fd({ id: v.id, act: a }));
        if (a === "accept") location.hash = "#/g/" + x.id;
        else inbox(true);
      } catch (e) {
        alert(e.e || "Could not update this invite.");
        inbox(true);
      }
    };
    return h(
      "div",
      { class: "chat rqrow" },
      h(
        "div",
        { class: "rqopen" },
        gva(v, 44),
        h(
          "div",
          { class: "cx" },
          h("b", {}, v.name),
          h("span", { class: "hint" }, v.who + " invited " + (+v.pm ? "your Masque" + (v.mq ? " " + v.mq : "") : "you") + " to join"),
        ),
      ),
      h(
        "div",
        { class: "rqact" },
        h("button", { type: "button", class: "btn", onclick: () => act("accept") }, "Join"),
        h("button", { type: "button", class: "ghost", onclick: () => act("decline") }, "Decline"),
      ),
    );
  };
  const swRow = () =>
    h(
      "div",
      { class: "mqsw" },
      h(
        "div",
        { class: "cx" },
        h("b", {}, "New messages"),
        h(
          "span",
          { class: "hint" },
          +inb
            ? "Anyone can send " + M.mask.name + " a message request."
            : "Turned off. Only chats you started can continue.",
        ),
      ),
      h(
        "button",
        {
          type: "button",
          class: "ghost",
          "aria-pressed": String(!!+inb),
          onclick: async () => {
            try {
              await api("maskinb", fd({ on: +inb ? 0 : 1 }));
              inbox(true);
            } catch (e) {
              alert(e.e || "Could not change that.");
            }
          },
        },
        +inb ? "Turn off" : "Turn on",
      ),
    );
  let fl = null,
    pf = [],
    pt = 0,
    pseq = 0;
  /* people search for the box above the list: your friends (loaded once) and everyone matching on Masque (same lookup as Explore) */
  const lookup = () => {
    clearTimeout(pt);
    const v = IQ.trim(),
      my = ++pseq;
    if (!v || tab === "k") {
      if (pf.length) {
        pf = [];
        paint();
      }
      return;
    }
    if (!fl) {
      fl = [];
      api("friends")
        .then(({ list }) => {
          fl = list.filter((x) => +x.st);
          paint();
        })
        .catch(() => {});
    }
    pt = setTimeout(async () => {
      try {
        const { users } = await api("find", null, "&q=" + encodeURIComponent(v));
        if (my === pseq) {
          pf = users;
          paint();
        }
      } catch (e) {}
    }, 250);
  };
  const paint = () => {
    const sr = IQ.trim() !== "",
      qn = IQ.trim().toLowerCase(),
      list = all.filter(
        (c) =>
          inTab(c, tab) &&
          (!sr || (c.name + " " + (c.k === "g" ? "" : pdn(c)) + " " + (c.txt || "")).toLowerCase().includes(qn)),
      );
    /* while searching on the Main tab: friends you have not chatted with yet (tap to message), then anyone else on Masque (tap to open their profile). Masque chats are started from a profile, so that tab only filters. */
    const have = new Set(list.filter((c) => c.k === "d").map((c) => c.name)),
      fm = sr && tab !== "k" ? (fl || []).filter((u) => !have.has(u.name) && (u.name + " " + dn(u)).toLowerCase().includes(qn)) : [],
      seen = new Set([...have, ...fm.map((u) => u.name), M.name]),
      pp = sr && tab !== "k" ? pf.filter((u) => !seen.has(u.name)) : [],
      extra = [
        ...(fm.length
          ? [
              h("h3", { class: "vt" }, "Friends"),
              ...fm.map((u) =>
                h(
                  "button",
                  { class: "chat", onclick: () => (location.hash = "#/m/" + u.name) },
                  av(u, 44),
                  h("div", { class: "cx" }, h("b", {}, dn(u)), h("span", { class: "hint" }, "Message")),
                ),
              ),
            ]
          : []),
        ...(pp.length
          ? [
              h("h3", { class: "vt" }, "People"),
              ...pp.map((u) =>
                h(
                  "button",
                  { class: "chat", onclick: () => (location.hash = "#/u/" + u.name) },
                  av(u, 44),
                  h("div", { class: "cx" }, h("b", {}, dn(u)), h("span", { class: "hint" }, "View profile")),
                ),
              ),
            ]
          : []),
      ];
    body.className = "ilist" + (tab === "k" ? " mqlist" : "");
    const rcnt = !sr
      ? recentRow(
          "inbox",
          (x) => {
            IQ = x;
            sq.value = x;
            paint();
            lookup();
            sq.focus();
          },
          paint,
        )
      : null;
    body.replaceChildren(
      ...(rcnt ? [rcnt] : []),
      ...(!sr
        ? [
            h(
              "button",
              { type: "button", class: "chat rmentry", onclick: () => (location.hash = "#/o") },
              h("span", { class: "rmdot", "aria-hidden": "true" }),
              h("div", { class: "cx" }, h("b", {}, "Rooms"), h("span", { class: "hint" }, "Temporary themed chats that close by themselves")),
              ic("chev", 16),
            ),
          ]
        : []),
      ...(tab === "k" && !sr
        ? [
            h(
              "div",
              { class: "mqnote", role: "note" },
              lmIcon(20),
              h(
                "span",
                {},
                h("b", {}, "Masque chats"),
                "These are chats you have as " + M.mask.name + ". Nobody is told it's you.",
              ),
            ),
            swRow(),
            ...(reqs.length
              ? [
                  h(
                    "div",
                    { class: "rqhead" },
                    h("b", {}, "Message requests (" + reqs.length + ")"),
                    h(
                      "small",
                      { class: "hint" },
                      "Strangers who wrote to " +
                        M.mask.name +
                        ". They stay here until you accept, and replying accepts too.",
                    ),
                  ),
                  ...reqs.map(rqRow),
                ]
              : []),
          ]
        : []),
      ...(tab !== "k" && invs.length && !sr
        ? [h("div", { class: "rqhead" }, h("b", {}, "Group invites (" + invs.length + ")")), ...invs.map(invRow)]
        : []),
      ...(list.length
        ? grouped(list)
        : sr
          ? extra.length
            ? []
            : [emp("search", "No matches", "Nothing in this list matches \u201c" + IQ.trim() + "\u201d.")]
          : (tab === "k" && reqs.length) || (tab !== "k" && invs.length)
          ? []
          : [
              tab === "k"
                ? emp("chat", "No Masque chats yet", "Open a chat with someone and tap As Masque to start one.")
                : emp(
                    "chat",
                    "No conversations yet",
                    "Visit someone's profile and tap Message, or start a group with your friends.",
                  ),
            ]),
      ...extra,
    );
  };
  const pickTab = (k) => {
    if (tab === k) return;
    tab = k;
    ITAB = k;
    [...tb.children].forEach((x) => x.setAttribute("aria-selected", String(x.dataset.k === k)));
    document.querySelector(".feed")?.classList.remove("go");
    paint();
    lookup();
    swap(body, k === "k" ? 1 : -1);
  };
  /* holding the Profile button (you <-> your Masque) moves this list to the matching tab too */
  INSET = has ? Object.assign(pickTab, { tb }) : null;
  if (has)
    [
      ["m", "Main", ic("chat", 18)],
      ["k", "Masque", lmIcon(18)],
    ].forEach(([k, label, icon]) => {
      const n = cnt(k);
      tb.append(
        h(
          "button",
          { type: "button", role: "tab", "data-k": k, "aria-selected": String(k === tab), onclick: () => pickTab(k) },
          icon,
          h("span", {}, label),
          n ? h("span", { class: "badge", "aria-label": n + " unread" }, n) : null,
        ),
      );
    });
  const hadF = !!(document.activeElement && document.activeElement.classList && document.activeElement.classList.contains("isearch")),
    sq = h("input", {
      type: "search",
      class: "isearch",
      placeholder: "Search chats, friends and people",
      "aria-label": "Search your chats, friends and people",
      autocomplete: "off",
      maxlength: 60,
      oninput: (e) => {
        IQ = e.target.value;
        paint();
        lookup();
      },
      onkeydown: (e) => {
        if (e.key === "Enter") recentAdd(e.target.value, "inbox");
      },
    });
  /* tapping any search result (a chat, a friend, a person) also saves the search */
  body.addEventListener("click", () => {
    if (IQ.trim()) recentAdd(IQ, "inbox");
  });
  sq.value = IQ;
  paint();
  if (IQ.trim()) lookup();
  shell([
    big("Messages", "tight"),
    h(
      "div",
      { class: "row inbar" },
      h("button", { class: "ghost", onclick: newGroup }, ic("plus", 16), "Group"),
      h("button", { class: "ghost", onclick: to("#/f") }, ic("users", 16), "Friends"),
      h(
        "button",
        {
          type: "button",
          class: "ghost",
          "aria-label": "Set your status",
          title: "Set your status",
          onclick: () => statusSheet(() => inbox(true)),
        },
        h("span", { class: "pdot s-" + { "": "on", online: "on", idle: "idle", lurk: "lurk", off: "off" }[M.pst || ""] }),
        { "": "Auto", online: "Online", idle: "Idle", lurk: "Lurking", off: "Invisible" }[M.pst || ""],
      ),
    ),
    has ? tb : null,
    sq,
    body,
  ]);
  if (hadF) {
    sq.focus();
    try {
      sq.setSelectionRange(sq.value.length, sq.value.length);
    } catch (e) {}
  }
}
function newGroup() {
  sheet("New group", (close) => {
    const nm = h("input", {
        placeholder: "Group name",
        maxlength: 40,
        "aria-label": "Group name",
        autocomplete: "off",
      }),
      err = h("p", { class: "err", role: "alert" }),
      box = h("div", { class: "gpick" }, h("p", { class: "hint" }, "Loading friends\u2026")),
      go = h("button", { class: "btn full", type: "submit" }, "Create group"),
      sel = new Set();
    api("friends")
      .then(({ list }) => {
        const fr = list.filter((x) => +x.st);
        box.replaceChildren(
          ...(fr.length
            ? fr.map((u) => {
                const b = h(
                  "button",
                  { type: "button", class: "chat gp", "aria-pressed": "false" },
                  av(u, 36),
                  h("div", { class: "cx" }, h("b", {}, dn(u))),
                  h("span", { class: "gtick" }, ic("check", 16)),
                );
                b.onclick = () => {
                  const on = !sel.has(u.name);
                  on ? sel.add(u.name) : sel.delete(u.name);
                  b.setAttribute("aria-pressed", on);
                };
                return b;
              })
            : [h("p", { class: "hint" }, "Add some friends first, then you can start a group.")]),
        );
      })
      .catch(() => box.replaceChildren(h("p", { class: "hint" }, "Couldn\u2019t load your friends.")));
    return h(
      "form",
      {
        class: "form",
        onsubmit: async (e) => {
          e.preventDefault();
          if (!nm.value.trim()) {
            err.textContent = "Give the group a name.";
            return;
          }
          if (!sel.size) {
            err.textContent = "Pick at least one friend.";
            return;
          }
          go.disabled = true;
          err.textContent = "";
          try {
            const r = await api("gcreate", fd({ name: nm.value, members: [...sel].join(",") }));
            close();
            location.hash = "#/g/" + r.id;
          } catch (x) {
            err.textContent = x.e || "Could not create the group.";
            go.disabled = false;
          }
        },
      },
      nm,
      box,
      err,
      go,
    );
  });
}
/* search inside one chat: type 2+ letters, tap a result and the chat scrolls to that message (loading older history around it if needed) */
function chatSearch(o) {
  sheet("Search messages", (close) => {
    const inp = h("input", {
        type: "search",
        placeholder: "Search this chat\u2026",
        maxlength: 60,
        "aria-label": "Search messages",
        autocomplete: "off",
      }),
      box = h("div", { class: "sres", "aria-live": "polite" });
    let t = 0,
      seq = 0;
    const idle = () => {
      const r = recentRow(
        "chat",
        (x) => {
          inp.value = x;
          inp.oninput();
          inp.focus();
        },
        idle,
      );
      box.replaceChildren(...(r ? [r] : []), h("p", { class: "hint" }, "Type at least 2 letters."));
    };
    const mark = (txt, q) => {
      const i = txt.toLowerCase().indexOf(q.toLowerCase()),
        a = Math.max(0, i - 40),
        z = txt.slice(a, a + 140);
      if (i < 0) return [z];
      const k = i - a;
      return [
        (a ? "\u2026" : "") + z.slice(0, k),
        h("mark", {}, z.slice(k, k + q.length)),
        z.slice(k + q.length) + (a + 140 < txt.length ? "\u2026" : ""),
      ];
    };
    const paint = (res, q) =>
      box.replaceChildren(
        ...(res.length
          ? res.map((m) =>
              h(
                "button",
                {
                  type: "button",
                  class: "ghost sresr",
                  onclick: () => {
                    recentAdd(inp.value, "chat");
                    close();
                    o.jump(m.id);
                  },
                },
                h(
                  "span",
                  { class: "srh" },
                  h("b", {}, +m.mine ? "You" : o.who(m)),
                  h(
                    "small",
                    { class: "hint" },
                    new Date(m.ts * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }),
                  ),
                ),
                h("span", { class: "srt" }, ...mark(ptx(m.txt), q)),
              ),
            )
          : [h("p", { class: "hint" }, "No messages found.")]),
      );
    inp.oninput = () => {
      clearTimeout(t);
      const v = inp.value.trim();
      if (v.length < 2) {
        seq++;
        idle();
        return;
      }
      t = setTimeout(async () => {
        const my = ++seq;
        try {
          const x = await api(o.api, null, o.qs + "&q=" + encodeURIComponent(v));
          if (my === seq) paint(x.res, v);
        } catch (e) {
          if (my === seq) box.replaceChildren(h("p", { class: "err", role: "alert" }, (e && e.e) || "Search failed."));
        }
      }, 250);
    };
    inp.onkeydown = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (inp.value.trim().length >= 2) recentAdd(inp.value, "chat");
      }
    };
    idle();
    setTimeout(() => inp.focus(), 60);
    return h("div", { class: "form" }, inp, box);
  });
}
/* the chat message box. A plain <input> makes phones show the autofill bar (passwords, cards, addresses); an editable div does not, which is what Discord does. It answers to the same things the code uses on an input: value, maxLength, placeholder, selection, focus, Enter sends the form. Text only, one line. */
function chatBox(o) {
  const el = h("div", {
    class: "mbox",
    role: "textbox",
    "aria-label": o.label || "Message",
    "aria-multiline": "false",
    enterkeyhint: "send",
    spellcheck: "true",
    autocapitalize: "sentences",
    "data-ph": o.placeholder || "",
  });
  el.contentEditable = "plaintext-only";
  if (el.contentEditable !== "plaintext-only") el.contentEditable = "true";
  const max = o.maxlength || 500;
  const txt = () => el.textContent.replace(/\u00a0/g, " ");
  const off = (node, n) => {
    const r = document.createRange();
    r.selectNodeContents(el);
    try {
      r.setEnd(node, n);
    } catch (e) {
      return txt().length;
    }
    return r.toString().length;
  };
  const sel = () => {
    const s = getSelection();
    if (!s || !s.rangeCount || !el.contains(s.anchorNode)) return [txt().length, txt().length];
    const a = off(s.anchorNode, s.anchorOffset),
      b = off(s.focusNode, s.focusOffset);
    return [Math.min(a, b), Math.max(a, b)];
  };
  const put = (a, b) => {
    const t = el.firstChild;
    const s = getSelection(),
      r = document.createRange();
    if (!t) {
      r.selectNodeContents(el);
      r.collapse(true);
    } else {
      r.setStart(t, Math.min(a, t.length));
      r.setEnd(t, Math.min(b, t.length));
    }
    s.removeAllRanges();
    s.addRange(r);
  };
  Object.defineProperties(el, {
    value: {
      get: txt,
      set: (v) => {
        el.textContent = v;
        if (!v) el.replaceChildren();
      },
    },
    maxLength: { get: () => max },
    placeholder: { get: () => el.dataset.ph, set: (v) => (el.dataset.ph = v) },
    selectionStart: { get: () => sel()[0] },
    selectionEnd: { get: () => sel()[1] },
  });
  el.setSelectionRange = (a, b) => put(a, b);
  el.select = () => put(0, txt().length);
  const fit = () => {
    if (!el.textContent) el.replaceChildren();
    if (txt().length > max) {
      el.textContent = txt().slice(0, max);
      put(max, max);
    }
  };
  el.addEventListener("input", fit);
  el.addEventListener("beforeinput", (e) => {
    if (e.inputType === "insertParagraph" || e.inputType === "insertLineBreak") e.preventDefault();
  });
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing) {
      e.preventDefault();
      const f = el.closest("form");
      if (f && f.requestSubmit) f.requestSubmit();
    }
  });
  el.addEventListener("paste", (e) => {
    const d = e.clipboardData,
      t = d && d.getData("text/plain");
    if (!t) return;
    e.preventDefault();
    const [a, b] = sel(),
      room = max - (txt().length - (b - a));
    const add = t.replace(/\s*[\r\n]+\s*/g, " ").slice(0, Math.max(0, room));
    if (add) document.execCommand("insertText", false, add);
  });
  return el;
}
/* typing: your input pings the server at most every 2.5 s while you type (and says "stopped" if you clear it); the open chat shows a dots bubble while the other side is typing */
function pinger(inp, mk) {
  let last = 0,
    on = false;
  return () => {
    const v = inp.value.trim(),
      n = Date.now();
    if (!v) {
      if (on) {
        on = false;
        mk(1);
      }
      return;
    }
    if (n - last > 2500) {
      last = n;
      on = true;
      mk(0);
    }
  };
}
function typer(list) {
  const lab = h("span", { class: "tl" }),
    el = h(
      "div",
      { class: "typ", role: "status" },
      h("span", { class: "dots", "aria-hidden": "true" }, h("i"), h("i"), h("i")),
      lab,
    );
  let names = [],
    tm = 0;
  new MutationObserver(() => {
    if (names.length && el.parentNode !== list) {
      list.append(el);
      if (list.dataset.stick === "1") list.scrollTop = list.scrollHeight;
    }
  }).observe(list, { childList: true });
  return (v) => {
    const n = Array.isArray(v) ? v : v ? [""] : [];
    if (JSON.stringify(n) === JSON.stringify(names)) return;
    names = n;
    clearTimeout(tm);
    if (!n.length) {
      if (el.parentNode === list && !RM.matches) {
        el.classList.add("out");
        tm = setTimeout(() => {
          if (!names.length) el.remove();
        }, 200);
      } else el.remove();
      return;
    }
    el.classList.remove("out");
    lab.textContent = n[0] ? n.join(", ") + (n.length > 1 ? " are typing" : " is typing") : "typing";
    const end = list.scrollHeight - list.scrollTop - list.clientHeight < 80;
    if (el.parentNode !== list) list.append(el);
    if (end) list.scrollTop = list.scrollHeight;
  };
}
/* paste or drop an image into a chat: it goes through the same flow as the paperclip (shown as a chip, sent with Send), so the size limits and photo clean-up are the same */
function chatPaste(inp, area, pick) {
  const take = (files) => {
    const f = [...(files || [])].find((x) => x.type && x.type.startsWith("image/"));
    if (!f) return false;
    try {
      const dt = new DataTransfer();
      dt.items.add(f);
      pick.files = dt.files;
    } catch (_) {
      return false;
    }
    pick.onchange();
    return true;
  };
  inp.addEventListener("paste", (e) => {
    const d = e.clipboardData;
    if (d && !d.getData("text/plain") && take(d.files)) e.preventDefault();
  });
  const hasFiles = (e) => e.dataTransfer && [...(e.dataTransfer.types || [])].includes("Files");
  let depth = 0;
  area.addEventListener("dragenter", (e) => {
    if (!hasFiles(e)) return;
    depth++;
    area.classList.add("dropping");
  });
  area.addEventListener("dragover", (e) => {
    if (hasFiles(e)) e.preventDefault();
  });
  area.addEventListener("dragleave", () => {
    if (--depth <= 0) {
      depth = 0;
      area.classList.remove("dropping");
    }
  });
  area.addEventListener("drop", (e) => {
    depth = 0;
    area.classList.remove("dropping");
    if (!hasFiles(e)) return;
    e.preventDefault();
    take(e.dataTransfer.files);
  });
}
/* opened from a group invite link (#/gj/<code>): shows the group and asks before joining */
async function gjoinPage(c) {
  let x;
  try {
    x = await api("glinkinfo", null, "&c=" + encodeURIComponent(c));
  } catch (e) {
    shell(emp("lock", "Invite link not valid", (e && e.e) || "This invite link is not valid any more."));
    return;
  }
  if (+x.in) {
    location.hash = "#/g/" + x.g.id;
    return;
  }
  const err = h("p", { class: "err", role: "alert" }),
    go = h("button", { type: "button", class: "btn full" }, "Join group");
  go.onclick = async () => {
    go.disabled = true;
    err.textContent = "";
    try {
      const j = await api("gjoin", fd({ c }));
      location.hash = "#/g/" + j.id;
    } catch (e) {
      err.textContent = e.e || "Could not join.";
      go.disabled = false;
    }
  };
  shell(
    h(
      "div",
      { class: "card gjoin" },
      gva(x.g, 72),
      h("h3", {}, x.g.name),
      h("p", { class: "hint" }, "You were invited to this group chat. " + x.g.n + (+x.g.n === 1 ? " member" : " members") + "."),
      go,
      h("button", { type: "button", class: "ghost full", onclick: () => (location.hash = "#/m") }, "Not now"),
      err,
    ),
  );
}
/* chat background choices for groups: [key, label] */
const GBG = [
  ["", "Default"],
  ["sage", "Sage"],
  ["sky", "Sky"],
  ["rose", "Rose"],
  ["sand", "Sand"],
  ["lilac", "Lilac"],
  ["dusk", "Dusk"],
  ["dots", "Dots"],
  ["grid", "Grid"],
  ["starry", "Starry"],
  ["petals", "Petals"],
  ["curtain", "Curtain call"],
  ["castle", "Castle Night"],
  ["castlepaint", "Painted castle"],
  ["castleash", "Shadow castle"],
];
/* the sentence for a group notice: e = {kind, who, tw, arg} */
const gevText = (e) => {
  const w = e.who,
    t = e.tw || "someone";
  switch (e.kind) {
    case "name":
      return w + ' changed the group name to "' + e.arg + '"';
    case "icon":
      return w + (e.arg === "removed" ? " removed the group photo" : " changed the group photo");
    case "bg": {
      const l = (GBG.find(([k]) => k === e.arg) || [])[1];
      return w + (e.arg ? " changed the chat theme to " + (l || "a new theme") : " reset the chat theme");
    }
    case "add":
      return w + " added " + t;
    case "invite":
      return w + " invited " + t;
    case "join":
      return w + (e.arg === "link" ? " joined with an invite link" : " joined the group");
    case "kick":
      return w + " removed " + t;
    case "leave":
      return w + " left the group";
  }
  return "";
};
function groupSheet(g) {
  sheet("Edit group", (close, veil) => {
    const fa = picForm(
      "Group picture",
      "Shown in the chat list and at the top of the chat. Anyone in the group can change it.",
      g.avatar ? "?img=" + g.avatar : "",
      gav,
      async (avF, rm) => {
        const d = new FormData();
        d.append("gid", g.id);
        if (avF) d.append("avatar", await avF);
        else d.append("noavatar", "1");
        g.avatar = (await api("gicon", d)).avatar;
      },
    );
    const nm = h("input", { value: g.name, maxlength: 40, autocomplete: "off", "aria-label": "Group name" });
    const fn = pform(
      "Group name",
      null,
      async () => {
        const v = nm.value.trim();
        if (!v) throw { e: "Give the group a name." };
        g.name = (await api("grename", fd({ gid: g.id, name: v }))).name;
      },
      h("label", { class: "f" }, "Name", nm),
    );
    fn.addEventListener("input", () => fn.touch());
    return pagg(close, veil, [["Group name", fn, true], ["Group picture", fa]]);
  });
}
async function gthread(id) {
  const h0 = location.hash;
  let r;
  try {
    r = await api("gthread", null, "&id=" + id);
  } catch (e) {
    shell(emp("lock", "Group unavailable", "It doesn't exist, or you're not in it."));
    return;
  }
  refineTitle(h0, r.g.name || "Group");
  const list = h("div", { class: "mlist", role: "log" }),
    err = h("p", { class: "err", role: "alert" }),
    inp = chatBox({ placeholder: "Message\u2026", maxlength: 500 }),
    go = h("button", { class: "btn", type: "submit" }, "Send");
  let sig = "",
    seenBy = r.seen || { mid: 0, by: [] },
    mem = r.members,
    cur = [],
    evs = r.events || [],
    pins = r.pins || [];
  const cx = chatx({
      mnt: (n) => {
        n = n.toLowerCase();
        if (n === "everyone") return { all: 1, me: 1 };
        return mem.some((z) => String(z.name).toLowerCase() === n) ? { me: isMe(n) } : null;
      },
      rk: "greact",
      pk: "gpin",
      who: (m) => dn(m),
      qsend: async (t, rp) => {
        const d = new FormData();
        d.append("gid", id);
        d.append("txt", t);
        d.append("rp", rp);
        await api("gsend", d);
        SFX.play("send");
        await reload();
      },
      inp,
      jump: (id) => jump(id),
      patch: (id, fn) => {
        const m = cur.find((z) => +z.id === +id);
        if (m) {
          fn(m);
          draw(cur, true, true);
        }
      },
      setPin: (m, v) => {
        m.pin = v;
        pins = pins.filter((p) => +p.id !== +m.id);
        if (v) pins.unshift({ id: m.id, t: (m.txt || "").slice(0, 80), i: m.img ? 1 : 0, mine: +m.mine, who: dn(m) });
        pins = pins.slice(0, 5);
      },
    }),
    put = (x, f, k) => {
      pins = x.pins || [];
      evs = x.events || [];
      csUpd(x.cs);
      draw(x.msgs, f, k);
    };
  let jb = null;
  const showBack = () => {
      if (jb && jb.isConnected) return;
      jb = h("button", { type: "button", class: "btn jlat" }, "Jump to latest");
      jb.onclick = () => reload();
      list.closest(".tcard").append(jb);
    },
    jump = async (mid) => {
      const f = () => list.querySelector('[data-mid="' + mid + '"]');
      let e = f();
      if (!e) {
        if (CUR) CUR.hold = 1;
        try {
          const x = await api("gthread", null, "&id=" + id + "&around=" + mid);
          mem = x.members;
          seenBy = x.seen || seenBy;
          put(x, true);
        } catch (_) {
          return;
        }
        e = f();
        showBack();
      }
      if (e) {
        e.scrollIntoView({ block: "center" });
        e.classList.add("mflash");
        setTimeout(() => e.classList.remove("mflash"), 1800);
      }
    };
  const sub = h("small", { class: "hint" }, mem.length + " members"),
    nameEl = h("b", {}, r.g.name),
    sync = (g) => {
      sub.textContent = mem.length + " members";
      if (g && g.name) nameEl.textContent = g.name;
      if (g && "bg" in g) {
        r.g.bg = g.bg || "";
        list.dataset.bg = r.g.bg;
      }
    },
    gone = (e) => {
      if (e && e.e === "No such group.") location.hash = "#/m";
    };
  const draw = (ms, force, keep) => {
    cur = ms;
    grp(ms, 1);
    const s =
      ms
        .map(
          (m) =>
            m.id +
            ":" +
            m.ed +
            ":" +
            (+m.pin || 0) +
            ":" +
            (m.rx || []).map((r) => r.e + r.n + r.me).join("") +
            ":" +
            (m.rq ? m.rq.id + (m.rq.t || "") + (m.rq.gone || "") : ""),
        )
        .join() +
      "|" +
      seenBy.mid +
      ":" +
      seenBy.by.join() +
      "|" +
      pins.map((p) => p.id + p.t).join() +
      "|" +
      evs.map((e) => e.id).join();
    if (s === sig && !force) return;
    if (list.querySelector(".cform")) return;
    sig = s;
    cx.paint(pins);
    const pv = chatsnap(list),
      atEnd = list.scrollHeight - list.scrollTop - list.clientHeight < 80,
      st = list.scrollTop;
    /* notices (renamed, theme, added, removed, left) sit between the messages by time; ones older than the loaded messages are left out */
    const t0 = ms.length ? +ms[0].ts : 0,
      pend = evs.filter((e) => +e.ts >= t0),
      evRow = (e) => h("div", { class: "gev hint", role: "note" }, gevText(e)),
      mrows = ms.flatMap((m) => {
        const out = [];
        while (pend.length && +pend[0].ts <= +m.ts) out.push(evRow(pend.shift()));
        const e = msg(m, false, reload, 1, cx.x);
        e.dataset.mid = m.id;
        out.push(e);
        if (+m.id === +seenBy.mid && seenBy.by.length) {
          const n = seenBy.by.length;
          out.push(
            h(
              "div",
              { class: "rcpt hint" },
              "Seen by " + (n > 2 && n === mem.length - 1 ? "everyone" : n <= 3 ? seenBy.by.join(", ") : n),
            ),
          );
        }
        return out;
      });
    pend.forEach((e) => mrows.push(evRow(e)));
    list.replaceChildren(
      ...(mrows.length
        ? mrows
        : [h("p", { class: "hint", style: "text-align:center" }, "No messages yet. Say hi to the group.")]),
    );
    chatfx(list, pv);
    if (keep) {
      list.dataset.stick = atEnd ? "1" : "0";
      list.scrollTop = atEnd ? list.scrollHeight : st;
      return;
    }
    list.dataset.stick = atEnd || force ? "1" : "0";
    if (atEnd || force) list.scrollTop = list.scrollHeight;
  };
  async function reload() {
    if (CUR) CUR.hold = 0;
    if (jb) jb.remove();
    try {
      const x = await api("gthread", null, "&id=" + id);
      mem = x.members;
      gmup(x.gm);
      seenBy = x.seen || seenBy;
      sync(x.g);
      put(x, true);
    } catch (e) {
      gone(e);
    }
  }
  const dclr = dbind(inp, dkG(id));
  /* Masques in this group: gm.in = your Masque is in it, gm.only = it is the only way you are here. When yours is in, a small picture next to the box switches who you write as. */
  const gm = Object.assign({ has: 0, in: 0, only: 0, name: "", avatar: "" }, r.gm || {});
  let asMk = 0;
  const sendMask = () => !!(+gm.only || (+gm.in && asMk)),
    swb = h("button", { type: "button", class: "cswh gsw", hidden: "" }),
    paintSw = () => {
      const mk = sendMask();
      swb.hidden = !+gm.in || !!+gm.only;
      swb.replaceChildren(mk ? avw(av({ avatar: gm.avatar, mk: 1 }, 34), null, 1) : av(M, 34));
      swb.classList.toggle("on", mk);
      swb.setAttribute("aria-pressed", String(mk));
      const l = mk ? "Writing as " + gm.name + ". Tap to write as you" : "Writing as you. Tap to write as " + gm.name;
      swb.setAttribute("aria-label", l);
      swb.title = l;
      swb.closest(".tcard")?.classList.toggle("asm", mk);
      inp.placeholder = mk ? "Message as " + gm.name + "\u2026" : "Message\u2026";
    },
    gmup = (x) => {
      if (!x) return;
      Object.assign(gm, x);
      if (!+gm.in) asMk = 0;
      paintSw();
    };
  swb.onclick = () => {
    ASKAS = 1;
    asMk = asMk ? 0 : 1;
    paintSw();
    inp.focus();
  };
  paintSw();
  CHATAS = {
    el: inp,
    fn: (on) => {
      if (!+gm.in || +gm.only) return;
      asMk = on ? 1 : 0;
      paintSw();
    },
  };
  let file = null;
  const pick = h("input", {
      type: "file",
      accept: "image/*,audio/*,.mp3,.m4a,.aac,.ogg,.opus,.wav,.flac",
      hidden: "",
      "aria-label": "Attach photo or audio",
    }),
    att = h(
      "button",
      { type: "button", class: "ghost ibtn", "aria-label": "Attach photo or audio", title: "Attach photo or audio" },
      ic("clip", 20),
    ),
    chip = h("button", { type: "button", class: "ghost", hidden: "" });
  const clr = () => {
    file = null;
    pick.value = "";
    chip.hidden = true;
  };
  att.onclick = () => pick.click();
  chip.onclick = clr;
  pick.onchange = () => {
    const x = pick.files[0];
    if (!x) return;
    const au = isAud(x);
    if (au ? x.size > AUDMAX : x.size > IMGMAX) {
      err.textContent = au ? "Audio must be under " + AUDMB + " MB." : "Image must be under " + IMGMB + " MB.";
      pick.value = "";
      return;
    }
    err.textContent = "";
    file = x;
    chip.textContent = "Remove " + (au ? "file" : "photo") + ": " + x.name;
    chip.hidden = false;
  };
  const emo = emojiPad({
    inp,
    send: async (t) => {
      const d = new FormData();
      d.append("gid", id);
      d.append("txt", t);
      if (cx.rep()) d.append("rp", cx.rep().id);
      await api("gsend", d);
      SFX.play("send");
      cx.clear();
      await reload();
    },
  });
  const f = h(
    "form",
    {
      class: "cform",
      onsubmit: async (e) => {
        e.preventDefault();
        if (!inp.value.trim() && !file) return;
        if (!+gm.only && +gm.in && !(await asOk(sendMask()))) return;
        go.disabled = true;
        err.textContent = "";
        const d = new FormData();
        d.append("gid", id);
        d.append("txt", inp.value);
        if (sendMask()) d.append("as", "mask");
        if (cx.rep()) d.append("rp", cx.rep().id);
        try {
          if (file) d.append("img", await (isAud(file) ? file : shrink(file)));
          await api("gsend", d);
      SFX.play("send");
          inp.value = "";
          dclr();
          clr();
          cx.clear();
          await reload();
        } catch (x) {
          err.textContent = x.e || "Could not send.";
        }
        go.disabled = false;
        inp.focus();
      },
    },
    swb,
    att,
    inp,
    emo.btn,
    go,
    emo.panel,
  );
  f.classList.add("hasemo");
  mentionPick(inp, (q) => {
    const l = mem.filter((z) => !isMe(z.name) && (String(z.name).toLowerCase().includes(q) || String(z.nick || "").toLowerCase().includes(q)));
    l.sort((a, b) => +String(b.name).toLowerCase().startsWith(q) - +String(a.name).toLowerCase().startsWith(q));
    return ("everyone".startsWith(q) ? [{ name: "everyone", every: 1 }] : []).concat(l);
  });
  const isOwner = +r.g.own;
  list.dataset.bg = r.g.bg || "";
  const themeB = h(
    "button",
    {
      type: "button",
      class: "ghost ibtn",
      "aria-label": "Chat theme",
      title: "Chat theme",
      onclick: () =>
        sheet("Chat theme", (close) => {
          const e = h("p", { class: "err", role: "alert" }),
            pickBg = async (k) => {
              e.textContent = "";
              try {
                const x = await api("gsetbg", fd({ gid: id, bg: k }));
                r.g.bg = x.bg;
                list.dataset.bg = x.bg;
                close();
                reload();
              } catch (x) {
                e.textContent = x.e || "Could not change the theme.";
              }
            };
          return h(
            "div",
            { class: "form" },
            h("p", { class: "hint" }, "Everyone in the group sees this theme, and the chat shows who changed it."),
            h(
              "div",
              { class: "bgsw-row", role: "group", "aria-label": "Backgrounds" },
              ...GBG.filter(
                ([k]) => !/^castle/.test(k) || !UNL || UNL.admin || (UNL.ev && +UNL.ev.on) || (r.g.bg || "") === k,
              ).map(([k, l]) =>
                h(
                  "button",
                  {
                    type: "button",
                    class: "bgsw",
                    "data-bg": k,
                    "aria-pressed": String((r.g.bg || "") === k),
                    "aria-label": l,
                    title: l,
                    onclick: () => pickBg(k),
                  },
                  h("span", {}, l),
                ),
              ),
            ),
            e,
          );
        }),
    },
    ic("image", 16),
  );
  const addPeople = (done) =>
    sheet("Invite people", (close) => {
      const err = h("p", { class: "err", role: "alert" }),
        box = h("div", { class: "gpick" }, h("p", { class: "hint" }, "Loading friends\u2026")),
        go = h("button", { class: "btn full", type: "submit" }, "Send invites"),
        sel = new Set(),
        have = new Set(mem.filter((u) => !+u.mk).map((u) => u.name));
      api("friends")
        .then(({ list }) => {
          const fr = list.filter((x) => +x.st && !have.has(x.name));
          box.replaceChildren(
            ...(fr.length
              ? fr.map((u) => {
                  const b = h(
                    "button",
                    { type: "button", class: "chat gp", "aria-pressed": "false" },
                    av(u, 36),
                    h("div", { class: "cx" }, h("b", {}, dn(u))),
                    h("span", { class: "gtick" }, ic("check", 16)),
                  );
                  b.onclick = () => {
                    const on = !sel.has(u.name);
                    on ? sel.add(u.name) : sel.delete(u.name);
                    b.setAttribute("aria-pressed", on);
                  };
                  return b;
                })
              : [h("p", { class: "hint" }, "All your friends are already in this group.")]),
          );
        })
        .catch(() => box.replaceChildren(h("p", { class: "hint" }, "Couldn\u2019t load your friends.")));
      return h(
        "form",
        {
          class: "form",
          onsubmit: async (e) => {
            e.preventDefault();
            if (!sel.size) {
              err.textContent = "Pick at least one friend.";
              return;
            }
            go.disabled = true;
            err.textContent = "";
            try {
              await api("gadd", fd({ gid: id, members: [...sel].join(",") }));
              close();
              await reload();
              done();
            } catch (x) {
              err.textContent = x.e || "Could not send the invites.";
              go.disabled = false;
            }
          },
        },
        box,
        err,
        go,
      );
    });
  /* invite somebody's Masque by name; whoever owns it gets the invite, and nobody in the group learns who that is */
  const addMask = (done) =>
    sheet("Invite a Masque", (close) => {
      const err = h("p", { class: "err", role: "alert" }),
        inp = h("input", { placeholder: "Masque name", maxlength: 40, "aria-label": "Masque name", autocomplete: "off", autocapitalize: "off" }),
        go = h("button", { class: "btn full", type: "submit" }, "Send invite");
      return h(
        "form",
        {
          class: "form",
          onsubmit: async (e) => {
            e.preventDefault();
            const n = inp.value.trim().replace(/^@/, "");
            if (!n) {
              err.textContent = "Type the name of the Masque.";
              return;
            }
            go.disabled = true;
            err.textContent = "";
            try {
              await api("gaddmask", fd({ gid: id, name: n }));
              close();
              await reload();
              done();
            } catch (x) {
              err.textContent = x.e || "Could not send the invite.";
              go.disabled = false;
            }
          },
        },
        h("p", { class: "hint" }, "Masques stay anonymous. They get an invite, and nobody here finds out who is behind it."),
        inp,
        err,
        go,
      );
    });
  const members = () =>
    sheet("Members (" + mem.length + ")", (close) => {
      const box = h("div", {}),
        top = h("div", {});
      const paint = () => {
        const sh = box.closest(".sheet"),
          hd = sh && sh.querySelector("h2");
        if (hd && hd.firstChild) hd.firstChild.textContent = "Members (" + mem.length + ")";
        box.replaceChildren(
          ...mem.map((u) => {
            const who = h(
                "button",
                {
                  type: "button",
                  class: "gm",
                  onclick: () => {
                    close();
                    location.hash = (+u.mk ? "#/k/" : "#/u/") + u.name;
                  },
                },
                av(u, 44),
                h(
                  "div",
                  { class: "cx" },
                  h("b", {}, dn(u), +u.own ? crown() : null),
                  +u.own
                    ? h("span", { class: "hint" }, "Group creator")
                    : +u.mk
                      ? h("span", { class: "hint" }, +gm.in && u.name === gm.name ? "Your Masque" : "Masque")
                      : null,
                ),
              ),
              row = h("div", { class: "chat" }, who);
            if (isOwner && !+u.own && !(+u.mk && +gm.in && u.name === gm.name))
              row.append(
                h(
                  "button",
                  {
                    type: "button",
                    class: "ghost ibtn",
                    "aria-label": "Remove " + u.name,
                    title: "Remove " + u.name,
                    onclick: async () => {
                      if (!(await cbox("Remove " + u.name + "? They will no longer see this group or its messages.")))
                        return;
                      try {
                        await api("gremove", fd({ gid: id, name: u.name, mk: +u.mk ? 1 : 0 }));
                        await reload();
                        paint();
                      } catch (x) {
                        alert(x.e || "Could not remove them.");
                      }
                    },
                  },
                  ic("close", 16),
                ),
              );
            return row;
          }),
        );
      };
      const topPaint = () =>
        top.replaceChildren(
          ...[
          h(
            "button",
            { type: "button", class: "ghost full", style: "margin-bottom:10px", onclick: () => addPeople(paint) },
            ic("plus", 16),
            "Invite people",
          ),
          h(
            "button",
            { type: "button", class: "ghost full", style: "margin-bottom:10px", onclick: () => addMask(paint) },
            ic("mask", 16),
            "Invite a Masque",
          ),
          +gm.has && !+gm.only
            ? h(
                "button",
                {
                  type: "button",
                  class: "ghost full",
                  style: "margin-bottom:10px",
                  onclick: async () => {
                    try {
                      await api("gmaskme", fd({ gid: id, on: +gm.in ? 0 : 1 }));
                      await reload();
                      paint();
                      topPaint();
                    } catch (x) {
                      alert(x.e || "Could not change that.");
                    }
                  },
                },
                ic("mask", 16),
                +gm.in ? "Remove my Masque from this group" : "Add my Masque to this group",
              )
            : null,
        ].filter(Boolean));
      topPaint();
      const lv = h(
        "button",
        {
          type: "button",
          class: "ghost full",
          style: "margin-top:6px",
          onclick: async () => {
            const last = mem.length < 2,
              msg = last
                ? "Leave this group? You are the last member, so the group and its messages will be deleted."
                : isOwner
                  ? "Leave this group? The longest-standing member becomes the new creator."
                  : "Leave this group? You will no longer see its messages.";
            if (!(await cbox(msg))) return;
            try {
              await api("gleave", fd({ gid: id }));
              close();
              location.hash = "#/m";
            } catch (x) {
              alert(x.e || "Could not leave the group.");
            }
          },
        },
        "Leave group",
      );
      setTimeout(paint, 0);
      /* invite link: made only when someone asks for it; anyone in the group can copy or reset it */
      const li = h("input", { readonly: "", "aria-label": "Invite link", hidden: "" }),
        cp = h("button", { type: "button", class: "ghost", hidden: "" }, "Copy link"),
        rs = h("button", { type: "button", class: "ghost", hidden: "" }, "Reset link"),
        mk = h("button", { type: "button", class: "ghost full" }, ic("plus", 16), "Get invite link"),
        lerr = h("p", { class: "err", role: "alert" }),
        fill = async (reset) => {
          lerr.textContent = "";
          try {
            const x = await api("glink", fd({ gid: id, reset: reset ? 1 : 0 }));
            li.value = location.origin + location.pathname + "#/gj/" + x.code;
            li.hidden = cp.hidden = rs.hidden = false;
            mk.hidden = true;
          } catch (e) {
            lerr.textContent = e.e || "Could not get the link.";
          }
        };
      mk.onclick = () => fill(false);
      cp.onclick = async () => {
        try {
          await navigator.clipboard.writeText(li.value);
        } catch (_) {
          li.select();
        }
        cp.textContent = "Copied";
        setTimeout(() => (cp.textContent = "Copy link"), 1500);
      };
      rs.onclick = async () => {
        if (await cbox("Reset the invite link? The old link stops working.")) fill(true);
      };
      const lk = h(
        "div",
        { class: "glink" },
        h("b", {}, "Invite link"),
        h("p", { class: "hint" }, "Anyone with an account who opens this link can join the group. Reset it if it gets shared too widely."),
        mk,
        li,
        h("div", { class: "row" }, cp, rs),
        lerr,
      );
      return h("div", {}, top, box, lk, lv);
    });
  const csB = h("span", { class: "csw" });
  csHere(csB, "g" + id, r.cs);
  shell(
    h(
      "div",
      { class: "tcard" },
      h(
        "div",
        { class: "th" },
        h(
          "button",
          { class: "ghost", onclick: () => (location.hash = "#/m"), "aria-label": "Back to messages" },
          ic("back", 18),
        ),
        r.g.avatar
          ? h(
              "button",
              {
                type: "button",
                class: "gicon",
                "aria-label": "View group picture",
                title: "View group picture",
                onclick: () => view("?img=" + r.g.avatar, r.g.name),
              },
              gva(r.g, 36),
            )
          : gva(r.g, 36),
        h("button", { type: "button", class: "gtitle", onclick: members }, nameEl, sub),
        csB,
        h(
          "button",
          {
            type: "button",
            class: "ghost ibtn",
            style: "margin-left:auto;flex:none",
            "aria-label": "Chat options",
            title: "Chat options",
            onclick: () =>
              sheet("Chat options", (close) => {
                const row = (l, i, fn) =>
                  h(
                    "button",
                    {
                      type: "button",
                      class: "ghost mrow2",
                      onclick: () => {
                        close();
                        fn();
                      },
                    },
                    ic(i, 16),
                    l,
                  );
                return h(
                  "div",
                  { class: "form" },
                  row("Search messages", "search", () => chatSearch({ api: "gsearch", qs: "&id=" + id, who: (m) => m.who, jump })),
                  csRow(row, "g" + id),
                  row("Chat theme", "image", () => themeB.click()),
                  row("Edit group", "pencil", () => groupSheet({ id, name: nameEl.textContent, avatar: r.g.avatar })),
                  row("Members", "users", members),
                );
              }),
          },
          ic("more", 16),
        ),
      ),
      cx.pbar,
      list,
      err,
      chip,
      cx.rbar,
      f,
      pick,
    ),
    1,
  );
  list.classList.add("first");
  chatPaste(inp, list.closest(".tcard") || list, pick);
  paintSw();
  draw(r.msgs, true);
  {
    const tc = document.querySelector(".tcard"),
      vv = window.visualViewport;
    if (tc && vv) {
      const fit = () => {
        if (!tc.isConnected) {
          vv.removeEventListener("resize", fit);
          vv.removeEventListener("scroll", fit);
          return;
        }
        if (matchMedia("(max-width:899px)").matches) {
          tc.style.height = vv.height + "px";
          tc.style.top = vv.offsetTop + "px";
          tc.style.bottom = "auto";
          const l = tc.querySelector(".mlist");
          if (l && l.dataset.stick === "1") l.scrollTop = l.scrollHeight;
        } else {
          tc.style.height = tc.style.top = tc.style.bottom = "";
        }
      };
      vv.addEventListener("resize", fit);
      vv.addEventListener("scroll", fit);
      fit();
    }
  }
  setTimeout(() => list.classList.remove("first"), 1500);
  const tyg = typer(list);
  inp.addEventListener(
    "input",
    pinger(inp, (off) => api("typing", fd({ k: "g", gid: id, as: sendMask() ? "mask" : "", off: off ? 1 : 0 })).catch(() => {})),
  );
  CUR = {
    k: "g",
    qs: "&id=" + id,
    sig: null,
    ty: tyg,
    sync: async () => {
      if (CUR && CUR.hold) return;
      try {
        const x = await api("gthread", null, "&id=" + id);
        mem = x.members;
        gmup(x.gm);
        seenBy = x.seen || seenBy;
        sync(x.g);
        put(x);
      } catch (e) {
        gone(e);
      }
    },
  };
}
async function thread(name, asM) {
  const h0 = location.hash;
  asM = !!asM && !!M.mask;
  const q2 = "&u=" + encodeURIComponent(name) + (asM ? "&as=1" : "");
  let r;
  try {
    r = await api("thread", null, q2);
  } catch (e) {
    shell(emp("search", "No such account", "Check the spelling and try again."));
    return;
  }
  refineTitle(h0, "Chat with " + pdn(r.u));
  const list = h("div", { class: "mlist", role: "log" }),
    err = h("p", { class: "err", role: "alert" }),
    inp = chatBox({
      placeholder: asM ? "Message as " + M.mask.name + "…" : "Message…",
      maxlength: 500,
    }),
    go = h("button", { class: "btn", type: "submit" }, "Send");
  let sig = "",
    cur = [],
    pins = r.pins || [];
  const cx = chatx({
      mnt: (n) => {
        n = n.toLowerCase();
        return n === String(r.u.name).toLowerCase() || isMe(n) ? { me: isMe(n) } : null;
      },
      rk: "react",
      pk: "pinm",
      qsend: async (t, rp) => {
        const d = new FormData();
        d.append("to", name);
        d.append("txt", t);
        if (asM) d.append("as", "mask");
        d.append("rp", rp);
        await api("send", d);
        SFX.play("send");
        await reload();
      },
      who: () => pdn(r.u),
      meAv: () => (asM && M.mask ? { avatar: M.mask.avatar, mk: 1 } : M),
      otherAv: () => r.u,
      inp,
      jump: (id) => jump(id),
      patch: (id, fn) => {
        const m = cur.find((z) => +z.id === +id);
        if (m) {
          fn(m);
          draw(cur, true, true);
        }
      },
      setPin: (m, v) => {
        m.pin = v;
        pins = pins.filter((p) => +p.id !== +m.id);
        if (v) pins.unshift({ id: m.id, t: (m.txt || "").slice(0, 80), i: m.img ? 1 : 0, mine: +m.mine, who: "" });
        pins = pins.slice(0, 5);
      },
    }),
    put = (x, f, k) => {
      pins = x.pins || [];
      csUpd(x.cs);
      draw(x.msgs, f, k);
    };
  const draw = (ms, force, keep) => {
    cur = ms;
    grp(ms, 0);
    const s =
      ms
        .map(
          (m) =>
            m.id +
            ":" +
            m.ed +
            ":" +
            m.seen +
            ":" +
            (+m.pin || 0) +
            ":" +
            (m.rx || []).map((r) => r.e + r.n + r.me).join("") +
            ":" +
            (m.rq ? m.rq.id + (m.rq.t || "") + (m.rq.gone || "") : ""),
        )
        .join() +
      "|" +
      pins.map((p) => p.id + p.t).join();
    if (s === sig && !force) return;
    if (list.querySelector(".cform")) return;
    sig = s;
    cx.paint(pins);
    const pv = chatsnap(list),
      atEnd = list.scrollHeight - list.scrollTop - list.clientHeight < 80,
      st = list.scrollTop;
    const lastMine = [...ms].reverse().find((m) => +m.mine);
    list.replaceChildren(
      ...(ms.length
        ? ms.map((m) => {
            const e = msg(m, m === lastMine, reload, 0, cx.x);
            e.dataset.mid = m.id;
            return e;
          })
        : [
            h(
              "div",
              { style: "text-align:center" },
              h("p", { class: "hint" }, "Say hi to " + pdn(r.u) + "."),
              M.mask && !+r.u.mk
                ? h(
                    "div",
                    {
                      class: "row",
                      style: "justify-content:center;gap:8px;margin-top:8px",
                      role: "group",
                      "aria-label": "Chat as",
                    },
                    h(
                      "button",
                      {
                        type: "button",
                        class: "ghost",
                        "aria-pressed": String(!asM),
                        onclick: () => {
                          if (asM) {
                            ASKAS = 1;
                            location.hash = "#/m/" + name;
                          }
                        },
                      },
                      "As me",
                    ),
                    h(
                      "button",
                      {
                        type: "button",
                        class: "ghost",
                        "aria-pressed": String(asM),
                        onclick: () => {
                          if (!asM) {
                            ASKAS = 1;
                            location.hash = "#/m/" + name + "/k";
                          }
                        },
                      },
                      ic("mask", 16),
                      "As " + M.mask.name,
                    ),
                  )
                : null,
            ),
          ]),
    );
    chatfx(list, pv);
    if (keep) {
      list.dataset.stick = atEnd ? "1" : "0";
      list.scrollTop = atEnd ? list.scrollHeight : st;
      return;
    }
    list.dataset.stick = atEnd || force ? "1" : "0";
    if (atEnd || force) list.scrollTop = list.scrollHeight;
  };
  async function reload() {
    if (CUR) CUR.hold = 0;
    if (jb) jb.remove();
    try {
      const x = await api("thread", null, q2);
      put(x, true);
    } catch (e) {}
  }
  const dclr = dbind(inp, dkD(name, asM));
  /* holding the nav Profile button while in this chat moves the chat to the other persona's version of it */
  CHATAS = M.mask && !+r.u.mk
    ? {
        el: inp,
        fn: (on) => {
          if (on !== asM) location.hash = "#/m/" + name + (on ? "/k" : "");
        },
      }
    : null;
  let file = null;
  const pick = h("input", {
      type: "file",
      accept: "image/*,audio/*,.mp3,.m4a,.aac,.ogg,.opus,.wav,.flac",
      hidden: "",
      "aria-label": "Attach photo or audio",
    }),
    att = h(
      "button",
      { type: "button", class: "ghost ibtn", "aria-label": "Attach photo or audio", title: "Attach photo or audio" },
      ic("clip", 20),
    ),
    chip = h("button", { type: "button", class: "ghost", hidden: "" });
  const clr = () => {
    file = null;
    pick.value = "";
    chip.hidden = true;
  };
  att.onclick = () => pick.click();
  chip.onclick = clr;
  pick.onchange = () => {
    const x = pick.files[0];
    if (!x) return;
    const au = isAud(x);
    if (au ? x.size > AUDMAX : x.size > IMGMAX) {
      err.textContent = au ? "Audio must be under " + AUDMB + " MB." : "Image must be under " + IMGMB + " MB.";
      pick.value = "";
      return;
    }
    err.textContent = "";
    file = x;
    chip.textContent = "Remove " + (au ? "file" : "photo") + ": " + x.name;
    chip.hidden = false;
  };
  const emo = emojiPad({
    inp,
    send: async (t) => {
      const d = new FormData();
      d.append("to", name);
      d.append("txt", t);
      if (asM) d.append("as", "mask");
      if (cx.rep()) d.append("rp", cx.rep().id);
      await api("send", d);
      SFX.play("send");
      cx.clear();
      await reload();
    },
  });
  const f = h(
    "form",
    {
      class: "cform",
      onsubmit: async (e) => {
        e.preventDefault();
        if (!inp.value.trim() && !file) return;
        if (!(await asOk(asM))) return;
        go.disabled = true;
        err.textContent = "";
        const d = new FormData();
        d.append("to", name);
        d.append("txt", inp.value);
        if (asM) d.append("as", "mask");
        if (cx.rep()) d.append("rp", cx.rep().id);
        try {
          if (file) d.append("img", await (isAud(file) ? file : shrink(file)));
          await api("send", d);
      SFX.play("send");
          inp.value = "";
          dclr();
          clr();
          cx.clear();
          await reload();
        } catch (x) {
          err.textContent = x.e || "Could not send.";
        }
        go.disabled = false;
        inp.focus();
      },
    },
    asM ? h("span", { class: "cswh cswi", title: "Writing as " + M.mask.name }, avw(av({ avatar: M.mask.avatar, mk: 1 }, 34), null, 1)) : null,
    att,
    inp,
    emo.btn,
    go,
    emo.panel,
  );
  f.classList.add("hasemo");
  mentionPick(inp, (q) => {
    const u = r.u;
    return String(u.name).toLowerCase().includes(q) || String(u.nick || "").toLowerCase().includes(q) ? [{ name: u.name, nick: u.nick, avatar: u.avatar, mk: u.mk }] : [];
  });
  list.dataset.bg = r.u.bg || "";
  const bgB = h(
    "button",
    {
      type: "button",
      class: "ghost",
      style: "flex:none",
      "aria-label": "Chat background",
      title: "Chat background",
      onclick: () =>
        sheet("Chat background", (close) => {
          const e = h("p", { class: "err", role: "alert" }),
            pick = async (k) => {
              e.textContent = "";
              try {
                const x = await api("setbg", fd({ u: r.u.name, mk: +r.u.mk ? 1 : 0, bg: k }));
                r.u.bg = x.bg;
                list.dataset.bg = x.bg;
                close();
              } catch (x) {
                e.textContent = x.e || "Could not save.";
              }
            };
          return h(
            "div",
            { class: "form" },
            h("p", { class: "hint" }, "Only you see this background."),
            h(
              "div",
              { class: "bgsw-row", role: "group", "aria-label": "Backgrounds" },
              ...[
                ["", "Default"],
                ["sage", "Sage"],
                ["sky", "Sky"],
                ["rose", "Rose"],
                ["sand", "Sand"],
                ["lilac", "Lilac"],
                ["dusk", "Dusk"],
                ["dots", "Dots"],
                ["grid", "Grid"],
                ["starry", "Starry"],
                ["petals", "Petals"],
                ["curtain", "Curtain call"],
                ["castle", "Castle Night"],
                ["castlepaint", "Painted castle"],
                ["castleash", "Shadow castle"],
              ]
                .filter(
                  ([k]) => !/^castle/.test(k) || !UNL || UNL.admin || (UNL.ev && +UNL.ev.on) || (r.u.bg || "") === k,
                )
                .map(([k, l]) =>
                  h(
                    "button",
                    {
                      type: "button",
                      class: "bgsw",
                      "data-bg": k,
                      "aria-pressed": String((r.u.bg || "") === k),
                      "aria-label": l,
                      title: l,
                      onclick: () => pick(k),
                    },
                    h("span", {}, l),
                  ),
                ),
            ),
            e,
          );
        }),
    },
    ic("image", 16),
  );
  const nameB = h("b", {
      onclick: () => (location.hash = (+r.u.mk ? "#/k/" : "#/u/") + r.u.name),
      style: "cursor:pointer",
    }),
    realB = h("small", { class: "hint" }),
    nickB = h(
      "button",
      {
        type: "button",
        class: "ghost",
        style: "margin-left:auto;flex:none",
        "aria-label": "Set a nickname",
        title: "Set a nickname",
        onclick: () =>
          sheet("Nickname", (close) => {
            const i = h("input", {
                value: r.u.pn || "",
                maxlength: 32,
                placeholder: dn(r.u),
                "aria-label": "Nickname",
                autocomplete: "off",
              }),
              e = h("p", { class: "err", role: "alert" }),
              save = async (v) => {
                e.textContent = "";
                try {
                  const x = await api("setpn", fd({ u: r.u.name, mk: +r.u.mk ? 1 : 0, nick: v }));
                  r.u.pn = x.pn;
                  showName();
                  close();
                } catch (x) {
                  e.textContent = x.e || "Could not save.";
                }
              };
            return h(
              "form",
              {
                class: "form",
                onsubmit: (ev) => {
                  ev.preventDefault();
                  save(i.value);
                },
              },
              h("p", { class: "hint" }, "Only you can see this. " + dn(r.u) + " won't be told."),
              i,
              e,
              h(
                "div",
                { class: "row", style: "gap:8px" },
                h("button", { class: "btn", type: "submit" }, "Save"),
                r.u.pn ? h("button", { type: "button", class: "ghost", onclick: () => save("") }, "Remove") : null,
              ),
            );
          }),
      },
      ic("pencil", 16),
    );
  const showName = () => {
    nameB.textContent = pdn(r.u);
    realB.textContent = r.u.pn ? dn(r.u) : "";
    realB.hidden = !r.u.pn;
  };
  showName();
  const noSt = !!(+r.u.mk || asM),
    aw = avw(av(r.u, 36), noSt ? null : r.u.st, noSt),
    sd = aw.querySelector(".pdot:not(.mk)"),
    stB = h("small", { class: "hint" }),
    setSt = (st) => {
      if (noSt || !ST[st]) return;
      r.u.st = st;
      setDot(sd, st);
      stB.textContent = ST[st];
    };
  if (!noSt && r.u.st) stB.textContent = ST[r.u.st];
  let jb = null;
  const showBack = () => {
      if (jb && jb.isConnected) return;
      jb = h("button", { type: "button", class: "btn jlat" }, "Jump to latest");
      jb.onclick = () => reload();
      list.closest(".tcard").append(jb);
    },
    jump = async (id) => {
      const f = () => list.querySelector('[data-mid="' + id + '"]');
      let e = f();
      if (!e) {
        if (CUR) CUR.hold = 1;
        try {
          const x = await api("thread", null, q2 + "&around=" + id);
          put(x, true);
        } catch (_) {
          return;
        }
        e = f();
        showBack();
      }
      if (e) {
        e.scrollIntoView({ block: "center" });
        e.classList.add("mflash");
        setTimeout(() => e.classList.remove("mflash"), 1800);
      }
    },
    moreB = h(
      "button",
      {
        type: "button",
        class: "ghost",
        style: "margin-left:auto;flex:none",
        "aria-label": "Chat options",
        title: "Chat options",
        onclick: () =>
          sheet("Chat options", (close) => {
            const row = (l, i, fn) =>
              h(
                "button",
                {
                  type: "button",
                  class: "ghost mrow2",
                  onclick: () => {
                    close();
                    fn();
                  },
                },
                ic(i, 16),
                l,
              );
            return h(
              "div",
              { class: "form" },
              row("Nickname", "pencil", () => nickB.click()),
              row("Chat background", "image", () => bgB.click()),
              row("Search messages", "search", () => chatSearch({ api: "msearch", qs: q2, who: () => pdn(r.u), jump })),
              csRow(row, "d" + r.u.name + (asM ? "/k" : "")),
              M.mask && !+r.u.mk
                ? row(asM ? "Write as yourself" : "Write as " + M.mask.name, "mask", () => {
                  ASKAS = 1;
                  location.hash = "#/m/" + name + (asM ? "" : "/k");
                })
                : null,
              +r.u.mk ? row(+mbk ? "Unblock this Masque" : "Block this Masque", "close", blockFn) : null,
              +r.u.mk ? row("Report", "shield", () => reportSheet("mask", r.u.name)) : null,
            );
          }),
      },
      ic("more", 16),
    );
  let mbk = +r.mb;
  const blockFn = async () => {
    try {
      const on = !+mbk;
      await api("mblock", fd({ k: r.u.name, on: on ? 1 : 0 }));
      mbk = on ? 1 : 0;
      if (on)
        alert("Blocked. You will no longer see this Masque's posts, comments or Room messages, and it can no longer message you. Your account and friendships are not affected.");
    } catch (x) {
      alert(x.e || "Could not change that.");
    }
  };
  const csB = h("span", { class: "csw" });
  csHere(csB, "d" + r.u.name + (asM ? "/k" : ""), r.cs);
  shell(
    h(
      "div",
      { class: "tcard" + (asM ? " asm" : "") },
      h(
        "div",
        { class: "th" },
        h(
          "button",
          { class: "ghost", onclick: () => (location.hash = "#/m"), "aria-label": "Back to messages" },
          ic("back", 18),
        ),
        aw,
        h(
          "div",
          { class: "cx" },
          nameB,
          asM
            ? h(
                "small",
                { class: "asmtag" },
                lmIcon(16),
                h(
                  "span",
                  { class: "asmt" },
                  h("span", { class: "asml" }, "Masque chat"),
                  h("span", { class: "asmw" }, "as " + M.mask.name),
                ),
              )
            : +r.u.mk
              ? h("small", { class: "hint" }, "Masque")
              : null,
          realB,
          stB,
        ),
        csB,
        moreB,
      ),
      cx.pbar,
      list,
      err,
      chip,
      cx.rbar,
      f,
      pick,
    ),
    1,
  );
  list.classList.add("first");
  chatPaste(inp, list.closest(".tcard") || list, pick);
  draw(r.msgs, true);
  {
    const tc = document.querySelector(".tcard"),
      vv = window.visualViewport;
    if (tc && vv) {
      const fit = () => {
        if (!tc.isConnected) {
          vv.removeEventListener("resize", fit);
          vv.removeEventListener("scroll", fit);
          return;
        }
        if (matchMedia("(max-width:899px)").matches) {
          tc.style.height = vv.height + "px";
          tc.style.top = vv.offsetTop + "px";
          tc.style.bottom = "auto";
          const l = tc.querySelector(".mlist");
          if (l && l.dataset.stick === "1") l.scrollTop = l.scrollHeight;
        } else {
          tc.style.height = tc.style.top = tc.style.bottom = "";
        }
      };
      vv.addEventListener("resize", fit);
      vv.addEventListener("scroll", fit);
      fit();
    }
  }
  {
    const n = list.children.length;
    [...list.children].forEach((c, i) => c.style.setProperty("--i", Math.max(0, i - (n - 8))));
  }
  setTimeout(() => list.classList.remove("first"), 1500);
  const tyd = typer(list);
  inp.addEventListener(
    "input",
    pinger(inp, (off) => api("typing", fd({ to: name, as: asM ? "mask" : "", off: off ? 1 : 0 })).catch(() => {})),
  );
  CUR = {
    k: "d",
    qs: q2,
    sig: null,
    ty: tyd,
    st: setSt,
    sync: async () => {
      if (CUR && CUR.hold) return;
      try {
        const x = await api("thread", null, q2);
        put(x);
      } catch (e) {}
    },
  };
}
const REACTS = ["❤️", "\u{1F602}", "\u{1F62E}", "\u{1F622}", "\u{1F44D}", "\u{1F525}"];
/* who reacted: opened by holding a reaction (or from the message menu). Groups ask the server; direct chats already know both sides. */
async function rxWho(m, g, x) {
  let list;
  try {
    if (g) list = (await api("rxwho", null, "&id=" + m.id)).rx;
    else {
      const me = x.meAv ? x.meAv() : {},
        ot = x.otherAv ? x.otherAv() : {};
      list = (m.rx || []).map((r) => {
        const w = [];
        if (+r.me) w.push({ name: "You", avatar: me.avatar || "", mk: me.mk || 0, me: 1 });
        if (+r.n - (+r.me ? 1 : 0) > 0) w.push({ name: x.other(), avatar: ot.avatar || "", mk: ot.mk || 0, me: 0 });
        return { e: r.e, w };
      });
    }
  } catch (z) {
    alert((z && z.e) || "Could not load reactions.");
    return;
  }
  list = list || [];
  sheet("Reactions", (close) =>
    h(
      "div",
      { class: "form rxwho" },
      list.length ? null : h("p", { class: "hint" }, "No reactions left on this message."),
      ...list.map((r) =>
        h(
          "div",
          { class: "rxwg" },
          h("div", { class: "rxwe" }, r.e, h("small", {}, r.w.length)),
          ...r.w.map((u) =>
            h(
              "button",
              {
                type: "button",
                class: "ghost rxwr",
                onclick: () => {
                  close();
                  if (+u.me) x.react && x.react(m, r.e);
                },
                "aria-label": +u.me ? "Remove your " + r.e + " reaction" : u.name,
              },
              avw(av(u, 28), null, +u.mk),
              h("b", {}, g && +u.me ? u.name + " (you)" : u.name),
              +u.mk ? h("small", { class: "mkt" }, "Masque") : null,
              +u.me ? h("small", { class: "hint" }, "Tap to remove") : null,
            ),
          ),
        ),
      ),
    ),
  );
}
function msgSheet(m, x, ops) {
  ops = ops || {};
  sheet("Message", (close) => {
    const my = (m.rx || []).find((r) => +r.me),
      row = (l, i, fn) =>
        h(
          "button",
          {
            type: "button",
            class: "ghost mrow2",
            onclick: () => {
              close();
              fn();
            },
          },
          ic(i, 16),
          l,
        );
    return h(
      "div",
      { class: "form" },
      h(
        "div",
        { class: "rxpick", role: "group", "aria-label": "React" },
        ...REACTS.map((e, i) => {
          const on = !!(my && my.e === e);
          return h(
            "button",
            {
              type: "button",
              style: "--i:" + i,
              class: "rxp" + (on ? " on" : ""),
              "aria-pressed": String(on),
              "aria-label": "React " + e,
              onclick: () => {
                close();
                x.react && x.react(m, e);
              },
            },
            e,
          );
        }),
      ),
      row("Reply", "reply", () => x.reply && x.reply(m)),
      (m.rx || []).length && ops.who ? row("See who reacted", "users", ops.who) : null,
      row(+m.pin ? "Unpin message" : "Pin message", "pin", () => x.pin && x.pin(m)),
      ops.simg ? row("Save as sticker", "smile", () => stkFromChat(ops.simg)) : null,
      ops.sref
        ? row(SF.has(ops.sref) ? "Remove from my stickers" : "Add to my stickers", "smile", async () => {
            try {
              await SF.load();
              await SF.set(ops.sref, !SF.has(ops.sref));
            } catch (x) {
              alert((x && x.e) || "Could not update your stickers.");
            }
          })
        : null,
      ops.copy ? row("Copy text", "link", ops.copy) : null,
      ops.edit ? row("Edit", "pencil", ops.edit) : null,
      ops.del ? row("Delete", "close", ops.del) : null,
    );
  });
}
/* Emoji and sticker picker for chat. Built-in stickers are NOT files: sending one stores only the text ":stk:ID:" (about 10 bytes) and every browser draws the artwork itself from the list below. To add one, add a row [id (a-z0-9), emoji, caption, colour]. Old ids must stay, or old messages show as plain text.
   Picture stickers: you add a picture, the browser shrinks it (max 256 px, WebP, about 50 KB), the server keeps ONE copy per distinct picture, and a message only stores ":sti:ID:". Favourites (built-in or picture) are kept on the server per account (`SF`) so they follow you to every chat and device. */
const EMO = {
  "Smileys":
    "😀 😃 😄 😁 😆 😅 😂 🤣 🙂 😉 😊 😇 🥰 😍 🤩 😘 😋 😛 😜 🤪 😎 🤓 🥳 😏 😒 🙄 😬 😌 😔 😴 🤤 😷 🤒 🤕 🤢 🥵 🥶 😵 🤯 🥺 😢 😭 😤 😡 🤬 😱 😨 😰 😳 🤔 🤭 🤫 🫠 😶 😐 😑 🫡 🤗",
  "Hands": "👍 👎 👌 ✌️ 🤞 🤟 🤘 🤙 👈 👉 👆 👇 ☝️ ✋ 🖐️ 👋 🤝 🙏 👏 🙌 🫶 💪 🤲 ✍️ 🫰 🖕",
  "Hearts": "❤️ 🧡 💛 💚 💙 💜 🖤 🤍 🤎 💔 ❣️ 💕 💞 💓 💗 💖 💘 💝 💯 💢 💥 💫 ✨ 🔥 ⭐ 🌟 💤",
  "Animals": "🐶 🐱 🐭 🐹 🐰 🦊 🐻 🐼 🐨 🐯 🦁 🐮 🐷 🐸 🐵 🙈 🙉 🙊 🐔 🐧 🐦 🦄 🐝 🦋 🐢 🐙 🐬 🐳 🦈 🐍",
  "Food": "🍎 🍌 🍉 🍓 🍒 🍑 🥭 🍍 🥑 🌽 🍕 🍔 🍟 🌭 🌮 🍿 🍣 🍜 🍩 🍪 🎂 🍰 🍫 🍦 ☕ 🍵 🍺 🥂",
  "Things":
    "🎉 🎊 🎁 🎈 🎮 🎧 🎤 🎬 📸 📱 💻 ⚽ 🏀 🚗 ✈️ 🚀 🌈 ☀️ 🌙 ⚡ ❄️ 🌸 🌹 💀 👻 👀 🧠 💩 🤡 👑 💎 🔔 🔒 ✅ ❌ ❓ ❗",
};
const STK = [
  ["lol", "😂", "LOL", "#ffe27a"],
  ["haha", "🤣", "HAHA", "#ffd48a"],
  ["love", "🥰", "LOVE", "#ffc2d4"],
  ["hug", "🤗", "HUG", "#ffdca8"],
  ["kiss", "😘", "MWAH", "#ffc2d4"],
  ["hearts", "💕", "AWW", "#ffc7e0"],
  ["cool", "😎", "COOL", "#b9e4ff"],
  ["fire", "🔥", "FIRE", "#ffb88a"],
  ["ok", "👌", "OKAY", "#c8f0c0"],
  ["yes", "👍", "YES", "#c8f0c0"],
  ["no", "🙅", "NOPE", "#ffc0b8"],
  ["wow", "😮", "WOW", "#d9ccff"],
  ["omg", "😱", "OMG", "#d9ccff"],
  ["sad", "😢", "SAD", "#bfdcff"],
  ["cry", "😭", "CRYING", "#bfdcff"],
  ["angry", "😡", "GRR", "#ffb0a0"],
  ["think", "🤔", "HMM", "#e8e0b0"],
  ["sleep", "😴", "ZZZ", "#cfd8ff"],
  ["party", "🥳", "PARTY", "#ffe0a0"],
  ["gg", "🏆", "GG", "#ffe27a"],
  ["thanks", "🙏", "THANKS", "#d4f0d0"],
  ["hi", "👋", "HI!", "#c0e8ff"],
  ["bye", "✌️", "BYE", "#e0d0ff"],
  ["ghost", "👻", "BOO", "#e4e4f4"],
  ["skull", "💀", "DEAD", "#e0e0e0"],
  ["eyes", "👀", "SEEN", "#ffe9a8"],
  ["clap", "👏", "BRAVO", "#ffe0a0"],
  ["mind", "🤯", "MIND BLOWN", "#ffd0a0"],
  ["pls", "🥺", "PLEASE", "#ffd9e6"],
  ["bored", "😒", "MEH", "#dcdcdc"],
  ["sorry", "😅", "OOPS", "#ffe4b0"],
  ["goodnight", "🌙", "NIGHT", "#cfd8ff"],
  ["whois", "❓", "WHO?", "#dfe5e9"],
  ["reveal", "🎭", "REVEAL", "#ffd48a"],
  ["shh", "🤫", "SHHH", "#d9ccff"],
  ["twin", "🎭", "TWINS", "#b9e4ff"],
  ["psst", "👀", "PSST", "#c8f0c0"],
  ["spot", "⭐", "SPOTLIGHT", "#ffe27a"],
];
/* Game invites: a chat message that is only ":gi:<base64url JSON>:" is drawn as an invite card (giCard). JSON = {n: game name, u: join link, o: note, x: minutes it stays open (15, 60 or 1440)}.
   The server checks the same rules in giparse() (index.php); a link that fails them is never drawn as a link. */
const GIRE = /^:gi:([A-Za-z0-9_-]{8,470}):$/,
  GIX = [
    [15, "15 minutes"],
    [60, "1 hour"],
    [1440, "24 hours"],
  ],
  giUrlOk = (u) =>
    typeof u === "string" &&
    u.length <= 220 &&
    !/[\x00-\x20\x7f-\uffff"<>\\^`{|}]/.test(u) &&
    !/^https:\/\/[\d.]+(:\d+)?([\/?#]|$)/.test(u) &&
    (/^https:\/\/[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+(:\d{1,5})?([\/?#]|$)/i.test(u) ||
      /^steam:\/\/[A-Za-z0-9\/_.:=&?%+-]{1,200}$/.test(u)),
  giOf = (t) => {
    const m = GIRE.exec(t || "");
    if (!m) return null;
    try {
      const b = m[1].replace(/-/g, "+").replace(/_/g, "/"),
        d = JSON.parse(decodeURIComponent(escape(atob(b + "=".repeat((4 - (b.length % 4)) % 4)))));
      if (!d || typeof d.n !== "string" || typeof d.u !== "string" || (d.o != null && typeof d.o !== "string")) return null;
      if (!d.n.trim() || d.n.length > 40 || (d.o || "").length > 60 || ![15, 60, 1440].includes(d.x) || !giUrlOk(d.u)) return null;
      return { n: d.n.trim(), u: d.u, o: d.o || "", x: d.x };
    } catch (_) {
      return null;
    }
  },
  giTx = (d) =>
    ":gi:" +
    btoa(unescape(encodeURIComponent(JSON.stringify({ n: d.n, u: d.u, o: d.o || "", x: d.x }))))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "") +
    ":";
const STKRE = /^:stk:([a-z0-9]{1,12}):$/,
  STIRE = /^:sti:([a-f0-9]{16}):$/,
  /* a built-in sticker is [id,emoji,caption,colour]; a picture sticker is [id,"","Sticker","",1] */
  stkOf = (t) => {
    let m = STKRE.exec(t || "");
    if (m) return STK.find((z) => z[0] === m[1]) || null;
    m = STIRE.exec(t || "");
    return m ? [m[1], "", "Sticker", "", 1] : null;
  },
  ptx = (t) => (stkOf(t) ? "Sticker" : GIRE.test(t || "") ? "\u{1F3AE} Game invite" : t),
  stkRef = (z) => (z[4] ? "i:" : "b:") + z[0],
  stkTx = (z) => (z[4] ? ":sti:" : ":stk:") + z[0] + ":";
/* the person's favourite stickers (refs "b:id" / "i:id", newest first), loaded once from the server and kept in sync */
const SF = {
  l: [],
  s: new Set(),
  p: null,
  done: false,
  load() {
    return (
      this.p ||
      (this.p = api("stkfavs")
        .then((r) => {
          this.l = (r.items || []).slice();
          this.s = new Set(this.l);
          this.done = true;
        })
        .catch(() => {
          this.p = null;
        }))
    );
  },
  has(r) {
    return this.s.has(r);
  },
  async set(r, on) {
    const l0 = this.l.slice();
    if (on && !this.s.has(r)) {
      this.l.unshift(r);
      this.s.add(r);
    } else if (!on) {
      this.l = this.l.filter((x) => x !== r);
      this.s.delete(r);
    }
    try {
      await api("stkfav", fd({ ref: r, on: on ? 1 : 0 }));
    } catch (x) {
      this.l = l0;
      this.s = new Set(l0);
      throw x;
    }
  },
};
/* ---- Animated stickers: GIF in, small animated WebP out (all in the browser) ----
   gifRead / gifPaint are a small GIF decoder (browsers cannot hand out GIF frames everywhere); webpAnim joins single-frame WebP files into one animated WebP. */
function gifRead(u) {
  if (u.length < 14) return null;
  const sig = String.fromCharCode(u[0], u[1], u[2], u[3], u[4], u[5]);
  if (sig !== "GIF87a" && sig !== "GIF89a") return null;
  const W = u[6] | (u[7] << 8),
    H = u[8] | (u[9] << 8);
  let p = 10;
  const pk = u[p++];
  p += 2;
  let gct = null;
  if (pk & 128) {
    const n = 3 << ((pk & 7) + 1);
    gct = u.subarray(p, p + n);
    p += n;
  }
  const fr = [];
  let g = null;
  const sub = () => {
    const a = [];
    let n = 0;
    while (p < u.length) {
      const l = u[p++];
      if (!l) break;
      a.push(u.subarray(p, p + l));
      p += l;
      n += l;
    }
    const o = new Uint8Array(n);
    let q = 0;
    for (const x of a) {
      o.set(x, q);
      q += x.length;
    }
    return o;
  };
  while (p < u.length) {
    const b = u[p++];
    if (b === 0x3b) break;
    if (b === 0x21) {
      const l = u[p++];
      if (l === 0xf9) {
        const n = u[p++],
          f = u[p];
        g = { disp: (f >> 2) & 7, tr: f & 1 ? u[p + 3] : -1, delay: u[p + 1] | (u[p + 2] << 8) };
        p += n + 1;
      } else sub();
      continue;
    }
    if (b === 0x2c) {
      const x = u[p] | (u[p + 1] << 8),
        y = u[p + 2] | (u[p + 3] << 8),
        w = u[p + 4] | (u[p + 5] << 8),
        h = u[p + 6] | (u[p + 7] << 8),
        k = u[p + 8];
      p += 9;
      let pal = null;
      if (k & 128) {
        const n = 3 << ((k & 7) + 1);
        pal = u.subarray(p, p + n);
        p += n;
      }
      const min = u[p++],
        data = sub(),
        d = g ? g.delay : 0;
      fr.push({
        x,
        y,
        w,
        h,
        il: !!(k & 64),
        pal,
        min,
        data,
        disp: g ? g.disp : 0,
        tr: g ? g.tr : -1,
        delay: (d <= 1 ? 10 : d) * 10,
      });
      g = null;
      continue;
    }
    break;
  }
  return { w: W, h: H, gct, fr };
}
function gifLzw(min, data, np) {
  const clear = 1 << min,
    eoi = clear + 1;
  let size = min + 1,
    next = eoi + 1,
    mask = (1 << size) - 1;
  const pre = new Uint16Array(4096),
    suf = new Uint8Array(4096),
    stk = new Uint8Array(4097),
    out = new Uint8Array(np);
  for (let i = 0; i < clear; i++) suf[i] = i;
  let op = 0,
    old = -1,
    first = 0,
    bits = 0,
    acc = 0,
    ip = 0;
  while (op < np) {
    while (bits < size) {
      if (ip >= data.length) return out;
      acc |= data[ip++] << bits;
      bits += 8;
    }
    let code = acc & mask;
    acc >>= size;
    bits -= size;
    if (code === clear) {
      size = min + 1;
      next = eoi + 1;
      mask = (1 << size) - 1;
      old = -1;
      continue;
    }
    if (code === eoi) break;
    if (old === -1) {
      out[op++] = suf[code];
      old = code;
      first = code;
      continue;
    }
    const inc = code;
    let sp = 0;
    if (code >= next) {
      stk[sp++] = first;
      code = old;
    }
    while (code >= clear) {
      stk[sp++] = suf[code];
      code = pre[code];
    }
    first = suf[code];
    stk[sp++] = first;
    if (next < 4096) {
      pre[next] = old;
      suf[next] = first;
      next++;
      if ((next & mask) === 0 && next < 4096) {
        size++;
        mask = (1 << size) - 1;
      }
    }
    old = inc;
    while (sp > 0 && op < np) out[op++] = stk[--sp];
  }
  return out;
}
/* paints every frame onto one running picture (honouring transparency and disposal) and calls cb(index, rgba) for the frames in `want` */
function gifPaint(G, want, cb) {
  const W = G.w,
    H = G.h,
    buf = new Uint8ClampedArray(W * H * 4);
  let prev = null,
    save = null;
  for (let k = 0; k < G.fr.length; k++) {
    const f = G.fr[k];
    if (prev) {
      if (prev.disp === 2) {
        for (let r = prev.y; r < Math.min(H, prev.y + prev.h); r++)
          buf.fill(0, (r * W + prev.x) * 4, (r * W + Math.min(W, prev.x + prev.w)) * 4);
      } else if (prev.disp === 3 && save) buf.set(save);
    }
    save = f.disp === 3 ? buf.slice() : null;
    const pal = f.pal || G.gct;
    if (pal && f.w > 0 && f.h > 0) {
      const px = gifLzw(f.min, f.data, f.w * f.h),
        rows = [];
      if (f.il) {
        for (const [s, t] of [
          [0, 8],
          [4, 8],
          [2, 4],
          [1, 2],
        ])
          for (let r = s; r < f.h; r += t) rows.push(r);
      } else for (let r = 0; r < f.h; r++) rows.push(r);
      for (let i = 0; i < f.h; i++) {
        const dy = f.y + rows[i];
        if (dy >= H) continue;
        for (let j = 0; j < f.w; j++) {
          const dx = f.x + j;
          if (dx >= W) continue;
          const c = px[i * f.w + j];
          if (c === f.tr) continue;
          const o = (dy * W + dx) * 4,
            q = c * 3;
          buf[o] = pal[q];
          buf[o + 1] = pal[q + 1];
          buf[o + 2] = pal[q + 2];
          buf[o + 3] = 255;
        }
      }
    }
    prev = f;
    if (want.has(k)) cb(k, buf);
  }
}
/* the picture and alpha chunks of a single-frame WebP file */
function webpParts(u) {
  if (
    u.length < 20 ||
    String.fromCharCode(u[0], u[1], u[2], u[3]) !== "RIFF" ||
    String.fromCharCode(u[8], u[9], u[10], u[11]) !== "WEBP"
  )
    return null;
  const o = [];
  let p = 12;
  while (p + 8 <= u.length) {
    const t = String.fromCharCode(u[p], u[p + 1], u[p + 2], u[p + 3]),
      n = (u[p + 4] | (u[p + 5] << 8) | (u[p + 6] << 16) | (u[p + 7] << 24)) >>> 0;
    if (t === "ALPH" || t === "VP8 " || t === "VP8L")
      o.push({ t, d: u.subarray(p + 8, Math.min(u.length, p + 8 + n)) });
    p += 8 + n + (n & 1);
  }
  return o.some((c) => c.t !== "ALPH") ? o : null;
}
/* frames = list of webpParts() results, all W x H; every frame lasts ms; loops forever */
function webpAnim(frames, W, H, ms) {
  const le = (n, b) => {
      const a = new Uint8Array(b);
      for (let i = 0; i < b; i++) a[i] = (n >>> (8 * i)) & 255;
      return a;
    },
    tag = (s) => Uint8Array.from(s, (c) => c.charCodeAt(0)),
    cat = (a) => {
      let n = 0;
      for (const x of a) n += x.length;
      const o = new Uint8Array(n);
      let p = 0;
      for (const x of a) {
        o.set(x, p);
        p += x.length;
      }
      return o;
    },
    ck = (t, d) => cat([tag(t), le(d.length, 4), d, new Uint8Array(d.length & 1)]);
  const body = cat([
    tag("WEBP"),
    ck("VP8X", cat([Uint8Array.of(0x12), le(0, 3), le(W - 1, 3), le(H - 1, 3)])),
    ck("ANIM", cat([le(0, 4), le(0, 2)])),
    ...frames.map((ps) =>
      ck(
        "ANMF",
        cat([
          le(0, 3),
          le(0, 3),
          le(W - 1, 3),
          le(H - 1, 3),
          le(ms, 3),
          Uint8Array.of(2),
          ...ps.map((c) => ck(c.t, c.d)),
        ]),
      ),
    ),
  ]);
  return cat([tag("RIFF"), le(body.length, 4), body]);
}
/* GIF -> animated sticker: at most 3 seconds and 24 frames, 160 px, animated WebP of 150 KB or less. Returns null when it cannot (one frame only, or this browser cannot write WebP, like Safari); the caller then makes a still picture instead. */
async function stkAnimate(file) {
  const LIM = 150000;
  if (file.size > 20e6) return null;
  const u = new Uint8Array(await file.arrayBuffer()),
    G = gifRead(u);
  if (!G || G.fr.length < 2 || !G.w || !G.h || G.w * G.h > 16e6) return null;
  let T = 0;
  const st = G.fr.map((f) => {
    const a = T;
    T += f.delay;
    return a;
  });
  T = Math.min(T, 3000);
  const n = Math.min(24, st.filter((a) => a < T).length);
  if (n < 2) return null;
  const pick = [];
  for (let i = 0; i < n; i++) {
    const t = ((i + 0.5) * T) / n;
    let k = 0;
    while (k + 1 < G.fr.length && st[k + 1] <= t) k++;
    pick.push(k);
  }
  const k0 = Math.min(1, 160 / Math.max(G.w, G.h)),
    bw = Math.max(1, Math.round(G.w * k0)),
    bh = Math.max(1, Math.round(G.h * k0)),
    tc = document.createElement("canvas");
  tc.width = G.w;
  tc.height = G.h;
  const tx = tc.getContext("2d"),
    base = new Map();
  gifPaint(G, new Set(pick), (k, buf) => {
    tx.putImageData(new ImageData(buf, G.w, G.h), 0, 0);
    const c = document.createElement("canvas");
    c.width = bw;
    c.height = bh;
    const x = c.getContext("2d");
    x.imageSmoothingQuality = "high";
    x.drawImage(tc, 0, 0, bw, bh);
    base.set(k, c);
  });
  const enc = (c, q) =>
    new Promise((r) => {
      try {
        c.toBlob(r, "image/webp", q);
      } catch (_) {
        r(null);
      }
    });
  for (const a of [
    { m: 24, S: 160, q: 0.6 },
    { m: 24, S: 160, q: 0.4 },
    { m: 12, S: 128, q: 0.5 },
    { m: 12, S: 96, q: 0.35 },
  ]) {
    const sc = Math.min(1, a.S / Math.max(bw, bh)),
      w = Math.max(1, Math.round(bw * sc)),
      h = Math.max(1, Math.round(bh * sc)),
      m = Math.min(a.m, n),
      parts = [];
    for (let i = 0; i < m; i++) {
      const src = base.get(pick[Math.floor((i * n) / m)]);
      let c = src;
      if (w !== bw || h !== bh) {
        c = document.createElement("canvas");
        c.width = w;
        c.height = h;
        const x = c.getContext("2d");
        x.imageSmoothingQuality = "high";
        x.drawImage(src, 0, 0, w, h);
      }
      const b = await enc(c, a.q);
      if (!b || b.type !== "image/webp") return null;
      const p = webpParts(new Uint8Array(await b.arrayBuffer()));
      if (!p) return null;
      parts.push(p);
    }
    const out = webpAnim(parts, w, h, Math.max(20, Math.round(T / m)));
    if (out.length <= LIM)
      return { blob: new Blob([out], { type: "image/webp" }), w, h, anim: m, secs: Math.round(T / 100) / 10 };
  }
  throw { e: "That GIF is too long or detailed for a small animated sticker." };
}
/* Make any picture into a small sticker: max 256 px on the long side, WebP at the lowest quality that still looks fine, 50 KB or less. Browsers that cannot write WebP (Safari) get JPEG, or PNG when the picture has see-through parts, at smaller sizes until it fits. */
async function stkShrink(file) {
  const LIM = 51200;
  let bm;
  try {
    bm = await createImageBitmap(file);
  } catch (_) {
    try {
      bm = await new Promise((ok, no) => {
        const u = URL.createObjectURL(file),
          i = new Image();
        i.onload = () => {
          URL.revokeObjectURL(u);
          ok(i);
        };
        i.onerror = () => {
          URL.revokeObjectURL(u);
          no();
        };
        i.src = u;
      });
    } catch (__) {
      throw { e: "Could not read that picture. Try a JPG, PNG or WebP." };
    }
  }
  const bw = bm.width || bm.naturalWidth,
    bh = bm.height || bm.naturalHeight;
  if (!bw || !bh) throw { e: "Could not read that picture." };
  const enc = (c, t, q) =>
    new Promise((r) => {
      try {
        c.toBlob(r, t, q);
      } catch (_) {
        r(null);
      }
    });
  for (const S of [256, 192, 128, 96]) {
    const k = Math.min(1, S / Math.max(bw, bh)),
      c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(bw * k));
    c.height = Math.max(1, Math.round(bh * k));
    const x = c.getContext("2d", { willReadFrequently: true });
    x.drawImage(bm, 0, 0, c.width, c.height);
    let b = null;
    for (const q of [0.82, 0.7, 0.55, 0.4]) {
      b = await enc(c, "image/webp", q);
      if (!b || b.type !== "image/webp") break;
      if (b.size <= LIM) break;
    }
    if (!b || b.type !== "image/webp") {
      let al = false;
      try {
        const d = x.getImageData(0, 0, c.width, c.height).data;
        for (let i = 3; i < d.length; i += 4)
          if (d[i] < 250) {
            al = true;
            break;
          }
      } catch (_) {
        al = true;
      }
      if (al) b = await enc(c, "image/png");
      else
        for (const q of [0.82, 0.65, 0.5]) {
          b = await enc(c, "image/jpeg", q);
          if (b && b.size <= LIM) break;
        }
    }
    if (b && b.size > 0 && b.size <= LIM) {
      if (bm.close) bm.close();
      return { blob: b, w: c.width, h: c.height };
    }
  }
  if (bm.close) bm.close();
  throw { e: "That picture is too detailed for a small sticker. Try a simpler one." };
}
/* ---- Masque stickers: every built-in sticker is a little drawn mask character ----
   Still no files and no storage: a message keeps only ":stk:ID:" and each browser draws the art below (inline SVG, 100 x 100 box).
   To change one, edit its row in SKD: e = eyes, m = mouth, b = drawn behind the mask, x = drawn in front, t = move the whole mask, c = mask colour (defaults to the sticker colour). */
const SKI = "#16352a",
  SKS = "#ffcf9f",
  skF = (c, d) => '<path d="' + d + '" fill="' + c + '" stroke="' + SKI + '" stroke-width="3.2" stroke-linejoin="round"/>',
  skLn = (d, w, c) => '<path d="' + d + '" fill="none" stroke="' + (c || SKI) + '" stroke-width="' + (w || 4.5) + '" stroke-linecap="round" stroke-linejoin="round"/>',
  skLn2 = (d, c, w) => skLn(d, (w || 3.5) + 3.5, SKI) + skLn(d, w || 3.5, c),
  skHole = (x, y, rx, ry, g) =>
    '<ellipse cx="' + x + '" cy="' + y + '" rx="' + rx + '" ry="' + ry + '" fill="' + SKI + '"/>' +
    (g === 0 ? "" : '<circle cx="' + (x + (g || 2.5)) + '" cy="' + (y - 3) + '" r="2.3" fill="#fff"/>'),
  skSc = (s) => (2 / (s || 1)).toFixed(2),
  skSp = (x, y, s, f) =>
    '<path transform="translate(' + x + " " + y + ") scale(" + (s || 1) + ')" d="M0-8Q1-1 8 0Q1 1 0 8Q-1 1-8 0Q-1-1 0-8Z" fill="' + (f || "#fff6a8") + '" stroke="' + SKI + '" stroke-width="1.4" stroke-linejoin="round"/>',
  skHt = (x, y, s, f, r) =>
    '<path transform="translate(' + x + " " + y + ") rotate(" + (r || 0) + ") scale(" + (s || 1) + ')" d="M0 7C-12-1-7-12 0-5 7-12 12-1 0 7Z" fill="' + (f || "#ff3b5c") + '" stroke="' + SKI + '" stroke-width="' + skSc(s) + '" stroke-linejoin="round"/>',
  skSt = (x, y, s, f) =>
    '<polygon transform="translate(' + x + " " + y + ") scale(" + (s || 1) + ')" points="0,-10 3,-3.5 10,-3 4.5,2 6,9.5 0,5.5 -6,9.5 -4.5,2 -10,-3 -3,-3.5" fill="' + (f || "#ffd23f") + '" stroke="' + SKI + '" stroke-width="' + skSc(s) + '" stroke-linejoin="round"/>',
  skDrop = (x, y, s, f) =>
    '<path transform="translate(' + x + " " + y + ") scale(" + (s || 1) + ')" d="M0-8C4-2 6 1 6 3.5A6 6 0 0 1-6 3.5C-6 1-4-2 0-8Z" fill="' + (f || "#7cc4ff") + '" stroke="' + SKI + '" stroke-width="' + skSc(s) + '" stroke-linejoin="round"/>',
  skTx = (x, y, t, s, r) =>
    '<text x="' + x + '" y="' + y + '" text-anchor="middle" transform="rotate(' + (r || 0) + " " + x + " " + y + ')" font-family="Pirata One,Figtree,system-ui,sans-serif" font-weight="900" font-size="' + (s || 16) + '" fill="#fff" stroke="' + SKI + '" stroke-width="3.2" paint-order="stroke" stroke-linejoin="round">' + t + "</text>",
  skHand = (x, y, r, len, fl) => {
    len = len || [14, 16, 15, 12];
    let f = "";
    len.forEach((l, i) => {
      f += '<rect x="' + (-8 + i * 4.4) + '" y="' + (-6 - l) + '" width="4.2" height="' + (l + 4) + '" rx="2.1"/>';
    });
    return (
      '<g transform="translate(' + x + " " + y + ") rotate(" + (r || 0) + ") scale(" + (fl || 1) + ' 1)" fill="' + SKS + '" stroke="' + SKI + '" stroke-width="2.2" stroke-linejoin="round">' +
      f + '<rect x="-9" y="-8" width="19" height="17" rx="7"/><ellipse cx="-10.5" cy="-1" rx="3.4" ry="6" transform="rotate(-28 -10.5 -1)"/></g>'
    );
  },
  skHat = (c, p) =>
    '<path d="M34 18L50 -12L66 18Z" fill="' + c + '" stroke="' + SKI + '" stroke-width="3" stroke-linejoin="round"/>' +
    skLn("M41 6L59 11", 3, "#fff") + skLn("M37 14L63 18", 3, "#fff") +
    '<circle cx="50" cy="-12" r="4.2" fill="' + p + '" stroke="' + SKI + '" stroke-width="2.4"/>',
  skConf =
    '<rect x="6" y="2" width="5" height="5" fill="#4cc9f0" transform="rotate(30 8 4)"/><rect x="88" y="8" width="5" height="5" fill="#ff5ea8" transform="rotate(-20 90 10)"/><circle cx="92" cy="40" r="2.6" fill="#ffd23f"/><circle cx="6" cy="44" r="2.6" fill="#7bd88f"/><rect x="82" y="-8" width="4" height="7" fill="#ffd23f" transform="rotate(40 84 -4)"/>',
  skBadge = (c, inner) => '<circle cx="82" cy="76" r="14" fill="' + c + '" stroke="' + SKI + '" stroke-width="3"/>' + inner,
  skEyes = {
    o: () => skHole(34, 44, 7.5, 8.5) + skHole(66, 44, 7.5, 8.5),
    big: () => skHole(34, 44, 9.5, 11, 3) + skHole(66, 44, 9.5, 11, 3),
    happy: () => skLn("M26 47Q34 35 42 47") + skLn("M58 47Q66 35 74 47"),
    closed: () => skLn("M26 42Q34 52 42 42") + skLn("M58 42Q66 52 74 42"),
    squint: () => skLn("M27 36L41 44L27 52") + skLn("M73 36L59 44L73 52"),
    heart: () => skHt(34, 44, 0.95, "#ff3b5c") + skHt(66, 44, 0.95, "#ff3b5c"),
    star: () => skSt(34, 44, 1.05) + skSt(66, 44, 1.05),
    x: () => skLn("M27 37L41 51M41 37L27 51", 4) + skLn("M59 37L73 51M73 37L59 51", 4),
    side: () => skHole(34, 44, 7.5, 8.5, 0) + skHole(66, 44, 7.5, 8.5, 0) + '<circle cx="38.5" cy="44" r="3.2" fill="#fff"/><circle cx="70.5" cy="44" r="3.2" fill="#fff"/>',
    brows: () => skEyes.side() + skLn("M23 31Q34 24 44 32", 3.6) + skLn("M56 32Q66 24 77 31", 3.6),
    shades: () =>
      '<path d="M22 36H46V46Q46 55 38 55H30Q22 55 22 46Z M54 36H78V46Q78 55 70 55H62Q54 55 54 46Z" fill="' + SKI + '" stroke="' + SKI + '" stroke-width="2" stroke-linejoin="round"/>' +
      skLn("M46 39H54", 3) + skLn("M27 41H33M59 41H65", 2.4, "#fff"),
    angry: () => skHole(34, 47, 7, 6.5) + skHole(66, 47, 7, 6.5) + skLn("M22 30L44 39", 5) + skLn("M78 30L56 39", 5),
    wink: () => skLn("M26 47Q34 35 42 47") + skHole(66, 44, 7.5, 8.5),
    half: () => '<path d="M26 42H42A8 8 0 0 1 26 42ZM58 42H74A8 8 0 0 1 58 42Z" fill="' + SKI + '"/>' + skLn("M24 42H44M56 42H76", 3.4),
    pls: () =>
      skHole(34, 44, 9.5, 11, 0) + skHole(66, 44, 9.5, 11, 0) +
      '<circle cx="31" cy="40" r="3.8" fill="#fff"/><circle cx="37" cy="48.5" r="1.8" fill="#fff"/><circle cx="63" cy="40" r="3.8" fill="#fff"/><circle cx="69" cy="48.5" r="1.8" fill="#fff"/>',
    think: () => skHole(34, 44, 7.5, 8.5) + skHole(66, 44, 7.5, 8.5) + skLn("M55 31Q66 22 78 29", 3.8),
  },
  skMouth = {
    smile: () => skLn("M38 63Q50 76 62 63", 4),
    grin: () => '<path d="M35 61Q50 84 65 61Z" fill="' + SKI + '" stroke="' + SKI + '" stroke-width="3" stroke-linejoin="round"/><path d="M43 68Q50 64 57 68Q50 73 43 68Z" fill="#ff7a8a"/>',
    laugh: () => '<path d="M30 58Q50 92 70 58Z" fill="' + SKI + '" stroke="' + SKI + '" stroke-width="3" stroke-linejoin="round"/><path d="M41 71Q50 65 59 71Q50 77 41 71Z" fill="#ff7a8a"/>',
    o: () => '<ellipse cx="50" cy="70" rx="5.5" ry="7" fill="' + SKI + '"/>',
    bigo: () => '<ellipse cx="50" cy="71" rx="7.5" ry="9.5" fill="' + SKI + '"/>',
    tiny: () => '<ellipse cx="50" cy="68" rx="3" ry="3.5" fill="' + SKI + '"/>',
    flat: () => skLn("M40 68H60", 4),
    frown: () => skLn("M38 73Q50 62 62 73", 4),
    wavy: () => skLn("M35 68q4.2-5 8.3 0t8.3 0t8.3 0t8.3 0", 3.8),
    kiss: () => '<ellipse cx="52" cy="68" rx="5" ry="4" fill="#ff3b5c" stroke="' + SKI + '" stroke-width="2.5"/>',
    tongue: () => skLn("M38 63Q50 74 62 63", 4) + '<path d="M46 69V76A4 4 0 0 0 54 76V69Z" fill="#ff7a8a" stroke="' + SKI + '" stroke-width="2.4" stroke-linejoin="round"/>',
    teeth: () =>
      '<rect x="37" y="62" width="26" height="12" rx="4" fill="#fff" stroke="' + SKI + '" stroke-width="3"/>' + skLn("M44 62V74M50 62V74M56 62V74", 2),
    smirk: () => skLn("M39 67Q54 72 63 61", 4),
    wail: () => '<path d="M37 77Q50 57 63 77Z" fill="' + SKI + '" stroke="' + SKI + '" stroke-width="3" stroke-linejoin="round"/>',
    zig: () => skLn("M36 70L42 64L48 70L54 64L60 70L64 66", 3.6),
    pls: () => skLn("M40 71Q45 66 50 71T60 71", 3.6),
  },
  skX = {
    blush: () => '<ellipse cx="21" cy="58" rx="6.5" ry="3.8" fill="#ff5c86" fill-opacity=".5"/><ellipse cx="79" cy="58" rx="6.5" ry="3.8" fill="#ff5c86" fill-opacity=".5"/>',
    sweat: () => skDrop(88, 26, 0.95),
    zzz: () => skTx(78, 22, "Z", 17, -8) + skTx(89, 10, "z", 13, -8) + skTx(97, 0, "z", 10, -8),
    shock: () => skLn("M8 20L0 12M4 36L-4 34M92 20L100 12M96 36L104 34", 3.6),
    motion: () => skLn("M4 26L-4 22M4 38L-6 38M96 26L104 22M96 38L106 38", 3.6),
    sparks: () => skSp(10, 12, 1) + skSp(92, 18, 0.8) + skSp(88, 76, 0.7),
    hearts: () => skHt(86, 14, 0.95, "#ff3b5c", 12) + skHt(12, 20, 0.7, "#ff8fb1", -14) + skHt(94, 46, 0.55, "#ff8fb1", 10),
    hearts2: () => skHt(10, 14, 0.8, "#ff3b5c", -12) + skHt(90, 12, 1, "#ff8fb1", 12) + skHt(18, 82, 0.6, "#ff3b5c", -8) + skHt(88, 82, 0.7, "#ff3b5c", 8),
    flyheart: () => skHt(88, 50, 1.1, "#ff3b5c", 14) + skLn("M74 62L80 58M74 70L82 70", 2.6),
    joytears: () => skDrop(8, 42, 0.8) + skDrop(94, 40, 0.8) + skDrop(2, 58, 0.55) + skDrop(100, 56, 0.55),
    crytears: () =>
      skLn("M30 54Q24 66 26 78", 4.5, "#7cc4ff") + skLn("M70 54Q76 66 74 78", 4.5, "#7cc4ff") + skDrop(25, 84, 0.8) + skDrop(75, 84, 0.8),
    tear: () => skDrop(27, 64, 0.85),
    cloud:
      () => '<path d="M22 6Q22-6 36-6Q42-14 54-6Q70-8 70 6Q78 8 74 16H20Q12 14 22 6Z" fill="#c9d3dc" stroke="' + SKI + '" stroke-width="2.6" stroke-linejoin="round"/>' + skDrop(32, 25, 0.55) + skDrop(52, 27, 0.55) + skDrop(68, 24, 0.55),
    anger: () => '<path d="M76 16Q80 20 76 24M88 16Q84 20 88 24M74 18Q80 16 86 18M74 23Q80 25 86 23" fill="none" stroke="#e0314b" stroke-width="3.4" stroke-linecap="round"/>' + skLn("M16 14Q10 6 16 -2M26 10Q22 2 28 -4", 3.2, "#9aa5ab"),
    bubble: () => '<circle cx="62" cy="74" r="7" fill="#bfe8ff" stroke="' + SKI + '" stroke-width="2"/><circle cx="64" cy="72" r="2" fill="#fff"/>',
    thought: () => '<circle cx="80" cy="30" r="2.6" fill="#fff" stroke="' + SKI + '" stroke-width="1.6"/><circle cx="86" cy="22" r="3.6" fill="#fff" stroke="' + SKI + '" stroke-width="1.8"/><ellipse cx="92" cy="6" rx="12" ry="10" fill="#fff" stroke="' + SKI + '" stroke-width="2.4"/>' + skTx(92, 12, "?", 15),
    crown: () => '<path d="M28 16L30 -6L41 5L50 -10L59 5L70 -6L72 16Z" fill="#ffd23f" stroke="' + SKI + '" stroke-width="3" stroke-linejoin="round"/><circle cx="50" cy="6" r="2.8" fill="#ff3b5c" stroke="' + SKI + '" stroke-width="1.4"/><circle cx="31" cy="-3" r="2" fill="#ff3b5c"/><circle cx="69" cy="-3" r="2" fill="#ff3b5c"/>',
    party: () => skHat("#ff5ea8", "#ffd23f") + skConf,
    cap: () => skHat("#5b7cff", "#fff"),
    halo: () => '<ellipse cx="50" cy="4" rx="22" ry="6" fill="none" stroke="' + SKI + '" stroke-width="9"/><ellipse cx="50" cy="4" rx="22" ry="6" fill="none" stroke="#ffd23f" stroke-width="4.5"/>',
    moon: () => '<path d="M82 -2A14 14 0 1 0 98 18A11 11 0 1 1 82 -2Z" fill="#fff6a8" stroke="' + SKI + '" stroke-width="2.5" stroke-linejoin="round"/>' + skSp(10, 8, 0.8) + skSp(24, -4, 0.55),
    burst: () => skLn2("M50 8V-10M30 12L18-4M70 12L82-4M14 24L0 16M86 24L100 16", "#ffb703", 3.6) + skSp(50, -6, 0.9, "#fff"),
    hug: () => skLn("M2 74Q50 110 98 74", 15) + skLn("M2 74Q50 110 98 74", 9, SKS) + skHt(12, 50, 0.7, "#ff3b5c", -12) + skHt(90, 48, 0.8, "#ff3b5c", 12),
    yes: () => skBadge("#38c172", skLn("M74 76L80 82L91 70", 4.5, "#fff")),
    nope: () => skBadge("#ef4444", skLn("M75 69L89 83M89 69L75 83", 4.5, "#fff")),
    okb: () => skBadge("#ffd23f", skTx(82, 81, "OK", 13)),
    wave: () => skHand(90, 72, 16) + skLn("M99 38Q106 48 100 58", 3),
    peace: () => skHand(90, 72, 14, [7, 18, 18, 7]) + skLn("M99 38Q106 48 100 58", 3),
    clap: () => skHand(8, 84, -14, [9, 10, 9, 8], -1) + skHand(92, 84, 14, [9, 10, 9, 8]) + skSp(8, 54, 0.8) + skSp(92, 54, 0.8) + skLn("M14 60L6 56M86 60L94 56", 3),
    pray: () => '<path d="M50 99L36 88Q34 78 42 72Q47 70 50 76Q53 70 58 72Q66 78 64 88Z" fill="' + SKS + '" stroke="' + SKI + '" stroke-width="2.6" stroke-linejoin="round"/>' + skLn("M50 78V98", 2.4),
    q: () => skTx(88, 20, "?", 20, 12) + skTx(10, 24, "?", 15, -12),
    finger: () => '<rect x="45" y="54" width="10" height="38" rx="5" fill="' + SKS + '" stroke="' + SKI + '" stroke-width="2.6"/>' + skLn("M48 80H52", 2),
    wall: () =>
      '<rect x="-6" y="62" width="112" height="44" rx="6" fill="#8fa193" stroke="' + SKI + '" stroke-width="3.5"/>' + skLn("M-6 78H106M32 62V78M74 62V78M52 78V106", 2.2, "#5d7064"),
    fingers: () => ["13", "25", "73", "85"].map((x) => '<rect x="' + x + '" y="50" width="9" height="18" rx="4.5" fill="' + SKS + '" stroke="' + SKI + '" stroke-width="2.4"/>').join(""),
    stars: () => skSt(10, 12, 0.7) + skSt(92, 20, 0.85) + skSt(86, 78, 0.6),
  },
  skBack = {
    flame: () => '<path d="M16 34C10 20 22 16 20 2C32 8 36 16 34 24C38 10 44 8 44 -8C58 0 56 14 54 22C60 14 66 14 66 4C78 12 84 22 80 34Z" fill="#ff7a2e" stroke="' + SKI + '" stroke-width="3" stroke-linejoin="round"/><path d="M34 30C32 22 40 20 40 10C48 16 48 24 46 30Z" fill="#ffd23f"/>',
    ghost: () => '<path d="M8 34C8 12 92 12 92 34V92Q85 84 78 92T64 92T50 92T36 92T22 92T8 92Z" fill="#fff" stroke="' + SKI + '" stroke-width="3.4" stroke-linejoin="round"/>',
    spot: () => '<path d="M36 -14H64L102 98H-2Z" fill="#fff6a8" fill-opacity=".75"/>',
  },
  /* e eyes, m mouth, b/x extras (names in skBack / skX), c mask colour override, t transform for the mask */
  SKD = {
    lol: { e: "squint", m: "laugh", x: ["joytears"] },
    haha: { e: "happy", m: "grin", x: ["blush", "motion"] },
    love: { e: "heart", m: "smile", x: ["blush", "hearts"] },
    hug: { e: "happy", m: "smile", x: ["blush", "hug"] },
    kiss: { e: "wink", m: "kiss", x: ["blush", "flyheart"] },
    hearts: { e: "happy", m: "smile", x: ["blush", "hearts2"] },
    cool: { e: "shades", m: "smirk", x: ["sparks"] },
    fire: { e: "o", m: "grin", b: ["flame"], x: ["sparks"] },
    ok: { e: "wink", m: "smile", x: ["okb"] },
    yes: { e: "happy", m: "smile", x: ["yes"] },
    no: { e: "closed", m: "frown", x: ["nope"] },
    wow: { e: "big", m: "bigo", x: ["shock"] },
    omg: { e: "big", m: "bigo", x: ["shock", "sweat"] },
    sad: { e: "o", m: "frown", x: ["cloud", "tear"] },
    cry: { e: "closed", m: "wail", x: ["crytears"] },
    angry: { e: "angry", m: "teeth", c: "#ff9a8a", x: ["anger"] },
    think: { e: "think", m: "smirk", x: ["thought"] },
    sleep: { e: "closed", m: "tiny", x: ["bubble", "zzz"] },
    party: { e: "happy", m: "grin", x: ["party"] },
    gg: { e: "star", m: "grin", x: ["crown", "sparks"] },
    thanks: { e: "closed", m: "smile", x: ["blush", "pray"] },
    hi: { e: "happy", m: "smile", x: ["wave"] },
    bye: { e: "wink", m: "smile", x: ["peace"] },
    ghost: { e: "o", m: "bigo", b: ["ghost"] },
    skull: { e: "x", m: "tongue", x: ["halo"] },
    eyes: { e: "brows", m: "smirk" },
    clap: { e: "happy", m: "grin", x: ["clap"] },
    mind: { e: "big", m: "bigo", x: ["burst"] },
    pls: { e: "pls", m: "pls", x: ["blush", "tear"] },
    bored: { e: "half", m: "flat" },
    sorry: { e: "side", m: "wavy", x: ["blush", "sweat"] },
    goodnight: { e: "closed", m: "smile", x: ["cap", "moon"] },
    whois: { e: "o", m: "", c: "#dfe5e9", q: 1 },
    reveal: { e: "o", m: "", t: "translate(8 -18) rotate(-18 50 50) scale(.86)", reveal: 1 },
    shh: { e: "o", m: "", x: ["finger"] },
    twin: { twin: 1 },
    psst: { e: "side", m: "", t: "translate(0 6)", x: ["wall", "fingers"] },
    spot: { e: "star", m: "grin", b: ["spot"], x: ["stars"] },
  },
  skMask = (c, e, m, t, extra) =>
    '<g' + (t ? ' transform="' + t + '"' : "") + ">" +
    skF(c, "M8 30C8 19 30 13 50 13S92 19 92 30V42C92 67 74 87 50 87S8 67 8 42Z") +
    '<path d="M12 56C18 76 34 86 50 86S82 76 88 56C80 70 66 76 50 76S20 70 12 56Z" fill="#000" fill-opacity=".08"/>' +
    skLn("M15 29C18 22 30 18 42 17", 3.2, "rgba(255,255,255,.65)") +
    '<path d="M50 19l5 5-5 5-5-5z" fill="#d9472b" stroke="' + SKI + '" stroke-width="2" stroke-linejoin="round"/>' +
    (e ? skEyes[e]() : "") + (m ? skMouth[m]() : "") + (extra || "") + "</g>",
  skCache = {};
function stkSvg(z) {
  const k = z[0];
  if (skCache[k] !== undefined) return skCache[k];
  const d = SKD[k];
  let s = null;
  if (d) {
    const c = d.c || z[3] || "#ffe27a";
    let b = (d.b || []).map((n) => skBack[n]()).join(""),
      body;
    if (d.twin) {
      body = skMask(c, "o", "smile", "translate(-6 -2) scale(.68)") + skMask("#ff9d7a", "wink", "smirk", "translate(38 32) scale(.68)") + skSp(88, 14, 0.9) + skSp(8, 82, 0.7);
    } else if (d.reveal) {
      b = '<circle cx="50" cy="62" r="31" fill="#ffd9b0" stroke="' + SKI + '" stroke-width="3.4"/><circle cx="39" cy="64" r="3.6" fill="' + SKI + '"/><circle cx="61" cy="64" r="3.6" fill="' + SKI + '"/>' + skLn("M40 76Q50 85 60 76", 3.6) + skSp(86, 20, 0.9) + skSp(12, 24, 0.7);
      body = skMask(c, d.e, d.m, d.t);
    } else {
      body = skMask(c, d.e, d.m, d.t, d.q ? skTx(50, 82, "?", 40) : "");
    }
    s = '<svg viewBox="-6 -14 112 112" xmlns="http://www.w3.org/2000/svg" focusable="false" aria-hidden="true">' + b + body + (d.x || []).map((n) => skX[n]()).join("") + "</svg>";
  }
  return (skCache[k] = s);
}

IC.smile = '<circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="M9 9h.01M15 9h.01"/>';
function stkEl(z) {
  if (z[4]) {
    let r = 0;
    for (const c of z[0]) r += c.charCodeAt(0);
    return h(
      "div",
      { class: "stk stki", role: "img", "aria-label": "Sticker", style: "--r:" + ((r % 9) - 4) + "deg" },
      h("img", {
        src: "?stk=" + z[0],
        alt: "",
        draggable: "false",
        loading: "lazy",
        decoding: "async",
        onerror: (e) => {
          const d = e.target.parentNode;
          d.classList.add("gone");
          e.target.remove();
          d.append(h("span", { class: "stkt", "aria-hidden": "true" }, "Sticker unavailable"));
        },
      }),
    );
  }
  let r = 0;
  for (const c of z[0]) r += c.charCodeAt(0);
  return h(
    "div",
    {
      class: "stk",
      role: "img",
      "aria-label": "Sticker: " + z[2],
      style: "--c:" + z[3] + ";--r:" + ((r % 9) - 4) + "deg",
    },
    stkArt(z),
    h("span", { class: "stkt", "aria-hidden": "true" }, z[2]),
  );
}
/* the drawn mask character; an id with no drawing falls back to its emoji */
function stkArt(z) {
  const e = h("span", { class: "stke", "aria-hidden": "true" }),
    s = stkSvg(z);
  if (s) e.innerHTML = s;
  else e.textContent = z[1];
  return e;
}
/* o = {inp, send(text) -> promise}. Returns the button for the composer and the panel (put the panel inside a position:relative form). */
/* A picture (picked from the device, or a photo / GIF from a chat) becomes a favourite sticker: shrink it, show what will be saved, then add it. cb = {send(text) for "Add and send", done()} */
async function stkAdd(f, cb) {
  cb = cb || {};
  let r = null,
    note = "";
  const gif = f.type === "image/gif" || /\.gif$/i.test(f.name || "");
  if (gif) {
    try {
      r = await stkAnimate(f);
    } catch (x) {
      note = ((x && x.e) || "") + " It will be a still picture.";
    }
    if (!r && !note)
      note =
        "This GIF can't be animated in this browser (Chrome, Edge and Firefox can), so it will be a still picture.";
  }
  if (!r) {
    try {
      r = await stkShrink(f);
    } catch (x) {
      alert((x && x.e) || "Could not use that picture.");
      return;
    }
  }
  const url = URL.createObjectURL(r.blob),
    kb = Math.max(1, Math.round(r.blob.size / 1024));
  sheet("New sticker", (close) => {
    const err = h("span", { class: "err" }),
      go = async (send) => {
        err.textContent = "";
        bs.forEach((x) => (x.disabled = true));
        try {
          const j = await api("stkup", fd({ img: r.blob }));
          const ref = "i:" + j.id;
          if (!SF.s.has(ref)) {
            SF.l.unshift(ref);
            SF.s.add(ref);
          }
          URL.revokeObjectURL(url);
          close();
          if (cb.done) cb.done();
          if (send && cb.send) await cb.send(":sti:" + j.id + ":");
        } catch (x) {
          err.textContent = (x && x.e) || "Could not add that sticker.";
          bs.forEach((y) => (y.disabled = false));
        }
      },
      b1 = h("button", { type: "button", class: "btn", onclick: () => go(false) }, "Add to favorites"),
      b2 = h("button", { type: "button", class: "ghost", onclick: () => go(true) }, "Add and send"),
      bs = [b1, b2];
    return h(
      "div",
      { class: "form" },
      h("div", { class: "stkprev" }, h("img", { src: url, alt: "Sticker preview" })),
      h(
        "p",
        { class: "hint" },
        r.w +
          " \u00d7 " +
          r.h +
          " px" +
          (r.anim ? ", animated (" + r.anim + " frames, " + r.secs + " s)" : "") +
          ", " +
          kb +
          " KB. It is stored once, and sending it again costs almost nothing.",
      ),
      note ? h("p", { class: "hint" }, note) : null,
      err,
      b1,
      cb.send ? b2 : null,
    );
  });
}
/* a photo or GIF that is already in a chat: fetch it and offer it as a sticker */
async function stkFromChat(name) {
  let b;
  try {
    const r = await fetch("?img=" + name);
    if (!r.ok) throw 0;
    b = await r.blob();
  } catch (_) {
    alert("Could not load that picture.");
    return;
  }
  await stkAdd(new File([b], name, { type: b.type || (/\.gif$/.test(name) ? "image/gif" : "image/jpeg") }));
}
/* Which game site an invite link is for (just by its address; nothing is fetched), so the card can say "Roblox" or "Steam". */
function giPlat(u) {
  if (u.startsWith("steam://")) return { n: "Steam", host: "the Steam app", known: 1 };
  const host = ((/^https:\/\/([^\/:?#]+)/i.exec(u) || [])[1] || "").toLowerCase().replace(/^www\./, ""),
    on = (d) => host === d || host.endsWith("." + d);
  if (on("roblox.com") || on("ro.blox.com")) return { n: "Roblox", host, known: 1 };
  if (on("steampowered.com") || on("steamcommunity.com") || on("s.team")) return { n: "Steam", host, known: 1 };
  if (on("discord.gg") || on("discord.com")) return { n: "Discord", host, known: 1 };
  if (on("epicgames.com")) return { n: "Epic Games", host, known: 1 };
  return { n: host || "Link", host, known: 0 };
}
const giLeft = (ms) =>
  ms < 60000 ? "Closing soon" : ms < 3600000 ? Math.ceil(ms / 60000) + " min left" : Math.ceil(ms / 3600000) + " h left";
/* The last few games you invited people to (name + link), kept in this browser only, so the Game tab can suggest them again. */
const GIRK = "mq_gi_recent",
  giRecent = () => {
    try {
      const a = JSON.parse(localStorage.getItem(GIRK) || "[]");
      return Array.isArray(a) ? a.filter((z) => z && typeof z.n === "string" && giUrlOk(z.u)).slice(0, 6) : [];
    } catch (_) {
      return [];
    }
  },
  giRemember = (n, u) => {
    try {
      const a = giRecent().filter((z) => z.u !== u);
      a.unshift({ n, u });
      localStorage.setItem(GIRK, JSON.stringify(a.slice(0, 6)));
    } catch (_) {}
  };
/* invites already answered with a quick reply this session (message ids), so a redraw keeps their buttons off */
const GIR = new Set();
/* The invite card in a chat bubble. d = decoded invite, m = the message (m.ts, seconds), mine = sent by you. Join opens the link in a new tab; the card closes by itself when the time is up. */
function giCard(d, m, mine, x) {
  const pl = giPlat(d.u),
    exp = ((+m.ts || Math.floor(Date.now() / 1000)) + d.x * 60) * 1000,
    box = h("div", { class: "gic", role: "group", "aria-label": "Game invite: " + d.n }),
    tag = h("small", { class: "gic-t" }),
    act = h("div", { class: "gia" }),
    qr = h("div", { class: "gia gir" });
  const cp = h(
    "button",
    {
      type: "button",
      class: "ghost gic-c",
      onclick: async (e) => {
        const b = e.currentTarget;
        try {
          await navigator.clipboard.writeText(d.u);
          b.textContent = "Copied";
        } catch (_) {
          b.textContent = "Copy failed";
        }
        setTimeout(() => (b.textContent = "Copy link"), 1500);
      },
    },
    "Copy link",
  );
  let dead = null;
  const paint = () => {
    const left = exp - Date.now(),
      d2 = left <= 0;
    tag.textContent = d2 ? "Expired" : giLeft(left);
    if (d2 === dead) return;
    dead = d2;
    box.classList.toggle("gx", d2);
    act.replaceChildren(
      ...[
        d2
          ? h("span", { class: "gis" }, "This invite has expired")
          : mine
            ? h("span", { class: "gis" }, "Invite sent")
            : h(
                "a",
                { class: "btn gij", href: d.u, target: "_blank", rel: "noopener noreferrer nofollow" },
                "\u25B6 Play",
              ),
        d2 ? null : cp,
      ].filter(Boolean),
    );
    qr.replaceChildren(
      ...(d2 || mine || !x || !x.quick
        ? []
        : [
            ["I\u2019m in \u{1F44D}", "I\u2019m in! \u{1F3AE}"],
            ["Can\u2019t now", "Can\u2019t right now"],
          ].map(([l, t]) => {
            const bt = h(
              "button",
              {
                type: "button",
                class: "ghost gic-q",
                onclick: async (e) => {
                  const row = e.currentTarget.parentNode;
                  row.querySelectorAll("button").forEach((b) => (b.disabled = true));
                  try {
                    await x.quick(m, t);
                    GIR.add(m.id);
                  } catch (z) {
                    row.querySelectorAll("button").forEach((b) => (b.disabled = false));
                    alert((z && z.e) || "Could not send the reply.");
                  }
                },
              },
              l,
            );
            bt.disabled = GIR.has(m.id);
            return bt;
          })),
    );
  };
  box.append(
    ...[
    h(
      "div",
      { class: "gih" },
      h("span", { class: "gic-i", "aria-hidden": "true" }, "\u{1F3AE}"),
      h("span", {}, "Game invite"),
      tag,
    ),
    h("b", { class: "gin" }, d.n),
    d.o ? h("p", { class: "gio" }, d.o) : null,
    act,
    qr,
    h("small", { class: "gic-h" }, pl.known ? pl.n + (pl.host && pl.n !== pl.host ? " \u00b7 " + pl.host : "") : "Opens " + pl.host),
    ].filter(Boolean),
  );
  paint();
  /* Thumbnail: the same server-side link preview the rest of chat uses (it fetches the page once, keeps a small copy on this server and caches it for a week, so viewers never contact the game site). No picture found = the card stays as it is. steam:// links have no page to read. */
  if (!dead && d.u.startsWith("https://"))
    lpGet(d.u).then((r) => {
      if (!r || !/^[a-f0-9]{16}$/.test(r.i || "")) return;
      box.prepend(
        h("img", {
          class: "gic-img",
          src: "?lpi=" + r.i,
          alt: "",
          loading: "lazy",
          onerror: (e) => e.target.remove(),
          onload: (e) => {
            const l = e.target.closest(".mlist");
            if (l && l.dataset.stick === "1") l.scrollTop = l.scrollHeight;
          },
        }),
      );
    });
  const iv = setInterval(() => {
    if (!box.isConnected || dead) {
      clearInterval(iv);
      return;
    }
    paint();
    if (dead) clearInterval(iv);
  }, 15000);
  return box;
}
function emojiPad(o) {
  const btn = h(
      "button",
      {
        type: "button",
        class: "ghost ibtn emob",
        "aria-label": "Emojis and stickers",
        "aria-expanded": "false",
        title: "Emojis and stickers",
      },
      ic("smile", 20),
    ),
    panel = h("div", { class: "emop", hidden: "", role: "group", "aria-label": "Emojis and stickers" }),
    tE = h("button", { type: "button", class: "emot" }, "Emoji"),
    tS = h("button", { type: "button", class: "emot" }, "Stickers"),
    tF = h("button", { type: "button", class: "emot" }, "\u2605 Mine"),
    tG = h("button", { type: "button", class: "emot" }, "\u{1F3AE} Game"),
    grid = h("div", { class: "emog" }),
    file = h("input", { type: "file", accept: "image/*", hidden: "", "aria-hidden": "true", tabindex: "-1" });
  let tab = "e",
    busy = 0;
  const gs = { n: "", u: "", o: "", x: 60 };
  const ins = (e) => {
    const i = o.inp,
      lim = +i.maxLength > 0 ? +i.maxLength : 500,
      a = i.selectionStart ?? i.value.length,
      b = i.selectionEnd ?? a;
    if (i.value.length - (b - a) + e.length > lim) return;
    i.value = i.value.slice(0, a) + e + i.value.slice(b);
    const p = a + e.length;
    try {
      i.setSelectionRange(p, p);
    } catch (_) {}
    i.dispatchEvent(new Event("input", { bubbles: true }));
  };
  const open = (v) => {
    panel.hidden = !v;
    btn.setAttribute("aria-expanded", String(v));
    btn.classList.toggle("on", v);
    if (v) paint();
  };
  const sendS = async (z) => {
    if (busy) return;
    busy = 1;
    grid.classList.add("busy");
    try {
      await o.send(stkTx(z));
      open(false);
    } catch (x) {
      alert((x && x.e) || "Could not send the sticker.");
    }
    setTimeout(() => {
      busy = 0;
      grid.classList.remove("busy");
    }, 700);
  };
  const favT = async (z) => {
    const r = stkRef(z);
    try {
      await SF.set(r, !SF.has(r));
    } catch (x) {
      alert((x && x.e) || "Could not update your stickers.");
    }
    paint(true);
  };
  const tile = (z) => {
    const r = stkRef(z),
      on = SF.has(r);
    return h(
      "div",
      { class: "stkc" },
      h(
        "button",
        { type: "button", class: "sb", "aria-label": "Send sticker: " + z[2], onclick: () => sendS(z) },
        stkEl(z),
      ),
      h(
        "button",
        {
          type: "button",
          class: "sf" + (on ? " on" : ""),
          "aria-label": on ? "Remove from favorites" : "Add to favorites",
          "aria-pressed": String(on),
          title: on ? "Remove from favorites" : "Add to favorites",
          onclick: () => favT(z),
        },
        on ? "\u2605" : "\u2606",
      ),
    );
  };
  /* picture picked in the picker */
  const addPic = (f) =>
    stkAdd(f, {
      send: async (t) => {
        await o.send(t);
        open(false);
      },
      done: () => {
        tab = "f";
        paint(true);
      },
    });
  file.onchange = () => {
    const f = file.files && file.files[0];
    file.value = "";
    if (f) addPic(f);
  };
  /* Game tab: paste the link (the game is recognised from it), optionally name it and add a note, pick how long it stays open. Recent games are one tap away. What is typed is kept while the panel is closed and reopened. */
  function giForm() {
    const err = h("span", { class: "err", role: "alert" }),
      hint = h("small", { class: "gihint", "aria-live": "polite" }),
      u = h("input", {
        maxlength: 220,
        placeholder: "Paste the join link (Roblox, Steam\u2026)",
        "aria-label": "Join link",
        inputmode: "url",
        autocomplete: "off",
        autocapitalize: "off",
        spellcheck: "false",
      }),
      n = h("input", { maxlength: 40, placeholder: "Game name (optional)", "aria-label": "Game name", autocomplete: "off" }),
      t = h("input", { maxlength: 60, placeholder: "Note, like: join my server!", "aria-label": "Note", autocomplete: "off" }),
      x = h("select", { "aria-label": "Invite stays open for" }, ...GIX.map(([v, l]) => h("option", { value: String(v) }, l))),
      go = h("button", { class: "btn", type: "submit" }, "Send invite");
    const fix = (v) => (v && !/^[a-z][a-z0-9+.-]*:/i.test(v) ? "https://" + v : v);
    const upd = () => {
      const v = fix(gs.u.trim()),
        ok = giUrlOk(v);
      hint.textContent = !v ? "" : ok ? (giPlat(v).known ? giPlat(v).n + " link \u2713" : "Link \u2713") : v.length > 10 ? "Needs a full https:// or steam:// link" : "";
      hint.classList.toggle("bad", !!v && !ok && v.length > 10);
    };
    n.value = gs.n;
    u.value = gs.u;
    t.value = gs.o;
    x.value = String(gs.x);
    n.oninput = () => (gs.n = n.value);
    u.oninput = () => {
      gs.u = u.value;
      upd();
    };
    t.oninput = () => (gs.o = t.value);
    x.onchange = () => (gs.x = +x.value);
    upd();
    const rec = giRecent(),
      f = h(
        "form",
        { class: "gifm" },
        rec.length
          ? h(
              "div",
              { class: "gircs", role: "group", "aria-label": "Recent games" },
              ...rec.map((z) =>
                h(
                  "button",
                  {
                    type: "button",
                    class: "ghost girc",
                    title: z.u,
                    onclick: () => {
                      gs.n = z.n;
                      gs.u = z.u;
                      n.value = z.n;
                      u.value = z.u;
                      err.textContent = "";
                      upd();
                    },
                  },
                  "\u{1F3AE} " + z.n,
                ),
              ),
            )
          : null,
        u,
        hint,
        n,
        h("div", { class: "gifr" }, t, x),
        err,
        go,
        h("p", { class: "hint" }, "Everyone in the chat can tap Play. The link opens in a new tab, so only invite people to games you trust."),
      );
    f.onsubmit = async (e) => {
      e.preventDefault();
      if (busy) return;
      const link = fix(gs.u.trim());
      if (!giUrlOk(link)) {
        err.textContent = "Paste the full join link: https://\u2026 (or steam://\u2026).";
        return;
      }
      const pl = giPlat(link),
        d = { n: (gs.n.trim() || (pl.known ? pl.n + " game" : pl.n)).slice(0, 40), u: link, o: gs.o.trim().slice(0, 60), x: gs.x },
        tx = giTx(d);
      if (tx.length > 500) {
        err.textContent = "That is too long. Use a shorter link or note.";
        return;
      }
      busy = 1;
      go.disabled = true;
      err.textContent = "";
      try {
        await o.send(tx);
        giRemember(d.n, d.u);
        gs.n = gs.u = gs.o = "";
        open(false);
      } catch (z) {
        err.textContent = (z && z.e) || "Could not send the invite.";
      }
      busy = 0;
      go.disabled = false;
    };
    return f;
  }
  function paint(keep) {
    for (const [t, b] of [
      ["e", tE],
      ["s", tS],
      ["f", tF],
      ["g", tG],
    ])
      b.setAttribute("aria-pressed", String(tab === t));
    grid.className = "emog " + (tab === "e" ? "e" : tab === "g" ? "g" : "s");
    if (keep !== true) grid.scrollTop = 0;
    if (tab === "g") {
      grid.replaceChildren(giForm());
      return;
    }
    if (tab !== "e" && !SF.done)
      SF.load().then(() => {
        if (!panel.hidden && SF.done) paint(true);
      });
    if (tab === "e") {
      grid.replaceChildren(
        ...Object.entries(EMO).flatMap(([n, l]) => [
          h("div", { class: "emoh" }, n),
          ...l.split(" ").map((e) => h("button", { type: "button", "aria-label": e, onclick: () => ins(e) }, e)),
        ]),
      );
      return;
    }
    if (tab === "s") {
      grid.replaceChildren(...STK.map(tile));
      return;
    }
    const items = SF.l
      .map((r) => (r.slice(0, 2) === "b:" ? STK.find((z) => z[0] === r.slice(2)) : [r.slice(2), "", "Sticker", "", 1]))
      .filter(Boolean);
    grid.replaceChildren(
      h(
        "button",
        { type: "button", class: "stkadd", "aria-label": "Add a picture sticker", onclick: () => file.click() },
        h("span", { "aria-hidden": "true" }, "+"),
        h("small", {}, "Add picture"),
      ),
      ...items.map(tile),
      ...(items.length
        ? []
        : [
            h(
              "p",
              { class: "hint stkemp" },
              "Tap \u2606 on any sticker to keep it here, or add your own picture with +. Favorites work in every chat.",
            ),
          ]),
    );
  }
  tE.onclick = () => {
    tab = "e";
    paint();
  };
  tS.onclick = () => {
    tab = "s";
    paint();
  };
  tF.onclick = () => {
    tab = "f";
    paint();
  };
  tG.onclick = () => {
    tab = "g";
    paint();
  };
  btn.onclick = () => open(panel.hidden);
  panel.append(h("div", { class: "emotr" }, tE, tS, tF, ...(XP() ? [tG] : [])), grid, file);
  panel.addEventListener("mousedown", (e) => {
    if (e.target.closest("button")) e.preventDefault();
  });
  panel.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      open(false);
      btn.focus();
    }
  });
  const away = (e) => {
    if (!panel.isConnected) {
      document.removeEventListener("pointerdown", away);
      return;
    }
    if (!panel.hidden && !panel.contains(e.target) && !btn.contains(e.target) && !e.target.closest(".veil"))
      open(false);
  };
  document.addEventListener("pointerdown", away);
  return { btn, panel };
}
/* Shared by direct and group chats: the reply bar above the composer, the pinned bar under the header, and what reacting / pinning do.
   o = {rk,pk (api names), who(m), inp, jump(id), patch(id,fn), setPin(m,v)}. */
/* What was on screen before a redraw (message ids and reaction chips), so only NEW messages slide in and only NEW chips pop. */
function chatsnap(list) {
  const ids = new Set(),
    rx = new Map();
  list.querySelectorAll(".mrow[data-mid]").forEach((e) => {
    ids.add(+e.dataset.mid);
    rx.set(e.dataset.mid, new Set((e.dataset.rxs || "").split("|")));
  });
  return { ids, rx };
}
function chatfx(list, pv) {
  if (!pv.ids.size || RM.matches) return;
  const mx = Math.max(...pv.ids),
    fresh = [];
  list.querySelectorAll(".mrow[data-mid]").forEach((e) => {
    if (+e.dataset.mid > mx) fresh.push(e);
    else {
      const was = pv.rx.get(e.dataset.mid);
      if (was)
        e.querySelectorAll(".rx").forEach((c) => {
          if (!was.has(c.dataset.k)) c.classList.add("pop");
        });
    }
  });
  fresh.slice(-3).forEach((e) => e.classList.add("mnew"));
}
function chatx(o) {
  let rep = null,
    pi = 0;
  const rbar = h("div", { class: "rbar" }),
    pbar = h("div", { class: "pinbar" }),
    snip = (p) => ptx(p.t || p.txt) || (isAudN(p.img) ? "Audio" : +p.i || p.img ? "\u{1F4F7} Photo" : "");
  let rt = 0;
  const showRep = () => {
    clearTimeout(rt);
    rbar.classList.remove("out");
    if (!rep) {
      if (rbar.classList.contains("on") && !RM.matches) {
        rbar.classList.add("out");
        rt = setTimeout(() => {
          rbar.classList.remove("on", "out");
          rbar.replaceChildren();
        }, 200);
      } else {
        rbar.classList.remove("on");
        rbar.replaceChildren();
      }
      return;
    }
    rbar.replaceChildren();
    rbar.classList.add("on");
    rbar.append(
      ic("reply", 16),
      h(
        "div",
        { class: "rbt" },
        h("b", {}, "Replying to " + (+rep.mine ? "yourself" : o.who(rep))),
        h("span", {}, snip(rep)),
      ),
      h(
        "button",
        {
          type: "button",
          class: "ghost ibtn",
          "aria-label": "Cancel reply",
          title: "Cancel reply",
          onclick: () => {
            rep = null;
            showRep();
          },
        },
        ic("close", 16),
      ),
    );
  };
  let pt = 0;
  const paint = (pins) => {
    clearTimeout(pt);
    pbar.classList.remove("out");
    if (!pins.length) {
      pi = 0;
      if (pbar.classList.contains("on") && !RM.matches) {
        pbar.classList.add("out");
        pt = setTimeout(() => {
          pbar.classList.remove("on", "out");
          pbar.replaceChildren();
        }, 200);
      } else {
        pbar.classList.remove("on");
        pbar.replaceChildren();
      }
      return;
    }
    pbar.replaceChildren();
    pbar.classList.add("on");
    pi %= pins.length;
    const p = pins[pi];
    pbar.append(
      ic("pin", 14),
      h(
        "button",
        {
          type: "button",
          class: "pinb",
          "aria-label": "Go to pinned message",
          onclick: () => {
            o.jump(p.id);
            pi = (pi + 1) % pins.length;
            paint(pins);
          },
        },
        h("b", {}, "Pinned" + (pins.length > 1 ? " " + (pi + 1) + "/" + pins.length : "")),
        h("span", {}, snip(p)),
      ),
    );
  };
  const x = {
    other: () => o.who({ mine: 0 }),
    mnt: o.mnt,
    meAv: o.meAv,
    otherAv: o.otherAv,
    jump: (id) => o.jump(id),
    quick: (m, t) => o.qsend(t, m.id),
    reply: (m) => {
      rep = m;
      showRep();
      o.inp.focus();
    },
    react: async (m, e) => {
      try {
        const r = await api(o.rk, fd({ id: m.id, e }));
        const mine = (m.rx || []).find((z) => +z.me);
        if (mine && !RM.matches && !(r.rx || []).some((z) => z.e === mine.e)) {
          const c = document.querySelector('[data-mid="' + m.id + '"] .rx.on');
          if (c) {
            c.classList.add("out");
            await new Promise((f) => setTimeout(f, 170));
          }
        }
        o.patch(m.id, (mm) => {
          mm.rx = r.rx;
        });
      } catch (z) {
        alert(z.e || "Could not react.");
      }
    },
    pin: async (m) => {
      try {
        const r = await api(o.pk, fd({ id: m.id }));
        o.patch(m.id, (mm) => o.setPin(mm, +r.pin));
      } catch (z) {
        alert(z.e || "Could not change the pin.");
      }
    },
  };
  return {
    x,
    rbar,
    pbar,
    paint,
    rep: () => rep,
    clear: () => {
      rep = null;
      showRep();
    },
  };
}
/* collapse an element (fade, shrink, close the gap) and resolve when done */
function shrinkOut(el) {
  if (RM.matches) return Promise.resolve();
  el.style.height = el.offsetHeight + "px";
  el.style.overflow = "hidden";
  void el.offsetHeight;
  el.classList.add("mdel");
  return new Promise((r) => setTimeout(r, 240));
}
/* mark runs of messages from the same sender (within 5 min): _gs = starts a run, _ge = ends a run */
const crown = () => h("span", { class: "crown", title: "Group creator", "aria-hidden": "true" }, ic("crown", 14));
function grp(ms, g) {
  const same = (a, b) =>
    a && b && +a.mine === +b.mine && (!g || +a.mine || a.name === b.name) && Math.abs(+b.ts - +a.ts) < 300;
  ms.forEach((m, i) => {
    m._gs = !same(ms[i - 1], m);
    m._ge = !same(m, ms[i + 1]);
  });
}
function msg(m, last, reload, g, x) {
  x = x || {};
  const mine = +m.mine,
    rq = m.rq,
    quote = rq
      ? rq.gone
        ? h("div", { class: "rqw" }, h("div", { class: "rq gone" }, "Original message unavailable"))
        : h(
            "div",
            { class: "rqw" },
            h(
              "div",
              { class: "rqh" },
              ic("reply", 12),
              av(
                g ? { avatar: rq.av, mk: rq.mk } : +rq.mine ? (x.meAv ? x.meAv() : M) : x.otherAv ? x.otherAv() : {},
                18,
              ),
              h(
                "span",
                {},
                (() => {
                  const nm = mine ? "You" : g ? dn(m) : x.other ? x.other() : "",
                    tg = +rq.mine ? (mine ? "yourself" : "you") : rq.who || (x.other ? x.other() : "");
                  return nm + " replied to " + tg;
                })(),
              ),
            ),
            h(
              "button",
              {
                type: "button",
                class: "rq",
                "aria-label": "Go to the message being replied to",
                onclick: (e) => {
                  e.stopPropagation();
                  x.jump && x.jump(rq.id);
                },
              },
              rq.img && !isAudN(rq.img)
                ? h("img", { class: "rqi", src: "?img=" + rq.img, alt: "", loading: "lazy" })
                : null,
              rq.t
                ? h("span", {}, ptx(rq.t))
                : rq.img
                  ? isAudN(rq.img)
                    ? h("span", {}, "Audio")
                    : null
                  : h("span", {}, ""),
            ),
          )
      : null,
    stk = stkOf(m.txt),
    gi = stk || !XP() ? null : giOf(m.txt),
    body = h(
      "div",
      { class: "bub" + (mine ? " me" : "") + (stk ? " stkb" : "") + (gi ? " gib" : "") + (!stk && spk(m.txt) ? " spb" : "") },
      m.img && isAudN(m.img)
        ? h("audio", {
            class: "maud",
            controls: "",
            preload: "metadata",
            src: "?img=" + m.img,
            "aria-label": "Audio message",
          })
        : m.img
          ? h(
              "a",
              {
                href: "?img=" + m.img,
                target: "_blank",
                rel: "noopener",
                onclick: (e) => {
                  e.preventDefault();
                  view("?img=" + m.img, "Photo");
                },
              },
              h("img", {
                class: "mimg",
                src: "?img=" + m.img,
                alt: "Photo",
                loading: "lazy",
                onload: (e) => {
                  const l = e.target.closest(".mlist");
                  if (l && l.dataset.stick === "1") l.scrollTop = l.scrollHeight;
                },
              }),
            )
          : null,
      stk ? stkEl(stk) : gi ? giCard(gi, m, mine, x) : GIRE.test(m.txt || "") && !XP() ? h("span", { class: "hint" }, "\u{1F3AE} Game invite (turn on Experimental in Settings to see it)") : spk(m.txt) ? null : m.txt ? mentionText(m.txt, x.mnt) : null,
      !stk && !gi && m.txt ? (spk(m.txt) ? spCard(m.txt, x) : lpCard(m.txt)) : null,
      +m.ed ? h("small", { class: "edt" }, " (edited)") : null,
    );
  if (x.react) body.ondblclick = () => x.react(m, REACTS[0]);
  let rxT = 0,
    rxX = 0,
    rxY = 0,
    rxHeld = false;
  const showWho = () => rxWho(m, g, x);
  const rxs = (m.rx || []).length
    ? h(
        "div",
        { class: "rxs" },
        ...m.rx.map((r) =>
          h(
            "button",
            {
              type: "button",
              "data-k": r.e + r.n,
              class: "rx" + (+r.me ? " on" : ""),
              "aria-pressed": String(!!+r.me),
              "aria-label": r.e + " " + r.n,
              onclick: () => x.react && x.react(m, r.e),
              oncontextmenu: (e) => {
                e.preventDefault();
                showWho();
              },
              onpointerdown: (e) => {
                if (e.pointerType === "mouse" && e.button !== 0) return;
                rxHeld = false;
                rxX = e.clientX;
                rxY = e.clientY;
                clearTimeout(rxT);
                rxT = setTimeout(() => {
                  rxHeld = true;
                  if (navigator.vibrate)
                    try {
                      navigator.vibrate(12);
                    } catch (_) {}
                  showWho();
                }, 450);
              },
              onpointermove: (e) => {
                if (Math.abs(e.clientX - rxX) > 10 || Math.abs(e.clientY - rxY) > 10) clearTimeout(rxT);
              },
              onpointerup: () => clearTimeout(rxT),
              onpointercancel: () => clearTimeout(rxT),
              onpointerleave: () => clearTimeout(rxT),
              onclickcapture: (e) => {
                if (rxHeld) {
                  e.preventDefault();
                  e.stopPropagation();
                  rxHeld = false;
                }
              },
            },
            r.e,
            +r.n > 1 ? h("small", {}, r.n) : null,
          ),
        ),
      )
    : null;
  const who =
    g && !mine && m._gs !== false
      ? h(
          "button",
          {
            type: "button",
            class: "gwho",
            "aria-label": "View " + m.name + (+m.mk ? " (Masque)" : "") + (+m.co ? " (group creator)" : ""),
            onclick: () => (location.hash = (+m.mk ? "#/k/" : "#/u/") + m.name),
          },
          avw(av(m, 28), null, +m.mk),
          h("b", {}, dn(m)),
          +m.mk ? h("small", { class: "mkt" }, "Masque") : null,
          +m.co ? crown() : null,
        )
      : null;
  const w = h(
    "div",
    { class: "mrow" + (mine ? " me" : "") + (m._ge === false ? " gc" : "") },
    h(
      "div",
      { class: "mc" },
      who,
      quote,
      body,
      rxs,
      m._ge === false && !+m.pin
        ? null
        : h(
            "small",
            { class: "hint" },
            ago(m.ts) + (mine && last && +m.seen ? " \u00b7 Seen" : "") + (+m.pin ? " \u00b7 Pinned" : ""),
          ),
    ),
  );
  w.dataset.rxs = (m.rx || []).map((r) => r.e + r.n).join("|");
  /* options (reply, react, pin, copy, edit, delete) open when you hold a message (or right-click it), not as buttons under every bubble */
  const ops = {};
  if (stk) {
    ops.sref = stkRef(stk);
    SF.load();
  }
  if (!stk && m.img && !isAudN(m.img)) ops.simg = m.img;
  if (m.txt && !stk && !gi)
    ops.copy = () => {
      try {
        navigator.clipboard.writeText(m.txt);
      } catch (e) {}
    };
  if (mine && m.txt != null && !stk && !gi) {
    ops.edit = () => {
      const i = h("input", { value: m.txt, maxlength: 500, "aria-label": "Edit message" }),
        e2 = h("span", { class: "err" });
      const f2 = h(
        "form",
        {
          class: "cform",
          onsubmit: async (e) => {
            e.preventDefault();
            try {
              await api(g ? "gedit" : "editm", fd({ id: m.id, txt: i.value }));
              /* the chat will not redraw while an edit box is open, so close it first or the new text only shows after a refresh */
              f2.replaceWith(body);
              reload();
            } catch (x) {
              e2.textContent = x.e || "Could not save.";
            }
          },
        },
        i,
        h("button", { class: "btn", type: "submit" }, "Save"),
        h(
          "button",
          {
            class: "ghost",
            type: "button",
            onclick: () => {
              f2.replaceWith(body);
              reload();
            },
          },
          "Cancel",
        ),
        e2,
      );
      body.replaceWith(f2);
      i.focus();
    };
  }
  if (mine || (g && M.admin))
    ops.del = async () => {
      if (await cbox(mine ? "Delete this message?" : "Delete this message? You are deleting someone else\u2019s message as an admin. It is written to the admin log.")) {
        await api(g ? "gdel" : "delm", fd({ id: m.id }));
        await shrinkOut(w);
        reload();
      }
    };
  if ((m.rx || []).length) ops.who = showWho;
  const openMenu = () => msgSheet(m, x, ops),
    hs = [body, quote].filter(Boolean),
    on = (ev, fn, c) => hs.forEach((t) => t.addEventListener(ev, fn, c));
  let lt = 0,
    px = 0,
    py = 0,
    held = false;
  on("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    held = false;
    px = e.clientX;
    py = e.clientY;
    clearTimeout(lt);
    lt = setTimeout(() => {
      held = true;
      if (navigator.vibrate)
        try {
          navigator.vibrate(12);
        } catch (_) {}
      openMenu();
    }, 450);
  });
  on("pointermove", (e) => {
    if (Math.abs(e.clientX - px) > 10 || Math.abs(e.clientY - py) > 10) clearTimeout(lt);
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((ev) => on(ev, () => clearTimeout(lt)));
  on(
    "click",
    (e) => {
      if (held) {
        e.preventDefault();
        e.stopPropagation();
        held = false;
      }
    },
    true,
  );
  on("contextmenu", (e) => {
    e.preventDefault();
    clearTimeout(lt);
    openMenu();
  });
  /* swipe a message toward the middle of the screen to reply (touch only; long-press and scrolling still work) */
  if (x.reply) {
    const mc = w.querySelector(".mc"),
      sg = mine ? -1 : 1,
      MAX = 72,
      GO = 56,
      ind = h("span", { class: "swr", "aria-hidden": "true" }, ic("reply", 16));
    w.append(ind);
    let sx = 0,
      sy = 0,
      dx = 0,
      on = 0,
      tracking = 0,
      fired = 0,
      swiped = false;
    const reset = () => {
      if (!RM.matches) {
        mc.style.transition = "transform .22s cubic-bezier(.2,1,.3,1)";
        ind.style.transition = "opacity .2s,transform .2s";
      }
      mc.style.transform = "";
      ind.style.opacity = "";
      ind.style.transform = "";
      setTimeout(() => {
        mc.style.transition = "";
        ind.style.transition = "";
      }, 240);
    };
    mc.addEventListener("pointerdown", (e) => {
      if (e.pointerType === "mouse" || w.querySelector(".cform")) return;
      tracking = 1;
      on = 0;
      fired = 0;
      dx = 0;
      sx = e.clientX;
      sy = e.clientY;
    });
    mc.addEventListener("pointermove", (e) => {
      if (!tracking) return;
      const ax = (e.clientX - sx) * sg,
        ay = Math.abs(e.clientY - sy);
      if (!on) {
        if (ay > 10 && ay > ax) {
          tracking = 0;
          return;
        }
        if (ax > 12 && ax > ay * 1.5) {
          on = 1;
          clearTimeout(lt);
        } else return;
      }
      dx = Math.max(0, ax);
      const t = dx > MAX ? MAX + (dx - MAX) * 0.15 : dx,
        p = Math.min(1, t / GO);
      mc.style.transform = "translateX(" + t * sg + "px)";
      ind.style.opacity = String(p);
      ind.style.transform = "scale(" + (0.6 + 0.4 * p) + ")";
      if (dx >= GO && !fired) {
        fired = 1;
        if (navigator.vibrate)
          try {
            navigator.vibrate(10);
          } catch (_) {}
      } else if (dx < GO) fired = 0;
    });
    const end = (cancel) => {
      if (!tracking) return;
      tracking = 0;
      if (!on) return;
      on = 0;
      swiped = true;
      setTimeout(() => {
        swiped = false;
      }, 300);
      const go = !cancel && dx >= GO;
      reset();
      if (go) x.reply(m);
    };
    mc.addEventListener("pointerup", () => end(false));
    mc.addEventListener("pointercancel", () => end(true));
    mc.addEventListener(
      "click",
      (e) => {
        if (swiped) {
          e.preventDefault();
          e.stopPropagation();
        }
      },
      true,
    );
  }
  return w;
}
/* notifications */
/* ===== Gift opening: tapping a gift notification shows a wrapped box, then reveals each item with a preview of how it looks ===== */
function giftPrev(k, id) {
  const bg = M.tbg || "sunset",
    post = (txt) => h("div", { class: "tpost" }, h("div", { class: "tn" }, h("i"), dn(M)), h("p", {}, txt));
  let e;
  if (k === "tas" || k === "taf") {
    e = h("div", { class: "apv" }, h("div", { class: "pavw" }, av({ src: M.avatar ? "?img=" + M.avatar : "" }, 96), batFlock("o")));
    const sh = k === "tas" ? id : M.tas || "",
      fr = k === "taf" ? id : M.taf || "";
    sh ? (e.dataset.pas = sh) : 0;
    fr ? (e.dataset.paf = fr) : 0;
  } else if (k === "tcf") {
    e = h("div", { class: "cover plain", style: "height:110px" }, batFlock("f"));
    const f = bfx(id, M.taf || "");
    f ? (e.dataset.cf = f) : 0;
  } else {
    e = h("div", { class: "tprev" }, post(k === "tfn" ? "Aa Bb Cc, this is your new font." : k === "tcd" ? "Your posts, in a new card style." : "Your profile, with something new."));
    const d = { pbg: k === "tbg" ? id : k === "tbp" || k === "tcd" ? bg : M.tbg || "", pbp: k === "tbp" ? id : M.tbp || "", pcd: k === "tcd" ? id : M.tcd || "", pfn: k === "tfn" ? id : M.tfn || "" };
    for (const x in d) d[x] ? (e.dataset[x] = d[x]) : 0;
  }
  e.setAttribute("aria-hidden", "true");
  return e;
}
const WHERE = { tbg: "Edit profile \u203a Theme", tbp: "Edit profile \u203a Theme", tcd: "Edit profile \u203a Theme", tfn: "Edit profile \u203a Theme", tas: "Edit profile \u203a Avatar style", taf: "Edit profile \u203a Avatar style", tcf: "Edit banner \u203a Banner style" };
async function openGift(gid, after) {
  let g;
  try {
    g = await api("gift", null, "&id=" + encodeURIComponent(gid));
  } catch (x) {
    alert((x && x.e) || "Could not open the gift.");
    return;
  }
  if (!g.items.length) return;
  const reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches,
    ov = h("div", { class: "gftv", role: "dialog", "aria-modal": "true", "aria-label": "Your gift" }),
    stage = h("div", { class: "gfts" }),
    done = () => {
      document.removeEventListener("keydown", onk);
      ov.classList.add("out");
      setTimeout(() => ov.remove(), 260);
      if (after) after();
    },
    onk = (e) => e.key === "Escape" && done(),
    lab = (k, id) => ((GL()[k] || []).find((a) => a[0] === id) || [0, id])[1];
  document.addEventListener("keydown", onk);
  const x = h("button", { type: "button", class: "gftx", "aria-label": "Close", onclick: done }, ic("close", 20));
  ov.append(x, stage);
  document.body.append(ov);
  const confetti = () => {
    if (reduce) return;
    const c = h("div", { class: "gcf", "aria-hidden": "true" }),
      cols = ["var(--ink)", "var(--sigil)", "var(--edge)", "var(--ember)", "var(--card)", "var(--line)"];
    for (let i = 0; i < 40; i++) {
      const a = Math.random() * Math.PI * 2,
        r = 80 + Math.random() * 180,
        p = h("i", { class: i % 3 === 0 ? "dm" : "" });
      p.style.cssText = `--dx:${Math.cos(a) * r}px;--dy:${Math.sin(a) * r - 60}px;--r:${Math.random() * 720 - 360}deg;--c:${cols[i % cols.length]};--d:${(Math.random() * 0.18).toFixed(2)}s;--w:${7 + Math.random() * 5}px`;
      c.append(p);
    }
    stage.append(c);
    setTimeout(() => c.remove(), 1800);
  };
  let n = 0;
  const reveal = () => {
    const [k, id] = g.items[n],
      last = n === g.items.length - 1,
      wear = h("button", { type: "button", class: "ghost" }, "Wear it now"),
      card = h(
        "div",
        { class: "gfc" },
        h("p", { class: "gfk" }, g.items.length > 1 ? "Item " + (n + 1) + " of " + g.items.length : "Your gift"),
        giftPrev(k, id),
        h("h2", {}, lab(k, id)),
        h("p", { class: "hint" }, GIVEN[k]),
        last ? h("p", { class: "hint gfwh" }, "Saved to your profile themes. Find it in " + WHERE[k] + " any time, or tap this gift in Notifications to see it again.") : null,
        h(
          "div",
          { class: "gfb" },
          wear,
          h("button", { type: "button", class: "btn", onclick: last ? done : () => { n++; reveal(); } }, last ? "Done" : "Next"),
        ),
      );
    wear.onclick = async () => {
      wear.disabled = true;
      try {
        M = (await api("profile", fd({ [k]: id }))).me;
        wear.textContent = "\u2713 Wearing it";
      } catch (e) {
        wear.textContent = (e && e.e) || "Could not equip";
        wear.disabled = false;
      }
    };
    stage.replaceChildren(card);
    if (g.msg) card.append(h("p", { class: "gfm" }, "\u201c" + g.msg + "\u201d"));
    if (n > 0) confetti();
  };
  /* the wrapped box: first time only (and on "Watch it open again") */
  const intro = () => {
    ov.classList.remove("rev");
    n = 0;
  const lid = h("div", { class: "gbl" }, h("i", { class: "bw l" }), h("i", { class: "bw r" })),
      box = h(
        "button",
        { type: "button", class: "gbox", "aria-label": "Open your gift" },
        h("i", { class: "rp" }),
        h("i", { class: "rp b" }),
        h("div", { class: "gbb" }, h("i", { class: "rib" })),
        h("div", { class: "seal" }, ic("mask", 22)),
        lid,
      );
    let opened = false;
    box.onclick = () => {
      if (opened) return;
      opened = true;
      box.classList.add("open");
      confetti();
      api("gopen", fd({ id: gid })).catch(() => {});
      setTimeout(reveal, reduce ? 0 : 950);
    };
    stage.append(
      h("p", { class: "gft" }, g.items.length > 1 ? "You got a gift with " + g.items.length + " things inside" : "You got a gift"),
      box,
      h("p", { class: "hint gfh" }, "Tap to open"),
    );
    box.focus();
  };
  /* opened before: no box, just everything that was in it, with a preview of each, where to find it, and wear buttons */
  const review = () => {
    ov.classList.add("rev");
    const worn = (k, id) => (M[k] || "") === id,
      paints = [],
      repaint = () => paints.forEach((f) => f()),
      rows = g.items.map(([k, id]) => {
        const b = h("button", { type: "button", class: "ghost gfwb" }),
          paint = () => {
            const on = worn(k, id);
            b.textContent = on ? "\u2713 Wearing it" : "Wear it";
            b.disabled = on;
          };
        paints.push(paint);
        paint();
        b.onclick = async () => {
          b.disabled = true;
          try {
            M = (await api("profile", fd({ [k]: id }))).me;
            repaint();
          } catch (e) {
            b.textContent = (e && e.e) || "Could not equip";
            setTimeout(paint, 2200);
          }
        };
        return h("div", { class: "gfc gfr" }, giftPrev(k, id), h("div", { class: "gfrh" }, h("div", { class: "gfrn" }, h("h3", {}, lab(k, id)), h("small", { class: "hint" }, GIVEN[k])), b));
      }),
      ks = g.items.map((z) => z[0]),
      places = [...new Set(ks.map((k) => WHERE[k]))],
      onlyBanner = ks.every((k) => k === "tcf"),
      all = h("button", { type: "button", class: "ghost" }, "Wear everything"),
      edit = h("button", { type: "button", class: "btn" }, onlyBanner ? "Open Edit banner" : "Open Edit profile");
    all.onclick = async () => {
      all.disabled = true;
      try {
        const o = {};
        g.items.forEach(([k, id]) => (o[k] = id));
        M = (await api("profile", fd(o))).me;
        repaint();
        all.textContent = "\u2713 Wearing all of it";
      } catch (e) {
        all.textContent = (e && e.e) || "Could not equip";
        all.disabled = false;
      }
    };
    edit.onclick = () => {
      done();
      setTimeout(() => editProfile(M, onlyBanner ? "cover" : undefined), 300);
    };
    const again = h("button", { type: "button", class: "ghost gfagain" }, ic("gift", 16), "Watch it open again");
    again.onclick = () => {
      stage.replaceChildren();
      intro();
    };
    stage.replaceChildren(
      ...[
        h("div", { class: "gfhd" }, h("p", { class: "gft sm" }, "Your gift"), h("p", { class: "hint gfsub" }, g.items.length === 1 ? "1 thing from this gift" : g.items.length + " things from this gift")),
        g.msg ? h("p", { class: "gfq" }, "\u201c" + g.msg + "\u201d") : null,
        ...rows,
        h("div", { class: "gfn" }, ic("gift", 18), h("p", {}, "These are saved to your profile themes and are yours to keep. Find them in " + places.join(" and ") + " whenever you like.")),
        h("div", { class: "gfact" }, ...[edit, g.items.length > 1 && new Set(ks).size === ks.length ? all : null, again].filter(Boolean)),
      ].filter(Boolean),
    );
    repaint();
  };
  if (+g.opened) review();
  else intro();
}
async function notifs() {
  const { list } = await api("notifs"),
    PV = NPREV,
    live = !!PV && SHOWN === location.hash,
    _np = ((NPREV = new Set(list.map((n) => n.id))), 0),
    T2 = {
      comment: " commented on your post",
      like: " marked your post with a sigil",
      clike: " marked your comment with a sigil",
      reply: " replied to your comment",
      freq: " sent you a friend request",
      mention: " mentioned you",
      gment: " mentioned you in a group",
      gall: " mentioned everyone in a group",
      tag: " posted with a tag you follow",
      facc: " accepted your friend request",
      follow: " started following you",
      ask: " sent you an anonymous question",
      answer: " answered your question",
      reveal: " told you their Masque is them",
      rview: " was reviewed by the team. Thank you for helping keep Masque safe.",
      gift: " got a gift",
    };
  /* many likes or comments on the same thing become one row: "Ana, Ben and 3 others marked your post with a sigil" */
  const GK = new Set(["like", "clike", "comment", "reply", "follow"]),
    groups = [],
    byKey = new Map();
  for (const n of list) {
    const k = GK.has(n.kind) ? n.kind + "|" + (n.kind === "follow" ? 0 : n.pid) : "";
    let g = k && byKey.get(k);
    if (!g) {
      g = { n, all: [n] };
      groups.push(g);
      if (k) byKey.set(k, g);
    } else g.all.push(n);
  }
  const whoText = (g) => {
    const seenW = new Set(),
      names = [];
    for (const x of g.all) {
      const w = dn(x);
      if (!seenW.has(w)) {
        seenW.add(w);
        names.push(w);
      }
    }
    if (names.length === 1) return names[0];
    if (names.length === 2) return names[0] + " and " + names[1];
    return names[0] + ", " + names[1] + " and " + (names.length - 2) + (names.length - 2 === 1 ? " other" : " others");
  };
  const go = (n) =>
    (location.hash =
      n.kind === "gment" || n.kind === "gall"
        ? "#/g/" + n.pid
        : n.kind === "ask"
        ? ((ASKOPEN = true), "#/u/" + M.name)
        : n.kind === "freq"
          ? "#/f"
          : n.kind === "facc" || n.kind === "follow"
            ? "#/u/" + n.name
            : n.kind === "rview"
              ? location.hash
              : n.kind === "gift"
                ? (openGift(n.pid, () => route()), location.hash)
              : n.kind === "reveal"
                ? "#/k/" + n.cap
                : n.pid
                  ? "#/p/" + n.pid
                  : "#/u/" + M.name);
  /* friend requests still waiting for an answer get Accept / Decline right on the row */
  let pend = new Set();
  try {
    pend = new Set((await api("friends")).list.filter((x) => !+x.st && !+x.mine).map((x) => String(x.name).toLowerCase()));
  } catch (e) {}
  const NI = { comment: "comment", reply: "comment", like: "check", clike: "check", freq: "users", facc: "users", follow: "users", mention: "chat", gment: "chat", gall: "users", tag: "chat", ask: "bell", answer: "bell", reveal: "mask", gift: "gift", rview: "bell" };
  const d0 = new Date();
  d0.setHours(0, 0, 0, 0);
  const today0 = d0.getTime() / 1000;
  let lastSec = "";
  const rowsOut = [];
  for (const g of groups) {
    const n = g.n,
      sec = +n.ts >= today0 ? "Today" : "Earlier",
      anyNew = g.all.some((x) => !+x.seen),
      anyLive = live && g.all.some((x) => !PV.has(x.id)),
      canAct = n.kind === "freq" && pend.has(String(n.name).toLowerCase());
    if (sec !== lastSec) {
      rowsOut.push(h("h3", { class: "vt nsec fsh" }, h("span", {}, sec), h("i", { class: "fcn" }, String(groups.filter((z) => (+z.n.ts >= today0 ? "Today" : "Earlier") === sec).length))));
      lastSec = sec;
    }
    const lead =
        n.kind === "gift"
          ? h("div", { class: "gifti" + (+n.opened ? "" : " un"), "aria-hidden": "true" }, ic("gift", 22))
          : h("span", { class: "nav" }, av(n.kind === "ask" || n.kind === "rview" ? {} : n, 44), h("i", { class: "nti", "aria-hidden": "true" }, ic(NI[n.kind] || "bell", 11))),
      body = [
        lead,
        h(
          "div",
          { class: "cx" },
          h("span", {}, h("b", {}, n.kind === "ask" ? "Someone" : n.kind === "rview" ? "A report you sent" : n.kind === "gift" ? "You" : whoText(g)), T2[n.kind] || " did something"),
          n.kind === "gift"
            ? h("span", { class: "hint" }, +n.opened ? "Opened \u00b7 " + n.cnt + (+n.cnt === 1 ? " item" : " items") + ". Tap to see " + (+n.cnt === 1 ? "it" : "them") + " again." : n.cnt + (+n.cnt === 1 ? " item" : " items") + " inside. Tap to open.")
            : n.cap
              ? h("span", { class: "hint" }, n.cap)
              : null,
        ),
        h("small", { class: "hint" }, ago(n.ts)),
      ],
      cls = "chat nk-" + n.kind + (anyNew ? " new" : "") + (anyLive ? " rnew" : "");
    if (canAct) {
      rowsOut.push(
        h(
          "div",
          { class: cls + " nreq" },
          h("button", { type: "button", class: "nmain", onclick: () => go(n) }, ...body),
          h("div", { class: "nact" }, h("button", { type: "button", class: "btn", onclick: fcall("facc", n.name) }, "Accept"), h("button", { type: "button", class: "ghost", onclick: fcall("frem", n.name) }, "Decline")),
        ),
      );
    } else rowsOut.push(h("button", { class: cls, onclick: () => go(n) }, ...body));
  }
  shell([big("Notifications"), list.length ? rowsOut : emp("bell", "All caught up", "Likes, comments and friend requests will show up here.")]);
}
/* anonymous questions: visitors send a nameless question, the owner picks which to answer; an answer becomes a normal post with the question shown above it */
let ASKOPEN = false;
/* on someone's profile: one slim button; the question form opens in a sheet so it doesn't push the posts down */
function askBox(u) {
  if (u.name.toLowerCase() === M.name.toLowerCase() || !+u.askon || +u.locked || +u.blocked) return null;
  return h(
    "button",
    {
      type: "button",
      class: "ghost askbtn",
      onclick: () => sheet(u.askp || "Ask anonymously", () => askForm(u)),
    },
    ic("chat", 16),
    h("span", {}, u.askp || "Ask anonymously"),
  );
}
function askForm(u) {
  const t = h("textarea", {
      rows: 3,
      maxlength: 200,
      placeholder: "Ask " + dn(u) + " anything, anonymously",
      "aria-label": "Your question",
    }),
    cnt = h("small", { class: "hint cnt" }, "0 / 200"),
    st = h("p", { class: "hint", role: "status" }),
    b = h("button", { class: "btn", type: "submit" }, "Send");
  t.oninput = () => {
    cnt.textContent = t.value.length + " / 200";
  };
  return h(
    "form",
    {
      class: "askbox askf",
      onsubmit: async (e) => {
        e.preventDefault();
        if (!t.value.trim()) return;
        b.disabled = true;
        st.className = "hint";
        st.textContent = "";
        try {
          await api("ask", fd({ to: u.name, txt: t.value }));
          t.value = "";
          cnt.textContent = "0 / 200";
          st.textContent = "Sent.";
        } catch (x) {
          st.className = "err";
          st.textContent = x.e || "Could not send.";
        }
        b.disabled = false;
      },
    },
    t,
    h("div", { class: "askrow" }, cnt, b),
    st,
    h("p", { class: "hint" }, "Your name stays hidden. If a question is reported, site admins can see who sent it."),
  );
}
function askInbox() {
  sheet("Inbox", (close) => {
    const box = h("div", { class: "asklist" });
    let L = [];
    const paint = () =>
      rc(
        box,
        L.length
          ? L.map(row)
          : h(
              "p",
              { class: "hint" },
              +M.askon
                ? "No questions yet. Share your profile link and they will show up here."
                : "Anonymous questions are off. You can turn them on in Settings.",
            ),
      );
    const drop = (id) => {
      L = L.filter((x) => x.id !== id);
      paint();
    };
    function row(q) {
      const ans = h("textarea", {
          rows: 3,
          maxlength: 300,
          placeholder: "Your answer, shown on your profile",
          "aria-label": "Your answer",
        }),
        err = h("p", { class: "err", role: "alert" }),
        go = h("button", { class: "btn", type: "button" }, "Post answer");
      let file = null;
      const pick = h("input", { type: "file", accept: "image/*", hidden: "", "aria-label": "Attach photo" }),
        att = h(
          "button",
          { type: "button", class: "ghost", onclick: () => pick.click() },
          ic("camera", 16),
          "Add photo",
        ),
        chip = h("button", {
          type: "button",
          class: "ghost",
          hidden: "",
          onclick: () => {
            file = null;
            pick.value = "";
            chip.hidden = true;
          },
        });
      pick.onchange = () => {
        const x = pick.files[0];
        if (!x) return;
        if (x.size > IMGMAX) {
          err.textContent = "Image must be under " + IMGMB + " MB.";
          pick.value = "";
          return;
        }
        err.textContent = "";
        file = x;
        chip.textContent = "Remove photo: " + x.name;
        chip.hidden = false;
      };
      const form = h("div", { class: "askans", hidden: "" }, ans, h("div", { class: "row" }, pick, att, chip), err, go);
      go.onclick = async () => {
        if (!ans.value.trim()) {
          err.textContent = "Write an answer first.";
          return;
        }
        go.disabled = true;
        err.textContent = "";
        try {
          const d = fd({ id: q.id, cap: ans.value });
          if (file) d.append("img", await shrink(file));
          await api("askans", d);
          close();
          route();
        } catch (x) {
          err.textContent = x.e || "Could not post.";
          go.disabled = false;
        }
      };
      return h(
        "div",
        { class: "askq" },
        h("div", { class: "askhd" }, h("span", {}, ic("mask", 14), "Anonymous"), h("small", { class: "hint" }, ago(q.ts))),
        h("p", { class: "qt" }, q.txt),
        form,
        h(
          "div",
          { class: "row" },
          h(
            "button",
            {
              class: "btn askgo",
              type: "button",
              onclick: () => {
                form.hidden = !form.hidden;
                if (!form.hidden) ans.focus();
              },
            },
            "Answer",
          ),
          h(
            "button",
            {
              class: "ghost askdel",
              type: "button",
              onclick: async () => {
                try {
                  await api("askdel", fd({ id: q.id }));
                  drop(q.id);
                } catch (x) {
                  alert(x.e || "Could not delete.");
                }
              },
            },
            "Delete",
          ),
          h(
            "button",
            { class: "ghost askrep", type: "button", onclick: () => reportSheet("ask", q.id, () => drop(q.id)) },
            "Report",
          ),
        ),
      );
    }
    rc(box, h("div", { class: "skel", "aria-hidden": "true" }, skRow(), skRow()));
    api("asks")
      .then((r) => {
        L = r.list;
        paint();
      })
      .catch((x) => rc(box, h("p", { class: "err" }, (x && x.e) || "Could not load questions.")));
    return h(
      "div",
      {},
      h(
        "p",
        { class: "hint askhint" },
        "Nobody knows who asked. Answer one and it becomes a public post on your profile, with the question above it.",
      ),
      box,
    );
  });
}
/* masks: one extra persona per account, with its own name, photo and bio. Posts and comments made as the mask carry only the mask's identity. */
let ASM = false;
/* picture at the left of a comment box: your profile by default, hold it to switch to your mask (hold again to go back). It stays on that persona until you switch. Keyboard: Enter or Space toggles. On your own mask's posts it is locked to the mask, which is what the server does anyway. */
const SWS = new Set();
/* the open chat (DM or group) registers itself here so holding the nav Profile button also switches who you write as inside it */
let CHATAS = null;
/* set when you switch who you write as; the next chat message asks "Send as ...?" once, so a message never goes out as the wrong persona by accident */
let ASKAS = 0;
async function asOk(mask) {
  if (!ASKAS || !M.mask) return true;
  const nm = mask ? M.mask.name : dn(M);
  const ok = await cbox("Send as " + nm + "? You just switched who you write as. This message goes out as " + nm + ".");
  if (ok) ASKAS = 0;
  return ok;
}
function flipPersona(b, nav) {
  ASM = !ASM;
  ASKAS = 1;
  if (CHATAS && CHATAS.el.isConnected && M.mask) CHATAS.fn(ASM);
  SWS.forEach((f) => {
    if (f.b.isConnected) f.paint();
    else SWS.delete(f);
  });
  b.classList.remove("pop");
  void b.offsetWidth;
  b.classList.add("pop");
  maskBar();
  NAVME.forEach((f) => {
    if (f.b.isConnected) f.paint();
    else NAVME.delete(f);
  });
  maskReveal();
  if (INSET && INSET.tb.isConnected && M.mask) INSET(ASM ? "k" : "m");
  if (navigator.vibrate)
    try {
      navigator.vibrate(12);
    } catch (_) {}
  /* switching from the nav button while one of your own profiles is open: go straight to the other one, no second tap needed */
  if (nav && M.mask) {
    const hm = location.hash.match(/^#\/([uk])\/(\w+)/);
    if (
      hm &&
      ((hm[1] === "u" && hm[2].toLowerCase() === M.name.toLowerCase()) ||
        (hm[1] === "k" && hm[2].toLowerCase() === M.mask.name.toLowerCase()))
    )
      location.hash = ASM ? "#/k/" + M.mask.name : "#/u/" + M.name;
  }
}
/* In mask mode the nav Profile button turns into your mask (its picture and name) and opens the mask profile. */
const NAVME = new Set();
function navMe(b) {
  const paint = () => {
    const m = !!(ASM && M.mask),
      old = b.querySelector(".av");
    if (old) old.replaceWith(av(m ? { avatar: M.mask.avatar } : M, parseInt(old.style.width) || 26));
    const l = b.querySelector(".nl");
    if (l) l.textContent = m ? M.mask.name : "Profile";
    b.setAttribute("aria-label", m ? M.mask.name + " (your Masque)" : "Profile");
  };
  b.onclick = () => (location.hash = ASM && M.mask ? "#/k/" + M.mask.name : "#/u/" + M.name);
  NAVME.add({ b, paint });
  paint();
}
/* when you switch, the profile you are switching to pops up in the middle of the screen for a moment */
function maskReveal() {
  if (matchMedia("(prefers-reduced-motion:reduce)").matches) return;
  const m = !!(ASM && M && M.mask);
  document.getElementById("mqrev")?.remove();
  const r = h(
    "div",
    { id: "mqrev", class: "mqrev", "aria-hidden": "true" },
    h("div", { class: "mqring" }, av(m ? { avatar: M.mask.avatar } : M, 112)),
    h("b", {}, m ? M.mask.name : dn(M)),
    h("small", {}, m ? "Masque mode" : "Back to you"),
  );
  document.body.append(r);
  setTimeout(() => r.remove(), 1700);
}
/* "Masque mode" pill at the top while you act as your mask. It slides in and out, and <html> gets class "mm" so the rest of the app can restyle itself. */
function maskBar() {
  const on = !!(ASM && M && M.mask);
  document.documentElement.classList.toggle("mm", on);
  let b = document.getElementById("mqbar");
  if (on) {
    if (!b) {
      b = h(
        "div",
        { id: "mqbar", class: "mqbar", role: "status" },
        h("span", { class: "mqlm", "aria-hidden": "true" }, lmIcon(20)),
        h("b", {}, "Masque mode"),
        h("span", {}),
      );
      document.body.append(b);
      void b.offsetWidth;
    }
    b.lastChild.textContent = "as " + M.mask.name;
    b.classList.remove("out");
    b.classList.add("in");
  } else if (b) {
    b.classList.remove("in");
    b.classList.add("out");
    setTimeout(() => {
      if (!ASM && b.isConnected) b.remove();
    }, 500);
  }
}
/* the Profile button in the nav (phone dock and desktop side rail): tap goes to your profile, hold switches between you and your mask */
function navHold(b) {
  const has = !!M.mask;
  if (has) {
    b.classList.add("hv");
    b.title = "Hold to switch between you and " + M.mask.name;
  } else b.title = "Hold to create your Masque";
  let t = 0,
    fired = false;
  const stop = () => clearTimeout(t);
  b.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button) return;
    fired = false;
    stop();
    t = setTimeout(() => {
      fired = true;
      if (M.mask) flipPersona(b, true);
      else {
        if (navigator.vibrate)
          try {
            navigator.vibrate(12);
          } catch (_) {}
        maskSheet(() => route());
      }
    }, 380);
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((n) => b.addEventListener(n, stop));
  b.addEventListener("contextmenu", (e) => e.preventDefault());
  b.addEventListener(
    "click",
    (e) => {
      if (fired) {
        fired = false;
        e.stopImmediatePropagation();
        e.preventDefault();
      }
    },
    true,
  );
}
/* like buttons (posts and comments) act as whichever persona is active, like the comment box. Hold one to switch between you and your mask; it gets a dashed ring while it acts as the mask, and the alert the other person gets shows the mask's name. */
function likeSw(b) {
  if (!M.mask) return;
  let t = 0,
    fired = false;
  const base = b.getAttribute("aria-label") || "",
    stop = () => clearTimeout(t),
    paint = () => {
      b.classList.toggle("asm", ASM);
      const l = base + (ASM ? " as " + M.mask.name : "") + ". Hold to switch between you and your Masque";
      b.setAttribute("aria-label", l);
      b.title = l;
    };
  b.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button) return;
    fired = false;
    stop();
    t = setTimeout(() => {
      fired = true;
      flipPersona(b);
    }, 380);
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((n) => b.addEventListener(n, stop));
  b.addEventListener("contextmenu", (e) => e.preventDefault());
  b.addEventListener(
    "click",
    (e) => {
      if (fired) {
        fired = false;
        e.stopImmediatePropagation();
        e.preventDefault();
      }
    },
    true,
  );
  SWS.add({ b, paint });
  paint();
}
function maskSw(p, inp, verb) {
  if (!M.mask) return null;
  const nm = M.mask.name,
    lock = !!(+p.mk && +p.own),
    base = inp.placeholder,
    b = h("button", { type: "button", class: "cswh" }),
    mine = av(M, 34),
    msk = av({ avatar: M.mask.avatar }, 34);
  let t = 0,
    fired = false,
    tip = 0;
  const on = () => lock || ASM,
    paint = () => {
      b.replaceChildren(on() ? avw(msk, null, 1) : mine);
      b.classList.toggle("on", on());
      b.setAttribute("aria-pressed", String(on()));
      const l = lock
        ? verb + "ing as " + nm + " (replies on your Masque's posts always come from it)"
        : (on() ? verb + "ing as " + nm : verb + "ing as you") + ". Hold to switch to " + (on() ? "you" : nm);
      b.setAttribute("aria-label", l);
      b.title = l;
      inp.placeholder = on() ? verb + " as " + nm + "\u2026" : base;
    };
  const toggle = () => {
    if (!lock) flipPersona(b);
  };
  const stop = () => clearTimeout(t);
  b.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button) return;
    fired = false;
    stop();
    t = setTimeout(() => {
      fired = true;
      toggle();
    }, 380);
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((n) => b.addEventListener(n, stop));
  b.addEventListener("contextmenu", (e) => e.preventDefault());
  b.addEventListener("click", (e) => {
    if (fired) {
      fired = false;
      return;
    }
    if (e.detail === 0 && !lock) {
      toggle();
      return;
    }
    clearTimeout(tip);
    inp.placeholder = lock
      ? "Always your Masque on its own posts"
      : "Hold your picture to switch to " + (on() ? "you" : nm);
    tip = setTimeout(paint, 2200);
  });
  SWS.add({ b, paint });
  paint();
  return b;
}
function maskSheet(onDone) {
  const k = M.mask;
  sheet(k ? "Edit Masque" : "Create your Masque", (close, veil) => {
    const fb = (n) => av({ src: "" }, n);
    if (!k) {
      /* new Masque: picture, name and bio in one card */
      let avF = null;
      const pav = h("div"),
        set = (u) => pav.replaceChildren(av({ src: u }, 88));
      set("");
      const nm = h("input", {
          placeholder: "3 to 20 letters, numbers or _",
          maxlength: 20,
          autocomplete: "off",
          autocapitalize: "none",
          "aria-label": "Masque name",
        }),
        [bio, bioL] = bioBox("", "Tell people a little about this Masque (optional)", "Bio");
      const f = pform(
        "Your Masque",
        "A second name and picture for posting and commenting. Other people are not shown that it belongs to you.",
        async () => {
          const d = new FormData();
          d.append("name", nm.value.trim());
          d.append("bio", bio.value);
          if (avF) d.append("avatar", await avF);
          M.mask = (await api("maskset", d)).mask;
          close();
          if (onDone) setTimeout(onDone, 0);
        },
        h(
          "div",
          { class: "picrow" },
          pav,
          h(
            "div",
            { class: "picact" },
            drop(
              "Masque photo",
              (file) => {
                if (pbig(file, f.say)) {
                  avF = pprep(file, 800, f.say);
                  set(URL.createObjectURL(file));
                  f.touch();
                }
              },
              "Change photo",
            ),
            h(
              "button",
              {
                type: "button",
                class: "ghost rm",
                onclick: () => {
                  avF = null;
                  set("");
                  f.touch();
                },
              },
              "Remove photo",
            ),
          ),
        ),
        h(
          "label",
          { class: "f" },
          "Masque name",
          h("div", { class: "atw" }, nm),
          h("span", { class: "hint" }, "Pick a name that is nothing like yours. It can't be changed later."),
        ),
        bioL,
      );
      f.querySelector(".btn").textContent = "Create Masque";
      f.touch();
      return h("div", { class: "pforms" }, f);
    }
    const fa = picForm(
      "Masque picture",
      "Shown on your Masque's page, posts, comments and chats.",
      k.avatar ? "?img=" + k.avatar : "",
      fb,
      async (avF, rm) => {
        const d = new FormData();
        d.append("bio", M.mask.bio || "");
        if (avF) d.append("avatar", await avF);
        else d.append("noavatar", "1");
        M.mask = (await api("maskset", d)).mask;
      },
    );
    const [bio, bioL] = bioBox(k.bio, "Tell people a little about this Masque", "Bio");
    const fd3 = pform(
      "Masque details",
      null,
      async () => {
        const d = new FormData();
        d.append("bio", bio.value);
        M.mask = (await api("maskset", d)).mask;
      },
      bioL,
      h(
        "label",
        { class: "f" },
        "Masque name",
        h("div", { class: "atw" }, h("input", { value: k.name, disabled: "", "aria-label": "Masque name" })),
        h(
          "span",
          { class: "hint" },
          "The name can't be changed. To get a different name, delete this Masque and make a new one.",
        ),
      ),
    );
    fd3.addEventListener("input", () => fd3.touch());
    const er = h("p", { class: "hint", role: "alert" }),
      del = h(
        "div",
        { class: "pform" },
        h("h3", {}, "Delete Masque"),
        h(
          "p",
          { class: "sub" },
          "Its posts, comments and photos are deleted for good, and the name can never be used again.",
        ),
        er,
        h(
          "button",
          {
            type: "button",
            class: "ghost rm",
            onclick: async () => {
              if (
                !(await cbox(
                  "Delete your Masque? Its posts, comments and photos are deleted for good, and the name can never be used again.",
                ))
              )
                return;
              try {
                await api("maskdel", fd({}));
                M.mask = null;
                close();
                route();
              } catch (x) {
                er.className = "err";
                er.textContent = (x && x.e) || "Could not delete.";
              }
            },
          },
          "Delete Masque",
        ),
      );
    const delAcc = h("details", { class: "pacc" }, h("summary", {}, h("span", {}, "Delete Masque")), del);
    return pagg(close, veil, [["Masque details", fd3, true], ["Masque picture", fa], delAcc]);
  });
}
function revealSheet(k) {
  sheet("Tell a friend", (close) => {
    const box = h("div", { class: "gpick" }, h("p", { class: "hint" }, "Loading friends\u2026")),
      on = new Set((k.rv || []).map((x) => x.name));
    const draw = (fr) =>
      box.replaceChildren(
        ...(fr.length
          ? fr.map((u) => {
              const b = h(
                "button",
                { type: "button", class: "chat gp", "aria-pressed": String(on.has(u.name)) },
                av(u, 36),
                h(
                  "div",
                  { class: "cx" },
                  h("b", {}, dn(u)),
                  h(
                    "small",
                    { class: "hint" },
                    on.has(u.name) ? "Knows it's you. Tap to hide your name from this Masque's page." : "",
                  ),
                ),
                h("span", { class: "gtick" }, ic("check", 16)),
              );
              b.onclick = async () => {
                const was = on.has(u.name);
                try {
                  if (was) {
                    if (
                      !(await cbox(
                        "Stop showing your name on this Masque's page for @" +
                          u.name +
                          "? They will still remember what you told them.",
                      ))
                    )
                      return;
                    await api("mreveal", fd({ to: u.name, on: 0 }));
                    on.delete(u.name);
                  } else {
                    if (
                      !(await cbox(
                        "Tell @" +
                          u.name +
                          " that " +
                          k.name +
                          " is you? They get a notification and can't un-know it later.",
                      ))
                    )
                      return;
                    await api("mreveal", fd({ to: u.name, on: 1 }));
                    on.add(u.name);
                  }
                  b.setAttribute("aria-pressed", String(!was));
                  b.querySelector("small").textContent = !was
                    ? "Knows it's you. Tap to hide your name from this Masque's page."
                    : "";
                } catch (x) {
                  alert(x.e || "Could not do that.");
                }
              };
              return b;
            })
          : [h("p", { class: "hint" }, "You have no accepted friends to tell yet.")]),
      );
    api("friends")
      .then(({ list }) => draw(list.filter((x) => +x.st)))
      .catch(() => box.replaceChildren(h("p", { class: "hint" }, "Couldn\u2019t load your friends.")));
    return h(
      "div",
      { class: "form" },
      h(
        "p",
        { class: "hint" },
        "Only accepted friends. Nobody else is told, and the Masque stays anonymous to everyone else.",
      ),
      box,
    );
  });
}
function mkTabs(name, pr) {
  const tb = h("div", { class: "tabs", role: "tablist" }),
    body = h("div"),
    enc = encodeURIComponent(name);
  let cur = "";
  const cdraw = async () => {
    body.replaceChildren(h("p", { class: "hint" }, "Loading\u2026"));
    let r;
    try {
      r = await api("mcomments", null, "&k=" + enc);
    } catch (e) {
      body.replaceChildren(emp("lock", "Unavailable", "Could not load comments."));
      return;
    }
    const box = h("div", { class: "mcl" }),
      more = h("button", { class: "ghost", style: "width:100%;margin-top:10px", hidden: !r.more }, "Load more");
    let last = r.last;
    const add = (l) =>
      l.forEach((c) =>
        box.append(
          h(
            "button",
            {
              class: "card cmc",
              onclick: () => (location.hash = "#/p/" + c.pid),
              "aria-label": "Open the post this comment is on",
            },
            h("p", {}, c.txt),
            h(
              "small",
              { class: "hint" },
              "On " +
                (c.pcap ? "\u201c" + c.pcap + "\u201d" : c.photo ? "a photo post" : "a post") +
                " \u00b7 " +
                ago(c.ts),
            ),
          ),
        ),
      );
    add(r.list);
    more.onclick = async () => {
      more.disabled = true;
      try {
        const x = await api("mcomments", null, "&k=" + enc + "&before=" + last);
        add(x.list);
        last = x.last;
        more.hidden = !x.more;
      } catch (e) {}
      more.disabled = false;
    };
    body.replaceChildren(
      r.list.length || r.more ? box : emp("chat", "No comments yet", "Comments made with this Masque show up here."),
      more,
    );
  };
  const pick = (k) => {
    if (k === cur) return;
    const was = cur;
    cur = k;
    [...tb.children].forEach((b) => b.setAttribute("aria-selected", b.dataset.k === k));
    if (k === "posts")
      body.replaceChildren(
        feedBox("&k=" + enc, pr, emp("image", "No posts yet", "Posts made with this Masque show up here.")),
      );
    else cdraw();
    if (was) swap(body, k === "comments" ? 1 : -1);
  };
  [
    ["posts", "Posts"],
    ["comments", "Comments"],
  ].forEach(([k, l]) =>
    tb.append(h("button", { role: "tab", "data-k": k, "aria-selected": "false", onclick: () => pick(k) }, l)),
  );
  pick("posts");
  return h("div", {}, tb, body);
}
function repCard(r) {
  const nx = r.next,
    pc = nx ? Math.max(0, Math.min(100, Math.round((100 * (r.score - r.from)) / (nx - r.from)))) : 100;
  return h(
    "div",
    { class: "card rep2" },
    h(
      "div",
      { class: "repl" },
      h("span", { class: "repb", "data-lv": r.lv }, r.title),
      h("small", { class: "hint" }, r.score + " points"),
    ),
    h(
      "div",
      {
        class: "repbar",
        role: "progressbar",
        "aria-valuemin": 0,
        "aria-valuemax": 100,
        "aria-valuenow": pc,
        "aria-label": "Progress to " + (r.nextTitle || "top level"),
      },
      h("i", { style: "width:" + pc + "%" }),
    ),
    h("small", { class: "hint" }, nx ? nx - r.score + " more points to " + r.nextTitle : "Top level reached"),
    h(
      "div",
      { class: "reps" },
      h("span", {}, h("b", {}, r.posts), "posts"),
      h("span", {}, h("b", {}, r.comments), "comments"),
      h("span", {}, h("b", {}, r.marks), "marks"),
      h("span", {}, h("b", {}, r.downs || 0), "downvotes"),
    ),
    h(
      "small",
      { class: "hint" },
      "3 points per post, 1 per comment, 1 per mark received, minus 1 per downvote received. Points can go below zero.",
    ),
  );
}
async function maskPage(name) {
  let k, pr;
  try {
    [{ k }, pr] = await Promise.all([
      api("maskuser", null, "&k=" + encodeURIComponent(name)),
      api("feed", null, "&k=" + encodeURIComponent(name)),
    ]);
  } catch (e) {
    shell(emp("search", "No such Masque", "Check the spelling and try again."));
    return;
  }
  const mkh = h(
    "div",
    { class: "card mkhead" },
    h(
      "span",
      { class: "lmw" },
      av(k, 84),
      h(
        "span",
        { class: "lmb mkb", role: "img", "aria-label": "Laughing mask" },
        h("span", { class: "lmst" }, lmIcon(22)),
      ),
    ),
    h(
      "div",
      {},
      h("h1", { class: "kt" }, k.name),
      h("p", { class: "hint" }, "Masque"),
      h("p", {}, k.bio || "No bio yet."),
    ),
  );
  mkh.onclick = (e) => {
    if (e.target.closest(".lmw")) laugh(mkh);
  };
  setTimeout(() => laugh(mkh), 600);
  const blockMk = async (on) => {
    if (
      on &&
      !(await cbox(
        "Block this Masque? You will no longer see its posts, comments or Room messages, and it can no longer message you. Your account and friendships are not affected.",
      ))
    )
      return;
    try {
      await api("mblock", fd({ k: k.name, on: on ? 1 : 0 }));
      maskPage(name);
    } catch (x) {
      alert(x.e || "Could not change that.");
    }
  };
  shell([
    mkh,
    !+k.mb && k.rep ? repCard(k.rep) : null,
    k.by
      ? h(
          "div",
          { class: "card" },
          h(
            "p",
            {},
            "Told to you in private: this Masque is ",
            h("a", { href: BASE + "#/u/" + k.by.name, onclick: (e) => (e.preventDefault(), (location.hash = "#/u/" + k.by.name)) }, "@" + k.by.name),
            ".",
          ),
        )
      : null,
    +k.mine
      ? h(
          "div",
          { class: "row mkact" },
          h("button", { class: "ghost", onclick: () => maskSheet() }, "Edit Masque"),
          h("button", { class: "ghost", onclick: () => revealSheet(k) }, "Tell a friend"),
        )
      : +k.mb
        ? h("div", { class: "row mkact" }, h("button", { class: "btn", onclick: () => blockMk(false) }, "Unblock this Masque"))
        : h(
            "div",
            { class: "row mkact" },
            h(
              "button",
              { class: "btn", onclick: () => (location.hash = "#/m/" + k.name + (ASM && M.mask ? "/k" : "")) },
              ic("chat", 16),
              "Message",
            ),
            h("button", { class: "ghost", onclick: () => blockMk(true) }, "Block"),
            h("button", { class: "ghost", onclick: () => reportSheet("mask", k.name) }, "Report"),
          ),
    +k.mb
      ? h("div", { class: "card" }, h("p", { class: "hint" }, "You blocked this Masque. You will not see its posts, comments or Room messages, and it cannot message you."))
      : mkTabs(name, pr),
  ]);
}
/* block & report */
function reportSheet(kind, key, done, ctx) {
  sheet("Report", (close) => {
    const w = h("textarea", {
        rows: 3,
        maxlength: 200,
        placeholder: "What is wrong? (optional)",
        "aria-label": "Reason",
      }),
      err = h("p", { class: "err", role: "alert" }),
      b = h("button", { class: "btn full", type: "submit" }, "Send report");
    return h(
      "form",
      {
        class: "form",
        onsubmit: async (e) => {
          e.preventDefault();
          b.disabled = true;
          try {
            await api(
              "report",
              fd({ kind, why: ((ctx || "") + w.value).slice(0, 200), ...(kind === "user" || kind === "mask" ? { to: key } : { id: key }) }),
            );
            close();
            alert("Thanks. The report was sent.");
            if (done) done();
          } catch (x) {
            err.textContent = x.e || "Could not send.";
            b.disabled = false;
          }
        },
      },
      h(
        "p",
        { class: "hint" },
        kind === "ask"
          ? "Reports are private. Site admins will be able to see who sent this question. It disappears from your list."
          : "Reports are private. Only the site admins can see them.",
      ),
      w,
      err,
      b,
    );
  });
}
async function words() {
  let L;
  try {
    L = (await api("bwlist")).words;
  } catch (e) {
    shell(emp("shield", "Admins only", "This page is for site admins."));
    return;
  }
  const inp = h("input", { placeholder: "Word or phrase", maxlength: 40, "aria-label": "Word or phrase" }),
    sel = h(
      "select",
      { "aria-label": "What to do with a match" },
      h("option", { value: "0" }, "Flag for review (stays visible)"),
      h("option", { value: "1" }, "Hold back until approved"),
    ),
    err = h("p", { class: "err", role: "alert" }),
    add = h(
      "form",
      {
        class: "form",
        onsubmit: async (e) => {
          e.preventDefault();
          err.textContent = "";
          try {
            await api("bwadd", fd({ w: inp.value, hold: sel.value }));
            route();
          } catch (x) {
            err.textContent = x.e || "Could not add.";
          }
        },
      },
      inp,
      sel,
      err,
      h("button", { class: "btn", type: "submit" }, "Add"),
    ),
    row = (w) =>
      h(
        "div",
        { class: "row", style: "justify-content:space-between;align-items:center" },
        h("span", {}, h("b", {}, w.w), " ", h("small", { class: "hint" }, +w.hold ? "held back" : "flagged")),
        h(
          "button",
          {
            class: "ghost",
            onclick: async () => {
              if (await cbox("Remove \u201c" + w.w + "\u201d from the list?")) {
                try {
                  await api("bwdel", fd({ w: w.w }));
                  route();
                } catch (x) {
                  alert(x.e || "Could not remove.");
                }
              }
            },
          },
          "Remove",
        ),
      );
  shell([
    big("Blocked words"),
    h(
      "div",
      { class: "card" },
      h(
        "p",
        { class: "hint" },
        "Posts and comments that contain one of these words or phrases (whole words, any capitalization) are sent to the Reports page. \u201cFlag\u201d leaves them visible. \u201cHold back\u201d hides them from everyone except their author and admins until you approve them. Admins are never filtered. Existing posts are not re-checked.",
      ),
      add,
    ),
    h(
      "div",
      { class: "card" },
      h("h3", {}, "List (" + L.length + ")"),
      L.length ? L.map(row) : h("p", { class: "hint" }, "No words yet."),
    ),
  ]);
}
/* suspended or banned: write an appeal to the admins (one waiting at a time, a week between denied ones) */
function appealSheet() {
  sheet("Appeal", (close) => {
    const box = h("div", { class: "form" }, h("p", { class: "hint" }, "Loading\u2026"));
    (async () => {
      let r;
      try {
        r = await api("appealst");
      } catch (x) {
        rc(box, h("p", { class: "err" }, x.e || "Could not load."));
        return;
      }
      const a = r.appeal,
        st = a ? +a.st : -1;
      if (st === 0) {
        rc(
          box,
          h(
            "p",
            { class: "sub" },
            "Your appeal is waiting for an admin to read it. If they lift the suspension you can post again straight away.",
          ),
          h("p", { class: "hint" }, "You wrote: " + a.txt),
        );
        return;
      }
      const wait = st === 2 && +r.next > Date.now() / 1000,
        t = h("textarea", {
          rows: 5,
          maxlength: 1000,
          placeholder: "Tell the admins why this should be lifted\u2026",
          "aria-label": "Your appeal",
        }),
        cnt = h("p", { class: "hint cnt" }, "0 / 1000"),
        err = h("p", { class: "err", role: "alert" }),
        b = h("button", { class: "btn full", type: "submit" }, "Send appeal");
      b.disabled = true;
      t.oninput = () => {
        cnt.textContent = t.value.length + " / 1000";
        b.disabled = t.value.trim().length < 20;
      };
      const f = h(
        "form",
        {
          class: "form",
          onsubmit: async (e) => {
            e.preventDefault();
            b.disabled = true;
            err.textContent = "";
            try {
              await api("appeal", fd({ txt: t.value }));
              rc(
                box,
                h(
                  "p",
                  { class: "sub" },
                  "Appeal sent. An admin will read it. You can come back to this page to see what they decided.",
                ),
              );
            } catch (x) {
              err.textContent = x.e || "Could not send.";
              b.disabled = false;
            }
          },
        },
        t,
        cnt,
        err,
        b,
      );
      rc(
        box,
        st === 2 ? h("p", { class: "hint" }, "Your last appeal was denied" + (a.note ? ": " + a.note : ".")) : null,
        wait
          ? h(
              "p",
              { class: "hint" },
              "You can send another appeal after " +
                new Date(r.next * 1000).toLocaleDateString(undefined, {
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                }) +
                ".",
            )
          : [
              h(
                "p",
                { class: "hint" },
                "Explain what happened and why the suspension should be lifted. Be honest and specific. An admin reads every appeal.",
              ),
              f,
            ],
      );
    })();
    return box;
  });
}
/* ===== Management: a dashboard for every role, and users / posts / comments management for staff ===== */
const MGROLE = { admin: "Admin", mod: "Moderator", user: "User" },
  mgWhen = (t) => (t ? new Date(t * 1000).toLocaleDateString() : "never"),
  mgTiles = (list) => h("div", { class: "stiles" }, ...list.map(([n, l]) => h("div", { class: "stile" }, h("b", {}, String(n)), h("small", {}, l)))),
  mgBtn = (label, hash) => h("button", { type: "button", class: "ghost", style: "display:block;width:100%;margin-top:8px", onclick: () => (location.hash = hash) }, label),
  mgBack = () => h("button", { type: "button", class: "ghost", onclick: () => (location.hash = M && M.mod ? "#/dash" : "#/") }, "\u2190 Dashboard"),
  mgDenied = () => shell(emp("shield", "Staff only", "This page is for site moderators and admins."));
function mgPager(r, go) {
  const from = r.total ? r.page * r.per + 1 : 0,
    to = Math.min(r.total, (r.page + 1) * r.per);
  return h(
    "div",
    { class: "row", style: "justify-content:space-between;align-items:center;margin-top:8px" },
    h("button", { type: "button", class: "ghost", disabled: r.page < 1, onclick: () => go(r.page - 1) }, "Previous"),
    h("span", { class: "hint" }, from + "\u2013" + to + " of " + r.total),
    h("button", { type: "button", class: "ghost", disabled: to >= r.total, onclick: () => go(r.page + 1) }, "Next"),
  );
}
async function dashPage() {
  const d = await api("mg_dash"),
    k = d.mine,
    out = [big("Dashboard"), h("div", { class: "card" }, h("h3", {}, "Hi @" + d.name), h("p", { class: "hint" }, "You are signed in as: " + MGROLE[d.role] + "."))];
  if (d.site)
    out.push(
      h(
        "div",
        { class: "card" },
        h("h3", {}, "Site"),
        mgTiles([[d.site.users, "accounts"], [d.site.mods, "moderators"], [d.site.new7, "new this week"], [d.site.active1, "active today"], [d.site.posts, "posts"], [d.site.comments, "comments"]]),
        mgBtn("Manage users", "#/ausers"),
        mgBtn("Admin settings and stats", "#/settings/admin"),
      ),
    );
  if (d.queue)
    out.push(
      h(
        "div",
        { class: "card" },
        h("h3", {}, "Moderation queue"),
        mgTiles([[d.queue.reports, "reported things"], [d.queue.appeals, "appeals waiting"], [d.queue.held, "held back"], [d.queue.suspended, "suspended"]]),
        mgBtn("Reports and appeals", "#/r"),
        mgBtn("Manage posts", "#/aposts"),
        mgBtn("Manage comments", "#/acomments"),
        h("h4", { style: "margin-top:14px" }, "Your recent actions"),
        d.actions.length ? d.actions.map((a) => h("p", { class: "hint" }, a.act + (a.tgt ? " " + a.tgt : "") + " \u00b7 " + ago(a.ts))) : h("p", { class: "hint" }, "Nothing yet."),
      ),
    );
  out.push(
    h(
      "div",
      { class: "card" },
      h("h3", {}, "Your activity"),
      mgTiles([[k.posts, "posts"], [k.comments, "comments"], [k.likes, "likes received"], [k.friends, "friends"], [k.streak, "day streak"], [k.sigils, "Sigils"]]),
      mgTiles([[k.bell, "new alerts"], [k.unread, "unread messages"], [k.requests, "friend requests"]]),
      h("h4", {}, "Your latest posts"),
      k.recent.length
        ? k.recent.map((p) => h("p", {}, h("a", { href: "#/p/" + p.id }, p.cap || "(photo)"), " ", h("small", { class: "hint" }, p.likes + " likes \u00b7 " + ago(p.ts))))
        : h("p", { class: "hint" }, "You have not posted yet."),
    ),
  );
  shell(out);
}
function mgUserSheet(name, done) {
  sheet(name ? "Edit @" + name : "Add a person", (close) => {
    const box = h("div", { class: "form" }, h("p", { class: "hint" }, "Loading\u2026")),
      err = h("p", { class: "err", role: "alert" }),
      inp = (ph, v, ml, type) => h("input", { type: type || "text", placeholder: ph, "aria-label": ph, value: v || "", maxlength: ml, autocomplete: "off", autocapitalize: "off" }),
      roleSel = (v) => h("select", { "aria-label": "Role" }, h("option", { value: "user" }, "User"), h("option", { value: "mod" }, "Moderator")),
      build = (u) => {
        const nm = name ? null : inp("Username", "", 20),
          nick = name ? inp("Nickname", u.nick, 30) : null,
          bio = name ? h("textarea", { "aria-label": "Bio", maxlength: 160, placeholder: "Bio" }, u.bio || "") : null,
          priv = name ? h("input", { type: "checkbox", style: "width:auto", checked: +u.priv === 1 }) : null,
          rs = roleSel(),
          pw = inp(name ? "New password (leave empty to keep)" : "Password (8+ characters)", "", 72, "password"),
          go = h("button", { type: "submit", class: "btn full" }, name ? "Save changes" : "Create account");
        rs.value = name ? u.role : "user";
        box.replaceChildren(
          h(
            "form",
            {
              class: "form",
              onsubmit: async (e) => {
                e.preventDefault();
                err.textContent = "";
                go.disabled = true;
                try {
                  if (name) await api("mg_uedit", fd({ name, nick: nick.value, bio: bio.value, priv: priv.checked ? 1 : 0, role: rs.value, pw: pw.value }));
                  else await api("mg_uadd", fd({ name: nm.value.trim(), pw: pw.value, role: rs.value }));
                  close();
                  done();
                } catch (x) {
                  err.textContent = (x && x.e) || "Could not save.";
                }
                go.disabled = false;
              },
            },
            nm,
            nick,
            bio,
            priv ? h("label", { class: "row", style: "gap:8px;align-items:center" }, priv, "Private account") : null,
            h("label", { class: "hint" }, "Role"),
            rs,
            pw,
            name ? h("p", { class: "hint" }, "Setting a new password signs that person out everywhere. Masques are never shown here.") : h("p", { class: "hint" }, "They can change the password after signing in."),
            err,
            go,
          ),
        );
      };
    if (!name) build({});
    else
      api("mg_uget", fd({ name })).then(build, (x) => box.replaceChildren(h("p", { class: "err" }, (x && x.e) || "Could not load.")));
    return box;
  });
}
async function usersPage() {
  if (!(M && M.admin)) return mgDenied();
  const st = { q: "", role: "", page: 0 },
    list = h("div", {}),
    q = h("input", { type: "search", placeholder: "Search name or nickname", "aria-label": "Search people", maxlength: 20 }),
    rs = h("select", { "aria-label": "Show" }, ...[["", "Everyone"], ["user", "Users"], ["mod", "Moderators"], ["admin", "Admins"], ["suspended", "Suspended"]].map(([v, l]) => h("option", { value: v }, l)));
  const load = async () => {
    let r;
    try {
      r = await api("mg_ulist", fd(st));
    } catch (x) {
      rc(list, h("p", { class: "err" }, (x && x.e) || "Could not load."));
      return;
    }
    const row = (u) =>
      h(
        "div",
        { class: "card rep" },
        h("b", {}, "@" + u.name + (u.nick ? " \u00b7 " + u.nick : "")),
        h("p", { class: "hint" }, MGROLE[u.role] + " \u00b7 joined " + mgWhen(u.ts) + " \u00b7 last seen " + mgWhen(u.la) + " \u00b7 " + u.posts + " posts \u00b7 " + u.comments + " comments" + (u.sus > Date.now() / 1000 ? (u.sus >= 2e9 ? " \u00b7 banned" : " \u00b7 suspended") : "")),
        u.role === "admin"
          ? h("p", { class: "hint" }, "Admins are set in the server settings.")
          : h(
              "div",
              { class: "row" },
              h("button", { type: "button", class: "ghost", onclick: () => mgUserSheet(u.name, load) }, "Edit"),
              h(
                "button",
                {
                  type: "button",
                  class: "ghost",
                  onclick: async () => {
                    if (!(await cbox("Delete @" + u.name + " and everything they made (posts, comments, messages, photos)? This cannot be undone."))) return;
                    try {
                      await api("mg_udel", fd({ name: u.name }));
                      load();
                    } catch (x) {
                      alert((x && x.e) || "Could not delete.");
                    }
                  },
                },
                "Delete",
              ),
            ),
      );
    rc(list, r.users.length ? r.users.map(row) : h("p", { class: "hint" }, "Nobody matches."), mgPager(r, (p) => { st.page = p; load(); }));
  };
  q.addEventListener("input", () => { st.q = q.value; st.page = 0; clearTimeout(q._t); q._t = setTimeout(load, 250); });
  rs.addEventListener("change", () => { st.role = rs.value; st.page = 0; load(); });
  shell([big("People"), mgBack(), h("div", { class: "card" }, h("button", { type: "button", class: "btn full", onclick: () => mgUserSheet("", load) }, "Add a person"), q, rs), list]);
  load();
}
async function mgContent(kind) {
  if (!(M && M.mod)) return mgDenied();
  const post = kind === "post",
    cfg = post ? { list: "mg_mposts", edit: "mg_mpedit", del: "mg_mpdel", field: "cap", key: "posts", title: "Posts" } : { list: "mg_mcomments", edit: "mg_mcedit", del: "mg_mcdel", field: "txt", key: "comments", title: "Comments" },
    st = { q: "", page: 0 },
    list = h("div", {}),
    q = h("input", { type: "search", placeholder: "Search the text", "aria-label": "Search", maxlength: 40 });
  const edit = (x) =>
      sheet("Edit " + kind, (close) => {
        const t = h("textarea", { "aria-label": "Text", maxlength: post ? 1000 : 300, style: "min-height:120px" }, x[cfg.field] || ""),
          err = h("p", { class: "err", role: "alert" });
        return h(
          "form",
          {
            class: "form",
            onsubmit: async (e) => {
              e.preventDefault();
              try {
                await api(cfg.edit, fd({ id: x.id, [cfg.field]: t.value }));
                close();
                load();
              } catch (y) {
                err.textContent = (y && y.e) || "Could not save.";
              }
            },
          },
          h("p", { class: "hint" }, "The author is not told. Only the first 200 characters are loaded here, so saving replaces the whole text."),
          t,
          err,
          h("button", { type: "submit", class: "btn full" }, "Save"),
        );
      }),
    load = async () => {
      let r;
      try {
        r = await api(cfg.list, fd(st));
      } catch (x) {
        rc(list, h("p", { class: "err" }, (x && x.e) || "Could not load."));
        return;
      }
      const row = (x) =>
        h(
          "div",
          { class: "card rep" },
          h("b", {}, (x.masked ? "Masque" : "@" + x.author) + " \u00b7 " + ago(x.ts) + (+x.hold ? " \u00b7 held back" : "") + (+x.vis ? " \u00b7 not public" : "")),
          h("p", {}, x[cfg.field] || (x.himg ? "(photo only)" : "(no text)")),
          post ? h("p", { class: "hint" }, x.likes + " likes \u00b7 " + x.comments + " comments") : null,
          h(
            "div",
            { class: "row" },
            h("button", { type: "button", class: "ghost", onclick: () => (location.hash = "#/p/" + (post ? x.id : x.pid)) }, "View"),
            h("button", { type: "button", class: "ghost", onclick: () => edit(x) }, "Edit"),
            h(
              "button",
              {
                type: "button",
                class: "ghost",
                onclick: async () => {
                  if (!(await cbox("Delete this " + kind + (post ? " and its comments" : "") + "?"))) return;
                  try {
                    await api(cfg.del, fd({ id: x.id }));
                    load();
                  } catch (y) {
                    alert((y && y.e) || "Could not delete.");
                  }
                },
              },
              "Delete",
            ),
          ),
        );
      rc(list, r[cfg.key].length ? r[cfg.key].map(row) : h("p", { class: "hint" }, "Nothing found."), mgPager(r, (p) => { st.page = p; load(); }));
    };
  q.addEventListener("input", () => { st.q = q.value; st.page = 0; clearTimeout(q._t); q._t = setTimeout(load, 250); });
  shell([big(cfg.title), mgBack(), h("div", { class: "card" }, q, h("p", { class: "hint" }, "Masque posts are listed as \u201cMasque\u201d: nobody can see whose they are.")), list]);
  load();
}
const postsPage = () => mgContent("post"),
  commentsPage = () => mgContent("comment");
async function reports() {
  let r, lg, ap;
  try {
    const x = await api("reports");
    r = x.reports;
    lg = x.log || [];
    ap = x.appeals || [];
  } catch (e) {
    shell(emp("shield", "Staff only", "This page is for site moderators and admins."));
    return;
  }
  const act = (a, id, ask) => async () => {
    if (ask && !(await cbox(ask))) return;
    await api(a, fd({ id }));
    route();
  };
  const sus = (name, days, ask) => async () => {
    if (!(await cbox(ask))) return;
    try {
      await api("suspend", fd({ name, days }));
      route();
    } catch (x) {
      alert(x.e || "Could not do that.");
    }
  };
  const purge = (name) => async () => {
    if (
      !(await cbox(
        "Ban @" +
          name +
          " and permanently delete all their posts, comments, likes, messages and friend requests? This cannot be undone.",
      ))
    )
      return;
    try {
      const r = await api("purge", fd({ name }));
      alert(
        "Done. Deleted " +
          r.posts +
          " post" +
          (r.posts === 1 ? "" : "s") +
          " and " +
          r.comments +
          " comment" +
          (r.comments === 1 ? "" : "s") +
          ".",
      );
      route();
    } catch (x) {
      alert(x.e || "Could not do that.");
    }
  };
  const rep = (x) => {
    const t = x.target,
      on = t && t.sus > Date.now() / 1000;
    return h(
      "div",
      { class: "card rep" },
      h(
        "b",
        {},
        (x.kind === "ask" ? "anonymous question" : x.kind) +
          (+x.auto ? " · caught by the word filter" : " · by " + x.rname) +
          " · " +
          ago(x.ts),
      ),
      h("p", { class: "hint" }, x.why || "(no reason given)"),
      h(
        "p",
        {},
        t
          ? (x.kind === "ask" ? "Sender @" : x.kind === "mask" ? "Owner @" : "") +
              t.name +
              ": " +
              (t.cap || "(no text)")
          : "(already deleted)",
      ),
      t && +t.held
        ? h(
            "p",
            { class: "hint" },
            "Held back: only the author and admins can see it. Approve to publish it or Delete to remove it.",
          )
        : null,
      t && t.hid
        ? h(
            "p",
            { class: "hint" },
            "Auto-hidden from the feed for everyone but you and the author. Dismiss or delete to resolve.",
          )
        : null,
      t
        ? h(
            "p",
            { class: "hint" },
            "@" +
              t.name +
              " has " +
              t.n +
              " report" +
              (t.n === 1 ? "" : "s") +
              " in total" +
              (on
                ? t.sus >= 2e9
                  ? " · banned"
                  : " · suspended until " + new Date(t.sus * 1000).toLocaleDateString()
                : ""),
          )
        : null,
      h(
        "div",
        { class: "row" },
        x.kind === "user" && t
          ? h("button", { class: "ghost", onclick: () => (location.hash = "#/u/" + t.name) }, "View profile")
          : null,
        x.kind === "post" && t
          ? h("button", { class: "ghost", onclick: () => (location.hash = "#/p/" + x.tid) }, "View post")
          : null,
        x.kind === "post" && t && t.himg
          ? h(
              "button",
              {
                class: "ghost",
                onclick: async () => {
                  try {
                    await api("rblur", fd({ id: x.id }));
                    route();
                  } catch (e) {
                    alert(e.e || "Could not do that.");
                  }
                },
              },
              t.sens === 2 ? "Remove blur" : "Blur photo",
            )
          : null,
        x.kind !== "user" && x.kind !== "mask" && t
          ? h(
              "button",
              {
                class: "ghost",
                onclick: act("rdel", x.id, "Delete this " + (x.kind === "ask" ? "question" : x.kind) + "?"),
              },
              "Delete " + (x.kind === "ask" ? "question" : x.kind),
            )
          : null,
        h("button", { class: "ghost", onclick: act("rdone", x.id) }, +x.auto ? "Approve" : "Dismiss"),
      ),
      t && !t.adm
        ? h(
            "div",
            { class: "row" },
            on
              ? h(
                  "button",
                  { class: "ghost", onclick: sus(t.name, 0, "Lift the suspension on @" + t.name + "?") },
                  "Lift suspension",
                )
              : [
                  h(
                    "button",
                    {
                      class: "ghost",
                      onclick: sus(
                        t.name,
                        7,
                        "Suspend @" + t.name + " for 7 days? They can still read, but not post, comment or message.",
                      ),
                    },
                    "Suspend 7 days",
                  ),
                  !M.admin ? null : h(
                    "button",
                    {
                      class: "ghost",
                      onclick: sus(
                        t.name,
                        -1,
                        "Ban @" +
                          t.name +
                          "? They can still read, but not post, comment or message, until you lift it.",
                      ),
                    },
                    "Ban",
                  ),
                ],
            M.admin ? h("button", { class: "ghost", onclick: purge(t.name) }, "Ban + delete all content") : null,
          )
        : null,
    );
  };
  const ares = (id, ok) => async () => {
      const note = prompt(ok ? "Optional note to the user" : "Reason shown to the user (optional)");
      if (note === null) return;
      try {
        await api("appealres", fd({ id, ok: ok ? 1 : 0, note }));
        route();
      } catch (x) {
        alert(x.e || "Could not do that.");
      }
    },
    arow = (a) =>
      h(
        "div",
        { class: "card rep" },
        h("b", {}, "appeal \u00b7 @" + a.name + " \u00b7 " + (ago(a.ts) === "now" ? "now" : ago(a.ts) + " ago")),
        h(
          "p",
          { class: "hint" },
          a.sus >= 2e9 ? "Banned" : "Suspended until " + new Date(a.sus * 1000).toLocaleDateString(),
        ),
        h("p", {}, a.txt),
        h(
          "div",
          { class: "row" },
          h("button", { class: "ghost", onclick: () => (location.hash = "#/u/" + a.name) }, "View profile"),
          h("button", { class: "ghost", onclick: ares(a.id, 1) }, "Lift suspension"),
          h("button", { class: "ghost", onclick: ares(a.id, 0) }, "Deny"),
        ),
      );
  let st = null;
  try {
    st = await api("astats");
  } catch (e) {}
  const bars = (v, l) => {
      const mx = Math.max(1, ...v);
      return h(
        "div",
        { class: "sbars", role: "img", "aria-label": l + " per day, last 14 days: " + v.join(", ") },
        ...v.map((n, i) =>
          h("i", {
            title: n + (i === 13 ? " today" : ""),
            style: "height:" + Math.max(4, Math.round((n / mx) * 100)) + "%",
          }),
        ),
      );
    },
    tile = (n, l) => h("div", { class: "stile" }, h("b", {}, String(n)), h("small", {}, l)),
    mb = (b) => (b >= 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.round(b / 1024) + " KB"),
    statCard = st
      ? h(
          "div",
          { class: "card" },
          h("h3", {}, "Site stats"),
          h(
            "div",
            { class: "stiles" },
            tile(st.now, "online now"),
            tile(st.act1, "active today"),
            tile(st.act7, "active this week"),
            tile(st.users, "accounts"),
            tile(st.new1, "new today"),
            tile(st.new7, "new this week"),
            tile(st.posts1, "posts today"),
            tile(st.posts7, "posts this week"),
            tile(st.com1, "comments today"),
            tile(st.msg1, "messages today"),
            tile(st.masks, "Masques"),
            tile(st.posts, "posts in total"),
          ),
          h("p", { class: "hint sl" }, "New accounts, last 14 days"),
          bars(st.sg, "New accounts"),
          h("p", { class: "hint sl" }, "Posts, last 14 days"),
          bars(st.pg, "Posts"),
          h(
            "p",
            { class: "hint sl" },
            "To look at: " +
              st.rep +
              " report" +
              (st.rep === 1 ? "" : "s") +
              " \u00b7 " +
              st.app +
              " appeal" +
              (st.app === 1 ? "" : "s") +
              " \u00b7 " +
              st.held +
              " held back \u00b7 " +
              st.sus +
              " suspended or banned \u00b7 database " +
              mb(st.db),
          ),
        )
      : null;
  shell([
    big("Reports"),
    ...(statCard ? [statCard] : []),
    ...(ap.length ? [h("h3", { style: "margin:0 0 8px" }, "Appeals"), ...ap.map(arow)] : []),
    r.length ? r.map(rep) : emp("shield", "No reports", "Everything is clear. New reports will show up here."),
    h(
      "div",
      { class: "card" },
      h("h3", {}, "Recent admin actions"),
      lg.length
        ? lg.map((a) =>
            h(
              "p",
              { class: "hint" },
              (a.aname || "admin") +
                " " +
                a.act +
                (a.tgt ? " @" + a.tgt : "") +
                " · " +
                (ago(a.ts) === "now" ? "now" : ago(a.ts) + " ago"),
            ),
          )
        : h("p", { class: "hint" }, "Nothing yet."),
    ),
  ]);
}
/* friends */
const fcall = (a, n, ask, fx) => async (ev) => {
  const b = ev && ev.currentTarget && ev.currentTarget.closest ? ev.currentTarget : null;
  if (ask && !(await cbox(ask))) return;
  const row = fx && b ? b.closest(".frow") : null,
    bs = row ? [...row.querySelectorAll("button")] : b ? [b] : [];
  bs.forEach((x) => (x.disabled = true));
  try {
    await api(a, fd({ to: n }));
    if (row) await rowFx(row, fx, b);
    FNEW = fx === "acc" ? n : null;
    if (!row && /^f(add|acc|rem)$/.test(a)) FPOP = Date.now();
    route();
  } catch (x) {
    bs.forEach((y) => (y.disabled = false));
    alert(x.e || "Something went wrong.");
  }
};
function friendBtns(u) {
  const n = u.name,
    pop = Date.now() - FPOP < 3000;
  FPOP = 0;
  const b = (t, fn, c) => h("button", { class: (c || "ghost") + (pop ? " bpop" : ""), onclick: fn }, t);
  if (u.rel === "friends")
    return [b([ic("check", 16), h("span", {}, "Friends")], fcall("frem", n, "Remove " + n + " from your friends?"))];
  if (u.rel === "sent") return [b("Requested", fcall("frem", n, "Cancel your friend request to " + n + "?"))];
  if (u.rel === "got") return [b("Accept request", fcall("facc", n), "btn"), b("Decline", fcall("frem", n))];
  return [b("Add friend", fcall("fadd", n), "btn")];
}
/* invite card: shares the site's front page (the landing screen explains Masque). No tracking and no "invited by", so nobody's identity is tied to a link. */
function inviteCard() {
  const url = location.origin + BASE,
    idle = () => [ic("link", 16), h("span", {}, "Share Masque")],
    b = h("button", { type: "button", class: "btn invb" }, ...idle()),
    lab = (t) => {
      b.replaceChildren(ic("check", 16), h("span", {}, t));
      setTimeout(() => b.replaceChildren(...idle()), 1800);
    };
  b.onclick = async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title: "Masque", text: "Join me on Masque. Be anyone you want, no real names.", url });
        return;
      } catch (e) {
        if (e && e.name === "AbortError") return;
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      lab("Link copied");
    } catch (e) {
      prompt("Copy this link", url);
    }
  };
  return h(
    "div",
    { class: "card invite" },
    h(
      "div",
      {},
      h("b", {}, "Invite your friends"),
      h(
        "p",
        { class: "hint" },
        "Masque is better with people you know. Send them the link, then add each other as friends.",
      ),
    ),
    b,
  );
}
async function friends() {
  const nw = FNEW;
  FNEW = null;
  const { list } = await api("friends"),
    fr = list.filter((x) => +x.st),
    rq = list.filter((x) => !+x.st && !+x.mine),
    sn = list.filter((x) => !+x.st && +x.mine);
  const res = h("div"),
    q = h("input", {
      placeholder: "Find people by name or username…",
      "aria-label": "Find people",
      autocomplete: "off",
      autocapitalize: "none",
    });
  let t;
  q.oninput = () => {
    clearTimeout(t);
    t = setTimeout(async () => {
      const v = q.value.trim();
      if (!v) {
        res.replaceChildren();
        return;
      }
      try {
        const { users } = await api("find", null, "&q=" + encodeURIComponent(v));
        res.replaceChildren(
          ...(users.length
            ? users.map((u) =>
                h(
                  "button",
                  { class: "chat", onclick: () => (location.hash = "#/u/" + u.name) },
                  av(u, 44),
                  h("div", { class: "cx" }, h("b", {}, dn(u))),
                ),
              )
            : [h("p", { class: "hint" }, "No one found.")]),
        );
      } catch (e) {}
    }, 250);
  };
  const sid = (title) => "fsec-" + title.toLowerCase().replace(/\s+/g, "-"),
    sec = (title, items, actions) =>
    items.length
      ? [
          h("h3", { class: "vt fsh", id: sid(title) }, h("span", {}, title), h("i", { class: "fcn" }, String(items.length))),
          ...items.map((x) =>
            h(
              "div",
              { class: "chat frow fcmp" + (title === "Requests" ? " freq" : "") + (title === "Sent requests" ? " fsent" : "") + (x.name === nw ? " rnew" : "") },
              ((a) => {
                a.style.cursor = "pointer";
                a.onclick = () => (location.hash = "#/u/" + x.name);
                return a;
              })(av(x, 44)),
              h(
                "div",
                { class: "cx" },
                h("b", { style: "cursor:pointer", onclick: () => (location.hash = "#/u/" + x.name) }, dn(x)),
                dn(x) !== x.name || title === "Sent requests"
                  ? h("small", { class: "hint fun" }, "@" + x.name + (title === "Sent requests" && +x.ts ? " \u00b7 sent " + (ago(+x.ts) === "now" ? "just now" : ago(+x.ts) + " ago") : ""))
                  : null,
              ),
              h("span", { class: "fa" }, ...actions(x)),
            ),
          ),
        ]
      : [];
  const bt = (t, fn, c) => h("button", { class: c || "ghost", onclick: fn }, t);
  const stat = (label, n, id, hot) =>
      h(
        "button",
        {
          type: "button",
          class: "fstat" + (hot && n ? " hot" : ""),
          disabled: !n,
          onclick: () => document.getElementById(id)?.scrollIntoView({ block: "start", behavior: RM.matches ? "auto" : "smooth" }),
        },
        h("b", {}, String(n)),
        h("span", {}, label),
      ),
    stats = list.length ? h("div", { class: "fstats", role: "group", "aria-label": "Friends summary" }, stat("Friends", fr.length, sid("Your friends")), stat("Requests", rq.length, sid("Requests"), 1), stat("Sent", sn.length, sid("Sent requests"))) : null;
  shell([
    big("Friends"),
    inviteCard(),
    stats,
    q,
    res,
    ...sec("Requests", rq, (x) => [
      bt("Accept", fcall("facc", x.name, 0, "acc"), "btn"),
      bt("Decline", fcall("frem", x.name, 0, "out"), "ghost fdim"),
    ]),
    ...sec("Your friends", fr, (x) => [
      bt("Message", () => (location.hash = "#/m/" + x.name)),
      bt("Remove", fcall("frem", x.name, "Remove " + x.name + " from your friends?", "out"), "ghost fdim"),
    ]),
    ...sec("Sent requests", sn, (x) => [h("span", { class: "fpend" }, "Pending"), bt("Cancel", fcall("frem", x.name, "Cancel your request to " + x.name + "?", "out"), "ghost")]),
    !list.length ? emp("users", "No friends yet", "Search for a username above to send a request.") : null,
  ]);
}
function themePick() {
  let cur = "auto";
  try {
    cur = localStorage.getItem("mq-theme") || "auto";
  } catch (e) {}
  const row = h("div", { class: "row" }),
    set = (k) => {
      try {
        k === "auto" ? localStorage.removeItem("mq-theme") : localStorage.setItem("mq-theme", k);
      } catch (e) {}
      k === "auto" ? delete document.documentElement.dataset.theme : (document.documentElement.dataset.theme = k);
      pforce();
      [...row.children].forEach((b) => b.setAttribute("aria-pressed", b.dataset.k === k));
    };
  [
    ["auto", "Auto"],
    ["light", "Light"],
    ["dark", "Dark"],
  ].forEach(([k, l]) =>
    row.append(
      h("button", { type: "button", class: "ghost", "data-k": k, "aria-pressed": cur === k, onclick: () => set(k) }, l),
    ),
  );
  return row;
}
/* text size and reduce motion: saved on this device only (like the theme); html[data-ts] scales all text, html[data-motion=reduce] switches animation off */
function textSizePick() {
  const SZ = [["", "Default", 16], ["s", "Small", 14], ["l", "Large", 19], ["xl", "Largest", 22]];
  let cur = "";
  try {
    cur = localStorage.getItem("mq-ts") || "";
  } catch (e) {}
  const row = h("div", { class: "row tsrow", role: "group", "aria-label": "Text size" }),
    set = (k) => {
      try {
        k ? localStorage.setItem("mq-ts", k) : localStorage.removeItem("mq-ts");
      } catch (e) {}
      k ? (document.documentElement.dataset.ts = k) : delete document.documentElement.dataset.ts;
      [...row.children].forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.k === k)));
    };
  SZ.forEach(([k, l, px]) =>
    row.append(h("button", { type: "button", class: "ghost tsb", "data-k": k, "aria-pressed": String(cur === k), "aria-label": l + " text", onclick: () => set(k) }, h("span", { style: "font-size:" + px + "px", "aria-hidden": "true" }, "Aa"), h("small", {}, l))),
  );
  return h("div", { class: "setrow" }, h("b", { style: "display:block;margin-bottom:8px" }, "Text size"), row, h("p", { class: "hint" }, "Makes text bigger or smaller across Masque. Saved on this device."));
}
function soundPick() {
  const c = h("input", { type: "checkbox", style: "width:auto" }),
    r = h("input", { type: "range", min: "0", max: "100", step: "5", "aria-label": "Sound volume", style: "width:100%;max-width:240px" }),
    t = h("button", { type: "button", class: "ghost", style: "margin-top:6px" }, "Play notification sound");
  c.checked = SFX.on();
  r.value = String(Math.round(SFX.vol() * 100));
  r.disabled = t.disabled = !c.checked;
  c.onchange = () => {
    SFX.set(c.checked);
    r.disabled = t.disabled = !c.checked;
    if (c.checked) {
      SFX.wake();
      setTimeout(() => SFX.play("notif", 1), 60);
    }
  };
  r.oninput = () => SFX.setVol(r.value / 100);
  t.onclick = () => {
    SFX.wake();
    setTimeout(() => SFX.play("notif", 1), 40);
  };
  return h("div", { class: "setrow" }, h("label", { class: "chk" }, c, " Sounds"), h("p", { class: "hint" }, "Soft sounds for notifications, incoming messages and sending messages. Saved on this device."), r, h("div", {}, t));
}
function motionPick() {
  let on = false;
  try {
    on = localStorage.getItem("mq-rm") === "1";
  } catch (e) {}
  const c = h("input", { type: "checkbox", style: "width:auto" }),
    st = h("small", { class: "hint", role: "status" });
  c.checked = on || document.documentElement.dataset.motion === "reduce";
  c.onchange = () => {
    try {
      c.checked ? localStorage.setItem("mq-rm", "1") : localStorage.removeItem("mq-rm");
    } catch (e) {}
    c.checked ? (document.documentElement.dataset.motion = "reduce") : delete document.documentElement.dataset.motion;
    st.textContent = c.checked ? "Animations are off." : mm0("(prefers-reduced-motion: reduce)") ? "Your device already asks for less motion, so it stays calm." : "Animations are back on.";
  };
  return h("div", { class: "setrow" }, h("label", { class: "chk" }, c, " Reduce motion"), h("p", { class: "hint" }, "Stops the moving flames, bats, glows, confetti and slide animations. Saved on this device. If your device already asks for less motion, Masque follows that too."), st);
}
const mm0 = (q) => matchMedia(q).matches;
function delForm() {
  const w = h("input", {
      type: "password",
      placeholder: "Your password",
      "aria-label": "Password to confirm",
      autocomplete: "current-password",
    }),
    e = h("p", { class: "err", role: "alert" });
  return h(
    "div",
    { class: "form" },
    h(
      "p",
      { class: "hint" },
      "This permanently deletes your account, posts, photos, comments, likes, messages and friendships. It cannot be undone.",
    ),
    w,
    e,
    h(
      "button",
      {
        type: "button",
        class: "btn danger",
        onclick: async () => {
          if (!w.value) {
            e.textContent = "Enter your password to confirm.";
            return;
          }
          if (
            !(await cbox(
              "Delete your account forever? This removes your posts, photos, comments, likes, messages and friendships and cannot be undone.",
            ))
          )
            return;
          try {
            await api("delacct", fd({ pw: w.value }));
            M = null;
            T = (await api("me")).csrf;
            location.hash = "";
            auth();
          } catch (x) {
            e.textContent = x.e || "Could not delete the account.";
          }
        },
      },
      "Delete my account",
    ),
  );
}
/* start */
const dec = (s) => {
  try {
    return decodeURIComponent(s);
  } catch (e) {
    return s;
  }
};
/* follows: one way, instant, public accounts only (a private account only takes friend requests) */
function followBtn(u) {
  if (+u.priv) return [];
  return [
    +u.fol
      ? h("button", { class: "ghost folb", onclick: fcall("unfol", u.name, "Unfollow " + dn(u) + "?") }, ic("check", 16), h("span", {}, "Following"))
      : h("button", { class: "ghost folb", onclick: fcall("fol", u.name) }, "Follow"),
  ];
}
/* the people who follow someone, or the people they follow, opened from the counts on a public profile */
function followList(u, kind) {
  sheet(kind === "followers" ? "Followers" : "Following", (close) => {
    const box = h("div", { class: "fof" }, h("p", { class: "hint" }, "Loading\u2026"));
    api("flist", null, "&k=" + kind + "&u=" + encodeURIComponent(u.name))
      .then((r) => {
        const L = r.list || [];
        rc(
          box,
          ...(L.length
            ? L.map((x) =>
                h(
                  "button",
                  {
                    type: "button",
                    class: "chat",
                    onclick: () => {
                      close();
                      location.hash = "#/u/" + x.name;
                    },
                  },
                  av(x, 44),
                  h(
                    "div",
                    { class: "cx" },
                    h("b", {}, dn(x)),
                    +x.you ? h("span", { class: "hint" }, "You") : +x.fy ? h("span", { class: "fofm" }, ic("check", 12), "Following") : null,
                  ),
                ),
              )
            : [h("p", { class: "hint" }, kind === "followers" ? "No followers yet." : "Not following anyone yet.")]),
        );
      })
      .catch((e) => rc(box, h("p", { class: "err", role: "alert" }, (e && e.e) || "Could not load the list.")));
    return box;
  });
}
/* someone's friends, opened from the "N friends" count on their profile: mutual friends are marked and listed first */
function friendsOf(u) {
  sheet(dn(u) + "\u2019s friends", (close) => {
    const box = h("div", { class: "fof" }, h("p", { class: "hint" }, "Loading\u2026"));
    api("ufriends", null, "&u=" + encodeURIComponent(u.name))
      .then((r) => {
        const L = r.list || [];
        rc(
          box,
          h(
            "p",
            { class: "hint fofs" },
            L.length
              ? +r.mutual
                ? r.mutual + (+r.mutual === 1 ? " mutual friend" : " mutual friends")
                : "No mutual friends yet."
              : "",
          ),
          ...(L.length
            ? L.map((x) =>
                h(
                  "button",
                  {
                    type: "button",
                    class: "chat",
                    onclick: () => {
                      close();
                      location.hash = "#/u/" + x.name;
                    },
                  },
                  av(x, 44),
                  h(
                    "div",
                    { class: "cx" },
                    h("b", {}, dn(x)),
                    +x.you
                      ? h("span", { class: "hint" }, "You")
                      : +x.mu
                        ? h("span", { class: "fofm" }, ic("check", 12), "Mutual")
                        : null,
                  ),
                ),
              )
            : [h("p", { class: "hint" }, "No friends to show yet.")]),
        );
      })
      .catch((e) => rc(box, h("p", { class: "err", role: "alert" }, (e && e.e) || "Could not load friends.")));
    return box;
  });
}
/* Explore: "People you may know" (same suggestions as the welcome card); the whole section disappears when there is no one to suggest */
function xPeople() {
  const sec = h("section", { class: "xppl" }, h("h3", { class: "vt fsh" }, h("span", {}, "People you may know")));
  sec.append(sugList(4, () => sec.remove()));
  return sec;
}
async function explore() {
  const { tags } = await api("tags");
  const q = h("input", {
      type: "search",
      class: "xsearch",
      placeholder: "Search posts or people\u2026",
      "aria-label": "Search",
      autocomplete: "off",
      autocapitalize: "none",
      enterkeyhint: "search",
    }),
    res = h("div");
  let t,
    seq = 0;
  q.onkeydown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const v = q.value.trim();
      if (v) {
        xrecAdd("q", v);
        location.hash = "#/s/" + encodeURIComponent(v);
      }
    }
  };
  q.oninput = () => {
    clearTimeout(t);
    const v = q.value.trim(),
      my = ++seq;
    if (!v) {
      showRecent();
      return;
    }
    t = setTimeout(async () => {
      try {
        const { users, tags: tg } = await api("find", null, "&tg=1&q=" + encodeURIComponent(v));
        if (my !== seq) return;
        const go = (to, t, w, l) => {
          xrecAdd(t || "q", w || v, l);
          location.hash = to;
        };
        /* a few matching posts, shown right under the people (the full list is one tap away). Uses the normal feed search, so privacy rules are the same. */
        const posts = h("div", { class: "sposts" });
        api("feed", null, "&s=" + encodeURIComponent(v))
          .then((fr) => {
            if (my !== seq) return;
            const L = (fr.posts || []).filter((p) => (p.cap || "").trim()).slice(0, 3);
            if (!L.length) return;
            posts.replaceChildren(
              h("h3", { class: "vt fsh" }, h("span", {}, "Posts")),
              ...L.map((p) => {
                const t = String(p.cap).replace(/\s+/g, " ").trim(),
                  i = t.toLowerCase().indexOf(v.toLowerCase().replace(/^#/, "")),
                  a = Math.max(0, i - 40),
                  sn = (a ? "\u2026" : "") + t.slice(a, a + 120) + (a + 120 < t.length ? "\u2026" : "");
                return h(
                  "button",
                  { class: "chat", type: "button", onclick: () => go("#/p/" + p.id) },
                  av(p, 44),
                  h("div", { class: "cx" }, h("b", {}, p.name ? dn(p) : "Someone"), h("small", { class: "hint spsn" }, sn)),
                );
              }),
            );
          })
          .catch(() => {});
        const tagBlock =
            tg && tg.length
              ? [
                  h("h3", { class: "vt fsh" }, h("span", {}, "Tags")),
                  h(
                    "div",
                    {},
                    ...tg.map((x) =>
                      h("button", { class: "chip", onclick: () => go("#/t/" + x.tag, "t", x.tag) }, "#" + x.tag + " \u00b7 " + x.n),
                    ),
                  ),
                ]
              : [],
          peopleBlock = users.length
            ? [
                h("h3", { class: "vt fsh" }, h("span", {}, "People")),
                ...users.map((u) =>
                  h(
                    "button",
                    { class: "chat", onclick: () => go("#/u/" + u.name, "u", u.name, dn(u)) },
                    av(u, 44),
                    h("div", { class: "cx" }, h("b", {}, dn(u))),
                  ),
                ),
              ]
            : [];
        res.replaceChildren(
          ...(v[0] === "#" ? [...tagBlock, ...peopleBlock] : [...peopleBlock, ...tagBlock]),
          ...(tagBlock.length || peopleBlock.length ? [] : [h("p", { class: "hint" }, "No people or tags match. You can still search posts.")]),
          posts,
          h(
            "button",
            { class: "ghost", style: "width:100%;margin-top:8px", onclick: () => go("#/s/" + encodeURIComponent(v)) },
            "Search posts for \u201c" + v + "\u201d",
          ),
        );
      } catch (e) {
        if (my === seq) res.replaceChildren(h("p", { class: "hint" }, "Search failed. Try again."));
      }
    }, 250);
  };
  const showRecent = () => {
    const a = xrecGet();
    if (!a.length) {
      res.replaceChildren();
      return;
    }
    const lab = (x) => (x.t === "t" ? "#" + x.v : x.t === "u" ? x.l || x.v : x.v);
    res.replaceChildren(
      h(
        "div",
        { class: "row", style: "justify-content:space-between;align-items:center" },
        h("h3", { class: "vt" }, "Recent searches"),
        h(
          "button",
          {
            class: "ghost",
            type: "button",
            onclick: () => {
              xrecClear();
              recentClear();
              showRecent();
            },
          },
          "Clear",
        ),
      ),
      h(
        "div",
        {},
        ...a.map((x) =>
          h(
            "span",
            { class: "chip xrc" },
            h(
              "button",
              {
                type: "button",
                class: "xrl",
                onclick: () => {
                  if (x.t === "t") location.hash = "#/t/" + x.v;
                  else if (x.t === "u") location.hash = "#/u/" + x.v;
                  else {
                    q.value = x.v;
                    q.dispatchEvent(new Event("input"));
                    q.focus();
                  }
                },
              },
              lab(x),
            ),
            h(
              "button",
              {
                type: "button",
                class: "xrx",
                "aria-label": "Remove " + lab(x) + " from recent searches",
                onclick: () => {
                  xrecDel(x.t, x.v);
                  showRecent();
                },
              },
              ic("close", 12),
            ),
          ),
        ),
      ),
    );
  };
  showRecent();
  shell([
    big("Explore"),
    q,
    res,
    xPeople(),
    h("h3", { class: "vt fsh" }, h("span", {}, "Trending this week")),
    tags.length
      ? h(
          "ol",
          { class: "xtrend" },
          ...tags.map((x, i) =>
            h(
              "li",
              {},
              h(
                "button",
                { type: "button", class: "xtr" + (i < 3 ? " top" : ""), onclick: () => (location.hash = "#/t/" + x.tag) },
                h("i", { class: "xrk" }, String(i + 1)),
                h("span", { class: "xtg" }, "#" + x.tag),
                h("small", { class: "hint" }, x.n + (+x.n === 1 ? " post" : " posts")),
                h("span", { class: "xch", "aria-hidden": "true" }, "\u203a"),
              ),
            ),
          ),
        )
      : h("div", { class: "xempty" }, h("b", {}, "No trending tags yet"), h("span", {}, "Tags people use in their posts will show up here.")),
  ]);
}
async function results(title, q) {
  const r = await api("feed", null, q);
  shell([
    big(title, "sm"),
    h(
      "button",
      { class: "ghost", style: "margin-bottom:14px", onclick: () => (location.hash = /&pd=/.test(q) ? "#/" : "#/x") },
      /&pd=/.test(q) ? "\u2190 Home" : "\u2190 Explore",
    ),
    feedBox(q, r, emp("search", "Nothing found", "Try a different word or tag.")),
  ]);
}
/* maintenance mode: everyone except admins sees the admin's message instead of the site. Nobody is signed out; the page checks every 15 s and goes back to the site when it ends. */
let MT = { on: 0, msg: "" },
  MAINT = 0,
  MTI = 0;
const MTDEF = "Masque is down for maintenance. We'll be back soon.";
const mtBanner = () =>
  M && M.admin && +MT.on
    ? h(
        "div",
        { class: "sbanner", role: "status" },
        h("span", {}, "Maintenance mode is on: only admins can use Masque right now."),
        h("button", { type: "button", class: "ghost sapp", onclick: maintSheet }, "Manage"),
      )
    : null;
function maint(msg) {
  clearInterval(POLL);
  if (MAINT) {
    const p = $("#mtmsg");
    if (p) p.textContent = msg || MTDEF;
    return;
  }
  MAINT = 1;
  setPT(null);
  const t = h("p", { id: "mtmsg", class: "sub" }, msg || MTDEF);
  let taps = 0,
    tt = 0;
  $("#app").replaceChildren(
    h(
      "div",
      { class: "auth" },
      h(
        "h1",
        {
          class: "logo",
          "aria-label": "Masque",
          onclick: () => {
            clearTimeout(tt);
            if (++taps >= 5) {
              taps = 0;
              adminLogin();
              return;
            }
            tt = setTimeout(() => (taps = 0), 2500);
          },
        },
        "Mas",
        h("i", {}, "que"),
      ),
      h(
        "div",
        { class: "card mtcard" },
        h("h3", {}, "Down for maintenance"),
        t,
        h(
          "p",
          { class: "hint" },
          M
            ? "You are still signed in. This page comes back by itself when we are done."
            : "This page comes back by itself when we are done.",
        ),
      ),
    ),
  );
  clearInterval(MTI);
  MTI = setInterval(async () => {
    try {
      const s = await api("mtstat");
      MT = s;
      if (!s.on) {
        clearInterval(MTI);
        MAINT = 0;
        try {
          const j = await api("me");
          M = j.me;
          T = j.csrf;
        } catch (e) {}
        route();
      } else {
        const p = $("#mtmsg");
        if (p) p.textContent = s.msg || MTDEF;
      }
    } catch (e) {}
  }, 15000);
}
/* hidden way in for admins while maintenance is on: tap the Masque logo 5 times, or open the site with #/admin on the end of the address */
function adminLogin() {
  MAINT = 0;
  clearInterval(MTI);
  try {
    history.replaceState(null, "", location.pathname + location.search);
  } catch (e) {}
  auth();
}
/* force refresh: an admin bumps a version token (api "rfset"); every open page polls "rfstat", and when the token is not the one it loaded with it covers the screen with the admin's message and a spinner, clears the app shell cache and reloads. */
let RF = { v: "", msg: "" },
  RFV = null,
  RFB = 0;
const RFDEF = "Masque is updating. This only takes a moment, and the page will reload by itself.";
function rfGo(s) {
  if (RFB) return;
  RFB = 1;
  clearInterval(POLL);
  document.body.append(
    h(
      "div",
      { id: "rfo", class: "rfo", role: "alertdialog", "aria-modal": "true", "aria-live": "assertive", "aria-label": "Updating Masque" },
      h("h1", { class: "logo", "aria-hidden": "true" }, "Mas", h("i", {}, "que")),
      h("span", { class: "rfs", "aria-hidden": "true" }),
      h("h2", {}, "Updating Masque"),
      h("p", { class: "sub" }, s.msg || RFDEF),
    ),
  );
  /* a few seconds to read the message, plus a random wait so everyone does not reload in the same instant */
  setTimeout(async () => {
    try {
      const rg = await navigator.serviceWorker.getRegistrations();
      await Promise.all(rg.map((r) => r.unregister()));
    } catch (e) {}
    try {
      const ks = await caches.keys();
      await Promise.all(ks.map((k) => caches.delete(k)));
    } catch (e) {}
    location.reload();
  }, 3000 + Math.random() * 2000);
}
async function rfCheck() {
  if (RFB) return;
  try {
    const s = await api("rfstat");
    RF = s;
    if (RFV === null) RFV = s.v;
    else if (s.v !== RFV) rfGo(s);
  } catch (e) {}
}
setInterval(rfCheck, 30000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) rfCheck();
});
addEventListener("online", rfCheck);
function rfSheet() {
  sheet("Force refresh", (close) => {
    const msg = h("textarea", { rows: 4, maxlength: 300, placeholder: RFDEF, "aria-label": "Message everyone will see" }),
      err = h("p", { class: "err", role: "alert" }),
      sv = h("button", { class: "ghost full", type: "submit" }, "Save message only"),
      go = h("button", { class: "btn full", type: "button" }, "Refresh everyone now");
    msg.value = RF.msg || "";
    const send = async (now) => {
      sv.disabled = go.disabled = true;
      err.textContent = "";
      try {
        RF = await api("rfset", fd({ msg: msg.value, go: now ? 1 : 0 }));
        close();
        if (now) rfCheck();
        return;
      } catch (x) {
        err.textContent = x.e || "Could not save.";
      }
      sv.disabled = go.disabled = false;
    };
    go.onclick = async () => {
      if (await cbox("Refresh everyone now? Everyone using Masque sees your message, then their page reloads. Yours reloads too.")) send(1);
    };
    return h(
      "form",
      {
        class: "form",
        onsubmit: (e) => {
          e.preventDefault();
          send(0);
        },
      },
      h(
        "p",
        { class: "hint" },
        "Use this after you push an update so nobody keeps running the old version. Everyone with Masque open sees a loading screen with the message below, then the page reloads by itself within a few seconds. Chat drafts are kept on each device; other unsent text, like a half-written post, can be lost.",
      ),
      h("label", { class: "f" }, "Message", msg),
      err,
      sv,
      go,
    );
  });
}
function maintSheet() {
  sheet("Maintenance mode", (close) => {
    const on = h("input", { type: "checkbox" }),
      msg = h("textarea", { rows: 4, maxlength: 300, placeholder: MTDEF, "aria-label": "Message everyone will see" }),
      err = h("p", { class: "err", role: "alert" }),
      b = h("button", { class: "btn full", type: "submit" }, "Save");
    on.checked = !!+MT.on;
    msg.value = MT.msg || "";
    return h(
      "form",
      {
        class: "form",
        onsubmit: async (e) => {
          e.preventDefault();
          b.disabled = true;
          err.textContent = "";
          try {
            MT = await api("mtset", fd({ on: on.checked ? 1 : 0, msg: msg.value }));
            close();
            route();
            return;
          } catch (x) {
            err.textContent = x.e || "Could not save.";
          }
          b.disabled = false;
        },
      },
      h(
        "p",
        { class: "hint" },
        "While this is on, everyone except admins sees your message and can't use the site. Nobody gets signed out, and people return on their own when you turn it off.",
      ),
      h("label", { class: "chk" }, on, " Maintenance mode is on"),
      h("label", { class: "f" }, "Message", msg),
      err,
      b,
    );
  });
}
/* Back to the feed: remember how far down Home you were when you open a post or profile, and put you back there (instead of at the top) when you come back to Home */
const homeHash = (x) => x === "" || x === "#" || x === "#/";
addEventListener(
  "click",
  () => {
    if (M && homeHash(location.hash)) FSCR = window.scrollY;
  },
  true,
);
/* shimmer placeholders shown while a page loads: list pages get chat-style rows, profiles get a banner + avatar, everything else keeps the two post cards */
const skRow = () => h("div", { class: "chat skr" }, h("i", { class: "sk av44" }), h("div", { class: "cx" }, h("i", { class: "sk t1" }), h("i", { class: "sk t2" })));
function skelFor(hs) {
  const rows = (n) => Array.from({ length: n }, skRow);
  if (/^#\/(m|f|n|x)$/.test(hs)) return h("div", { class: "skel", "aria-hidden": "true" }, h("i", { class: "sk ttl" }), ...rows(6));
  if (/^#\/(u|k)\//.test(hs))
    return h("div", { class: "skel", "aria-hidden": "true" }, h("i", { class: "sk ban" }), h("div", { class: "skp" }, h("i", { class: "sk av80" }), h("i", { class: "sk t1 w" }), h("i", { class: "sk t2" })), ...rows(2));
  return h(
    "div",
    { class: "skel", "aria-hidden": "true" },
    ...[0, 1].map(() => h("div", { class: "post" }, h("div", { class: "ph" }, h("i", { class: "sk c" }), h("i", { class: "sk l" })), h("i", { class: "sk img" }), h("i", { class: "sk l w" }))),
  );
}
async function route() {
  reelOff(!/^#\/p\//.test(location.hash));
  if (location.hash !== CURH) {
    FREST = homeHash(location.hash) && /^#\/(p|u|m|t|s|k|h|d)\//.test(CURH) ? FSCR : 0;
    REF = CURH;
    CURH = location.hash;
  }
  if (MAINT) {
    if (location.hash === "#/admin") adminLogin();
    return;
  }
  clearInterval(POLL);
  CUR = null;
  if (!M) {
    setPT(null);
    setTitle("Masque");
    auth();
    return;
  }
  setTitle(titleFor(location.hash));
  const sk = setTimeout(() => {
    const mn = $("#app main");
    if (mn) mn.replaceChildren(skelFor(location.hash));
  }, 300);
  const h1 = location.hash,
    m = h1.match(/^#\/u\/(\w+)/),
    t = h1.match(/^#\/m\/(\w+)/),
    pp = h1.match(/^#\/p\/(\d+)/),
    tg = h1.match(/^#\/t\/(\w+)/),
    sr = h1.match(/^#\/s\/(.+)/),
    gp = h1.match(/^#\/g\/(\d+)/),
    gj = h1.match(/^#\/gj\/([a-f0-9]+)/),
    dp = h1.match(/^#\/d\/(\d+)/),
    mq = h1.match(/^#\/k\/(\w+)/),
    hh = h1.match(/^#\/h\/(\d+)/),
    ro = h1.match(/^#\/o\/(\d+)/);
  if (!m) setPT(null);
  try {
    ro
      ? await roomPage(ro[1])
      : h1 === "#/o"
      ? await rooms()
      : hh
      ? await hl(hh[1])
      : mq
        ? await maskPage(mq[1])
        : dp
          ? await pday(dp[1])
          : gj
            ? await gjoinPage(gj[1])
            : gp
            ? await gthread(gp[1])
            : m
              ? await profile(m[1])
              : tg
                ? await results("#" + tg[1].toLowerCase(), "&t=" + tg[1])
                : sr
                  ? await results("Results for \u201c" + dec(sr[1]) + "\u201d", "&s=" + encodeURIComponent(dec(sr[1])))
                  : h1 === "#/x"
                    ? await explore()
                    : pp
                      ? await postPage(pp[1])
                      : t
                        ? await thread(t[1], /\/k$/.test(h1))
                        : h1 === "#/m"
                          ? await inbox()
                          : h1 === "#/f"
                            ? await friends()
                            : h1 === "#/dash"
                              ? await dashPage()
                              : h1 === "#/ausers"
                              ? await usersPage()
                              : h1 === "#/aposts"
                              ? await postsPage()
                              : h1 === "#/acomments"
                              ? await commentsPage()
                              : h1 === "#/r"
                              ? await reports()
                              : h1 === "#/w"
                                ? await words()
                                : h1 === "#/n"
                                  ? await notifs()
                                  : h1 === "#/saved"
                                    ? await saved()
                                    : h1.startsWith("#/settings")
                                      ? await settings()
                                      : await home();
  } catch (e) {
    const mn = $("#app main");
    if (mn)
      mn.replaceChildren(
        emp(
          "close",
          "Something went wrong",
          (e && e.e) || "Couldn\u2019t load this page.",
          h("button", { class: "ghost", onclick: () => route() }, "Try again"),
        ),
      );
  }
  clearTimeout(sk);
  SHOWN = location.hash;
  window.scrollTo(0, FREST);
  FREST = 0;
}
/* live updates: one small request every few seconds (faster while a chat is open) asks the server what changed. Badges update on their own, and the open chat, the inbox and the notifications page refresh when something new arrives. It pauses while the tab is hidden and catches up the moment you come back. */
/* pop-up banner for a new message: tap it to open the chat, swipe it away (up or sideways) to dismiss, Reply answers without leaving the page. It fades by itself after a few seconds unless you hover or are typing. */
function leave(el) {
  el.style.height = el.offsetHeight + "px";
  el.style.pointerEvents = "none";
  void el.offsetHeight;
  el.classList.add("out");
  setTimeout(() => el.remove(), 320);
}
function toast(o) {
  let box = $("#toasts");
  if (!box) {
    box = h("div", { id: "toasts", class: "toasts", "aria-live": "polite" });
    document.body.append(box);
  }
  if (SEENT.has(o.key)) return;
  SEENT.add(o.key);
  if (SEENT.size > 200) SEENT.delete(SEENT.values().next().value);
  [...box.children].filter((x) => x.dataset.chat === o.chat).forEach((x) => x.remove());
  let tm = 0,
    gone = false;
  const out = h("p", { class: "hint terr", role: "alert", hidden: "" }),
    inp = h("input", { placeholder: "Reply…", maxlength: 500, "aria-label": "Reply", autocomplete: "off" }),
    sendB = h("button", { class: "btn", type: "submit" }, "Send"),
    rep = h(
      "form",
      {
        class: "trep",
        hidden: "",
        onsubmit: async (e) => {
          e.preventDefault();
          const v = inp.value.trim();
          if (!v) return;
          sendB.disabled = true;
          out.hidden = true;
          try {
            await o.reply(v);
            inp.value = "";
            out.textContent = "Sent";
            out.hidden = false;
            clearTimeout(tm);
            tm = setTimeout(bye, 900);
          } catch (x) {
            out.textContent = x.e || "Could not send.";
            out.hidden = false;
            sendB.disabled = false;
          }
        },
      },
      inp,
      sendB,
    ),
    main = h(
      "div",
      { class: "tmain", role: "button", tabindex: "0", "aria-label": "Open chat with " + o.title },
      o.av,
      h(
        "div",
        { class: "tx" },
        h("b", {}, o.title),
        o.sub ? h("small", { class: "hint" }, o.sub) : null,
        h("p", {}, o.body),
      ),
    ),
    rb = h(
      "button",
      {
        type: "button",
        class: "ghost",
        onclick: () => {
          rep.hidden = false;
          rb.hidden = true;
          clearTimeout(tm);
          inp.focus();
        },
      },
      "Reply",
    ),
    xb = h("button", { type: "button", class: "ghost", "aria-label": "Dismiss", onclick: () => bye() }, "Dismiss"),
    el = h(
      "div",
      { class: "toast", role: "group", "data-chat": o.chat },
      main,
      rep,
      out,
      h("div", { class: "tbar" }, rb, xb),
    );
  const bye = () => {
      if (gone) return;
      gone = true;
      clearTimeout(tm);
      leave(el);
    },
    arm = () => {
      clearTimeout(tm);
      if (gone || el.matches(":hover") || el.contains(document.activeElement) || inp.value) return;
      tm = setTimeout(bye, 6000);
    },
    open = () => {
      bye();
      o.open();
    };
  el.addEventListener("mouseenter", () => clearTimeout(tm));
  el.addEventListener("mouseleave", arm);
  el.addEventListener("focusin", () => clearTimeout(tm));
  el.addEventListener("focusout", () => setTimeout(arm, 0));
  main.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open();
    }
  });
  let sx = 0,
    sy = 0,
    dx = 0,
    dy = 0,
    drag = false;
  main.addEventListener("pointerdown", (e) => {
    sx = e.clientX;
    sy = e.clientY;
    dx = dy = 0;
    drag = true;
    clearTimeout(tm);
    main.setPointerCapture(e.pointerId);
    el.classList.add("drag");
  });
  main.addEventListener("pointermove", (e) => {
    if (!drag) return;
    dx = e.clientX - sx;
    dy = Math.min(0, e.clientY - sy);
    el.style.transform = "translate(" + dx + "px," + dy + "px)";
    el.style.opacity = String(Math.max(0.25, 1 - Math.max(Math.abs(dx) / 240, -dy / 120)));
  });
  const end = () => {
    if (!drag) return;
    drag = false;
    el.classList.remove("drag");
    if (Math.abs(dx) < 6 && dy > -6) {
      el.style.transform = el.style.opacity = "";
      open();
      return;
    }
    if (Math.abs(dx) > 70 || dy < -40) {
      el.style.transform = "translate(" + (Math.abs(dx) > 70 ? dx * 3 : 0) + "px," + (dy < -40 ? -160 : dy) + "px)";
      el.style.opacity = "0";
      gone = true;
      clearTimeout(tm);
      leave(el);
    } else {
      el.style.transform = el.style.opacity = "";
      arm();
    }
  };
  main.addEventListener("pointerup", end);
  main.addEventListener("pointercancel", end);
  const was = new Map([...box.children].map((c) => [c, c.getBoundingClientRect().top]));
  box.prepend(el);
  {
    const live = [...box.children].filter((c) => !c.classList.contains("out"));
    live.slice(3).forEach(leave);
  }
  if (!matchMedia("(prefers-reduced-motion:reduce)").matches)
    for (const c of box.children) {
      if (c === el || !was.has(c) || c.classList.contains("out")) continue;
      const d = was.get(c) - c.getBoundingClientRect().top;
      if (d && c.animate)
        c.animate([{ translate: "0 " + d + "px" }, { translate: "0 0" }], {
          duration: 280,
          easing: "cubic-bezier(.2,.9,.3,1)",
        });
    }
  arm();
}
function showToasts(r) {
  const here = (n) => CUR && CUR.k === "d" && CUR.qs.includes("u=" + encodeURIComponent(n)),
    fresh = (t) => r.now - t.ts < 90;
  if ((r.toast || []).some(fresh) || (r.gtoast || []).some(fresh)) SFX.play("msg");
  for (const t of (r.toast || []).slice().reverse()) {
    if (!fresh(t)) continue;
    const mk = +t.fm,
      mine = +t.tm,
      nm = t.name;
    if (here(nm) && (/&as=1/.test(CUR.qs) ? 1 : 0) === mine) continue;
    toast({
      key: "d" + t.id,
      chat: "d:" + nm + ":" + mine,
      title: t.pn || t.nick || nm,
      sub: mk ? "Masque" : "",
      body: ptx(t.txt) || (+t.img ? "Photo" : ""),
      av: av({ avatar: t.avatar }, 40),
      open: () => {
        location.hash = "#/m/" + nm + (mine ? "/k" : "");
      },
      reply: async (v) => {
        const d = new FormData();
        d.append("to", nm);
        d.append("txt", v);
        if (mine) d.append("as", "mask");
        await api("send", d);
      SFX.play("send");
        api("thread", null, "&u=" + encodeURIComponent(nm) + (mine ? "&as=1" : "")).catch(() => {});
      },
    });
  }
  for (const t of (r.gtoast || []).slice().reverse()) {
    if (!fresh(t)) continue;
    if (CUR && CUR.k === "g" && CUR.qs === "&id=" + t.gid) continue;
    toast({
      key: "g" + t.id,
      chat: "g:" + t.gid,
      title: t.gname,
      sub: "",
      body: t.who + ": " + (ptx(t.txt) || (+t.img ? "Photo" : "")),
      av: gva({ avatar: t.gav }, 40),
      open: () => {
        location.hash = "#/g/" + t.gid;
      },
      reply: async (v) => {
        await api("gsend", fd({ gid: t.gid, txt: v }));
        api("gthread", null, "&id=" + t.gid).catch(() => {});
      },
    });
  }
}
async function liveTick() {
  if (!M || LV.busy || document.hidden) return;
  LV.busy = 1;
  try {
    const r = await api(
      "live",
      null,
      (CUR ? "&k=" + CUR.k + CUR.qs : "") +
        "&af=" +
        LV.af +
        "&gaf=" +
        LV.gaf +
        (Date.now() - LV.act > 3e5 ? "&idl=1" : "") +
        (location.hash === "#/m" ? "&inb=1" : ""),
    );
    LV.fail = 0;
    const sg = [r.n, r.r, r.o, r.og, r.mid, r.gmid, r.mv, r.nv, r.th, JSON.stringify(r.ty), r.st].join("|");
    LV.same = sg === LV.sg ? (LV.same || 0) + 1 : 0;
    LV.sg = sg;
    showToasts(r);
    if (LV.o != null && r.o > LV.o) SFX.play(r.og && !LV.og ? "gift" : "notif");
    LV.o = r.o;
    LV.og = r.og;
    LV.af = r.mid;
    LV.gaf = r.gmid;
    for (const [k, v] of [
      ["m", r.n],
      ["f", r.r],
      ["n", r.o],
      ["mn", r.n + r.o],
    ])
      document.querySelectorAll('[data-b="' + k + '"]').forEach((x) => {
          badgeSet(x, v);
          /* gold while a new gift is waiting among the unseen notifications; back to red once the notifications were looked at */
          x.classList.toggle("gold", !!(r.og && v && (k === "n" || k === "mn")));
        });
    const hs = location.hash,
      idle = !document.querySelector(".veil"),
      mv = r.mv + "|" + r.n;
    if (CUR && r.th != null && r.th !== CUR.sig) {
      CUR.sig = r.th;
      await CUR.sync();
    } else if (idle && hs === "#/m" && LV.mv != null && mv !== LV.mv) await inbox(true);
    else if (idle && hs === "#/n" && LV.nv != null && r.nv !== LV.nv) await notifs();
    if (CUR && CUR.ty && "ty" in r) CUR.ty(r.ty);
    if (CUR && CUR.st && r.st) CUR.st(r.st);
    if (r.sts)
      for (const [n, v] of Object.entries(r.sts))
        document.querySelectorAll(".pdot[data-u]").forEach((d) => {
          if (d.dataset.u === n) setDot(d, v);
        });
    LV.mv = mv;
    LV.nv = r.nv;
  } catch (e) {
    LV.fail++;
    if (e && e.s === 401) LV.fail = 0;
  }
  LV.busy = 0;
}
/* how long to wait before the next check: fast while you are using the page, slower when it is quiet or nothing is changing. The cap stays under the server's 45 s "online" window so your status stays right. */
function liveDelay() {
  if (LV.fail > 2) return Math.min(30000, 4000 * LV.fail);
  const q = Date.now() - LV.act;
  if (q > 3e5) return 20000;
  let d = CUR ? 2000 : 4000;
  if (q > 3e4) d *= 2;
  if (q > 1e4) {
    if (LV.same >= 5) d *= 1.5;
    if (LV.same >= 15) d *= 1.5;
  }
  return Math.min(d, CUR ? 6000 : 12000);
}
function liveLoop() {
  clearTimeout(LV.t);
  LV.t = setTimeout(
    async () => {
      await liveTick();
      liveLoop();
    },
    document.hidden ? 30000 : liveDelay(),
  );
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && M) {
    clearTimeout(LV.t);
    liveTick().then(liveLoop);
  }
});
window.addEventListener("online", () => {
  LV.fail = 0;
});
/* offline pill: says so right away when the connection drops (instead of only after something fails), and "Back online" for a moment after */
(() => {
  let el = null,
    tm = 0;
  const say = (off) => {
    clearTimeout(tm);
    if (!el) {
      el = h("p", { class: "offpill", role: "status", "aria-live": "polite", hidden: "" });
      document.body.append(el);
    }
    el.classList.toggle("ok", !off);
    el.textContent = off ? "You're offline. Some things won't load." : "Back online";
    el.hidden = false;
    if (!off) tm = setTimeout(() => (el.hidden = true), 2500);
  };
  addEventListener("offline", () => say(true));
  addEventListener("online", () => {
    if (el && !el.hidden) say(false);
  });
  if (navigator.onLine === false) say(true);
})();
["pointerdown", "pointermove", "keydown", "touchstart", "wheel", "scroll"].forEach((e) =>
  addEventListener(
    e,
    () => {
      const was = Date.now() - LV.act;
      LV.act = Date.now();
      if (was > 3e4 && M && !document.hidden && !LV.busy) {
        LV.same = 0;
        clearTimeout(LV.t);
        liveTick().then(liveLoop);
      }
    },
    { passive: true, capture: true },
  ),
);
liveLoop();
window.onhashchange = () => {
  if (MAINT) {
    if (location.hash === "#/admin") adminLogin();
    return;
  }
  M && route();
};
/* open a shared link: /u/name, /p/id, or the older ?u= / ?p= forms, then show it as the normal #/u/name or #/p/id view */
{
  const pm = location.pathname.slice(BASE.length).match(/^(u|p)\/([^\/]*)\/?$/),
    sp = new URLSearchParams(location.search);
  let k = null,
    v = null;
  if (pm) {
    k = pm[1];
    v = pm[2];
  } else if (sp.get("p")) {
    k = "p";
    v = sp.get("p");
  } else if (sp.get("u")) {
    k = "u";
    v = sp.get("u");
  }
  if (k && (k === "p" ? /^[0-9]{1,12}$/ : /^[A-Za-z0-9_]{3,20}$/).test(v)) {
    const free = !location.hash || location.hash === "#/";
    if (free) history.replaceState(null, "", (pm ? BASE : location.pathname) + "#/" + k + "/" + v);
    else if (pm) history.replaceState(null, "", BASE + location.hash);
  } else if (pm) history.replaceState(null, "", BASE + location.hash);
}
/* Show profiles and posts as /u/name and /p/id in the address bar (the #/ part stays after it for the app). Link previews (Discord, WhatsApp...) never see what comes after a #, so a copied /#/u/name link only ever shows the homepage card. */
function prettyUrl() {
  try {
    const m = location.hash.match(/^#\/(u|p)\/([^\/?#]+)$/),
      ok = m && (m[1] === "p" ? /^[0-9]{1,12}$/ : /^[A-Za-z0-9_]{3,20}$/).test(m[2]),
      path = ok ? BASE + m[1] + "/" + m[2] : BASE,
      sp = new URLSearchParams(location.search);
    sp.delete("u");
    sp.delete("p");
    const q = sp.toString() ? "?" + sp : "";
    if (location.pathname !== path || location.search !== q) history.replaceState(history.state, "", path + q + location.hash);
  } catch (e) {}
}
prettyUrl();
addEventListener("hashchange", prettyUrl);
/* Back / forward (phone back button, mouse side buttons, Alt+Arrow). prettyUrl rewrites the path to /u/name or /p/id, and browsers do not fire hashchange when the path differs between two history entries, so the page used to stay on the old screen. popstate always fires, so route from it when the hash changed and hashchange did not. */
addEventListener("popstate", () => {
  setTimeout(() => {
    if (M && !MAINT && location.hash !== CURH) route();
    prettyUrl();
  }, 40);
});
/* links from emails: ?mr=<token> resets a password, ?mv=<token> confirms a recovery email. The token is removed from the address bar at once. */
let MLINK = null;
{
  const sp = new URLSearchParams(location.search);
  for (const k of ["mr", "mv"]) {
    const t = sp.get(k) || "";
    if (/^[a-f0-9]{48}$/.test(t)) {
      MLINK = { k, t };
      break;
    }
  }
  if (MLINK || sp.has("mr") || sp.has("mv")) {
    try {
      history.replaceState(null, "", location.pathname + location.hash);
    } catch (e) {}
  }
}
(async () => {
  try {
    const j = await api("me");
    M = j.me;
    T = j.csrf;
    MT = j.mt || MT;
    MAILOK = +j.mailok || 0;
    if (j.rf) RF = j.rf, RFV = j.rf.v;
  } catch (e) {}
  try {
    if (MT.on && !(M && M.admin)) {
      maint(MT.msg);
      if (location.hash === "#/admin") adminLogin();
    } else if (MLINK) await mailLink();
    else await route();
  } finally {
    const sp = document.getElementById("splash");
    if (sp) {
      sp.classList.add("out");
      setTimeout(() => sp.remove(), 400);
    }
  }
})();

/* back to top */
/* pull to refresh (touch only). It re-runs the current page, like tapping the logo on Home.
   It never fights the browser's own pull-to-refresh: CSS turns that off (overscroll-behavior), and while a pull is ours we cancel the touch so the browser cannot start one either.
   It only starts at the very top of the page, on a mostly-vertical drag, on feed-like pages, and never inside sheets, the photo viewer, forms or chats. */
(() => {
  const OK = (h) => !h || /^#\/(f|m|n|r|saved|x)?$/.test(h) || /^#\/(u|p|t|s|k)\//.test(h),
    TH = 70,
    MAXP = 110,
    el = h("div", { class: "ptr", "aria-hidden": "true" }, h("span", { class: "ptri" })),
    SC = () => document.scrollingElement || document.documentElement;
  let y0 = 0,
    x0 = 0,
    on = 0,
    pull = 0,
    busy = 0,
    live = 0;
  document.body.append(el);
  const show = (d, anim) => {
      el.style.transition = anim ? "transform .25s cubic-bezier(.16,1,.3,1),opacity .2s" : "none";
      el.style.transform = "translate(-50%," + (d - 52) + "px)";
      el.style.opacity = String(Math.min(1, d / 40));
      el.classList.toggle("rdy", d >= TH);
      el.firstChild.style.transform = busy ? "" : "rotate(" + Math.round(d * 4) + "deg)";
    },
    end = (refresh) => {
      on = 0;
      live = 0;
      if (refresh && !busy) {
        busy = 1;
        el.classList.add("spin");
        show(TH - 8, 1);
        const t = Date.now();
        Promise.resolve()
          .then(() => route())
          .catch(() => {})
          .then(() => new Promise((r) => setTimeout(r, Math.max(0, 500 - (Date.now() - t)))))
          .then(() => {
            busy = 0;
            el.classList.remove("spin");
            show(0, 1);
          });
      } else if (!busy) show(0, 1);
      pull = 0;
    };
  addEventListener(
    "touchstart",
    (e) => {
      live = 0;
      on = 0;
      if (busy || !M || MAINT || e.touches.length !== 1 || SC().scrollTop > 0 || !OK(location.hash)) return;
      const t = e.target;
      if (t.closest && t.closest(".veil,.lb,.sheet,.tcard,input,textarea,select,[contenteditable],.gal,.nolock"))
        return;
      if (document.documentElement.classList.contains("nolock")) return;
      y0 = e.touches[0].clientY;
      x0 = e.touches[0].clientX;
      live = 1;
    },
    { passive: true },
  );
  addEventListener(
    "touchmove",
    (e) => {
      if (!live) return;
      const c = e.touches[0],
        dy = c.clientY - y0,
        dx = c.clientX - x0;
      if (!on) {
        if ((Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy)) || dy < -6 || SC().scrollTop > 0) {
          live = 0;
          return;
        }
        if (dy > 10 && dy > Math.abs(dx) * 1.6) on = 1;
        else return;
      }
      if (e.cancelable) e.preventDefault();
      pull = Math.min(MAXP, Math.pow(Math.max(0, dy - 10), 0.85));
      show(pull, 0);
    },
    { passive: false },
  );
  addEventListener("touchend", () => {
    if (on) end(pull >= TH);
    live = 0;
  });
  addEventListener("touchcancel", () => {
    if (on) end(0);
    live = 0;
  });
})();
(() => {
  const b = h(
    "button",
    {
      class: "totop",
      hidden: "",
      "aria-label": "Back to top",
      title: "Back to top",
      onclick: () =>
        scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion:reduce)").matches ? "auto" : "smooth" }),
    },
    ic("back", 20),
  );
  document.body.append(b);
  let on = false;
  addEventListener(
    "scroll",
    () => {
      const v = scrollY > 700;
      if (v !== on) {
        on = v;
        b.hidden = !v;
      }
    },
    { passive: true },
  );
})();

/* top bar stays put so the messages button never disappears */
/* error messages: whenever a form error (or toast reply status) gets text, it shakes in (errors) or fades in (everything else) */
(() => {
  const rm = matchMedia("(prefers-reduced-motion:reduce)"),
    fx = (el) => {
      const t = el.textContent.trim();
      if (!t || el.hidden || !el.animate || rm.matches) return;
      if (el.classList.contains("err") || (el.classList.contains("terr") && t !== "Sent"))
        el.animate(
          [
            { transform: "translateX(0)", opacity: 0 },
            { transform: "translateX(-7px)", opacity: 1, offset: 0.18 },
            { transform: "translateX(6px)", offset: 0.38 },
            { transform: "translateX(-4px)", offset: 0.58 },
            { transform: "translateX(2px)", offset: 0.78 },
            { transform: "none" },
          ],
          { duration: 420, easing: "ease-out" },
        );
      else
        el.animate(
          [
            { opacity: 0, transform: "translateY(-4px)" },
            { opacity: 1, transform: "none" },
          ],
          { duration: 220, easing: "ease-out" },
        );
    };
  new MutationObserver((ms) => {
    const set = new Set();
    for (const m of ms) {
      const n = m.target.nodeType === 1 ? m.target : m.target.parentElement,
        el = n && n.closest && n.closest(".err,.terr");
      if (el) set.add(el);
    }
    set.forEach(fx);
  }).observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ["hidden"],
  });
})();

/* banner frame "Match avatar": uses the same look as the avatar frame (the avatar's plain Ring is the banner's Line) */
function bfx(b, a) {
  return b !== "match" ? b : a === "ring" ? "line" : a || "";
}

/* the line shown above your anonymous question box (Settings) */
function askLine() {
  const i = h("input", {
      type: "text",
      maxlength: 80,
      placeholder: "Ask me anything",
      value: M.askp || "",
      "aria-label": "Question box prompt",
    }),
    st = h("small", { class: "hint", role: "status" });
  i.onchange = async () => {
    st.textContent = "";
    try {
      M = (await api("profile", fd({ askp: i.value }))).me;
      st.textContent = "Saved.";
    } catch (x) {
      st.textContent = x.e || "Could not save.";
    }
  };
  return h(
    "div",
    { class: "setrow" },
    h("label", { class: "f" }, "Question box prompt", i),
    h(
      "p",
      { class: "hint" },
      'The line shown above your anonymous question box, like "Ask me about my art". Leave it empty for the default title.',
    ),
    st,
  );
}

/* recent searches: kept only in this browser, per account. kind "" = Explore, "inbox" = Messages list, "chat" = search inside a chat */
const RK = (k) => (k ? "mq_recent:" + k + ":" : "mq_recent_") + ((M && M.name) || "");
function recentGet(k) {
  try {
    const a = JSON.parse(localStorage.getItem(RK(k)) || "[]");
    return Array.isArray(a) ? a.filter((x) => typeof x === "string").slice(0, 8) : [];
  } catch (e) {
    return [];
  }
}
function recentAdd(v, k) {
  v = String(v || "")
    .trim()
    .slice(0, 60);
  if (!v) return;
  try {
    const a = recentGet(k).filter((x) => x.toLowerCase() !== v.toLowerCase());
    a.unshift(v);
    localStorage.setItem(RK(k), JSON.stringify(a.slice(0, 8)));
  } catch (e) {}
}
function recentClear(k) {
  try {
    localStorage.removeItem(RK(k));
  } catch (e) {}
}
/* Explore history: what you opened (a person, a tag) or searched for, newest first, on this device only. Entries are {t: "q" search | "u" person | "t" tag, v: what to open, l: label}. Older plain-text history is picked up until the first change. */
const XRK = () => "mq_xrec:" + ((M && M.name) || "");
function xrecGet() {
  try {
    let a = JSON.parse(localStorage.getItem(XRK()) || "null");
    if (!Array.isArray(a)) a = recentGet().map((v) => ({ t: "q", v }));
    return a.filter((x) => x && typeof x.v === "string" && ["q", "u", "t"].includes(x.t)).slice(0, 8);
  } catch (e) {
    return [];
  }
}
function xrecSet(a) {
  try {
    localStorage.setItem(XRK(), JSON.stringify(a.slice(0, 8)));
  } catch (e) {}
}
function xrecAdd(t, v, l) {
  v = String(v || "").trim().slice(0, 60);
  if (!v) return;
  const a = xrecGet().filter((x) => !(x.t === t && x.v.toLowerCase() === v.toLowerCase()));
  a.unshift({ t, v, l: l ? String(l).slice(0, 60) : undefined });
  xrecSet(a);
}
function xrecDel(t, v) {
  xrecSet(xrecGet().filter((x) => !(x.t === t && x.v === v)));
}
function xrecClear() {
  xrecSet([]);
}
/* a "Recent searches" block with tappable chips and a Clear button; null when there is nothing saved */
function recentRow(k, pick, redraw) {
  const a = recentGet(k);
  if (!a.length) return null;
  return h(
    "div",
    { class: "recent" },
    h(
      "div",
      { class: "row", style: "justify-content:space-between;align-items:center" },
      h("h3", { class: "vt" }, "Recent searches"),
      h(
        "button",
        {
          class: "ghost recclr",
          type: "button",
          onclick: () => {
            recentClear(k);
            redraw();
          },
        },
        "Clear",
      ),
    ),
    h("div", {}, ...a.map((x) => h("button", { class: "chip", type: "button", onclick: () => pick(x) }, x))),
  );
}

/* phones: the top bar slides away while you scroll down and comes back as soon as you scroll up (or reach the top), so it stops eating screen space */
(() => {
  let ly = 0,
    busy = false;
  const root = document.documentElement,
    mob = matchMedia("(max-width:899px)");
  addEventListener(
    "scroll",
    () => {
      if (busy) return;
      busy = true;
      requestAnimationFrame(() => {
        busy = false;
        const y = Math.max(0, scrollY);
        if (!mob.matches || y <= 80 || y < ly - 6) root.classList.remove("hdr-off");
        else if (y > ly + 6) root.classList.add("hdr-off");
        ly = y;
      });
    },
    { passive: true },
  );
  addEventListener("hashchange", () => root.classList.remove("hdr-off"));
})();

/* phones: no pinch / double-tap page zoom except on a post's own page (#/p/<id>); the photo viewer keeps its own zoom. No long-press text highlight or callout menu either, except in text boxes. */
(() => {
  const root = document.documentElement,
    vp = document.querySelector('meta[name="viewport"]'),
    base = "width=device-width, initial-scale=1, viewport-fit=cover",
    sync = () => {
      const ok = /^#\/p\//.test(location.hash) || /\/p\/\d+\/?$/.test(location.pathname);
      root.classList.toggle("zoomok", ok);
      if (vp) vp.setAttribute("content", ok ? base + ", maximum-scale=5" : base + ", maximum-scale=1, user-scalable=no");
    };
  sync();
  addEventListener("hashchange", sync);
  ["gesturestart", "gesturechange", "gestureend"].forEach((n) =>
    document.addEventListener(n, (e) => !root.classList.contains("zoomok") && e.preventDefault(), { passive: false }),
  );
  document.addEventListener("contextmenu", (e) => {
    if (matchMedia("(pointer:coarse)").matches && !(e.target.closest && e.target.closest("input,textarea,[contenteditable],.rcode")))
      e.preventDefault();
  });
})();

/* keep the phone keyboard's autofill bar (saved passwords, cards, addresses) away from chat, comment, search and post boxes: every text box that does not set its own autocomplete (log-in and password fields do) is told "off", given a name that is not an address or card field, and marked as not-a-login for password managers */
(function () {
  const fix = (el) => {
    if (!el || el.nodeType !== 1) return;
    const list = el.matches && el.matches("input,textarea") ? [el] : el.querySelectorAll ? [...el.querySelectorAll("input,textarea")] : [];
    for (const i of list) {
      const t = (i.getAttribute("type") || "text").toLowerCase();
      if (!["text", "search", "", "url", "email", "tel"].includes(t) && i.tagName !== "TEXTAREA") continue;
      if (i.hasAttribute("autocomplete") && i.getAttribute("autocomplete") !== "off") continue;
      if (i.dataset.mqaf) continue;
      i.dataset.mqaf = "1";
      i.setAttribute("autocomplete", "off");
      i.setAttribute("data-lpignore", "true");
      i.setAttribute("data-1p-ignore", "");
      i.setAttribute("data-form-type", "other");
      if (!i.getAttribute("name")) i.setAttribute("name", "mq-" + Math.random().toString(36).slice(2, 8));
    }
  };
  fix(document.body);
  new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach(fix))).observe(document.documentElement, { childList: true, subtree: true });
})();


/* motion: an ember sweep + page rise on every route change, (posts no longer animate in while scrolling) */
try {
  const rm = matchMedia("(prefers-reduced-motion:reduce)"),
    root = document.documentElement,
    app = document.getElementById("app");
  let tm = 0;
  addEventListener("hashchange", () => {
    if (rm.matches || !app) return;
    root.classList.remove("rtw");
    app.classList.remove("rt");
    void root.offsetWidth;
    root.classList.add("rtw");
    app.classList.add("rt");
    clearTimeout(tm);
    tm = setTimeout(() => {
      root.classList.remove("rtw");
      app.classList.remove("rt");
    }, 750);
  });
  /* posts used to fade/slide in as they scrolled into view; that made the feed look like it was constantly reloading, so it is gone */
} catch (_) {}

/* Browser bar colour: the phone's address/status bar now follows the real header colour (white on light, near-black on dark), including when the
   theme is switched by hand in Settings. Before, the bar was black on light phones and beige on dark ones. */
(() => {
  const root = document.documentElement;
  let tc = null;
  const sync = () => {
    try {
      const c = getComputedStyle(root).getPropertyValue("--card").trim();
      if (!c) return;
      if (!tc) {
        document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.remove());
        tc = document.createElement("meta");
        tc.name = "theme-color";
        document.head.append(tc);
      }
      tc.content = c;
    } catch (e) {}
  };
  sync();
  new MutationObserver(sync).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
  try {
    const q = matchMedia("(prefers-color-scheme: dark)");
    q.addEventListener ? q.addEventListener("change", sync) : q.addListener(sync);
  } catch (e) {}
})();
