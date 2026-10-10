/* Aangan Voice Desk dashboard. Vanilla JS + SVG, no dependencies.
   index.html: live data from /api/metrics + /api/leads.   demo.html: dashboard/demo-data.json (synthetic). */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const h = (tag, attrs = {}, kids = []) => {
    const svgTags = ["svg", "g", "path", "circle", "text", "line", "rect", "polyline", "polygon", "tspan", "title", "textPath"];
    const el = svgTags.includes(tag) ? document.createElementNS("http://www.w3.org/2000/svg", tag) : document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "text") el.textContent = v; else if (k === "html") el.innerHTML = v; else el.setAttribute(k, v);
    }
    (Array.isArray(kids) ? kids : [kids]).forEach(c => c != null && el.append(c.nodeType ? c : document.createTextNode(c)));
    return el;
  };
  const nf = new Intl.NumberFormat("en-IN");
  const fmtN = n => (n == null ? "–" : nf.format(Math.round(n)));
  const fmtINR = n => (n == null ? "unknown" : "₹" + new Intl.NumberFormat("en-IN", { maximumFractionDigits: n < 100 ? 1 : 0 }).format(n));
  const fmtMin = m => {
    if (m == null) return { v: "–", u: "" };
    if (m < 90) return { v: Math.round(m), u: "min" };
    if (m < 60 * 36) return { v: (m / 60).toFixed(m < 600 ? 1 : 0), u: "hours" };
    return { v: (m / 1440).toFixed(1), u: "days" };
  };
  const pct = (a, b) => (b ? Math.round((100 * a) / b) : 0);
  const hh = x => String(x).padStart(2, "0") + ":00";
  const OUTCOME = [ // fixed order = fixed colour slot, never cycled
    ["QUALIFIED", "Qualified → designer", "var(--s1)"], ["ASK", "Details missing → callback", "var(--s2)"],
    ["NURTURE", "Timeline too tight, can move", "var(--s3)"], ["DECLINE", "Declined politely", "var(--s4)"],
    ["ESCALATE", "Existing client escalated", "var(--s5)"]];
  const REASON = { service_area: "Outside Pune / PCMC", real_project: "Not a design + execution project", timeline: "Timeline under 10 weeks",
    budget: "Budget clearly below scope", decision_maker: "No decision-maker" };

  // ---------------------------------------------------------------- tooltip
  const tip = h("div", { class: "tip", role: "tooltip" });
  document.body.append(tip);
  const showTip = (e, html) => { tip.innerHTML = html; tip.style.opacity = 1; moveTip(e); };
  const moveTip = e => {
    const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8), y = Math.min(e.clientY + 14, innerHeight - tip.offsetHeight - 8);
    tip.style.left = x + "px"; tip.style.top = y + "px";
  };
  const hideTip = () => (tip.style.opacity = 0);
  const hover = (el, html) => {
    el.addEventListener("mouseenter", e => showTip(e, html)); el.addEventListener("mousemove", moveTip);
    el.addEventListener("mouseleave", hideTip);
  };

  // ---------------------------------------------------------------- card helpers
  function card(span, title, sub, body, table) {
    const toggle = table ? h("button", { class: "tbl-toggle", type: "button", "aria-expanded": "false", text: "Table" }) : null;
    const tbl = table ? h("div", { class: "data-table scroll-x", hidden: "" }, table) : null;
    if (toggle) toggle.onclick = () => {
      const open = tbl.hasAttribute("hidden"); tbl.toggleAttribute("hidden", !open);
      toggle.setAttribute("aria-expanded", String(open)); toggle.textContent = open ? "Chart" : "Table";
      body.toggleAttribute("hidden", open);
    };
    return h("section", { class: `card span-${span}` }, [
      h("div", { class: "card-head" }, [h("div", {}, [h("h2", { text: title }), sub ? h("p", { class: "sub", text: sub }) : null]), toggle]),
      body, tbl]);
  }
  const table = (cols, rows) => h("table", {}, [
    h("thead", {}, h("tr", {}, cols.map((c, i) => h("th", { class: i ? "num" : null, text: c })))),
    h("tbody", {}, rows.map(r => h("tr", {}, r.map((c, i) => h("td", { class: i ? "num" : null, text: c })))))]);

  // ---------------------------------------------------------------- hero
  function hero(m) {
    const t = m.time_to_claim, all = fmtMin(t.call_to_claim.median_min);
    const off = fmtMin(t.call_to_claim_office_hours?.median_min), aft = fmtMin(t.call_to_claim_after_hours?.median_min);
    const w60 = t.call_to_claim.within_60_min_pct;
    return h("section", { class: "card span-12" }, h("div", { class: "hero" }, [
      h("div", {}, [
        h("div", { class: "hero-label", text: "Median time from a caller hanging up to a designer claiming the lead" }),
        h("div", { class: "hero-num" }, [String(all.v), h("small", { text: all.u })]),
        h("p", { class: "hero-note", text: w60 == null ? "No claimed leads in this period yet." :
          `${w60}% of claimed leads were picked up within an hour, the window in which Nikhil's own numbers show a 4× conversion rate. ${t.unclaimed ? t.unclaimed + " handed-over lead" + (t.unclaimed > 1 ? "s are" : " is") + " still unclaimed." : "Every handed-over lead was claimed."}` })]),
      h("div", { class: "split" }, [
        h("div", { class: "tile" }, [h("div", { class: "k", text: "Calls in office hours" }),
          h("div", { class: "v", text: `${off.v} ${off.u}` }), h("div", { class: "d", text: `${t.call_to_claim_office_hours?.n ?? 0} claimed leads` })]),
        h("div", { class: "tile" }, [h("div", { class: "k", text: "Calls after hours" }),
          h("div", { class: "v", text: `${aft.v} ${aft.u}` }), h("div", { class: "d", text: `${t.call_to_claim_after_hours?.n ?? 0} claimed: they wait for the morning` })])])]));
  }

  function stat(span, k, v, d) {
    return h("section", { class: `card stat span-${span}` }, [h("div", { class: "k", text: k }), h("div", { class: "v", text: v }), d ? h("div", { class: "d", text: d }) : null]);
  }

  // ---------------------------------------------------------------- the 24-hour dial
  function dial(m) {
    const all = m.by_hour, q = m.qualified_by_hour || Array(24).fill(0);
    const S = 560, C = S / 2, r0 = 128, rMax = 238, max = Math.max(1, ...all);
    const open = 10, close = 19, quietFrom = 21, quietTo = 9;
    const ang = hr => (hr / 24) * 2 * Math.PI - Math.PI / 2;
    const pt = (r, a) => [C + r * Math.cos(a), C + r * Math.sin(a)];
    const wedge = (ra, rb, a0, a1) => {
      const [x0, y0] = pt(ra, a0), [x1, y1] = pt(rb, a0), [x2, y2] = pt(rb, a1), [x3, y3] = pt(ra, a1), big = a1 - a0 > Math.PI ? 1 : 0;
      return `M${x0} ${y0}L${x1} ${y1}A${rb} ${rb} 0 ${big} 1 ${x2} ${y2}L${x3} ${y3}A${ra} ${ra} 0 ${big} 0 ${x0} ${y0}Z`;
    };
    const arc = (r, a0, a1) => { const [x0, y0] = pt(r, a0), [x1, y1] = pt(r, a1); return `M${x0} ${y0}A${r} ${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${x1} ${y1}`; };
    const svg = h("svg", { class: "dial", viewBox: `0 0 ${S} ${S}`, role: "img",
      "aria-label": `Calls by hour of day. ${m.after_hours.share_pct}% arrive outside office hours ${m.after_hours.office_hours}.` });
    // office-hours band and quiet-hours band, inside the bars
    svg.append(h("path", { d: wedge(r0 - 30, r0 - 8, ang(open), ang(close)), fill: "var(--office)" }));
    svg.append(h("path", { d: wedge(r0 - 30, r0 - 8, ang(quietFrom), ang(24 + quietTo)), fill: "var(--night)" }));
    const labelOnArc = (id, r, a0, a1, text) => {
      const mid = (a0 + a1) / 2, bottom = Math.sin(mid) > 0.2;
      let d = arc(r, a0, a1);
      if (bottom) { const [x0, y0] = pt(r, a1), [x1, y1] = pt(r, a0); d = `M${x0} ${y0}A${r} ${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 0 ${x1} ${y1}`; r += 0; }
      svg.append(h("path", { id, d, fill: "none" }));
      svg.append(h("text", { class: "band-label", "text-anchor": "middle" }, h("textPath", { href: `#${id}`, startOffset: "50%", text })));
    };
    labelOnArc("arc-office", r0 - 15 + 4, ang(open), ang(close), "Front desk 10:00–19:00");
    labelOnArc("arc-quiet", r0 - 15, ang(quietFrom), ang(24 + quietTo), "No callbacks 21:00–09:00");
    // gridline rings
    [0.5, 1].forEach(f => svg.append(h("circle", { cx: C, cy: C, r: r0 + (rMax - r0) * f, fill: "none", stroke: "var(--hairline)", "stroke-width": 1 })));
    svg.append(h("circle", { cx: C, cy: C, r: r0, fill: "none", stroke: "var(--hairline)", "stroke-width": 1 }));
    const gap = 0.012;
    for (let hr = 0; hr < 24; hr++) {
      const a0 = ang(hr) + gap, a1 = ang(hr + 1) - gap, len = (rMax - r0) * (all[hr] / max), qlen = (rMax - r0) * (q[hr] / max);
      const office = hr >= open && hr < close;
      const g = h("g", { class: "hour" });
      g.append(h("path", { class: "hit", d: wedge(r0, rMax + 4, ang(hr), ang(hr + 1)) }));
      if (all[hr]) g.append(h("path", { class: "bar-all", d: wedge(r0 + 1, r0 + 1 + len, a0, a1), fill: "var(--s2)" }));
      if (q[hr]) {
        const mid = (a0 + a1) / 2, half = (a1 - a0) * 0.28;
        g.append(h("path", { d: wedge(r0 + 1, r0 + 1 + qlen, mid - half, mid + half), fill: "var(--s1)" }));
      }
      hover(g, `<b>${hh(hr)}–${hh((hr + 1) % 24)}</b><br>${all[hr]} calls · ${q[hr]} qualified<br>${office ? "Front desk open" : "After hours: only the AI answers"}`);
      svg.append(g);
      // ticks
      const [tx, ty] = pt(rMax + 18, ang(hr + 0.5));
      if (hr % 3 === 0) {
        const [lx, ly] = pt(rMax + 20, ang(hr));
        svg.append(h("text", { class: `tick ${hr % 6 === 0 ? "major" : ""}`, x: lx, y: ly, "text-anchor": "middle", "dominant-baseline": "middle", text: hh(hr).slice(0, 2) }));
      } else {
        const [ax, ay] = pt(rMax + 6, ang(hr)), [bx, by] = pt(rMax + 11, ang(hr));
        svg.append(h("line", { x1: ax, y1: ay, x2: bx, y2: by, stroke: "var(--text-muted)", "stroke-width": 1 }));
      }
    }
    // peak label (selective direct label: the busiest hour only)
    const peakVal = Math.max(...all);
    if (peakVal > 0) {
      const peak = all.indexOf(peakVal), [px, py] = pt(r0 + (rMax - r0) + 34, ang(peak + 0.5));
      svg.append(h("text", { class: "tick major", x: px, y: py, "text-anchor": "middle", "dominant-baseline": "middle",
        text: `${peakVal} call${peakVal === 1 ? "" : "s"}` }));
    }
    // centre
    svg.append(h("text", { class: "center-big", x: C, y: C + 6, "text-anchor": "middle", text: `${Math.round(m.after_hours.share_pct ?? 0)}%` }));
    svg.append(h("text", { class: "center-small", x: C, y: C + 30, "text-anchor": "middle", text: "of calls outside" }));
    svg.append(h("text", { class: "center-small", x: C, y: C + 46, "text-anchor": "middle", text: "office hours" }));

    const legend = h("div", { class: "legend" }, [
      h("div", { class: "row" }, [h("span", { class: "sw", style: "background:var(--s2)" }), h("span", {}, [h("b", { text: fmtN(m.volume.calls) }), " calls, by the hour they came in"])]),
      h("div", { class: "row" }, [h("span", { class: "sw", style: "background:var(--s1)" }), h("span", {}, [h("b", { text: fmtN(m.funnel.qualified) }), " qualified by the rules engine"])]),
      h("div", { class: "row" }, [h("span", { class: "sw", style: "background:var(--office)" }), h("span", { text: "Front desk staffed (10:00–19:00)" })]),
      h("div", { class: "row" }, [h("span", { class: "sw", style: "background:var(--night)" }), h("span", { text: "Callbacks paused (21:00–09:00)" })]),
      h("div", { class: "row" }, [h("span", { text: `${fmtN(m.after_hours.qualified_after_hours)} of the qualified leads came in after hours: calls that used to ring out.` })])]);
    const body = h("div", { class: "dial-wrap" }, [svg, legend]);
    const rows = all.map((n, i) => [`${hh(i)}–${hh((i + 1) % 24)}`, n, q[i], i >= open && i < close ? "office" : "after hours"]);
    return card(7, "Calls by hour of day", "Every call is answered, day or night. Hover an hour for detail.", body,
      table(["Hour", "Calls", "Qualified", "Desk"], rows));
  }

  // ---------------------------------------------------------------- horizontal bars
  function hbars(items, { max, color, unit = "" } = {}) {
    const mx = max ?? Math.max(1, ...items.map(i => i.value));
    return h("div", { class: "hbars" }, items.map(it => {
      const row = h("div", { class: "hbar" }, [
        h("div", { class: "lbl", title: it.label, text: it.label }),
        h("div", { class: "track" }, h("div", { class: "area" }, [
          // exact proportion of the bar area; the value label sits just past the bar's tip
          h("div", { class: "fill", style: `width:${(100 * it.value) / mx}%;background:${it.color || color}` }),
          h("span", { class: "val", style: `left:calc(${(100 * it.value) / mx}% + 6px)` },
            [fmtN(it.value) + unit, it.note ? h("small", { text: it.note }) : null])]))]);
      hover(row, `<b>${it.label}</b><br>${fmtN(it.value)}${unit}${it.note ? " · " + it.note : ""}`);
      return row;
    }));
  }

  function funnel(m) {
    const f = m.funnel, stages = [["Calls", f.calls], ["Answered by the AI", f.answered], ["Real enquiries", f.enquiries],
      ["Qualified by the rules", f.qualified], ["Handed to a designer", f.handed_to_designer], ["Claimed by a designer", f.claimed]];
    if (f.booked) stages.splice(4, 0, ["Booked on the call", f.booked]);
    const ramp = ["var(--ramp-1)", "var(--ramp-2)", "var(--ramp-3)", "var(--ramp-4)", "var(--ramp-5)", "var(--ramp-6)", "var(--ramp-6)"];
    const items = stages.map(([label, value], i) => ({ label, value, color: ramp[i], note: i ? `${pct(value, stages[0][1])}%` : "" }));
    return card(5, "From ring to designer", "Each step as a share of all calls. Escalations and dropped calls leave the funnel early.",
      hbars(items, { max: f.calls }), table(["Stage", "Count", "% of calls"], items.map(i => [i.label, fmtN(i.value), pct(i.value, f.calls) + "%"])));
  }

  function outcomes(m) {
    const total = Object.values(m.outcomes).reduce((a, b) => a + b, 0);
    const items = OUTCOME.filter(([k]) => m.outcomes[k]).map(([k, label, color]) => ({ label, value: m.outcomes[k], color, note: `${pct(m.outcomes[k], total)}%` }));
    return card(6, "What the rules engine decided", "Code decides, not the AI. One colour per outcome, always in this order.",
      items.length ? hbars(items) : h("p", { class: "sub", text: "No decisions yet in this period." }), table(["Outcome", "Calls", "Share"], items.map(i => [i.label, fmtN(i.value), i.note])));
  }

  function reasons(m) {
    const items = Object.entries(m.decline_reasons).map(([k, v]) => ({ label: REASON[k] || k, value: v }));
    const body = items.length ? hbars(items, { color: "var(--s4)" }) : h("p", { class: "sub", text: "No declines in this period." });
    return card(6, "Why callers weren't a fit", "Nikhil's criteria that failed, across declined and nurtured calls. No price was ever quoted.",
      body, table(["Reason", "Calls"], items.map(i => [i.label, fmtN(i.value)])));
  }

  // ---------------------------------------------------------------- daily line
  function daily(m) {
    const days = Object.keys(m.by_day), vals = Object.values(m.by_day);
    const W = 720, H = 190, pad = { l: 30, r: 12, t: 12, b: 26 }, max = Math.max(4, ...vals);
    const top = Math.ceil(max / 4) * 4;
    const x = i => pad.l + (i * (W - pad.l - pad.r)) / Math.max(1, days.length - 1), y = v => pad.t + (H - pad.t - pad.b) * (1 - v / top);
    const svg = h("svg", { class: "line-svg", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Calls per day" });
    [0, top / 2, top].forEach(v => {
      svg.append(h("line", { class: "grid-line", x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v) }));
      svg.append(h("text", { class: "axis", x: pad.l - 6, y: y(v) + 4, "text-anchor": "end", text: v }));
    });
    if (days.length) {
      const pts = vals.map((v, i) => `${x(i)},${y(v)}`).join(" ");
      svg.append(h("polygon", { points: `${x(0)},${y(0)} ${pts} ${x(vals.length - 1)},${y(0)}`, fill: "var(--s2)", opacity: 0.1 }));
      svg.append(h("polyline", { points: pts, fill: "none", stroke: "var(--s2)", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round", "vector-effect": "non-scaling-stroke" }));
      [0, Math.floor((days.length - 1) / 2), days.length - 1].forEach(i => svg.append(h("text", { class: "axis", x: x(i), y: H - 6,
        "text-anchor": i === 0 ? "start" : i === days.length - 1 ? "end" : "middle", text: new Date(days[i]).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) })));
      const last = vals.length - 1;
      svg.append(h("circle", { cx: x(last), cy: y(vals[last]), r: 4, fill: "var(--s2)", stroke: "var(--surface-1)", "stroke-width": 2 }));
      vals.forEach((v, i) => { const hit = h("rect", { x: x(i) - (W / days.length) / 2, y: 0, width: W / days.length, height: H, fill: "transparent" });
        hover(hit, `<b>${new Date(days[i]).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" })}</b><br>${v} calls`); svg.append(hit); });
    }
    return card(8, "Calls per day", `${fmtN(m.volume.calls)} calls · ${m.volume.avg_call_min ?? "–"} min average length`, svg,
      table(["Day", "Calls"], days.map((d, i) => [d, vals[i]])));
  }

  // ---------------------------------------------------------------- cost
  function cost(m) {
    const c = m.cost;
    const rows = [["Per call", c.per_call], ["Per qualified lead", c.per_qualified_lead], ["Per lead claimed by a designer", c.per_claimed_lead]];
    if (c.per_booked_consultation) rows.push(["Per consultation booked on the call", c.per_booked_consultation]);
    const body = h("div", {}, [
      h("div", { class: "stat" }, [h("div", { class: "k", text: "Total cost of the system this period" }),
        h("div", { class: "v", text: c.complete ? fmtINR(c.total) : "Unknown" }),
        h("div", { class: "d", text: c.complete ? `${fmtINR(c.variable)} call minutes${c.rate_per_min != null ? ` at ₹${c.rate_per_min}/min` : ""} + ${fmtINR(c.fixed_prorated || 0)} fixed (plan, hosting)` : c.note })]),
      h("div", { style: "height:12px" }),
      table(["Unit cost", "₹"], rows.map(([k, v]) => [k, c.complete ? fmtINR(v) : "–"]))]);
    return card(4, "What it costs", "Includes the tool's own running cost, so Nikhil never has to work it out by hand.", body);
  }

  // ---------------------------------------------------------------- recent leads
  function recent(list) {
    const color = Object.fromEntries(OUTCOME.map(([k, , c]) => [k, c]));
    const label = { QUALIFIED: "Qualified", ASK: "Callback: details missing", NURTURE: "Nurture", DECLINE: "Declined", ESCALATE: "Escalated" };
    const t = h("table", {}, [
      h("thead", {}, h("tr", {}, ["When", "Caller", "Area", "Decision", "Designer"].map(c => h("th", { text: c })))),
      h("tbody", {}, list.map(l => h("tr", {}, [
        h("td", { text: l.created_at ? new Date(l.created_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "" }),
        h("td", {}, [h("strong", { text: l.name || "–" }), l.priority ? " · priority" : ""]),
        h("td", { text: l.area || "–" }),
        h("td", {}, h("span", { class: "pill" }, [h("i", { style: `background:${color[l.outcome] || "var(--text-muted)"}` }),
          (label[l.outcome] || l.outcome || "–") + (l.reasons?.length && l.outcome !== "ESCALATE" ? ` · ${l.reasons.map(r => REASON[r] || r).join(", ").toLowerCase()}` : "")])),
        h("td", { text: l.claimed_by || (l.outcome === "QUALIFIED" ? "waiting…" : "") })])))]);
    return card(12, "Latest enquiries", "Most recent first. The full note with everything asked goes to the designer on Telegram.", h("div", { class: "scroll-x" }, t));
  }


  // ---------------------------------------------------------------- editorial statement + section labels
  function statement(m, demo) {
    const t = m.time_to_claim.call_to_claim, f = m.funnel, med = fmtMin(t.median_min);
    const parts = [
      demo ? "In this sample month the desk answered " : "In this period the desk answered ",
      ["em", fmtN(m.volume.answered) + " calls"], ", ",
      ["em", fmtN(m.after_hours.calls)], " of them after the front desk had gone home. ",
      ["em", fmtN(f.qualified) + " were worth a designer's time"], ", and a designer picked them up in a median of ",
      ["em", `${med.v} ${med.u}`], ". Nobody was quoted a price. Nobody had to repeat themselves."];
    const p = h("p", { class: "statement-text" });
    parts.forEach(part => {
      const [tag, text] = Array.isArray(part) ? part : [null, part];
      text.split(/(\s+)/).forEach(w => {
        if (!w.trim()) { p.append(w); return; }
        p.append(h("span", { class: "w" + (tag ? " hi" : "") , text: w }));
      });
    });
    return h("section", { class: "statement span-12" }, [h("div", { class: "kicker", text: "{ This month at the desk }" }), p]);
  }
  const kicker = text => h("div", { class: "kicker span-12", text: `{ ${text} }` });

  // ---------------------------------------------------------------- designers & ROI
  function pipeline(m) {
    const p = m.pipeline || {}, c = m.cost;
    const items = [
      { label: "Claimed by a designer", value: p.claimed || 0, color: "var(--ramp-3)" },
      { label: "Consultation booked", value: p.booked || 0, color: "var(--ramp-4)", note: p.self_booked ? `${p.self_booked} self-booked via link` : "" },
      { label: "Won: project signed", value: p.won || 0, color: "var(--ramp-6)" },
      { label: "Lost", value: p.lost || 0, color: "var(--text-muted)" }];
    const lakh = v => (v == null ? "–" : "₹" + (v / 1e5).toLocaleString("en-IN", { maximumFractionDigits: 1 }) + " lakh");
    const body = h("div", { class: "pipe" }, [
      h("div", { class: "pipe-big" }, [
        h("div", { class: "k", text: "System cost per won project" }),
        h("div", { class: "v", text: c.complete && c.per_won_project ? fmtINR(c.per_won_project) : "–" }),
        h("div", { class: "d", text: `vs. an average project of ${lakh(p.avg_project_value_inr)} (brief: ₹8–14 lakh). ` +
          `Win rate ${p.win_rate_pct ?? "–"}% of decided leads · ${fmtN(p.open || 0)} still open.` })]),
      hbars(items, { max: Math.max(1, p.claimed || 0) })]);
    return card(8, "Designers & ROI", "Designers tap Booked / Won / Lost in Telegram after the call. Attribution caveat: some of these projects would have come anyway.",
      body, table(["Stage", "Leads"], items.map(i => [i.label, fmtN(i.value)])));
  }

  // ---------------------------------------------------------------- motion (GSAP), skipped for reduced motion
  function animate(root) {
    const g = window.gsap;
    if (!g || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (window.ScrollTrigger) g.registerPlugin(window.ScrollTrigger);
    const ST = !!window.ScrollTrigger;
    // statement: words go from faint to ink as you scroll through it
    const words = root.querySelectorAll(".statement .w");
    if (words.length) g.fromTo(words, { opacity: 0.16 }, { opacity: 1, stagger: 0.04, ease: "none",
      scrollTrigger: ST ? { trigger: ".statement", start: "top 85%", end: "bottom 45%", scrub: true } : undefined });
    // cards rise in
    g.utils.toArray(root.querySelectorAll(".card")).forEach(card => g.from(card, { y: 28, opacity: 0, duration: 0.7, ease: "power3.out",
      scrollTrigger: ST ? { trigger: card, start: "top 92%", once: true } : undefined }));
    // numbers count up
    root.querySelectorAll(".stat .v, .tile .v, .hero-num, .pipe-big .v").forEach(el => {
      const node = [...el.childNodes].find(n => n.nodeType === 3 && /\d/.test(n.textContent));
      if (!node) return;
      const m = node.textContent.match(/^(\D*)([\d,]+(?:\.\d+)?)(.*)$/s);
      if (!m) return;
      const target = parseFloat(m[2].replace(/,/g, "")), dec = (m[2].split(".")[1] || "").length, obj = { v: 0 };
      g.to(obj, { v: target, duration: 1.2, ease: "power2.out", onUpdate: () => {
        node.textContent = m[1] + obj.v.toLocaleString("en-IN", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + m[3]; },
        scrollTrigger: ST ? { trigger: el, start: "top 95%", once: true } : undefined });
    });
    // the dial sweeps in around the clock
    const hours = root.querySelectorAll(".dial g.hour");
    if (hours.length) g.from(hours, { scale: 0, svgOrigin: "280 280", duration: 0.8, ease: "back.out(1.4)", stagger: 0.035,
      scrollTrigger: ST ? { trigger: ".dial", start: "top 80%", once: true } : undefined });
    // bars grow from the baseline
    root.querySelectorAll(".hbars").forEach(hb => g.from(hb.querySelectorAll(".fill"), { scaleX: 0, transformOrigin: "left center",
      duration: 0.9, ease: "power3.out", stagger: 0.07, scrollTrigger: ST ? { trigger: hb, start: "top 88%", once: true } : undefined }));
    // the daily line draws itself
    const line = root.querySelector(".line-svg polyline");
    if (line && line.getTotalLength) {
      const L = line.getTotalLength();
      const area = root.querySelector(".line-svg polygon");
      const tl = g.timeline({ scrollTrigger: ST ? { trigger: line, start: "top 90%", once: true } : undefined });
      tl.fromTo(line, { strokeDasharray: L, strokeDashoffset: L }, { strokeDashoffset: 0, duration: 1.6, ease: "power2.inOut" });
      if (area) tl.from(area, { opacity: 0, duration: 0.6 }, "-=0.5");
    }
  }

  // ---------------------------------------------------------------- page
  async function load() {
    const cfg = window.AANGAN || {};
    const root = $("#app");
    try {
      let m, leads, meta = {};
      if (cfg.demo) {
        const d = await fetch(cfg.demo).then(r => r.json());
        m = d.metrics; leads = d.recent_leads; meta = d.assumptions;
      } else {
        const q = range(cfg.range || "30");
        [m, leads] = await Promise.all([fetch(`/api/metrics?start=${q.start}&end=${q.end}`).then(r => r.json()), fetch("/api/leads?limit=12").then(r => r.json())]);
      }
      root.replaceChildren();
      if (cfg.demo) root.append(h("div", { class: "banner", role: "note" }, [h("b", { text: "Synthetic data." }), h("span", { text: " " + meta.note })]));
      const asked = m.price_question;
      root.append(h("div", { class: "grid" }, [
        statement(m, !!cfg.demo),
        kicker("Speed: the number that matters"),
        hero(m),
        stat(3, "Calls answered", fmtN(m.volume.answered), `${fmtN(m.volume.missed)} missed or dropped · each called back once`),
        stat(3, "Outside office hours", `${Math.round(m.after_hours.share_pct ?? 0)}%`, `${fmtN(m.after_hours.calls)} calls the desk would have missed`),
        stat(3, "Qualified for a designer", fmtN(m.funnel.qualified), `${pct(m.funnel.qualified, m.funnel.enquiries)}% of real enquiries`),
        stat(3, "Cost per qualified lead", m.cost.complete ? fmtINR(m.cost.per_qualified_lead) : "Unknown", m.cost.complete ? `${fmtINR(m.cost.per_call)} per call, all-in` : "Set the per-minute rate"),
        kicker("Every hour of the day"),
        dial(m), funnel(m),
        kicker("What the rules decided"),
        outcomes(m), reasons(m),
        kicker("Designers, money and ROI"),
        pipeline(m), cost(m),
        kicker("Volume and safety nets"),
        daily(m),
        h("div", { class: "stack span-4" }, [
          stat(12, "Asked for a price", fmtN(asked.asked), `${asked.share_of_calls_pct ?? 0}% of calls · deflected every time · ${fmtN(asked.claimed)} still reached a designer`),
          stat(12, "Existing clients escalated", fmtN(m.escalations), "Urgent alert to the studio head + priority callback"),
          stat(12, "Callbacks", fmtN((m.callbacks.dispatched || 0) + (m.callbacks.pending || 0)),
            `${fmtN(m.callbacks.dispatched || 0)} done · ${fmtN(m.callbacks.pending || 0)} waiting · ${fmtN(m.callbacks.cancelled || 0)} cancelled (caller rang back)`)]),
        kicker("Latest enquiries"),
        recent(leads)]));
      animate(root);
      root.append(h("p", { class: "foot", html: `Period ${m.period.start.slice(0, 10)} → ${m.period.end.slice(0, 10)} · IST. Office hours ${m.after_hours.office_hours}. ` +
        `Decisions come from the rules engine (<code>backend/app/rules</code>); the AI only collects facts. ` +
        (cfg.demo ? "Generated by <code>scripts/seed_demo.py</code> through the production code paths." : "Live data from <code>/api/metrics</code>.") }));
    } catch (e) {
      root.replaceChildren(h("div", { class: "err", text: "Couldn't load the numbers: " + e.message }));
    }
  }
  function range(key) {
    const end = new Date(), start = new Date();
    if (key === "month") start.setDate(1); else start.setDate(end.getDate() - (Number(key) - 1));
    const iso = d => d.toISOString().slice(0, 10);
    return { start: iso(start), end: iso(end) };
  }

  // theme toggle + range buttons
  document.addEventListener("click", e => {
    const t = e.target.closest("[data-theme-toggle]");
    if (t) {
      const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      document.documentElement.dataset.theme = dark ? "light" : "dark";
      try { localStorage.setItem("aangan-theme", document.documentElement.dataset.theme); } catch {}
    }
    const r = e.target.closest("[data-range]");
    if (r) {
      document.querySelectorAll("[data-range]").forEach(b => b.setAttribute("aria-pressed", String(b === r)));
      (window.AANGAN = window.AANGAN || {}).range = r.dataset.range; load();
    }
  });
  try { const saved = localStorage.getItem("aangan-theme"); if (saved) document.documentElement.dataset.theme = saved; } catch {}
  load();
})();
