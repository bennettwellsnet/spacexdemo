/* Shared live-board helpers for spacexdemo. Data: launches.json */
(function (global) {
  const YEAR = 2026;
  const AMBITIOUS_TARGET = 160;

  function escapeHtml(str) {
    // DOM path avoids HTML-entity literals that GitHub MCP XML-decodes on upload.
    const el = document.createElement("span");
    el.textContent = String(str);
    return el.innerHTML;
  }

  function parseNet(net) {
    if (!net) return null;
    const d = new Date(net);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function dayOfYear(date) {
    const y = date.getUTCFullYear();
    const start = Date.UTC(y, 0, 1);
    return Math.floor((date.getTime() - start) / 86400000) + 1;
  }

  function daysInYear(y) {
    return ((y % 4 === 0 && y % 100 !== 0) || y % 400 === 0) ? 366 : 365;
  }

  function paceProjection(value, asOf) {
    const diy = daysInYear(YEAR);
    const daysIn = Math.max(1, dayOfYear(asOf));
    const daysLeft = Math.max(0, diy - daysIn);
    const perDay = value / daysIn;
    const projected = Math.round(perDay * diy);
    return { daysIn, daysLeft, diy, perDay, projected };
  }

  function formatTons(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return Math.round(n).toLocaleString("en-US");
  }

  function formatAsOf(date) {
    return date.toLocaleDateString("en-US", {
      month: "long",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    }).toUpperCase();
  }

  function formatWhen(net) {
    const d = parseNet(net);
    if (!d) return "NET TBA";
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZone: "UTC",
      timeZoneName: "short",
    });
  }

  function formatDateShort(net) {
    const d = parseNet(net);
    if (!d) return "—";
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, "0");
    const day = String(d.getUTCDate()).padStart(2, "0");
    return y + "-" + m + "-" + day;
  }

  function flown(data) {
    return (data.launches || []).filter((l) =>
      l.status === "success" || l.status === "failure" || l.status === "partial"
    );
  }

  function upcoming(data) {
    const now = Date.now();
    return (data.launches || []).filter((l) => {
      if (l.status !== "upcoming") return false;
      const d = parseNet(l.net);
      return !d || d.getTime() >= now - 3600000;
    });
  }

  function asOfDate(data) {
    const f = flown(data);
    let latest = null;
    f.forEach((l) => {
      const d = parseNet(l.net);
      if (d && (!latest || d > latest)) latest = d;
    });
    if (latest) return latest;
    const fetched = parseNet(data.fetched_at);
    return fetched || new Date();
  }

  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  async function load() {
    const res = await fetch("launches.json", { cache: "no-store" });
    if (!res.ok) throw new Error("launches.json HTTP " + res.status);
    return res.json();
  }

  function renderIndex(data) {
    const f = flown(data);
    const up = upcoming(data);
    const success = f.filter((l) => l.status === "success").length;
    const f9 = f.filter((l) => l.vehicle === "falcon9").length;
    const ss = f.filter((l) => l.vehicle === "starship").length;
    const fh = f.filter((l) => l.vehicle === "falcon-heavy").length;
    const asOf = asOfDate(data);
    const rate = f.length ? ((success / f.length) * 100).toFixed(1) : "—";

    setText("as-of-label", "LIVE · AS OF " + formatAsOf(asOf));
    setText("main-counter", String(f.length));
    setText("success-count", success + " successful missions");
    setText("success-rate", "~" + rate + "% success rate");
    setText("f9-count", String(f9));
    setText("starship-count", String(ss));
    setText("fh-count", String(fh));
    setText("goal-current", String(f.length));

    const pace = paceProjection(f.length, asOf);
    const pct = Math.min(Math.round((f.length / AMBITIOUS_TARGET) * 100), 100);
    const bar = document.getElementById("goal-progress");
    if (bar) bar.style.width = pct + "%";
    setText("pace-projected", "~" + pace.projected);
    setText("pace-per-day", pace.perDay.toFixed(2));
    setText("pace-days-in", String(pace.daysIn));
    setText("pace-days-left", String(pace.daysLeft));
    setText("goal-pct-label", String(pct));
    const vs = pace.projected - AMBITIOUS_TARGET;
    const vsLabel = vs === 0
      ? "matches the ~160 ambitious target"
      : vs > 0
        ? "~" + vs + " above the ambitious ~160 target"
        : "~" + Math.abs(vs) + " below the ambitious ~160 target";
    setText("pace-summary",
      pace.daysIn + " days in → ~" + pace.projected + " year-end at this rate (" + vsLabel + ")");

    const sxT = (data.mass && data.mass.spacex_t) || f.reduce((s, l) => s + (l.payload_t || 0), 0);
    const rowT = data.mass && data.mass.row_t;
    if (rowT != null) {
      const worldYtd = sxT + rowT;
      const share = worldYtd > 0 ? (sxT / worldYtd) * 100 : 0;
      const sxPct = Math.max(0, Math.min(100, share));
      const rowPct = Math.max(0, 100 - sxPct);
      const sxYe = paceProjection(sxT, asOf).projected;
      const rowYe = paceProjection(rowT, asOf).projected;
      const worldYe = sxYe + rowYe;
      const shareYe = worldYe > 0 ? (sxYe / worldYe) * 100 : 0;
      const multiple = rowT > 0 ? sxT / rowT : 0;
      setText("mass-share", share.toFixed(1) + "%");
      setText("mass-sx-ytd", "~" + formatTons(sxT));
      setText("mass-row-ytd", "~" + formatTons(rowT));
      setText("mass-world-ytd", "World YTD ~" + formatTons(worldYtd) + " t");
      setText("mass-ratio-label",
        multiple >= 10 ? "~" + multiple.toFixed(0) + "× rest of world" : "~" + multiple.toFixed(1) + "× rest of world");
      const barSx = document.getElementById("mass-bar-sx");
      const barRow = document.getElementById("mass-bar-row");
      if (barSx) barSx.style.width = sxPct + "%";
      if (barRow) barRow.style.width = rowPct + "%";
      setText("mass-bar-sx-label", sxPct >= 12 ? share.toFixed(0) + "%" : "");
      setText("mass-bar-row-label", rowPct >= 12 ? rowPct.toFixed(0) + "%" : "");
      setText("mass-sx-ye", "~" + formatTons(sxYe));
      setText("mass-row-ye", "~" + formatTons(rowYe));
      setText("mass-world-ye", "~" + formatTons(worldYe));
      setText("mass-share-ye", shareYe.toFixed(0) + "%");
    }

    const next = up[0];
    const nextEl = document.getElementById("next-launch");
    if (nextEl && next) {
      nextEl.innerHTML =
        '<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">' +
        '<div><div class="text-[10px] uppercase tracking-wider text-[#f97316]/80 mb-1">Next launch</div>' +
        '<div class="font-medium text-lg">' + escapeHtml(next.name) + "</div>" +
        '<div class="text-xs text-white/60 mt-1">' + escapeHtml(formatWhen(next.net)) +
        " · " + escapeHtml(next.pad) + " · " + escapeHtml(next.site) + "</div></div>" +
        '<div class="text-right"><span class="px-2.5 py-1 rounded-full bg-emerald-500/15 text-emerald-400 text-xs">' +
        escapeHtml(next.status_label) + "</span>" +
        '<div class="text-[11px] text-white/45 mt-2">' + escapeHtml(next.vehicle_label) + "</div></div></div>";
    }

    const notable = document.getElementById("notable-missions");
    if (notable) {
      const picks = [];
      const last = f.slice().reverse();
      last.forEach((l) => {
        if (picks.length >= 4) return;
        picks.push(l);
      });
      notable.innerHTML = picks.map((l) => {
        const tag = l.vehicle === "starship" ? "bg-orange-500/20 text-orange-400"
          : l.vehicle === "falcon-heavy" ? "bg-zinc-400/20 text-zinc-300"
          : "bg-sky-500/20 text-sky-400";
        return '<div class="bg-white/5 border border-white/10 rounded-2xl p-5">' +
          '<div class="flex justify-between gap-3">' +
          "<div><div class=\"font-medium\">" + escapeHtml(l.name) + "</div>" +
          '<div class="text-xs text-white/60">' + escapeHtml(formatWhen(l.net)) +
          " · " + escapeHtml(l.pad) + "</div></div>" +
          '<div class="text-right text-xs"><span class="px-2 py-px rounded ' + tag + '">' +
          escapeHtml(l.vehicle_label) + "</span></div></div></div>";
      }).join("");
    }

    setText("footer-as-of", "as of " + formatAsOf(asOf).toLowerCase());
    const src = document.getElementById("data-source-stamp");
    if (src) {
      src.textContent = "Live from " + (data.source || "Launch Library 2") +
        " · fetched " + (data.fetched_at || "—");
    }
  }

  function outcomeBadge(status, label) {
    const cls = status === "success" ? "bg-emerald-500/20 text-emerald-400"
      : status === "partial" ? "bg-amber-500/20 text-amber-400"
      : status === "failure" ? "bg-red-500/20 text-red-400"
      : "bg-blue-500/20 text-blue-400";
    return '<span class="inline-block text-[10px] px-2.5 py-px rounded-full ' + cls + '">' +
      escapeHtml(label || status) + "</span>";
  }

  function renderFalcon9(data) {
    const rows = (data.launches || []).filter((l) => l.vehicle === "falcon9");
    const flownN = rows.filter((l) => l.status === "success" || l.status === "failure" || l.status === "partial").length;
    setText("f9-heading-count", flownN + " missions · YTD live from Launch Library 2");
    setText("f9-big-count", String(flownN));
    setText("visible-count", String(rows.length));
    const tbody = document.getElementById("missions-tbody");
    if (!tbody) return;
    const render = (list) => {
      tbody.innerHTML = "";
      list.forEach((m) => {
        const tr = document.createElement("tr");
        tr.className = "mission-row border-b border-white/10";
        tr.innerHTML =
          '<td class="px-6 py-3 font-mono text-xs text-white/70">' + escapeHtml(formatDateShort(m.net)) + "</td>" +
          '<td class="px-6 py-3 font-medium">' + escapeHtml(m.name) + "</td>" +
          '<td class="px-6 py-3 text-xs text-white/70">' + escapeHtml(m.pad + " · " + m.site) + "</td>" +
          '<td class="px-6 py-3 text-xs">' + escapeHtml(m.mission_type || "—") + "</td>" +
          '<td class="px-6 py-3 font-mono text-xs text-white/70">—</td>' +
          '<td class="px-6 py-3 text-center">' + outcomeBadge(m.status, m.status_label) + "</td>";
        tbody.appendChild(tr);
      });
      setText("visible-count", String(list.length));
    };
    render(rows);

    const search = document.getElementById("search");
    const month = document.getElementById("month-filter");
    const apply = () => {
      const q = (search && search.value || "").toLowerCase().trim();
      const mo = month && month.value;
      let list = rows;
      if (q) list = list.filter((m) => m.name.toLowerCase().includes(q) || (m.mission_type || "").toLowerCase().includes(q));
      if (mo) list = list.filter((m) => (m.net || "").slice(5, 7) === mo);
      render(list);
    };
    if (search) search.addEventListener("input", apply);
    if (month) month.addEventListener("change", apply);
    global.resetFilters = function () {
      if (search) search.value = "";
      if (month) month.value = "";
      render(rows);
    };
  }

  const STARSHIP_HISTORY = [
    { date: "2023-04-20", flight: "Flight 1 (IFT-1)", type: "Integrated flight test", outcome: "Partial success", notes: "First integrated flight; lost control after ascent" },
    { date: "2023-11-18", flight: "Flight 2 (IFT-2)", type: "Integrated flight test", outcome: "Partial success", notes: "Hot-staging success; both stages lost later" },
    { date: "2024-03-14", flight: "Flight 3 (IFT-3)", type: "Integrated flight test", outcome: "Success", notes: "Reached space; ship lost on reentry" },
    { date: "2024-06-06", flight: "Flight 4 (IFT-4)", type: "Integrated flight test", outcome: "Success", notes: "Controlled splashdowns for booster and ship" },
    { date: "2024-10-13", flight: "Flight 5 (IFT-5)", type: "Integrated flight test", outcome: "Success", notes: "First successful booster tower catch" },
    { date: "2024-11-19", flight: "Flight 6 (IFT-6)", type: "Integrated flight test", outcome: "Success", notes: "Final Block 1 ship; booster diverted to ocean" },
    { date: "2025-01-16", flight: "Flight 7", type: "Block 2 debut", outcome: "Partial success", notes: "Booster catch success; ship lost on ascent" },
    { date: "2025-03-06", flight: "Flight 8", type: "Integrated flight test", outcome: "Partial success", notes: "Booster catch; ship lost control mid-burn" },
    { date: "2025-05-27", flight: "Flight 9", type: "Integrated flight test", outcome: "Partial success", notes: "First reused Super Heavy; both stages lost late" },
    { date: "2025-08-26", flight: "Flight 10", type: "Integrated flight test", outcome: "Success", notes: "Starlink simulators deployed; soft ocean splashdowns" },
    { date: "2025-10-13", flight: "Flight 11", type: "Final Block 2", outcome: "Success", notes: "Last flight from Pad 1 before retrofit" },
  ];

  function renderStarship(data) {
    const live = (data.launches || []).filter((l) => l.vehicle === "starship").map((l) => ({
      date: formatDateShort(l.net),
      flight: l.name,
      type: l.mission_type || l.vehicle_label,
      outcome: l.status === "success" ? "Success"
        : l.status === "partial" ? "Partial success"
        : l.status === "failure" ? "Failure"
        : "Test",
      notes: (l.pad || "") + (l.site ? " · " + l.site : "") + (l.status === "upcoming" ? " · " + l.status_label : ""),
      status: l.status,
    }));
    const missions = STARSHIP_HISTORY.concat(live);
    const ytd = live.filter((l) => l.status === "success" || l.status === "partial" || l.status === "failure").length;
    setText("ss-ytd", String(ytd || live.filter((l) => l.outcome === "Success" || l.outcome === "Partial success").length));
    setText("ss-as-of", "Current as of live Launch Library 2 feed");

    const tbody = document.getElementById("missions-tbody");
    const render = (list) => {
      if (!tbody) return;
      tbody.innerHTML = "";
      list.forEach((m) => {
        const tr = document.createElement("tr");
        tr.className = "mission-row border-b border-white/10";
        const outcomeClass = m.outcome === "Success" ? "bg-emerald-500/20 text-emerald-400"
          : m.outcome === "Partial success" ? "bg-amber-500/20 text-amber-400"
          : "bg-blue-500/20 text-blue-400";
        tr.innerHTML =
          '<td class="px-6 py-3 font-mono text-xs text-white/70">' + escapeHtml(m.date) + "</td>" +
          '<td class="px-6 py-3 font-medium">' + escapeHtml(m.flight) + "</td>" +
          '<td class="px-6 py-3 text-xs text-white/70">' + escapeHtml(m.type) + "</td>" +
          '<td class="px-6 py-3 text-center"><span class="inline-block text-[10px] px-2.5 py-px rounded-full ' +
          outcomeClass + '">' + escapeHtml(m.outcome) + "</span></td>" +
          '<td class="px-6 py-3 text-xs">' + escapeHtml(m.notes) + "</td>";
        tbody.appendChild(tr);
      });
      setText("visible-count", String(list.length));
    };
    render(missions);
    const search = document.getElementById("search");
    const year = document.getElementById("year-filter");
    const outcome = document.getElementById("outcome-filter");
    const apply = () => {
      const q = (search && search.value || "").toLowerCase().trim();
      const y = year && year.value;
      const o = outcome && outcome.value;
      let list = missions;
      if (q) list = list.filter((m) => m.flight.toLowerCase().includes(q) || m.notes.toLowerCase().includes(q));
      if (y) list = list.filter((m) => (m.date || "").startsWith(y));
      if (o) list = list.filter((m) => m.outcome === o);
      render(list);
    };
    if (search) search.addEventListener("input", apply);
    if (year) year.addEventListener("change", apply);
    if (outcome) outcome.addEventListener("change", apply);
    global.resetFilters = function () {
      if (search) search.value = "";
      if (year) year.value = "";
      if (outcome) outcome.value = "";
      render(missions);
    };
  }

  function renderFalconHeavy(data) {
    const rows = (data.launches || []).filter((l) => l.vehicle === "falcon-heavy");
    const flownN = rows.filter((l) => l.status !== "upcoming").length;
    setText("fh-heading", flownN + " launches · YTD live from Launch Library 2");
    setText("fh-big-count", String(flownN));
    const host = document.getElementById("fh-missions");
    if (!host) return;
    const upcomingHtml = rows.filter((l) => l.status === "upcoming").map((l) =>
      "<li>" + escapeHtml(l.name) + " — " + escapeHtml(formatWhen(l.net)) + " · " + escapeHtml(l.pad) + "</li>"
    ).join("");
    const planned = document.getElementById("fh-planned-list");
    if (planned && upcomingHtml) planned.innerHTML = upcomingHtml;

    host.innerHTML = rows.filter((l) => l.status !== "upcoming").slice().reverse().map((l) =>
      '<div class="bg-white/5 border border-white/10 rounded-3xl p-8">' +
      '<div class="grid grid-cols-1 md:grid-cols-2 gap-8"><div>' +
      '<h2 class="font-semibold text-lg mb-2">' + escapeHtml(l.name) + "</h2>" +
      '<div class="space-y-1 text-sm">' +
      "<div><span class=\"text-white/60\">Date:</span> " + escapeHtml(formatWhen(l.net)) + "</div>" +
      "<div><span class=\"text-white/60\">Launch Site:</span> " + escapeHtml(l.pad) + " · " + escapeHtml(l.site) + "</div>" +
      "<div><span class=\"text-white/60\">Type:</span> " + escapeHtml(l.mission_type || "—") + "</div>" +
      "<div><span class=\"text-white/60\">Outcome:</span> " + outcomeBadge(l.status, l.status_label) + "</div>" +
      "</div></div><div><h2 class=\"font-semibold text-lg mb-2\">Key Details</h2>" +
      '<ul class="text-sm space-y-1 text-white/80">' +
      "<li>• " + escapeHtml(l.vehicle_label) + "</li>" +
      "<li>• Estimated payload ~" + escapeHtml(String(l.payload_t)) + " t (demo)</li>" +
      "</ul></div></div></div>"
    ).join("");
  }

  function createStars(count) {
    const container = document.getElementById("stars");
    if (!container) return;
    for (let i = 0; i < count; i++) {
      const star = document.createElement("div");
      star.className = "star";
      const size = Math.random() * 2.5 + 0.6;
      star.style.width = size + "px";
      star.style.height = size + "px";
      star.style.left = Math.random() * 100 + "%";
      star.style.top = Math.random() * 100 + "%";
      container.appendChild(star);
    }
  }

  global.LaunchBoard = {
    load, flown, upcoming, renderIndex, renderFalcon9, renderStarship, renderFalconHeavy, createStars, escapeHtml,
  };
})(window);
