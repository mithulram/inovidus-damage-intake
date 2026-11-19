// Schadenmeldungen · Prüfplatz – vanilla JS, no build step. German default, English on request.
// The UI only displays and asks; every decision comes from the API, every action goes through /api/approve.
import { L } from "/static/i18n.js";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (id) => `<svg aria-hidden="true"><use href="#i-${id}"/></svg>`;
const cap = (v) => (v ? v.charAt(0).toUpperCase() + v.slice(1) : v);

function localGet(k) { try { return localStorage.getItem("intake." + k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem("intake." + k, v); } catch { /* private mode */ } }

const state = {
  provider: localGet("provider") || "offline",
  lang: localGet("lang") || "de",            // de | en | both (English with German original)
  source: "demo",
  scenarios: [],
  results: new Map(),   // scenario id -> case
  store: [],
  current: null,        // { kind: 'scenario'|'store'|'custom', id, case, scenario }
  sheet: "reply",
  rules: null,
  actor: localGet("actor") || "Sachbearbeitung",
  tx: new Map(),        // German system text -> English (or null)
};

/* ------------------------------------------------------------------ language */

const ui = () => L[state.lang === "de" ? "de" : "en"];
function t(key, ...args) { const v = ui()[key] ?? L.de[key] ?? key; return typeof v === "function" ? v(...args) : v; }
const num = (v, d = 2) => (v == null ? "–" : Number(v).toLocaleString(ui().numLocale, { minimumFractionDigits: d, maximumFractionDigits: d }));
const time = (iso) => (iso ? new Date(iso).toLocaleString(ui().numLocale, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "–");
const clock = (iso) => (iso ? new Date(iso).toLocaleTimeString(ui().numLocale, { hour: "2-digit", minute: "2-digit" }) : "");

// A German system text (reason, gate, task item …) rendered in the chosen language.
// en: English only (German on hover); both: English + German original; untranslatable free text stays German, labelled.
function X(de, { free = false } = {}) {
  if (de == null || de === "") return "";
  if (state.lang === "de") return esc(de);
  const en = state.tx.get(de);
  if (en) {
    return state.lang === "both"
      ? `${esc(en)}<span class="orig" lang="de">${esc(de)}</span>`
      : `<span title="DE: ${esc(de)}">${esc(en)}</span>`;
  }
  return `<span lang="de">${esc(de)}</span>${free ? ` <span class="untr">${esc(t("aiFree"))} · DE</span>` : ""}`;
}

function caseTexts(c) {
  if (!c?.match) return [];
  const m = c.match, u = c.urgency, it = c.internal_task, cl = c.understanding?.classification;
  const out = [m.reason, ...(m.flags || []).map((f) => f.message), ...(c.warnings || []), cl?.reason, cl?.category, cl?.trade,
    u?.reason, ...(u?.triggers || []), u?.response_target, ...(u?.safety_instructions || []),
    it?.title, ...(it?.checklist || []), it?.assignee_role, ...(c.staff_options || []).map((o) => o.label),
    ...(c.prior_cases || []).map((p) => p.reason), ...(c.prior_cases || []).map((p) => p.title)];
  for (const k of m.candidates || []) out.push(...k.signals.map((s) => s.reason), ...k.vetoes);
  return out.filter(Boolean);
}

async function ensureTx(texts) {
  if (state.lang === "de") return false;
  const missing = [...new Set(texts)].filter((x) => !state.tx.has(x));
  if (!missing.length) return false;
  try {
    const { translations } = await api("/api/translate", { texts: missing });
    for (const [k, v] of Object.entries(translations)) state.tx.set(k, v);
  } catch { for (const k of missing) state.tx.set(k, null); }
  return true;
}

function applyStatic() {
  document.documentElement.lang = state.lang === "de" ? "de" : "en";
  $$("[data-t]").forEach((el) => { el.textContent = t(el.dataset.t); });
  $("#lang").value = state.lang;
  document.title = `${t("brand")} · ${t("brandSub")}`;
}

const STATUS = () => ({
  READY_FOR_APPROVAL: { label: t("stReady"), long: t("stReadyLong"), icon: "ready" },
  NEEDS_REVIEW: { label: t("stReview"), long: t("stReviewLong"), icon: "review" },
  OUT_OF_SCOPE: { label: t("stOut"), long: t("stOutLong"), icon: "route" },
});
const URG = (lv) => (state.lang === "de" ? lv : { NOTFALL: "EMERGENCY", DRINGEND: "URGENT", NORMAL: "NORMAL" }[lv] || lv);
const URG_RANK = { NOTFALL: 0, DRINGEND: 1, NORMAL: 2 };
const SIG = (n) => t({ name: "sigName", address: "sigAddress", floor: "sigFloor", side: "sigSide", contact: "sigContact" }[n]);
const RES = (r) => t({ match: "rMatch", partial: "rPartial", missing: "rMissing", mismatch: "rMismatch" }[r]);
function readerLabel(p) {
  const name = { offline: t("rOffline"), groq: t("rGroq"), "recorded(groq)": t("rRecorded"), "groq→offline": t("rFallback") }[p.provider] || p.provider;
  return p.model ? `${name} · ${p.model}` : name;
}
const providerLabel = () => ({ offline: t("provOffline"), recorded: t("provRecorded"), groq: t("provGroq") }[state.provider]);

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
    const err = new Error(msg || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.hidden = true), 3200);
}

/* ------------------------------------------------------------------ inbox */

function urgencyOf(c) { return c?.urgency?.level || null; }

function mailRow({ key, subject, sender, status, urgency, idText, current, pending }) {
  if (pending) return `<li><div class="mail skeleton" aria-label="${esc(t("reading"))}"></div></li>`;
  const s = STATUS()[status];
  return `<li><button class="mail ${urgency ? "u-" + urgency : ""}" data-key="${esc(key)}" aria-current="${current}">
      <span class="mail-subject">${esc(subject || t("noSubject"))}</span>
      <span class="mail-id">${esc(idText)}</span>
      <span class="mail-meta">
        ${urgency === "NOTFALL" ? `<span class="chip u-NOTFALL">${icon("alert")}${URG("NOTFALL")}</span>` : ""}
        ${s ? `<span class="chip s-${status}">${icon(s.icon)}${esc(s.label)}</span>` : `<span class="chip s-OUT_OF_SCOPE">${esc(t("notRead"))}</span>`}
        <span class="who">${esc(sender || t("senderUnknown"))}</span>
      </span>
    </button></li>`;
}

function renderInbox() {
  const list = $("#inbox-list");
  const cur = state.current;
  if (state.source === "demo") {
    $("#inbox-note").textContent = t("inboxDemoNote");
    const rows = state.scenarios.map((sc, i) => ({ sc, i, c: state.results.get(sc.id) }));
    rows.sort((a, b) => (URG_RANK[urgencyOf(a.c)] ?? 3) - (URG_RANK[urgencyOf(b.c)] ?? 3) || a.i - b.i);
    list.innerHTML = rows.map(({ sc, c }) => mailRow({
      key: sc.id, subject: sc.email.subject, sender: sc.email.sender_email || c?.understanding?.extraction?.sender_name,
      status: c?.status, urgency: urgencyOf(c), idText: sc.id,
      current: cur?.kind === "scenario" && cur.id === sc.id,
      pending: c === undefined && state.provider !== "groq",
    })).join("");
  } else {
    $("#inbox-note").textContent = state.store.length ? t("inboxStoreNote") : "";
    if (!state.store.length) {
      list.innerHTML = `<li class="empty-state"><h3>${esc(t("storeEmptyH"))}</h3><p>${esc(t("storeEmptyP"))}</p></li>`;
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
    } catch { state.results.set(sc.id, null); }
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

function field(label, valueHtml, extra = "", wide = false) {
  const empty = valueHtml == null || valueHtml === "";
  return `<div class="field${wide ? " wide" : ""}"><span class="label">${esc(label)}</span>
    <span class="v${empty ? " empty" : ""}">${empty ? esc(t("notGiven")) : valueHtml}${extra}</span></div>`;
}

const floorName = (f) => (f === 0 ? t("gfloor") : t("ogFloor", f));

function effectiveRules(sc) {
  const base = state.rules?.parsed?.match || {};
  const over = sc?.rule_overrides?.match || {};
  return { threshold: over.threshold ?? base.threshold, min_margin: over.min_margin ?? base.min_margin };
}

function expectationCheck(sc, c) {
  if (!sc?.expected || !c) return null;
  const e = sc.expected, misses = [];
  if (e.status && e.status !== c.status) misses.push(t("mStatus"));
  if ("contract" in e && (e.contract ?? null) !== (c.match?.selected_contract ?? null)) misses.push(t("mContract"));
  if (e.urgency && e.urgency !== c.urgency?.level) misses.push(t("mUrgency"));
  if (e.failed_gates) {
    const a = [...(c.match?.failed_gates || [])].sort().join(","), b = [...e.failed_gates].sort().join(",");
    if (a !== b) misses.push(t("mGates"));
  }
  return misses;
}

function stepsIndex(c) {
  const m = c.match, u = c.urgency, cl = c.understanding?.classification;
  const stop = c.status === "NEEDS_REVIEW";
  const items = [
    ["s-input", t("step1"), esc(c.input.sender_email || t("senderUnknown")), "done"],
    ["s-read", t("step2"), cl ? X(cl.category || cl.type) : "–", "done"],
    ["s-match", t("step3"), esc(m?.approved_contract || m?.selected_contract || (c.status === "OUT_OF_SCOPE" ? t("notNeeded") : t("openReview"))),
      m?.selected_contract || m?.approved_contract || c.status === "OUT_OF_SCOPE" ? "done" : "stop"],
    ["s-prior", t("step4"), esc(c.prior_cases?.length ? t("relatedN", c.prior_cases.filter((p) => p.related).length) : t("none")), "done"],
    ["s-urgency", t("step5"), esc(u ? URG(u.level) : "–"), u?.level === "NOTFALL" ? "alarm" : "done"],
    ["s-carbon", t("step6"), esc(t("draftNotSent")), stop ? "stop" : "done"],
  ];
  return `<ol class="steps" aria-label="${esc(t("stepsAria"))}">${items.map(([id, name, out, st]) =>
    `<li class="${st}"><a href="#${id}"><span class="step-name">${esc(name)}</span><span class="step-out">${out}</span></a></li>`).join("")}</ol>`;
}

function verdict(c) {
  const s = STATUS()[c.status] || STATUS().NEEDS_REVIEW;
  const m = c.match;
  let line = X(m?.reason || "");
  if (c.status === "READY_FOR_APPROVAL") line = esc(t("allPassed", m.selected_contract, num(m.score), num(m.margin)));
  if (c.status === "NEEDS_REVIEW") line = (m.flags || []).map((f) => X(f.message)).join(" · ");
  if (m?.approved_contract) line = esc(t("humanApproved", m.approved_contract)) + line;
  const u = c.urgency;
  return `<div class="verdict s-${c.status}${u?.level === "NOTFALL" ? " emergency" : ""}">
    <svg class="verdict-icon" aria-hidden="true"><use href="#i-${s.icon}"/></svg>
    <div class="verdict-text"><h3>${esc(s.long)}</h3><p>${line}</p></div>
    <div class="verdict-urgency">${u ? `<span class="chip u-${u.level}">${u.level === "NOTFALL" ? icon("alert") : ""}${URG(u.level)}</span><span>${X(u.response_target)}</span>` : ""}</div>
  </div>`;
}

function sigCell(sig) {
  const label = `${SIG(sig.name)}: ${state.lang === "de" ? sig.reason : state.tx.get(sig.reason) || sig.reason}`;
  return `<td class="sig"><span class="sig-mark sig-${sig.result}" title="${esc(label)}">
    <svg role="img" aria-label="${esc(SIG(sig.name))} ${esc(RES(sig.result))}"><use href="#i-${sig.result}"/></svg></span></td>`;
}

function clearWinner(m) {
  const f = new Set(m.failed_gates || []);
  return m.winner && !f.has("threshold") && !f.has("margin") ? m.winner : null;
}

function candidatesTable(c) {
  const m = c.match, win = clearWinner(m);
  if (!m?.candidates?.length) return `<p class="err">${esc(t("noContract"))}</p>`;
  const order = ["name", "address", "floor", "side", "contact"];
  const rows = m.candidates.map((cand) => {
    const sigs = order.map((n) => cand.signals.find((s) => s.name === n));
    const cls = ["cand", cand.contract_id === win ? "winner" : "", cand.vetoes.length ? "vetoed" : ""].join(" ");
    const reasons = [...cand.vetoes.map((v) => `<span class="veto">Veto: ${X(v)}</span>`),
      ...sigs.filter((s) => s.result === "partial" || (s.result === "missing" && s.name !== "contact") || (s.result === "mismatch" && !["address", "floor", "side"].includes(s.name)))
        .map((s) => `${esc(SIG(s.name))}: ${X(s.reason)}`)];
    return `<tr class="${cls}" data-unit="${esc(cand.unit_id)}">
      <td><span class="cid">${esc(cand.contract_id)}</span> ${cand.active ? "" : `<span class="inactive-tag">${esc(t("inactive"))}</span>`}
        <span class="unit">${esc(cand.tenant_name)} · ${esc(cand.unit_label)}</span>
        <div class="why">${reasons.length ? reasons.join("<br>") : esc(t("allFit"))}</div></td>
      ${sigs.map(sigCell).join("")}
      <td class="score">${num(cand.score)}</td>
    </tr>`;
  }).join("");
  return `<table class="cands"><thead><tr><th>${esc(t("contract"))}</th>${order.map((n) => `<th class="sig">${esc(SIG(n))}</th>`).join("")}<th>${esc(t("points"))}</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="legend">
      <span><span class="sig-mark sig-match"><svg><use href="#i-match"/></svg></span>${esc(t("legMatch"))}</span>
      <span><span class="sig-mark sig-partial"><svg><use href="#i-partial"/></svg></span>${esc(t("legPartial"))}</span>
      <span><span class="sig-mark sig-missing"><svg><use href="#i-missing"/></svg></span>${esc(t("legMissing"))}</span>
      <span><span class="sig-mark sig-mismatch"><svg><use href="#i-mismatch"/></svg></span>${esc(t("legMismatch"))}</span>
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
  const maxF = Math.min(30, Math.max(3, ...units.map((u) => u.pos.floor)));
  const sides = units.some((u) => u.pos.side === "M") ? ["L", "M", "R"] : ["L", "R"];
  const sideName = { L: t("left"), M: t("centre"), R: t("right") };
  const addr = inHouse[0]?.unit_label?.split(",")[0] || objectId;
  let cells = `<span></span>${sides.map((s) => `<span class="colh">${esc(sideName[s])}</span>`).join("")}`;
  for (let f = maxF; f >= 0; f--) {
    cells += `<span class="fl">${esc(floorName(f))}</span>`;
    for (const s of sides) {
      const here = units.filter((u) => u.pos.floor === f && u.pos.side === s);
      const said = m.object_id === objectId && Number.isInteger(loc.floor) && loc.floor === f && (loc.side == null || loc.side === s);
      const saidTag = said ? `<span class="said" title="${esc(t("perEmail"))}">${esc(t("emailTag"))}</span>` : "";
      if (!here.length) { cells += `<div class="unit-cell empty">${saidTag}</div>`; continue; }
      const u = here[0];
      const cls = ["unit-cell", "cand", u.contract_id === win ? "winner" : "", u.vetoes.length ? "vetoed" : "", u.active ? "" : "inactive"].join(" ");
      cells += `<div class="${cls}" data-unit="${esc(u.unit_id)}">${saidTag}<span class="uc-id">${esc(u.contract_id)}</span>${esc(u.tenant_name)}</div>`;
    }
  }
  return `<div class="house" aria-label="${esc(addr)}"><div class="house-title">${esc(addr)}</div>
    <div class="house-sub">${esc(t("houseSub"))}</div>
    <div class="house-grid" style="--cols:${sides.length}">${cells}</div></div>`;
}

function gatesPanel(c, sc) {
  const m = c.match, failed = new Set(m.failed_gates || []);
  if (c.status === "OUT_OF_SCOPE") return `<p class="reader-note">${esc(t("outNote"))}</p>`;
  const r = effectiveRules(sc);
  const vetoFailed = failed.has("veto_address") || failed.has("veto_unit") || failed.has("no_candidate");
  const vetoCount = (m.candidates || []).filter((x) => x.vetoes.length).length;
  const vetoText = vetoCount === 0 ? t("vetoNone") : vetoCount === 1 ? t("veto1") : t("vetoN", vetoCount);
  const unitOpen = failed.has("threshold") || failed.has("margin") || m.winner == null;
  const g = [
    [t("gVeto"), vetoFailed ? "fail" : "pass", vetoFailed ? t("vetoTop") : vetoText],
    [t("gThreshold"), m.winner == null ? "skip" : failed.has("threshold") ? "fail" : "pass", m.winner == null ? t("noCand") : `${num(m.score)} ${failed.has("threshold") ? "<" : "≥"} ${num(r.threshold)}`],
    [t("gMargin"), m.winner == null ? "skip" : failed.has("margin") ? "fail" : "pass", m.winner == null ? "–" : `${num(m.margin)} ${failed.has("margin") ? "<" : "≥"} ${num(r.min_margin)}`],
    [t("gActive"), failed.has("eligibility") ? "fail" : unitOpen ? "skip" : "pass", failed.has("eligibility") ? t("ended") : unitOpen ? t("afterUnit") : t("active")],
  ];
  const ico = { pass: "match", fail: "mismatch", skip: "missing" };
  const otherFlags = (m.flags || []).filter((f) => ["identity", "floor_missing", "floor_ambiguous", "unit_ambiguous"].includes(f.gate));
  return `<ul class="gates" aria-label="${esc(t("gatesAria"))}">${g.map(([n, st, v]) =>
      `<li class="gate ${st}"><span class="g-name">${icon(ico[st])}${esc(n)}</span><span class="g-val">${esc(v)}</span></li>`).join("")}</ul>
    ${otherFlags.length ? `<div class="flags">${otherFlags.map((f) => `<div class="flag">${icon("review")}<span>${X(f.message)}</span></div>`).join("")}</div>` : ""}
    ${c.match.unknown_sender ? `<div class="flags"><div class="flag">${icon("review")}<span>${esc(t("unknownSenderFlag"))}</span></div></div>` : ""}`;
}

function priorPanel(c) {
  if (!c.prior_cases?.length) return `<p class="reader-note">${esc(t("noPrior", c.match?.approved_contract || c.match?.selected_contract || c.match?.winner || t("theCands")))}</p>`;
  return `<ul class="prior">${c.prior_cases.map((p) => `<li class="${p.related ? "related" : ""}">
      <span class="p-id">${esc(p.case_id)}</span><span class="p-title">${X(p.title)} · ${esc(p.state === "closed" ? t("closed") : t("open"))}${p.possible_duplicate ? " · " + esc(t("dup")) : ""}</span>
      <span class="p-why">${esc(p.contract_id)} · ${X(p.reason)}${p.contractor ? ` · ${esc(t("then"))}: ${esc(p.contractor)}` : ""}</span></li>`).join("")}</ul>
    <p class="internal-note">${esc(t("internalOnly"))}</p>`;
}

function urgencyPanel(c) {
  const u = c.urgency;
  if (!u) return "";
  return `<div class="urgency-big"><span class="lvl ${u.level}">${URG(u.level)}</span><span>${X(u.response_target)}</span></div>
    <dl class="urgency-rows">
      <dt>${esc(t("ruleFloor"))}</dt><dd>${URG(u.rule_level)}${u.triggers.length ? ` – ${u.triggers.map((x) => X(x)).join(", ")}` : ` – ${esc(t("noRule"))}`}</dd>
      <dt>${esc(t("aiHint"))}</dt><dd>${u.llm_level ? `${URG(u.llm_level)} – ${esc(t("strictWins"))}` : esc(t("noHint"))}</dd>
      <dt>${esc(t("urgentWord"))}</dt><dd>${esc(u.tenant_says_urgent ? t("urgentYes") : t("no"))}</dd>
    </dl>
    ${u.safety_instructions?.length ? `<ol class="safety">${u.safety_instructions.map((s) => `<li>${X(s)}</li>`).join("")}</ol>` : ""}`;
}

function approvals(c) {
  const all = c.audit || [];
  const reset = all.map((a) => a.event.startsWith("neu verarbeitet (Regeln geändert)")).lastIndexOf(true);
  const ev = all.slice(reset + 1).filter((a) => a.actor !== "system");
  const assignIdx = ev.map((a) => a.event).lastIndexOf("approve_assignment");
  const assignment = assignIdx >= 0 ? ev[assignIdx] : undefined;
  return {
    assignment,
    // an order only counts for the CURRENT assignment (later than it, same contract)
    order: ev.slice(assignIdx + 1).filter((a) => a.event === "order_contractor"
      && a.details?.contract_id === c.match?.approved_contract).at(-1),
    reply: ev.filter((a) => a.event === "approve_reply").at(-1),
    object: ev.filter((a) => a.event === "object_action").at(-1),
    option: ev.filter((a) => a.event === "choose_staff_option").at(-1),
  };
}

function stampHtml(a, fresh) {
  if (!a) return "";
  return `<div class="stamp${fresh ? " fresh" : ""}"><b>${esc(t("approved"))}</b><span>${esc(a.details?.contract_id || "")} · ${esc(a.actor)} · ${clock(a.ts)}</span></div>`;
}

const actionName = (ev) => ui().actions[ev] || ev;

function carbon(c, opts = {}) {
  const ap = approvals(c);
  const stamp = stampHtml(ap.assignment, opts.freshStamp);
  const r = c.reply_draft, tk = c.internal_task;
  const scope = { contract: t("lvContract"), object: t("lvObject"), routing: t("lvRouting"), clarification: t("lvClar") };
  const sheets = {
    reply: `<div class="sheet-meta"><span class="label">${esc(t("to"))}</span><span>${esc(r?.to || t("toUnknown"))}</span>
        <span class="label">${esc(t("subject"))}</span><span>${esc(r?.subject)}</span>
        <span class="label">${esc(t("language"))}</span><span>${esc(r?.language === "en" ? t("langEnEmail") : t("langDe"))}</span></div>
      <div class="letter" lang="${esc(r?.language || "de")}">${esc(r?.body)}</div>
      <p style="margin-top:.8rem"><span class="never-sent">${icon("mail")}${esc(t("neverSent"))}${r?.variant === "ask_registered_email" ? esc(t("variantReg")) : ""}</span>
      ${state.lang !== "de" ? `<span class="never-sent" style="margin-left:.4rem">${esc(t("replyLangNote"))}</span>` : ""}</p>`,
    task: tk ? `<div class="task-title">${X(tk.title)}</div>
      <div class="task-head"><span class="chip u-${tk.priority}">${URG(tk.priority)}</span><span>${esc(t("assignee"))}: ${X(tk.assignee_role)}</span><span>${esc(t("due"))}: ${tk.due_hours} ${esc(t("hours"))}</span>
        <span>${esc(t("level"))}: ${esc(scope[tk.scope])}</span>
        ${tk.contract_id ? `<span>${esc(t("contract"))}: ${esc(tk.contract_id)}</span>` : ""}</div>
      <ol class="checklist">${tk.checklist.map((x) => `<li>${X(x)}</li>`).join("")}</ol>` : "",
    file: `<div class="file-grid"><div><span class="label">${esc(t("caseLog"))}</span>
        <ul class="audit-mini">${(c.audit || []).slice(-12).map((a) => `<li><time>${clock(a.ts)}</time><span><b>${esc(a.actor)}</b> · ${esc(actionName(a.event))}${a.details?.contract_id ? " · " + esc(a.details.contract_id) : ""}${a.details?.simulated ? " · " + esc(t("simulated")) : ""}</span></li>`).join("")}</ul></div>
      <div><span class="label">${esc(t("record"))}</span><pre class="json">${esc(JSON.stringify(c, null, 2))}</pre></div></div>`,
  };
  const tabs = [["reply", t("shReply"), t("shReplyW")], ["task", t("shTask"), t("shTaskW")], ["file", t("shFile"), t("shFileW")]];
  return `<section class="carbon" id="s-carbon" aria-label="${esc(t("carbonAria"))}">
    <div class="carbon-tabs" role="tablist">${tabs.map(([k, n, w]) =>
      `<button class="carbon-tab" role="tab" data-sheet="${k}" aria-selected="${state.sheet === k}">${esc(n)}<span class="who">${esc(w)}</span></button>`).join("")}</div>
    <div class="carbon-stack"><div class="carbon-sheet" data-sheet="${state.sheet}" role="tabpanel">${stamp}${sheets[state.sheet]}
      ${actionBar(c, ap)}</div></div>
  </section>`;
}

function actionBar(c, ap) {
  const m = c.match;
  const actor = `<label class="label" style="display:flex;flex-direction:column;gap:.2rem">${esc(t("editedBy"))}<input class="input" id="actor" value="${esc(state.actor)}" autocomplete="name"></label>`;
  let left = "", right = "";
  const replyBtn = `<button class="btn" data-act="approve_reply">${icon("copy")}${esc(t("approveCopy"))}</button>`;
  if (c.status === "OUT_OF_SCOPE") {
    left = `${actor}${replyBtn}`;
    right = `<span class="hint">${esc(t("noContractAction", "§")).replace("§", X(c.internal_task?.assignee_role || "") || esc(t("theRole")))}</span>`;
  } else if (ap.assignment) {
    left = `${actor}${replyBtn}`;
    right = ap.order
      ? `<span class="hint">${esc(t("ordered", clock(ap.order.ts)))}</span>`
      : `<button class="btn primary" data-act="order_contractor">${esc(t("order"))}</button><span class="hint">${esc(t("orderHint"))}</span>`;
  } else if (c.status === "READY_FOR_APPROVAL") {
    left = `${actor}${replyBtn}`;
    right = `<button class="btn primary ${c.urgency?.level === "NOTFALL" ? "alarm" : ""}" data-act="approve_assignment" data-contract="${esc(m.selected_contract)}">${esc(t("approveX", m.selected_contract))}</button>
      <span class="hint">${esc(t("approveHint"))}</span>`;
  } else {
    const opts = (m.candidates || []).map((x) => `<option value="${esc(x.contract_id)}" ${x.contract_id === m.winner ? "selected" : ""}>${esc(x.contract_id)} · ${esc(x.unit_label)}${x.vetoes.length ? esc(t("contradicts")) : ""}${x.active ? "" : esc(t("inactiveOpt"))}</option>`).join("");
    left = `<div class="manual">${actor}
        <label class="label">${esc(t("chooseContract"))}<select class="input" id="manual-contract">${opts}</select></label>
        <label class="label" style="grid-column:1/-1">${esc(t("reasonReq"))}<textarea class="input" id="manual-reason" placeholder="${esc(t("reasonPh"))}"></textarea></label></div>`;
    right = `${replyBtn}<button class="btn primary" data-act="approve_assignment" data-manual="1">${esc(t("approveManual"))}</button>
      <span class="hint">${esc(t("askFirst"))}</span>`;
    if (c.urgency?.level === "NOTFALL" && m.object_id && !m.building_uncertain && !ap.object) {
      right = `<button class="btn alarm primary" data-act="object_action">${esc(t("objectAction"))}</button><span class="hint">${esc(t("objectHint"))}</span>` + right;
    }
  }
  const staff = c.staff_options?.length && c.status !== "OUT_OF_SCOPE" ? `<div class="staff"><h4>${icon("review")}${esc(t("staffH"))}</h4>
      <div class="opts">${c.staff_options.map((o) => `<button class="btn" data-act="staff" data-option="${o.code}" ${o.available ? "" : "disabled"}>
        ${o.code === "call_tenant" ? icon("phone") : o.code === "ask_registered_email" ? icon("mail") : icon("ready")}${X(o.label)}${o.detail ? ` · ${esc(o.detail)}` : ""}</button>`).join("")}</div>
      ${ap.option ? `<span class="hint" style="text-align:left">${esc(t("chosen"))}: ${esc(ap.option.details?.staff_option)} (${esc(ap.option.actor)}, ${clock(ap.option.ts)})</span>` : ""}</div>` : "";
  return `<div class="actions"><div class="left">${left}</div><div class="right">${right}</div></div>${staff}<p class="err" id="act-err" role="alert"></p>`;
}

function renderCase(opts = {}) {
  const cur = state.current, view = $("#view-case");
  if (!cur) {
    view.innerHTML = `<div class="case"><div class="empty-state"><h3>${esc(t("pickH"))}</h3><p>${esc(t("pickP"))}</p></div></div>`;
    return;
  }
  if (cur.loading) {
    view.innerHTML = `<div class="case"><div class="verdict"><div class="verdict-text"><h3>${esc(t("readingH"))}</h3><p>${esc(providerLabel())}</p></div></div><div class="sheet" style="height:320px"></div></div>`;
    return;
  }
  if (cur.error) {
    view.innerHTML = `<div class="case"><div class="empty-state"><h3>${esc(t("failedH"))}</h3><p class="err">${X(cur.error)}</p></div></div>`;
    return;
  }
  const c = cur.case;
  // English: fetch translations of this case's system texts once, then render again
  if (state.lang !== "de") {
    const texts = caseTexts(c);
    if (texts.some((x) => !state.tx.has(x))) { ensureTx(texts).then(() => { if (state.current?.case === c) renderCase(opts); }); }
  }
  const sc = cur.scenario, ext = c.understanding.extraction, cl = c.understanding.classification, loc = c.match.location;
  const misses = expectationCheck(sc, c);
  const floorShow = ext.floor_raw ? `<small> → ${loc.floor != null ? esc(floorName(loc.floor)) : X(loc.floor_note || "")}</small>` : "";
  const type = { SCHADENMELDUNG: t("tDamage"), ANFRAGE_MIETE: t("tRent") }[cl.type] || t("tOther");
  const freeReason = !/^Regelmodus/.test(cl.reason || "");
  view.innerHTML = `<div class="case">
    <div class="case-head">
      <h1 class="case-title">${esc(c.input.subject || t("noSubject"))}</h1>
      ${misses ? `<span class="expect ${misses.length ? "bad" : "ok"}">${icon(misses.length ? "mismatch" : "match")}${esc(misses.length ? t("expectBad") + misses.join(", ") : t("expectOk", sc.id))}</span>` : "<span></span>"}
      <div class="case-facts"><span>${esc(t("caseNo"))} <b>${esc(c.case_id)}</b></span><span>${esc(t("received"))} <b>${time(c.received_at)}</b></span>
        <span>${esc(t("readBy"))} <b>${esc(readerLabel(c.processing))}</b></span>
        <span>${esc(t("rulesVer"))} <b>${esc(c.processing.rules_version)}</b></span></div>
    </div>
    ${verdict(c)}
    ${stepsIndex(c)}
    <div class="grid-2">
      <section class="sheet" id="s-input"><div class="sheet-head"><h3><span class="n">1</span>${esc(t("secInput"))}</h3><span class="aside">${esc(t("underlined"))}</span></div>
        <div class="email"><div class="email-head"><span class="label">${esc(t("from"))}</span><span>${esc(c.input.sender_email || t("unknown"))}</span>
          <span class="label">${esc(t("subject"))}</span><span>${esc(c.input.subject)}</span></div>
          <div class="email-body" lang="${esc(ext.language)}">${highlight(c.input.body, ext)}</div></div></section>
      <section class="sheet" id="s-read"><div class="sheet-head"><h3><span class="n">2</span>${esc(t("secRead"))}</h3><span class="aside">${esc(t("confidence"))} ${num(cl.confidence * 100, 0)} %</span></div>
        <div class="fields">
          ${field(t("fType"), esc(type))}
          ${field(t("fCat"), [cl.category, cl.trade].filter(Boolean).map((x) => X(x)).join(" · "))}
          ${field(t("fHolder"), ext.tenant_name && esc(ext.tenant_name))}${field(t("fSender"), ext.sender_name && esc(ext.sender_name))}
          ${field(t("fAddress"), esc([ext.street_raw, ext.house_no].filter(Boolean).join(" ")))}
          ${field(t("fFloor"), ext.floor_raw && esc(ext.floor_raw), floorShow)}${field(t("fSide"), ext.side_raw && esc(ext.side_raw))}${field(t("fRoom"), ext.room && X(cap(ext.room)))}
          ${field(t("fSince"), ext.since && esc(ext.since))}${field(t("fPhotos"), esc(ext.photos_mentioned ? (c.input.attachments?.length ? t("photosAtt") : t("photosNot")) : t("photosNone")))}
          ${field(t("fDesc"), ext.damage_description && esc(ext.damage_description), "", true)}
        </div>
        <p class="reader-note"><b>${esc(t("reason"))}:</b> ${X(cl.reason, { free: freeReason })}${c.understanding.fallback_used ? ` <span class="err">· ${c.understanding.warnings.map((w) => X(w)).join(" ")}</span>` : ""}</p>
      </section>
    </div>
    <section class="sheet" id="s-match"><div class="sheet-head"><h3><span class="n">3</span>${esc(t("secMatch"))}</h3><span class="aside">${esc(t("fixedRules"))}</span></div>
      <div class="match-layout"><div>${candidatesTable(c)}</div>${houseGrid(c)}</div>
      ${gatesPanel(c, sc)}
    </section>
    <div class="grid-2">
      <section class="sheet" id="s-prior"><div class="sheet-head"><h3><span class="n">4</span>${esc(t("secPrior"))}</h3></div>${priorPanel(c)}</section>
      <section class="sheet" id="s-urgency"><div class="sheet-head"><h3><span class="n">5</span>${esc(t("secUrgency"))}</h3><span class="aside">${esc(t("rulesMin"))}</span></div>${urgencyPanel(c)}</section>
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
  let stored = await api(`/api/cases/${encodeURIComponent(c.case_id)}?allow_missing=true`);
  if (!stored) stored = await api("/api/cases", c);  // first action: put this proposal into the review inbox
  const humanCount = (x) => (x.audit || []).filter((e) => e.actor !== "system").length;
  const gen = (x) => x.processing?.generation ?? 0;
  if (humanCount(stored) === 0 && gen(c) > gen(stored)) {
    stored = await api("/api/cases", c);  // this view is newer (e.g. rules changed) and nobody acted yet: refresh
  }
  // everything a person reads before approving: decision, evidence, reply text and task
  const key = (x) => JSON.stringify([x.status, x.match, x.urgency, x.prior_cases, x.reply_draft, x.internal_task,
    x.staff_options, (x.audit || []).filter((e) => e.actor !== "system").length]);
  if (key(stored) !== key(c)) {
    cur.case = stored; renderCase();
    const err = new Error(t("staleMsg"));
    err.status = 409; throw err;
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
      try { await navigator.clipboard.writeText(cur.case.reply_draft.body); toast(t("toastCopied")); }
      catch { toast(t("toastNoCopy")); }
      renderCase();
    } else if (kind === "approve_assignment") {
      const manual = btn.dataset.manual === "1";
      const contract = manual ? $("#manual-contract").value : btn.dataset.contract;
      const reason = manual ? $("#manual-reason").value.trim() : null;
      if (manual && !reason) { errEl.textContent = t("needReason"); $("#manual-reason").focus(); return; }
      await adopt(cur, c);
      cur.case = await approve(cur, { action: "approve_assignment", contract_id: contract, reason });
      toast(t("toastAssigned", contract));
      renderCase({ freshStamp: true });
    } else if (kind === "order_contractor") {
      await adopt(cur, c);
      const a = approvals(cur.case).assignment;
      cur.case = await approve(cur, { action: "order_contractor", contract_id: cur.case.match.approved_contract, reason: a?.details?.reason });
      toast(t("toastOrdered"));
      renderCase();
    } else if (kind === "object_action") {
      await adopt(cur, c);
      cur.case = await approve(cur, { action: "object_action", reason: "Notfall im Gebäude" });
      toast(t("toastObject"));
      renderCase();
    } else if (kind === "staff") {
      const option = btn.dataset.option;
      await adopt(cur, c);
      cur.case = await approve(cur, { action: "choose_staff_option", option, reason: option });
      if (option !== "call_tenant") state.sheet = "reply";
      toast(option === "call_tenant" ? t("toastCall") : t("toastOption"));
      renderCase();
    }
    loadStore();
  } catch (e) {
    if (e.status === 409 && /Regeln/.test(e.message)) {
      // rules changed since processing: re-process with today's rules; earlier approvals become invalid
      try {
        cur.case = await api("/api/process", { email: c.input, scenario_id: c.processing?.scenario_id, provider: state.provider, store: true });
        if (cur.kind === "scenario") state.results.set(cur.id, cur.case);
        renderCase();
        const el2 = $("#act-err"); if (el2) el2.textContent = t("rulesChanged");
        return;
      } catch { /* fall through to message */ }
    } else if (e.status === 409) { try { cur.case = await api(`/api/cases/${encodeURIComponent(c.case_id)}`); renderCase(); } catch { /* keep view */ } }
    const el = $("#act-err");
    if (el) {
      const msg = state.lang === "de" ? e.message : (state.tx.get(e.message) || e.message);
      el.textContent = e.status === 403 ? t("notAllowed") + msg : e.status === 409 ? msg : t("error") + msg;
    }
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
  $("#view-case").innerHTML = `<div class="case"><h1 class="case-title">${esc(t("composeH"))}</h1>
    <form class="compose" id="compose">
      <label class="label">${esc(t("senderOpt"))}<input class="input" name="sender_email" type="email" placeholder="mieter@example.org"></label>
      <label class="label">${esc(t("subject"))}<input class="input" name="subject" required placeholder="${esc(t("subjectPh"))}"></label>
      <label class="label">${esc(t("text"))}<textarea class="input" name="body" required placeholder="${esc(t("bodyPh"))}"></textarea></label>
      <div><button class="btn primary" type="submit">${esc(t("process"))}</button></div>
      <p class="hint" style="text-align:left">${esc(t("composeNote"))}</p>
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
  v.innerHTML = `<div class="page"><h2>${esc(t("rulesH"))}</h2><div class="sheet" style="height:200px"></div></div>`;
  try {
    state.rules = await api("/api/rules");
    const p = state.rules.parsed, m = p.match, w = m.weights;
    const lv = p.urgency.levels;
    await ensureTx(Object.values(lv).map((x) => x.response_target));
    v.innerHTML = `<div class="page"><h2>${esc(t("rulesH"))}</h2>
      <p class="lead">${t("rulesLead", esc(state.rules.version))}</p>
      <div class="rule-cards">
        <div class="rule-card"><h3>${esc(t("rcMatch"))}</h3><dl><dt>${esc(t("threshold"))}</dt><dd>${num(m.threshold)}</dd><dt>${esc(t("minMargin"))}</dt><dd>${num(m.min_margin)}</dd>
          <dt>${esc(t("unknownForces"))}</dt><dd>${esc(m.unknown_sender_forces_review ? t("yes") : t("no"))}</dd></dl></div>
        <div class="rule-card"><h3>${esc(t("rcWeights"))}</h3><dl>${Object.entries(w).map(([k, x]) => `<dt>${esc(SIG(k))}</dt><dd>${num(x)}</dd>`).join("")}</dl></div>
        <div class="rule-card"><h3>${esc(t("rcUrgency"))}</h3><dl>${Object.entries(lv).map(([k, x]) => `<dt>${URG(k)}</dt><dd>${X(x.response_target)}</dd>`).join("")}
          <dt>${esc(t("engFloors"))}</dt><dd>${esc(p.normalize.english_floor_counting === "ask" ? t("ask") : t("european"))}</dd></dl></div>
      </div>
      <div><button class="btn primary" id="recheck">${esc(t("recheck"))}</button></div>
      <div id="recheck-out"></div>
      <pre class="yaml">${yamlHtml(state.rules.yaml)}</pre></div>`;
    $("#recheck").addEventListener("click", recheckAll);
  } catch (e) { v.innerHTML = `<div class="page"><h2>${esc(t("rulesH"))}</h2><p class="err">${esc(e.message)}</p></div>`; }
}

async function recheckAll() {
  const out = $("#recheck-out");
  out.innerHTML = `<p class="reader-note">${esc(t("checking", state.scenarios.length))}</p>`;
  state.results.clear();
  const rows = [];
  for (const sc of state.scenarios) {
    const c = await api("/api/process", { email: sc.email, scenario_id: sc.id, provider: state.provider === "groq" ? "offline" : state.provider });
    state.results.set(sc.id, c);
    rows.push({ sc, c, misses: expectationCheck(sc, c) });
  }
  const bad = rows.filter((r) => r.misses.length).length;
  out.innerHTML = `<table class="log"><thead><tr><th>${esc(t("scenario"))}</th><th>${esc(t("mStatus"))}</th><th>${esc(t("contract"))}</th><th>${esc(t("secUrgency"))}</th><th>${esc(t("gatesAria"))}</th><th>${esc(t("expectation"))}</th></tr></thead><tbody>
    ${rows.map(({ sc, c, misses }) => `<tr><td><b>${esc(sc.id)}</b> ${esc(sc.title)}</td><td><span class="chip s-${c.status}">${esc(STATUS()[c.status].label)}</span></td>
      <td>${esc(c.match.selected_contract || "–")}</td><td>${URG(c.urgency.level)}</td><td>${esc((c.match.failed_gates || []).join(", ") || "–")}</td>
      <td>${misses.length ? `<span class="err">${esc(t("deviates") + misses.join(", "))}</span>` : esc(t("fulfilled"))}</td></tr>`).join("")}</tbody></table>
    <p class="reader-note">${esc(bad ? t("nBad", bad) : t("allGood"))}</p>`;
  renderInbox();
}

async function renderAudit() {
  const v = $("#view-audit");
  try {
    const lines = await api("/api/audit");
    await ensureTx(lines.map((l) => l.details?.reason).filter(Boolean));
    v.innerHTML = `<div class="page"><h2>${esc(t("auditH"))}</h2><p class="lead">${esc(t("auditLead"))}</p>
      ${lines.length ? `<table class="log"><thead><tr><th>${esc(t("time"))}</th><th>${esc(t("who"))}</th><th>${esc(t("action"))}</th><th>${esc(t("caseCol"))}</th><th>${esc(t("contract"))}</th><th>${esc(t("reasonCol"))}</th></tr></thead><tbody>
      ${[...lines].reverse().map((l) => `<tr><td>${time(l.ts)}</td><td>${esc(l.actor)}</td><td>${esc(actionName(l.event))}</td><td>${esc(l.details?.case_id)}</td><td>${esc(l.details?.contract_id || l.details?.object_id || "–")}</td><td>${l.details?.reason ? X(l.details.reason) : "–"}</td></tr>`).join("")}</tbody></table>`
      : `<div class="empty-state"><h3>${esc(t("auditEmptyH"))}</h3><p>${esc(t("auditEmptyP"))}</p></div>`}</div>`;
  } catch (e) { v.innerHTML = `<div class="page"><h2>${esc(t("auditH"))}</h2><p class="err">${esc(e.message)}</p></div>`; }
}

function renderFlow() {
  $("#view-flow").innerHTML = `<div class="page"><h2>${esc(t("flowH"))}</h2>
    <p class="lead">${esc(t("flowLead"))}</p>
    <figure class="flow-figure"><img src="/static/n8n-workflow.png" alt="${esc(t("flowAlt"))}" onerror="this.closest('figure').hidden=true"></figure>
    <ol class="flow-steps">${ui().flow.map(([h, p]) => `<li><b>${esc(h)}</b>${esc(p)}</li>`).join("")}</ol></div>`;
}

let currentView = "case";
function switchView(name) {
  currentView = name;
  $$(".view").forEach((v) => (v.hidden = v.dataset.view !== name));
  $$(".view-tab").forEach((tab) => tab.setAttribute("aria-current", tab.dataset.view === name ? "page" : "false"));
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
  $("#lang").addEventListener("change", (e) => {
    state.lang = e.target.value; localSet("lang", state.lang);
    applyStatic(); renderInbox(); switchView(currentView); renderCase();
  });
  $$(".view-tab").forEach((tab) => tab.addEventListener("click", () => switchView(tab.dataset.view)));
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
  applyStatic();
  renderCase();
  try {
    state.rules = await api("/api/rules");
    await loadScenarios();
    const first = [...state.scenarios].find((s) => s.id === "S1") || state.scenarios[0];
    if (first) openScenario(first.id);
    loadStore();
  } catch (e) {
    $("#view-case").innerHTML = `<div class="case"><div class="empty-state"><h3>${esc(t("offlineH"))}</h3><p class="err">${esc(e.message)}</p><p>${esc(t("start"))}: <code>uv run intake-ui</code></p></div></div>`;
  }
})();
