/* Vaani call widget: a floating "Talk to Aangan" button that opens a live voice call with the
   Vaani receptionist, right inside any dashboard page. Same backend as talk.html:
   POST /api/vaani/session -> {token, connection_url} -> LiveKit room in the browser.
   Drop-in:  <script src="vaani-call.js" defer></script>   (uses the page's CSS tokens if present) */
(() => {
  const LK_SRC = "https://cdn.jsdelivr.net/npm/livekit-client@2.9.0/dist/livekit-client.umd.js";
  const css = `
  .vc-fab{position:fixed;right:20px;bottom:20px;z-index:60;display:flex;align-items:center;gap:10px;border:0;cursor:pointer;
    padding:12px 18px 12px 12px;border-radius:999px;font:600 14px/1 "Instrument Sans",system-ui,sans-serif;
    color:#fff;background:var(--accent,#b24a22);box-shadow:0 12px 30px -12px rgba(178,74,34,.7)}
  .vc-fab:focus-visible{outline:3px solid var(--s1,#3b4fb8);outline-offset:3px}
  .vc-dot{width:26px;height:26px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#ffd9c4,#e07040 55%,#8a3214);
    box-shadow:0 0 0 0 rgba(255,255,255,.6);animation:vcPulse 2.4s infinite}
  @keyframes vcPulse{0%{box-shadow:0 0 0 0 rgba(255,255,255,.55)}70%{box-shadow:0 0 0 12px rgba(255,255,255,0)}100%{box-shadow:0 0 0 0 rgba(255,255,255,0)}}
  .vc-panel{position:fixed;right:20px;bottom:84px;z-index:61;width:min(380px,calc(100vw - 32px));max-height:min(640px,calc(100vh - 110px));
    display:flex;flex-direction:column;border-radius:22px;overflow:hidden;background:var(--surface-1,#faf6ef);color:var(--text-primary,#1f1a14);
    border:1px solid var(--hairline,#e3d9c8);box-shadow:0 30px 60px -30px rgba(0,0,0,.55);font-family:"Instrument Sans",system-ui,sans-serif;
    transform-origin:bottom right}
  .vc-panel[hidden]{display:none}
  .vc-head{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid var(--hairline,#e3d9c8)}
  .vc-head b{font-size:15px}.vc-head small{display:block;color:var(--text-muted,#7d7265);font-size:12px;margin-top:2px}
  .vc-x{border:0;background:none;color:var(--text-muted,#7d7265);font-size:22px;cursor:pointer;line-height:1;padding:4px 8px;border-radius:8px}
  .vc-body{padding:18px 16px 16px;display:flex;flex-direction:column;gap:14px;overflow:auto}
  .vc-langs{display:flex;gap:6px;align-self:center;background:var(--surface-2,#efe7d9);padding:4px;border-radius:999px}
  .vc-langs button{border:0;background:none;padding:6px 14px;border-radius:999px;cursor:pointer;color:var(--text-secondary,#5c5247);font:inherit;font-size:13px}
  .vc-langs button[aria-pressed=true]{background:var(--surface-1,#faf6ef);color:var(--text-primary,#1f1a14);font-weight:600}
  .vc-orb{width:132px;height:132px;align-self:center;border-radius:50%;border:0;cursor:pointer;position:relative;color:#fff;font-family:inherit;font-weight:600;font-size:13px;line-height:1.2;
    background:radial-gradient(circle at 35% 30%,#f3b392,#d0602f 50%,#7a2c10);box-shadow:0 20px 40px -18px rgba(208,96,47,.8);
    transition:transform .15s ease}
  .vc-orb:disabled{opacity:.45;cursor:not-allowed}
  .vc-orb::after{content:"";position:absolute;inset:-10px;border-radius:50%;border:2px solid var(--accent,#b24a22);opacity:var(--vc-ring,0);transform:scale(var(--vc-scale,1));transition:opacity .1s,transform .1s}
  .vc-consent{display:flex;gap:10px;font-size:13px;line-height:1.4;color:var(--text-secondary,#5c5247);background:var(--surface-2,#efe7d9);padding:10px 12px;border-radius:12px}
  .vc-consent input{margin-top:2px;accent-color:var(--accent,#b24a22)}
  .vc-status{font-size:13px;text-align:center;color:var(--text-secondary,#5c5247);min-height:18px}
  .vc-status.err{color:#c0392b}
  .vc-caps{border-top:1px solid var(--hairline,#e3d9c8);padding-top:10px;display:flex;flex-direction:column;gap:6px;font-size:13px;max-height:180px;overflow:auto}
  .vc-caps:empty::before{content:"Live captions appear here during the call.";color:var(--text-muted,#7d7265)}
  .vc-cap{padding:6px 10px;border-radius:12px;background:var(--surface-2,#efe7d9);align-self:flex-start;max-width:90%}
  .vc-cap.me{align-self:flex-end;background:color-mix(in srgb,var(--accent,#b24a22) 16%,transparent)}
  @media (prefers-reduced-motion:reduce){.vc-dot{animation:none}}`;

  const el = (tag, attrs = {}, html = "") => Object.assign(document.createElement(tag), attrs, html ? { innerHTML: html } : {});
  document.head.append(el("style", { textContent: css }));

  const fab = el("button", { className: "vc-fab", type: "button", ariaLabel: "Talk to the Aangan receptionist" },
    '<span class="vc-dot" aria-hidden="true"></span><span>Talk to Aangan</span>');
  const panel = el("section", { className: "vc-panel", hidden: true, role: "dialog", ariaLabel: "Live call with the Aangan receptionist" }, `
    <div class="vc-head"><div><b>Aangan receptionist</b><small>Live on Vaani · English or हिन्दी</small></div>
      <button class="vc-x" type="button" aria-label="Close">×</button></div>
    <div class="vc-body">
      <div class="vc-langs" role="group" aria-label="Language">
        <button type="button" data-l="en" aria-pressed="true">English</button><button type="button" data-l="hi" aria-pressed="false">हिन्दी</button></div>
      <button class="vc-orb" type="button" disabled>Start talking</button>
      <label class="vc-consent"><input type="checkbox"> <span>I understand I'm talking to an <b>AI assistant</b> and the call is <b>recorded</b> so a designer can follow up.</span></label>
      <div class="vc-status" aria-live="polite">Checking the line…</div>
      <div class="vc-caps" aria-live="polite"></div>
    </div>`);
  document.body.append(fab, panel);

  const $ = s => panel.querySelector(s);
  const orb = $(".vc-orb"), consent = $(".vc-consent input"), status = $(".vc-status"), caps = $(".vc-caps");
  let lang = "en", enabled = false, room = null, raf = 0;
  const say = (t, err) => { status.textContent = t; status.classList.toggle("err", !!err); };
  const refresh = () => { orb.disabled = !room && !(enabled && consent.checked); };

  function open(show) {
    panel.hidden = !show;
    fab.setAttribute("aria-expanded", String(show));
    if (show && window.gsap) gsap.fromTo(panel, { opacity: 0, y: 16, scale: .97 }, { opacity: 1, y: 0, scale: 1, duration: .35, ease: "power3.out" });
    if (show && !panel.dataset.checked) {
      panel.dataset.checked = "1";
      fetch("/api/vaani/status").then(r => r.json()).then(s => {
        enabled = !!s.enabled;
        say(enabled ? `Tick the box, then press Start. Up to ${s.max_minutes} minutes.` : "Online calling isn't switched on yet.", !enabled);
        refresh();
      }).catch(() => say("Couldn't reach the line.", true));
    }
  }
  fab.addEventListener("click", () => open(panel.hidden));
  $(".vc-x").addEventListener("click", () => open(false));
  addEventListener("keydown", e => { if (e.key === "Escape" && !panel.hidden) open(false); });
  consent.addEventListener("change", refresh);
  panel.querySelectorAll("[data-l]").forEach(b => b.addEventListener("click", () => {
    if (room) return;
    lang = b.dataset.l;
    panel.querySelectorAll("[data-l]").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
  }));

  const loadLK = () => window.LivekitClient ? Promise.resolve() : new Promise((ok, bad) => {
    const s = el("script", { src: LK_SRC, onload: ok, onerror: bad }); document.head.append(s);
  });

  function caption(segments, participant) {
    const me = participant && room && participant.identity === room.localParticipant.identity;
    for (const seg of segments) {
      let c = caps.querySelector(`[data-id="${CSS.escape(seg.id)}"]`);
      if (!c) { c = el("div", { className: "vc-cap" + (me ? " me" : "") }); c.dataset.id = seg.id; caps.append(c); }
      c.textContent = seg.text;
    }
    caps.scrollTop = caps.scrollHeight;
  }

  function meter() {
    if (!room) return;
    let level = room.localParticipant.audioLevel || 0;
    room.remoteParticipants.forEach(p => { level = Math.max(level, p.audioLevel || 0); });
    orb.style.setProperty("--vc-ring", Math.min(1, level * 3).toFixed(2));
    orb.style.setProperty("--vc-scale", (1 + Math.min(.12, level * .4)).toFixed(3));
    raf = requestAnimationFrame(meter);
  }

  async function start() {
    orb.disabled = true; say("Connecting…");
    try {
      await loadLK();
      const r = await fetch("/api/vaani/session", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language: lang }) });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "The line is busy.");
      const { Room, RoomEvent, Track } = LivekitClient;
      room = new Room({ adaptiveStream: true, dynacast: true });
      room.on(RoomEvent.TrackSubscribed, t => { if (t.kind === Track.Kind.Audio) { const a = t.attach(); a.hidden = true; document.body.append(a); } });
      room.on(RoomEvent.TranscriptionReceived, caption);
      room.on(RoomEvent.Disconnected, () => stop("Call ended. A designer will follow up."));
      await room.connect(data.connection_url, data.token);
      await room.localParticipant.setMicrophoneEnabled(true);
      orb.textContent = "End call"; orb.disabled = false; say("Connected. Go ahead and speak.");
      meter();
    } catch (e) {
      room = null; orb.textContent = "Start talking"; say(e.message || "Couldn't connect.", true); refresh();
    }
  }
  function stop(msg) {
    cancelAnimationFrame(raf);
    if (room) { const r = room; room = null; r.disconnect(); }
    orb.textContent = "Start talking"; orb.style.setProperty("--vc-ring", 0);
    say(msg || "Call ended."); refresh();
  }
  orb.addEventListener("click", () => room ? stop() : start());
  addEventListener("pagehide", () => room && room.disconnect());
})();
