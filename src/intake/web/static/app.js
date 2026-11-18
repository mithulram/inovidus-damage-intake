// Schadenmeldungen · Prüfplatz – vanilla JS, no build step.
// The UI only displays and asks; every decision comes from the API, every action goes through /api/approve.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v, d = 2) => (v == null ? "–" : Number(v).toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d }));
const icon = (id) => `<svg aria-hidden="true"><use href="#i-${id}"/></svg>`;
const time = (iso) => (iso ? new Date(iso).toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "–");
const cap = (v) => (v ? v.charAt(0).toUpperCase() + v.slice(1) : v);
function readerLabel(p) {
  const name = { offline: "Regeln (ohne KI)", groq: "Groq", "recorded(groq)": "Groq (Aufzeichnung)", "groq→offline": "Regeln – Groq nicht verfügbar" }[p.provider] || p.provider;
  return p.model ? `${name} · ${p.model}` : name;
}
const clock = (iso) => (iso ? new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" }) : "");

const STATUS = {
  READY_FOR_APPROVAL: { label: "Bitte freigeben", long: "Zuordnung eindeutig – bitte prüfen und freigeben", icon: "ready" },
  NEEDS_REVIEW: { label: "Prüfung nötig", long: "Prüfung nötig – das System rät nicht", icon: "review" },
  OUT_OF_SCOPE: { label: "Weiterleiten", long: "Keine Schadenmeldung – weiterleiten", icon: "route" },
};
const URG_RANK = { NOTFALL: 0, DRINGEND: 1, NORMAL: 2 };
const SIG_LABEL = { name: "Name", address: "Adresse", floor: "Etage", side: "Seite", contact: "Kontakt" };
const SIG_TEXT = { match: "passt", partial: "teilweise", missing: "fehlt", mismatch: "widerspricht" };
const PROVIDER_LABEL = { offline: "Regeln (ohne KI)", recorded: "Groq (Aufzeichnung)", groq: "Groq live" };

const state = {
  provider: localGet("provider") || "offline",
  source: "demo",
  scenarios: [],
  results: new Map(),   // scenario id -> case
  store: [],
  current: null,        // { kind: 'scenario'|'store'|'custom', id, case, scenario }
  sheet: "reply",
  rules: null,
  actor: localGet("actor") || "Sachbearbeitung",
};

function localGet(k) { try { return localStorage.getItem("intake." + k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem("intake." + k, v); } catch { /* private mode */ } }

async function api(path, body, method) {
  const res = await fetch(path, {
    method: method || (body ? "POST" : "GET"),
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) {
    const msg = typeof data?.detail === "string" ? data.detail : JSON.stringify(data?.detail ?? data);
    const err = new Error(msg || `Fehler ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (t.hidden = true), 3200);
}

/* ------------------------------------------------------------------ inbox */

function urgencyOf(c) { return c?.urgency?.level || null; }

function mailRow({ key, subject, sender, status, urgency, idText, current, pending }) {
  if (pending) return `<li><div class="mail skeleton" aria-label="wird gelesen"></div></li>`;
  const s = STATUS[status];
  return `<li><button class="mail ${urgency ? "u-" + urgency : ""}" data-key="${esc(key)}" aria-current="${current}">
      <span class="mail-subject">${esc(subject || "(ohne Betreff)")}</span>
      <span class="mail-id">${esc(idText)}</span>
      <span class="mail-meta">
        ${urgency === "NOTFALL" ? `<span class="chip u-NOTFALL">${icon("alert")}NOTFALL</span>` : ""}
        ${s ? `<span class="chip s-${status}">${icon(s.icon)}${s.label}</span>` : `<span class="chip s-OUT_OF_SCOPE">noch nicht gelesen</span>`}
        <span class="who">${esc(sender || "Absender unbekannt")}</span>
      </span>
    </button></li>`;
}

function renderInbox() {
  const list = $("#inbox-list");
  const cur = state.current;
  if (state.source === "demo") {
    $("#inbox-note").textContent = "14 Beispiel-E-Mails mit erwartetem Ergebnis. Dringendes steht oben.";
    const rows = state.scenarios.map((sc, i) => ({ sc, i, c: state.results.get(sc.id) }));
    rows.sort((a, b) => (URG_RANK[urgencyOf(a.c)] ?? 3) - (URG_RANK[urgencyOf(b.c)] ?? 3) || a.i - b.i);
    list.innerHTML = rows.map(({ sc, c }) => mailRow({
      key: sc.id, subject: sc.email.subject, sender: sc.email.sender_email || c?.understanding?.extraction?.sender_name,
      status: c?.status, urgency: urgencyOf(c), idText: sc.id,
      current: cur?.kind === "scenario" && cur.id === sc.id,
      pending: c === undefined && state.provider !== "groq",
    })).join("");
  } else {
    $("#inbox-note").textContent = state.store.length
      ? "Vorgänge, die der n8n-Workflow (oder diese Oberfläche) zur Prüfung abgelegt hat."
      : "";
    if (!state.store.length) {
      list.innerHTML = `<li class="empty-state"><h3>Prüfliste ist leer</h3><p>Hier landen E-Mails aus dem n8n-Workflow. Freigaben legen Vorgänge ebenfalls hier ab.</p></li>`;
      return;
    }
    const rows = [...state.store].sort((a, b) => (URG_RANK[a.urgency] ?? 3) - (URG_RANK[b.urgency] ?? 3) || String(b.received_at).localeCompare(String(a.received_at)));
    list.innerHTML = rows.map((c) => mailRow({
      key: c.case_id, subject: c.subject, sender: c.sender || time(c.received_at), status: c.status, urgency: c.urgency,
      idText: c.case_id, current: cur?.kind === "store" && cur.id === c.case_id,
    })).join("");
  }
}

async function loadScenarios() {
  state.scenarios = await api("/api/scenarios");
  state.results.clear();
  renderInbox();
  if (state.provider === "groq") { renderInbox(); return; } // live: read only on open (free-tier limits)
  await Promise.all(state.scenarios.map(async (sc) => {
    try {
      state.results.set(sc.id, await api("/api/process", { email: sc.email, scenario_id: sc.id, provider: state.provider }));
    } catch (e) { state.results.set(sc.id, null); }
    renderInbox();
  }));
}

async function loadStore() {
  try { state.store = await api("/api/cases"); } catch { state.store = []; }
  if (state.source === "store") renderInbox();
}

/* ------------------------------------------------------------------ case view */

function highlight(body, ext) {
  if (!body) return "";
  const spans = [];
  const wanted = [ext.street_raw && ext.house_no ? `${ext.street_raw} ${ext.house_no}` : ext.street_raw, ext.floor_raw, ext.side_raw,
    ext.tenant_name, ext.sender_name, ext.room, ext.since, ext.phone].filter(Boolean);
  const lower = body.toLowerCase();
  for (const w of wanted) {
    const at = lower.indexOf(String(w).toLowerCase());
    if (at >= 0) spans.push([at, at + String(w).length]);
  }
  spans.sort((a, b) => a[0] - b[0]);
  let out = "", pos = 0;
  for (const [s, e] of spans) {
    if (s < pos) continue;
    out += esc(body.slice(pos, s)) + `<mark class="read">${esc(body.slice(s, e))}</mark>`;
    pos = e;
  }
  return out + esc(body.slice(pos));
}

function field(label, value, extra = "", wide = false) {
  const empty = value == null || value === "";
  return `<div class="field${wide ? " wide" : ""}"><span class="label">${label}</span>
    <span class="v${empty ? " empty" : ""}">${empty ? "nicht genannt" : esc(value)}${extra}</span></div>`;
}

function floorText(loc) {
  if (!loc) return "";
  if (loc.floor == null) return "";
  return loc.floor === 0 ? "EG" : `${loc.floor}. OG`;
}

function effectiveRules(sc) {
  const base = state.rules?.parsed?.match || {};
  const over = sc?.rule_overrides?.match || {};
  return { threshold: over.threshold ?? base.threshold, min_margin: over.min_margin ?? base.min_margin };
}

function expectationCheck(sc, c) {
  if (!sc?.expected || !c) return null;
  const e = sc.expected, misses = [];
  if (e.status && e.status !== c.status) misses.push("Status");
  if ("contract" in e && (e.contract ?? null) !== (c.match?.selected_contract ?? null)) misses.push("Vertrag");
  if (e.urgency && e.urgency !== c.urgency?.level) misses.push("Dringlichkeit");
  if (e.failed_gates) {
    const a = [...(c.match?.failed_gates || [])].sort().join(","), b = [...e.failed_gates].sort().join(",");
    if (a !== b) misses.push("Prüfregeln");
  }
  return misses;
}

function stepsIndex(c) {
  const m = c.match, u = c.urgency, cl = c.understanding?.classification;
  const stop = c.status === "NEEDS_REVIEW";
  const items = [
    ["s-input", "Eingang", c.input.sender_email || "Absender unbekannt", "done"],
    ["s-read", "Erkannt", cl ? `${cl.category || cl.type}` : "–", "done"],
    ["s-match", "Zuordnung", m?.selected_contract || (c.status === "OUT_OF_SCOPE" ? "nicht nötig" : "offen – Prüfung"), m?.selected_contract || c.status === "OUT_OF_SCOPE" ? "done" : "stop"],
    ["s-prior", "Frühere Vorgänge", c.prior_cases?.length ? `${c.prior_cases.filter((p) => p.related).length} verwandt` : "keine", "done"],
    ["s-urgency", "Dringlichkeit", u?.level || "–", u?.level === "NOTFALL" ? "alarm" : "done"],
    ["s-carbon", "Antwort & Aufgabe", "Entwurf, nicht gesendet", stop ? "stop" : "done"],
  ];
  return `<ol class="steps" aria-label="Ablauf dieses Vorgangs">${items.map(([id, name, out, st]) =>
    `<li class="${st}"><a href="#${id}"><span class="step-name">${name}</span><span class="step-out">${esc(out)}</span></a></li>`).join("")}</ol>`;
}

function verdict(c) {
  const s = STATUS[c.status] || STATUS.NEEDS_REVIEW;
  const m = c.match;
  let line = m?.reason || "";
  if (c.status === "READY_FOR_APPROVAL") line = `Alle Prüfungen bestanden: ${m.selected_contract}, ${num(m.score)} Punkte, Abstand ${num(m.margin)}. Nichts passiert ohne Ihre Freigabe.`;
  if (c.status === "NEEDS_REVIEW") line = (m.flags || []).map((f) => f.message).join(" · ");
  if (m?.approved_contract) line = `Von einem Menschen freigegeben: ${m.approved_contract}. ` + line;
  const u = c.urgency;
  return `<div class="verdict s-${c.status}${u?.level === "NOTFALL" ? " emergency" : ""}">
    <svg class="verdict-icon" aria-hidden="true"><use href="#i-${s.icon}"/></svg>
    <div class="verdict-text"><h3>${s.long}</h3><p>${esc(line)}</p></div>
    <div class="verdict-urgency">${u ? `<span class="chip u-${u.level}">${u.level === "NOTFALL" ? icon("alert") : ""}${u.level}</span><span>${esc(u.response_target)}</span>` : ""}</div>
  </div>`;
}

function sigCell(sig) {
  return `<td class="sig"><span class="sig-mark sig-${sig.result}" title="${esc(SIG_LABEL[sig.name])}: ${esc(sig.reason)}">
    <svg role="img" aria-label="${esc(SIG_LABEL[sig.name])} ${SIG_TEXT[sig.result]}"><use href="#i-${sig.result}"/></svg></span></td>`;
}

function clearWinner(m) {
  const f = new Set(m.failed_gates || []);
  return m.winner && !f.has("threshold") && !f.has("margin") ? m.winner : null;
}

function candidatesTable(c) {
  const m = c.match, win = clearWinner(m);
  if (!m?.candidates?.length) return `<p class="err">Kein passender Vertrag im ERP gefunden.</p>`;
  const order = ["name", "address", "floor", "side", "contact"];
  const rows = m.candidates.map((cand) => {
    const sigs = order.map((n) => cand.signals.find((s) => s.name === n));
    const cls = ["cand", cand.contract_id === win ? "winner" : "", cand.vetoes.length ? "vetoed" : ""].join(" ");
    const reasons = [...cand.vetoes.map((v) => `<span class="veto">Veto: ${esc(v)}</span>`),
      ...sigs.filter((s) => s.result === "partial" || (s.result === "missing" && s.name !== "contact") || (s.result === "mismatch" && !["address", "floor", "side"].includes(s.name))).map((s) => `${esc(SIG_LABEL[s.name])}: ${esc(s.reason)}`)];
    return `<tr class="${cls}" data-unit="${esc(cand.unit_id)}">
      <td><span class="cid">${esc(cand.contract_id)}</span> ${cand.active ? "" : `<span class="inactive-tag">inaktiv</span>`}
        <span class="unit">${esc(cand.tenant_name)} · ${esc(cand.unit_label)}</span>
        ${reasons.length ? `<div class="why">${reasons.join("<br>")}</div>` : `<div class="why">Alle Merkmale passen.</div>`}</td>
      ${sigs.map(sigCell).join("")}
      <td class="score">${num(cand.score)}</td>
    </tr>`;
  }).join("");
  return `<table class="cands"><thead><tr><th>Vertrag</th>${order.map((n) => `<th class="sig">${SIG_LABEL[n]}</th>`).join("")}<th>Punkte</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="legend">
      <span><span class="sig-mark sig-match"><svg><use href="#i-match"/></svg></span>passt</span>
      <span><span class="sig-mark sig-partial"><svg><use href="#i-partial"/></svg></span>teilweise (halbe Punkte)</span>
      <span><span class="sig-mark sig-missing"><svg><use href="#i-missing"/></svg></span>fehlt (0, kein Widerspruch)</span>
      <span><span class="sig-mark sig-mismatch"><svg><use href="#i-mismatch"/></svg></span>widerspricht (Veto)</span>
    </div>`;
}

function parseUnit(unitId) {
  const m = /-(\d+)([LRM])$/.exec(unitId || "");
  return m ? { floor: Number(m[1]), side: m[2] } : null;
}

function houseGrid(c) {
  const m = c.match, win = clearWinner(m);
  if (!m?.candidates?.length) return "";
  const objectId = m.object_id || m.candidates.find((x) => x.contract_id === m.winner)?.object_id || m.candidates[0].object_id;
  const inHouse = m.candidates.filter((x) => x.object_id === objectId);
  const units = inHouse.map((x) => ({ ...x, pos: parseUnit(x.unit_id) })).filter((x) => x.pos);
  const loc = m.location || {};
  const erpMax = Math.min(30, Math.max(3, ...units.map((u) => u.pos.floor)));
  const maxF = erpMax, sides = units.some((u) => u.pos.side === "M") ? ["L", "M", "R"] : ["L", "R"];
  const sideName = { L: "links", M: "Mitte", R: "rechts" };
  const addr = inHouse[0]?.unit_label?.split(",")[0] || objectId;
  let cells = `<span></span>${sides.map((s) => `<span class="colh">${sideName[s]}</span>`).join("")}`;
  for (let f = maxF; f >= 0; f--) {
    cells += `<span class="fl">${f === 0 ? "EG" : f + ". OG"}</span>`;
    for (const s of sides) {
      const here = units.filter((u) => u.pos.floor === f && u.pos.side === s);
      const said = m.object_id === objectId && Number.isInteger(loc.floor) && loc.floor === f && (loc.side == null || loc.side === s);
      const saidTag = said ? `<span class="said" title="Laut E-Mail">E-Mail</span>` : "";
      if (!here.length) { cells += `<div class="unit-cell empty">${saidTag}</div>`; continue; }
      const u = here[0];
      const cls = ["unit-cell", "cand", u.contract_id === win ? "winner" : "", u.vetoes.length ? "vetoed" : "", u.active ? "" : "inactive"].join(" ");
      cells += `<div class="${cls}" data-unit="${esc(u.unit_id)}">${saidTag}<span class="uc-id">${esc(u.contract_id)}</span>${esc(u.tenant_name)}</div>`;
    }
  }
  return `<div class="house" aria-label="Hausraster ${esc(addr)}"><div class="house-title">${esc(addr)}</div>
    <div class="house-sub">Kandidaten im Haus. Schraffiert = ausgeschlossen, durchgestrichen = Vertrag inaktiv.</div>
    <div class="house-grid" style="--cols:${sides.length}">${cells}</div></div>`;
}

function gatesPanel(c, sc) {
  const m = c.match, failed = new Set(m.failed_gates || []);
  if (c.status === "OUT_OF_SCOPE") return `<p class="reader-note">Keine Schadenmeldung – die Zuordnung dient nur der Weiterleitung, es wird keine Aktion am Vertrag vorbereitet.</p>`;
  const r = effectiveRules(sc);
  const vetoFailed = failed.has("veto_address") || failed.has("veto_unit") || failed.has("no_candidate");
  const vetoCount = (m.candidates || []).filter((x) => x.vetoes.length).length;
  const vetoText = vetoCount === 0 ? "keine Widersprüche" : vetoCount === 1 ? "1 Vertrag wegen Widerspruch ausgeschlossen" : `${vetoCount} Verträge wegen Widerspruch ausgeschlossen`;
  const g = [
    ["Widersprüche", vetoFailed ? "fail" : "pass", vetoFailed ? "Der passendste Vertrag widerspricht der E-Mail" : vetoText],
    ["Schwelle", m.winner == null ? "skip" : failed.has("threshold") ? "fail" : "pass", m.winner == null ? "kein Kandidat übrig" : `${num(m.score)} ${failed.has("threshold") ? "<" : "≥"} ${num(r.threshold)}`],
    ["Abstand", m.winner == null ? "skip" : failed.has("margin") ? "fail" : "pass", m.winner == null ? "–" : `${num(m.margin)} ${failed.has("margin") ? "<" : "≥"} ${num(r.min_margin)}`],
    ["Vertrag aktiv", failed.has("eligibility") ? "fail" : (failed.has("threshold") || failed.has("margin") || m.winner == null) ? "skip" : "pass",
      failed.has("eligibility") ? "Vertrag beendet – kein Ausweichen" : (failed.has("threshold") || failed.has("margin") || m.winner == null) ? "erst nach eindeutiger Einheit" : "aktiv"],
  ];
  const ico = { pass: "match", fail: "mismatch", skip: "missing" };
  const otherFlags = (m.flags || []).filter((f) => ["identity", "floor_missing", "floor_ambiguous"].includes(f.gate));
  return `<ul class="gates" aria-label="Prüfregeln">${g.map(([n, st, v]) =>
      `<li class="gate ${st}"><span class="g-name">${icon(ico[st])}${n}</span><span class="g-val">${esc(v)}</span></li>`).join("")}</ul>
    ${otherFlags.length ? `<div class="flags">${otherFlags.map((f) => `<div class="flag">${icon("review")}<span>${esc(f.message)}</span></div>`).join("")}</div>` : ""}
    ${c.match.unknown_sender ? `<div class="flags"><div class="flag">${icon("review")}<span>Nicht von der registrierten E-Mail-Adresse – siehe Optionen unten.</span></div></div>` : ""}`;
}

function priorPanel(c) {
  if (!c.prior_cases?.length) return `<p class="reader-note">Keine früheren Vorgänge für ${esc(c.match?.approved_contract || c.match?.selected_contract || c.match?.winner || "die Kandidaten")}.</p>`;
  return `<ul class="prior">${c.prior_cases.map((p) => `<li class="${p.related ? "related" : ""}">
      <span class="p-id">${esc(p.case_id)}</span><span class="p-title">${esc(p.title)} · ${p.state === "closed" ? "abgeschlossen" : "offen"}${p.possible_duplicate ? " · mögliche Doppelmeldung" : ""}</span>
      <span class="p-why">${esc(p.contract_id)} · ${esc(p.reason)}${p.contractor ? ` · damals: ${esc(p.contractor)}` : ""}</span></li>`).join("")}</ul>
    <p class="internal-note">Nur intern: frühere Vorgänge erscheinen nie in der Antwort an den Mieter.</p>`;
}

function urgencyPanel(c) {
  const u = c.urgency;
  if (!u) return "";
  return `<div class="urgency-big"><span class="lvl ${u.level}">${u.level}</span><span>${esc(u.response_target)}</span></div>
    <dl class="urgency-rows">
      <dt>Regel-Untergrenze</dt><dd>${u.rule_level}${u.triggers.length ? ` – ${esc(u.triggers.join(", "))}` : " – keine Regel getroffen"}</dd>
      <dt>KI-Hinweis</dt><dd>${u.llm_level ? `${u.llm_level} – die strengere Stufe gewinnt` : "keiner (Regelmodus)"}</dd>
      <dt>„dringend“ im Text</dt><dd>${u.tenant_says_urgent ? "ja – notiert, erhöht aber nicht" : "nein"}</dd>
    </dl>
    ${u.safety_instructions?.length ? `<ol class="safety">${u.safety_instructions.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>` : ""}`;
}

function approvals(c) {
  const ev = (c.audit || []).filter((a) => a.actor !== "system");
  return {
    assignment: ev.filter((a) => a.event === "approve_assignment").at(-1),
    order: ev.filter((a) => a.event === "order_contractor").at(-1),
    reply: ev.filter((a) => a.event === "approve_reply").at(-1),
    object: ev.filter((a) => a.event === "object_action").at(-1),
    option: ev.filter((a) => a.event === "choose_staff_option").at(-1),
  };
}

function stampHtml(a, fresh) {
  if (!a) return "";
  return `<div class="stamp${fresh ? " fresh" : ""}"><b>Freigegeben</b><span>${esc(a.details?.contract_id || "")} · ${esc(a.actor)} · ${clock(a.ts)}</span></div>`;
}

function carbon(c, opts = {}) {
  const ap = approvals(c);
  const stamp = stampHtml(ap.assignment, opts.freshStamp);
  const r = c.reply_draft, t = c.internal_task;
  const sheets = {
    reply: `<div class="sheet-meta"><span class="label">An</span><span>${esc(r?.to || "Absender (Adresse nicht übermittelt)")}</span>
        <span class="label">Betreff</span><span>${esc(r?.subject)}</span>
        <span class="label">Sprache</span><span>${r?.language === "en" ? "Englisch (wie die E-Mail)" : "Deutsch"}</span></div>
      <div class="letter">${esc(r?.body)}</div>
      <p style="margin-top:.8rem"><span class="never-sent">${icon("mail")}Entwurf – wird nie automatisch gesendet${r?.variant === "ask_registered_email" ? " · Variante: registrierte Adresse erbitten" : ""}</span></p>`,
    task: t ? `<div class="task-title">${esc(t.title)}</div>
      <div class="task-head"><span class="chip u-${t.priority}">${t.priority}</span><span>an: ${esc(t.assignee_role)}</span><span>Frist: ${t.due_hours} Std.</span>
        <span>Ebene: ${{ contract: "Vertrag", object: "Gebäude", routing: "Weiterleitung", clarification: "Klärung" }[t.scope]}</span>
        ${t.contract_id ? `<span>Vertrag: ${esc(t.contract_id)}</span>` : ""}</div>
      <ol class="checklist">${t.checklist.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` : "",
    file: `<div class="file-grid"><div><span class="label">Protokoll dieses Vorgangs</span>
        <ul class="audit-mini">${(c.audit || []).slice(-12).map((a) => `<li><time>${clock(a.ts)}</time><span><b>${esc(a.actor)}</b> · ${esc(a.event)}${a.details?.contract_id ? " · " + esc(a.details.contract_id) : ""}${a.details?.simulated ? " · simuliert" : ""}</span></li>`).join("")}</ul></div>
      <div><span class="label">Strukturierter Datensatz (JSON)</span><pre class="json">${esc(JSON.stringify(c, null, 2))}</pre></div></div>`,
  };
  const tabs = [["reply", "Antwort an Mieter", "weiß · Entwurf"], ["task", "Interne Aufgabe", "gelb · Technik"], ["file", "Aktenvermerk", "rosa · Akte"]];
  return `<section class="carbon" id="s-carbon" aria-label="Durchschreibesatz">
    <div class="carbon-tabs" role="tablist">${tabs.map(([k, n, w]) =>
      `<button class="carbon-tab" role="tab" data-sheet="${k}" aria-selected="${state.sheet === k}">${n}<span class="who">${w}</span></button>`).join("")}</div>
    <div class="carbon-stack"><div class="carbon-sheet" data-sheet="${state.sheet}" role="tabpanel">${stamp}${sheets[state.sheet]}
      ${actionBar(c, ap)}</div></div>
  </section>`;
}

function actionBar(c, ap) {
  const m = c.match;
  const actor = `<label class="label" style="display:flex;flex-direction:column;gap:.2rem">Bearbeitet von<input class="input" id="actor" value="${esc(state.actor)}" autocomplete="name"></label>`;
  let left = "", right = "";
  const replyBtn = `<button class="btn" data-act="approve_reply">${icon("copy")}Entwurf freigeben &amp; kopieren</button>`;
  if (c.status === "OUT_OF_SCOPE") {
    left = `${actor}${replyBtn}`;
    right = `<span class="hint">Keine Vertragsaktion: die Nachricht geht an ${esc(c.internal_task?.assignee_role || "die zuständige Stelle")}.</span>`;
  } else if (ap.assignment) {
    left = `${actor}${replyBtn}`;
    right = ap.order
      ? `<span class="hint">Handwerker beauftragt (simuliert) um ${clock(ap.order.ts)}.</span>`
      : `<button class="btn primary" data-act="order_contractor">Handwerker beauftragen</button><span class="hint">Im Prototyp simuliert – kein Schreibzugriff aufs ERP.</span>`;
  } else if (c.status === "READY_FOR_APPROVAL") {
    left = `${actor}${replyBtn}`;
    right = `<button class="btn primary ${c.urgency?.level === "NOTFALL" ? "alarm" : ""}" data-act="approve_assignment" data-contract="${esc(m.selected_contract)}">Zuordnung ${esc(m.selected_contract)} freigeben</button>
      <span class="hint">Erst nach Ihrer Freigabe darf etwas am Vertrag passieren.</span>`;
  } else {
    const opts = (m.candidates || []).map((x) => `<option value="${esc(x.contract_id)}" ${x.contract_id === m.winner ? "selected" : ""}>${esc(x.contract_id)} · ${esc(x.unit_label)}${x.vetoes.length ? " (widerspricht)" : ""}${x.active ? "" : " (inaktiv)"}</option>`).join("");
    left = `<div class="manual">${actor}
        <label class="label">Vertrag wählen<select class="input" id="manual-contract">${opts}</select></label>
        <label class="label" style="grid-column:1/-1">Begründung (Pflicht)<textarea class="input" id="manual-reason" placeholder="z. B. Mieter hat telefonisch 2. OG links bestätigt"></textarea></label></div>`;
    right = `${replyBtn}<button class="btn primary" data-act="approve_assignment" data-manual="1">Zuordnung manuell freigeben</button>
      <span class="hint">Empfohlen: zuerst die Rückfrage an den Mieter senden.</span>`;
    if (c.urgency?.level === "NOTFALL" && m.object_id && !m.building_uncertain && !ap.object) {
      right = `<button class="btn alarm primary" data-act="object_action">Notdienst zum Gebäude (simuliert)</button><span class="hint">Gebäude ist bekannt – das ist ohne Einheit erlaubt.</span>` + right;
    }
  }
  const staff = c.staff_options?.length && c.status !== "OUT_OF_SCOPE" ? `<div class="staff"><h4>${icon("review")}Nicht von der registrierten E-Mail-Adresse – wie weiter?</h4>
      <div class="opts">${c.staff_options.map((o) => `<button class="btn" data-act="staff" data-option="${o.code}" ${o.available ? "" : "disabled"}>
        ${o.code === "call_tenant" ? icon("phone") : o.code === "ask_registered_email" ? icon("mail") : icon("ready")}${esc(o.label)}${o.detail ? ` · ${esc(o.detail)}` : ""}</button>`).join("")}</div>
      ${ap.option ? `<span class="hint" style="text-align:left">Gewählt: ${esc(ap.option.details?.staff_option)} (${esc(ap.option.actor)}, ${clock(ap.option.ts)})</span>` : ""}</div>` : "";
  return `<div class="actions"><div class="left">${left}</div><div class="right">${right}</div></div>${staff}<p class="err" id="act-err" role="alert"></p>`;
}

function renderCase(opts = {}) {
  const cur = state.current, view = $("#view-case");
  if (!cur) {
    view.innerHTML = `<div class="case"><div class="empty-state"><h3>Eine E-Mail links auswählen</h3><p>Jede Nachricht wird in sechs Schritten gelesen, zugeordnet und eingestuft. Gehandelt wird erst nach Ihrer Freigabe.</p></div></div>`;
    return;
  }
  if (cur.loading) {
    view.innerHTML = `<div class="case"><div class="verdict"><div class="verdict-text"><h3>E-Mail wird gelesen …</h3><p>${esc(PROVIDER_LABEL[state.provider])}</p></div></div><div class="sheet" style="height:320px"></div></div>`;
    return;
  }
  if (cur.error) {
    view.innerHTML = `<div class="case"><div class="empty-state"><h3>Konnte nicht verarbeitet werden</h3><p class="err">${esc(cur.error)}</p></div></div>`;
    return;
  }
  const c = cur.case, sc = cur.scenario, ext = c.understanding.extraction, cl = c.understanding.classification, loc = c.match.location;
  const misses = expectationCheck(sc, c);
  const floorShow = ext.floor_raw ? `<small> → ${loc.floor_note ? esc(loc.floor_note.replace(/^'.*?' /, "")) : floorText(loc)}</small>` : "";
  view.innerHTML = `<div class="case">
    <div class="case-head">
      <h1 class="case-title">${esc(c.input.subject || "(ohne Betreff)")}</h1>
      ${misses ? `<span class="expect ${misses.length ? "bad" : "ok"}">${icon(misses.length ? "mismatch" : "match")}${misses.length ? "Abweichung: " + misses.join(", ") : `Szenario ${esc(sc.id)}: Erwartung erfüllt`}</span>` : "<span></span>"}
      <div class="case-facts"><span>Vorgang <b>${esc(c.case_id)}</b></span><span>Eingang <b>${time(c.received_at)}</b></span>
        <span>Gelesen von <b>${esc(readerLabel(c.processing))}</b></span>
        <span>Regelstand <b>${esc(c.processing.rules_version)}</b></span></div>
    </div>
    ${verdict(c)}
    ${stepsIndex(c)}
    <div class="grid-2">
      <section class="sheet" id="s-input"><div class="sheet-head"><h3><span class="n">1</span>Eingang</h3><span class="aside">unterstrichen = vom Leser erkannt</span></div>
        <div class="email"><div class="email-head"><span class="label">Von</span><span>${esc(c.input.sender_email || "unbekannt")}</span>
          <span class="label">Betreff</span><span>${esc(c.input.subject)}</span></div>
          <div class="email-body">${highlight(c.input.body, ext)}</div></div></section>
      <section class="sheet" id="s-read"><div class="sheet-head"><h3><span class="n">2</span>Erkannt</h3><span class="aside">Sicherheit ${num(cl.confidence * 100, 0)} %</span></div>
        <div class="fields">
          ${field("Art", cl.type === "SCHADENMELDUNG" ? "Schadenmeldung" : cl.type === "ANFRAGE_MIETE" ? "Anfrage zur Miete" : "Sonstiges")}
          ${field("Schadenart · Gewerk", [cl.category, cl.trade].filter(Boolean).join(" · "))}
          ${field("Vertragsinhaber laut Mail", ext.tenant_name)}${field("Absender", ext.sender_name)}
          ${field("Adresse", [ext.street_raw, ext.house_no].filter(Boolean).join(" "))}
          ${field("Etage", ext.floor_raw, floorShow)}${field("Seite", ext.side_raw)}${field("Raum", cap(ext.room))}
          ${field("Seit", ext.since)}${field("Fotos", ext.photos_mentioned ? (c.input.attachments?.length ? "erwähnt, angehängt" : "erwähnt, nicht angehängt") : "nicht erwähnt")}
          ${field("Beschreibung", ext.damage_description, "", true)}
        </div>
        <p class="reader-note"><b>Begründung:</b> ${esc(cl.reason)}${c.understanding.fallback_used ? ` <span class="err">· ${esc(c.understanding.warnings.join(" "))}</span>` : ""}</p>
      </section>
    </div>
    <section class="sheet" id="s-match"><div class="sheet-head"><h3><span class="n">3</span>Zuordnung im ERP</h3><span class="aside">feste Regeln – die KI wählt nie den Vertrag</span></div>
      <div class="match-layout"><div>${candidatesTable(c)}</div>${houseGrid(c)}</div>
      ${gatesPanel(c, sc)}
    </section>
    <div class="grid-2">
      <section class="sheet" id="s-prior"><div class="sheet-head"><h3><span class="n">4</span>Frühere Vorgänge</h3></div>${priorPanel(c)}</section>
      <section class="sheet" id="s-urgency"><div class="sheet-head"><h3><span class="n">5</span>Dringlichkeit</h3><span class="aside">Regeln setzen die Untergrenze</span></div>${urgencyPanel(c)}</section>
    </div>
    ${carbon(c, opts)}
  </div>`;
  bindCase();
}

function bindCase() {
  // linked hover: candidate row <-> flat in the building grid
  $$("[data-unit]").forEach((el) => {
    const on = () => $$(`[data-unit="${el.dataset.unit}"]`).forEach((x) => x.classList.add("hl"));
    const off = () => $$(`[data-unit="${el.dataset.unit}"]`).forEach((x) => x.classList.remove("hl"));
    el.addEventListener("mouseenter", on); el.addEventListener("mouseleave", off);
  });
  $$(".carbon-tab").forEach((b) => b.addEventListener("click", () => { state.sheet = b.dataset.sheet; renderCase(); $(".carbon-tab[aria-selected=true]")?.focus(); }));
  $("#actor")?.addEventListener("change", (e) => { state.actor = e.target.value.trim() || "Sachbearbeitung"; localSet("actor", state.actor); });
  $$("[data-act]").forEach((b) => b.addEventListener("click", () => act(b)));
}

/* ------------------------------------------------------------------ actions */

// Act only on what the server has stored. If that differs from what is on screen
// (e.g. someone else already acted), show the stored version instead of acting blindly.
async function adopt(cur, c) {
  const stored = await api("/api/cases", c);
  const human = (x) => (x.audit || []).filter((e) => e.actor !== "system").length;
  if (human(stored) !== human(c)) {
    cur.case = stored; renderCase();
    throw new Error("Der Vorgang wurde inzwischen geändert – bitte die aktuelle Fassung prüfen.");
  }
  cur.case = stored;
  return stored;
}

function approve(cur, body) {
  return api("/api/approve", { ...body, case_id: cur.case.case_id, actor: state.actor, revision: (cur.case.audit || []).length });
}

async function act(btn) {
  const cur = state.current, c = cur.case, errEl = $("#act-err");
  errEl.textContent = "";
  state.actor = ($("#actor")?.value || state.actor).trim() || "Sachbearbeitung";
  localSet("actor", state.actor);
  const kind = btn.dataset.act;
  btn.classList.add("loading"); btn.disabled = true;
  try {
    if (kind === "approve_reply") {
      await adopt(cur, c);
      cur.case = await approve(cur, { action: "approve_reply" });
      try { await navigator.clipboard.writeText(cur.case.reply_draft.body); toast("Entwurf freigegeben und kopiert – Versand bleibt bei Ihnen."); }
      catch { toast("Entwurf freigegeben. Kopieren nicht erlaubt – bitte Text markieren."); }
      renderCase();
    } else if (kind === "approve_assignment") {
      const manual = btn.dataset.manual === "1";
      const contract = manual ? $("#manual-contract").value : btn.dataset.contract;
      const reason = manual ? $("#manual-reason").value.trim() : null;
      if (manual && !reason) { errEl.textContent = "Bitte eine Begründung angeben – sie steht später im Protokoll."; $("#manual-reason").focus(); return; }
      await adopt(cur, c);
      cur.case = await approve(cur, { action: "approve_assignment", contract_id: contract, reason });
      toast(`Zuordnung ${contract} freigegeben.`);
      renderCase({ freshStamp: true });
    } else if (kind === "order_contractor") {
      await adopt(cur, c);
      const a = approvals(cur.case).assignment;
      cur.case = await approve(cur, { action: "order_contractor", contract_id: cur.case.match.approved_contract, reason: a?.details?.reason });
      toast("Handwerkerauftrag erfasst (simuliert).");
      renderCase();
    } else if (kind === "object_action") {
      await adopt(cur, c);
      cur.case = await approve(cur, { action: "object_action", reason: "Notfall im Gebäude" });
      toast("Notdienst für das Gebäude erfasst (simuliert).");
      renderCase();
    } else if (kind === "staff") {
      const option = btn.dataset.option;
      await adopt(cur, c);
      cur.case = await approve(cur, { action: "choose_staff_option", option, reason: option });
      if (option !== "call_tenant") state.sheet = "reply";
      toast(option === "call_tenant" ? "Anruf vorgemerkt." : "Option gewählt.");
      renderCase();
    }
    loadStore();
  } catch (e) {
    if (e.status === 409) { try { cur.case = await api(`/api/cases/${encodeURIComponent(c.case_id)}`); renderCase(); } catch { /* keep view */ } }
    const el = $("#act-err");
    if (el) el.textContent = e.status === 403 ? `Nicht erlaubt: ${e.message}` : e.status === 409 ? e.message : `Fehler: ${e.message}`;
  } finally {
    btn.classList.remove("loading"); btn.disabled = false;
  }
}

/* ------------------------------------------------------------------ opening */

let selection = 0; // increases with every selection; stale responses are dropped

async function openScenario(id) {
  const token = ++selection;
  const sc = state.scenarios.find((s) => s.id === id);
  const cached = state.results.get(id);
  state.current = { kind: "scenario", id, scenario: sc, case: cached, loading: !cached };
  state.sheet = "reply";
  renderInbox(); renderCase();
  try {
    const c = state.results.get(id) || await api("/api/process", { email: sc.email, scenario_id: sc.id, provider: state.provider });
    state.results.set(id, c);
    if (token !== selection) return;
    Object.assign(state.current, { case: c, loading: false });
  } catch (e) { if (token !== selection) return; Object.assign(state.current, { loading: false, error: e.message }); }
  renderInbox(); renderCase(); $("#desk").focus({ preventScroll: true }); window.scrollTo({ top: 0 });
}

async function openStored(id) {
  const token = ++selection;
  state.current = { kind: "store", id, loading: true };
  renderInbox(); renderCase();
  try { const c = await api(`/api/cases/${encodeURIComponent(id)}`); if (token !== selection) return; Object.assign(state.current, { case: c, loading: false }); }
  catch (e) { if (token !== selection) return; Object.assign(state.current, { loading: false, error: e.message }); }
  renderInbox(); renderCase(); window.scrollTo({ top: 0 });
}

function compose() {
  ++selection;
  switchView("case");
  state.current = null;
  $("#view-case").innerHTML = `<div class="case"><h1 class="case-title">Eigene E-Mail prüfen</h1>
    <form class="compose" id="compose">
      <label class="label">Absender (optional)<input class="input" name="sender_email" type="email" placeholder="mieter@example.org"></label>
      <label class="label">Betreff<input class="input" name="subject" required placeholder="Wasserschaden Küche"></label>
      <label class="label">Text<textarea class="input" name="body" required placeholder="Hallo, seit gestern läuft Wasser …"></textarea></label>
      <div><button class="btn primary" type="submit">E-Mail verarbeiten</button></div>
      <p class="hint" style="text-align:left">Nur Testdaten verwenden – im Modus „Groq live“ geht der Text an einen US-Anbieter.</p>
    </form></div>`;
  $("#compose").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const email = { subject: f.get("subject"), body: f.get("body"), sender_email: f.get("sender_email") || null };
    const token = ++selection;
    state.current = { kind: "custom", id: "custom", loading: true };
    renderCase();
    try { const c = await api("/api/process", { email, provider: state.provider }); if (token !== selection) return; Object.assign(state.current, { case: c, loading: false }); }
    catch (err) { if (token !== selection) return; Object.assign(state.current, { loading: false, error: err.message }); }
    renderCase();
  });
}

/* ------------------------------------------------------------------ other views */

function yamlHtml(text) {
  return text.split("\n").map((line) => {
    const e = esc(line);
    if (/^\s*#/.test(line)) return `<span class="c">${e}</span>`;
    return e.replace(/^(\s*)([\w-]+)(:)/, '$1<span class="k">$2</span>$3').replace(/(:\s*)(-?\d+(?:\.\d+)?|true|false|ask|european)(\s|$)/, '$1<span class="n">$2</span>$3').replace(/(#.*)$/, '<span class="c">$1</span>');
  }).join("\n");
}

async function renderRules() {
  const v = $("#view-rules");
  v.innerHTML = `<div class="page"><h2>Regeln</h2><div class="sheet" style="height:200px"></div></div>`;
  try {
    state.rules = await api("/api/rules");
    const p = state.rules.parsed, m = p.match, w = m.weights;
    const lv = p.urgency.levels;
    v.innerHTML = `<div class="page"><h2>Regeln</h2>
      <p class="lead">Alle fachlichen Regeln stehen in einer Datei: <b>config/rules.yaml</b>. Eine Regel ändern heißt: eine Zeile ändern, speichern und hier neu prüfen. Regelstand ${esc(state.rules.version)}.</p>
      <div class="rule-cards">
        <div class="rule-card"><h3>Zuordnung</h3><dl><dt>Schwelle</dt><dd>${num(m.threshold)}</dd><dt>Mindestabstand</dt><dd>${num(m.min_margin)}</dd>
          <dt>Unbekannter Absender erzwingt Prüfung</dt><dd>${m.unknown_sender_forces_review ? "ja" : "nein"}</dd></dl></div>
        <div class="rule-card"><h3>Punkte je Merkmal</h3><dl>${Object.entries(w).map(([k, x]) => `<dt>${SIG_LABEL[k]}</dt><dd>${num(x)}</dd>`).join("")}</dl></div>
        <div class="rule-card"><h3>Dringlichkeit</h3><dl>${Object.entries(lv).map(([k, x]) => `<dt>${k}</dt><dd>${esc(x.response_target)}</dd>`).join("")}
          <dt>Englische Etagen</dt><dd>${p.normalize.english_floor_counting === "ask" ? "nachfragen" : "europäisch"}</dd></dl></div>
      </div>
      <div><button class="btn primary" id="recheck">Alle Beispiele mit diesen Regeln neu prüfen</button></div>
      <div id="recheck-out"></div>
      <pre class="yaml">${yamlHtml(state.rules.yaml)}</pre></div>`;
    $("#recheck").addEventListener("click", recheckAll);
  } catch (e) { v.innerHTML = `<div class="page"><h2>Regeln</h2><p class="err">${esc(e.message)}</p></div>`; }
}

async function recheckAll() {
  const out = $("#recheck-out");
  out.innerHTML = `<p class="reader-note">Prüfe ${state.scenarios.length} Beispiele …</p>`;
  state.results.clear();
  const rows = [];
  for (const sc of state.scenarios) {
    const c = await api("/api/process", { email: sc.email, scenario_id: sc.id, provider: state.provider === "groq" ? "offline" : state.provider });
    state.results.set(sc.id, c);
    rows.push({ sc, c, misses: expectationCheck(sc, c) });
  }
  const bad = rows.filter((r) => r.misses.length).length;
  out.innerHTML = `<table class="log"><thead><tr><th>Szenario</th><th>Status</th><th>Vertrag</th><th>Dringlichkeit</th><th>Prüfregeln</th><th>Erwartung</th></tr></thead><tbody>
    ${rows.map(({ sc, c, misses }) => `<tr><td><b>${esc(sc.id)}</b> ${esc(sc.title)}</td><td><span class="chip s-${c.status}">${STATUS[c.status].label}</span></td>
      <td>${esc(c.match.selected_contract || "–")}</td><td>${esc(c.urgency.level)}</td><td>${esc((c.match.failed_gates || []).join(", ") || "–")}</td>
      <td>${misses.length ? `<span class="err">weicht ab: ${esc(misses.join(", "))}</span>` : "✓ erfüllt"}</td></tr>`).join("")}</tbody></table>
    <p class="reader-note">${bad ? `${bad} Beispiel(e) verhalten sich mit den geänderten Regeln anders als erwartet – genau das soll sichtbar werden.` : "Alle Beispiele verhalten sich wie erwartet."}</p>`;
  renderInbox();
}

async function renderAudit() {
  const v = $("#view-audit");
  try {
    const lines = await api("/api/audit");
    v.innerHTML = `<div class="page"><h2>Protokoll</h2><p class="lead">Jede menschliche Aktion – Freigabe, Auftrag, Option – wird hier unveränderlich angehängt (var/audit.jsonl). Systemschritte stehen im Vorgang selbst.</p>
      ${lines.length ? `<table class="log"><thead><tr><th>Zeit</th><th>Wer</th><th>Aktion</th><th>Vorgang</th><th>Vertrag</th><th>Begründung</th></tr></thead><tbody>
      ${[...lines].reverse().map((l) => `<tr><td>${time(l.ts)}</td><td>${esc(l.actor)}</td><td>${esc(l.event)}</td><td>${esc(l.details?.case_id)}</td><td>${esc(l.details?.contract_id || l.details?.object_id || "–")}</td><td>${esc(l.details?.reason || "–")}</td></tr>`).join("")}</tbody></table>`
      : `<div class="empty-state"><h3>Noch keine Aktionen</h3><p>Sobald jemand eine Zuordnung oder einen Entwurf freigibt, erscheint es hier.</p></div>`}</div>`;
  } catch (e) { v.innerHTML = `<div class="page"><h2>Protokoll</h2><p class="err">${esc(e.message)}</p></div>`; }
}

function renderFlow() {
  $("#view-flow").innerHTML = `<div class="page"><h2>Ablauf</h2>
    <p class="lead">Der sichtbare Prozess läuft in n8n: ein Knoten pro Schritt. n8n leitet nur weiter – entschieden wird im Python-Dienst nach den Regeln, gehandelt erst nach Freigabe hier.</p>
    <figure class="flow-figure"><img src="/static/n8n-workflow.png" alt="n8n-Workflow: E-Mail eingegangen, verstehen, zuordnen, frühere Vorgänge, Dringlichkeit, Entwurf, Aufgabe, Prüfliste" onerror="this.closest('figure').hidden=true"></figure>
    <ol class="flow-steps">
      <li><b>Verstehen</b>Art, Schadenart und Fakten aus der E-Mail lesen – mit Groq oder ohne KI per Regeln.</li>
      <li><b>Zuordnen</b>Punkte je Merkmal, Widersprüche schließen aus, Schwelle und Abstand, Vertrag aktiv?</li>
      <li><b>Frühere Vorgänge</b>Verwandte Fälle derselben Einheit, nur intern.</li>
      <li><b>Dringlichkeit</b>Regeln setzen die Untergrenze, die KI darf nur erhöhen.</li>
      <li><b>Entwurf</b>Antwort in der Sprache der E-Mail – ohne ERP-Daten, wenn unklar.</li>
      <li><b>Aufgabe</b>Handwerker, Klärung, Gebäude-Notdienst oder Weiterleitung – immer mit Freigabe.</li>
    </ol></div>`;
}

function switchView(name) {
  $$(".view").forEach((v) => (v.hidden = v.dataset.view !== name));
  $$(".view-tab").forEach((t) => t.setAttribute("aria-current", t.dataset.view === name ? "page" : "false"));
  if (name === "rules") renderRules();
  if (name === "audit") renderAudit();
  if (name === "flow") renderFlow();
}

/* ------------------------------------------------------------------ boot */

function bind() {
  $("#provider").value = state.provider;
  $("#provider").addEventListener("change", async (e) => {
    state.provider = e.target.value; localSet("provider", state.provider);
    const keep = state.current?.kind === "scenario" ? state.current.id : null;
    await loadScenarios();
    if (keep) openScenario(keep);
  });
  $$(".view-tab").forEach((t) => t.addEventListener("click", () => switchView(t.dataset.view)));
  $$(".segmented button").forEach((b) => b.addEventListener("click", async () => {
    state.source = b.dataset.source;
    $$(".segmented button").forEach((x) => x.setAttribute("aria-selected", x === b));
    if (state.source === "store") await loadStore();
    renderInbox();
  }));
  $("#inbox-list").addEventListener("click", (e) => {
    const b = e.target.closest(".mail[data-key]");
    if (!b) return;
    switchView("case");
    state.source === "demo" ? openScenario(b.dataset.key) : openStored(b.dataset.key);
  });
  $("#new-mail").addEventListener("click", compose);
}

(async function boot() {
  bind();
  renderCase();
  try {
    state.rules = await api("/api/rules");
    await loadScenarios();
    const first = [...state.scenarios].find((s) => s.id === "S1") || state.scenarios[0];
    if (first) openScenario(first.id);
    loadStore();
  } catch (e) {
    $("#view-case").innerHTML = `<div class="case"><div class="empty-state"><h3>Dienst nicht erreichbar</h3><p class="err">${esc(e.message)}</p><p>Start: <code>uv run intake-ui</code></p></div></div>`;
  }
})();
