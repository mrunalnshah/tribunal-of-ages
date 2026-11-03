// The court: the form, the verdict, and what happened to the case in the public record. It
// also routes between the two rooms: #court, #library, #library/verdicts, #law/<id>,
// #case/<id>, and #remove/<id>/<key> for the private removal link.
const LABELS = [["🙄", "Miffed"], ["😤", "Peeved"], ["😡", "Seething"], ["🔥", "Vengeful"], ["☠️", "Blood feud"]];
const $ = (id) => document.getElementById(id);
let catalog = null;
let traceId = "";
let archive = null; // the Hall of Fame, fetched the first time it's needed
let lastFamous = -1;
let live = null; // the visitor's own verdict, while it's on screen: their private names update it

function make(tag, text = "", className = "") {
  const node = document.createElement(tag); // text only, never HTML: model output is untrusted
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

// ---- The form
$("outrage").append(...LABELS.flatMap(([face, word], i) => {
  const input = Object.assign(document.createElement("input"), {
    type: "radio", name: "outrage", id: `outrage-${i + 1}`, value: String(i + 1), checked: i === 2,
  });
  const label = make("label");
  label.htmlFor = input.id;
  label.append(make("span", face, "face"), document.createTextNode(word));
  return [input, label];
}));
$("crime").addEventListener("input", () => {
  const length = $("crime").value.length;
  const over = length > 600; // the court reads 600 characters; a longer grievance is kept, unjudged
  $("crime-count").textContent = over
    ? `${length} characters: the court reads 600. Trim it to have it judged; filed as it is, it’s kept but not judged.`
    : `${length} of 600 characters.`;
  $("crime-count").classList.toggle("over", over);
});
for (const id of ["accused", "plaintiff"]) {
  $(id).addEventListener("input", () => {
    if (live && !$("verdict").hidden) fillText(live, "live");
  });
}

// Themes and jurisdictions come from the API, so new ones appear without editing this file.
async function loadCatalog() {
  $("themes-status").textContent = "Opening the court’s library…";
  try {
    catalog = await request("GET", "/api/v1/catalog");
    renderThemes();
    $("themes-status").textContent = "";
  } catch (error) {
    analytics.track("catalog_unavailable", { status: error.status });
    const retry = make("button", "Try again", "quiet");
    retry.type = "button";
    retry.addEventListener("click", loadCatalog);
    $("themes-status").replaceChildren(document.createTextNode(`${error.message} `), retry);
  }
}

function renderThemes() {
  $("themes").replaceChildren(...catalog.themes.map((theme) => {
    const label = make("label");
    const box = Object.assign(document.createElement("input"), { type: "checkbox", value: theme.id, checked: theme.default });
    box.addEventListener("change", renderJurisdictions);
    label.title = theme.description;
    label.append(box, document.createTextNode(theme.name));
    return label;
  }));
  renderJurisdictions();
}

function chosenThemes() {
  return [...$("themes").querySelectorAll("input:checked")].map((box) => box.value);
}

function renderJurisdictions() {
  const chosen = new Set(chosenThemes());
  const previous = $("jurisdiction").value;
  const realms = catalog.themes.filter((theme) => chosen.has(theme.id)).flatMap((theme) => theme.jurisdictions);
  $("jurisdiction").replaceChildren(new Option("Any realm", "any"), ...realms.map((j) => new Option(`${j.name} (${j.laws})`, j.id)));
  if (realms.some((j) => j.id === previous)) $("jurisdiction").value = previous;
}

$("case-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!catalog) return setStatus("The court’s library is still loading. Try again in a moment.");
  const themes = chosenThemes();
  if (!themes.length) return setStatus("Pick at least one kind of law.");
  const crime = $("crime").value.trim();
  if (crime.length < 10) {
    $("crime").focus();
    return setStatus("Tell the court a little more: at least 10 characters.");
  }
  const named = [...decree.people(), decree.plaintiff()].find((name) => mentions(crime, name));
  if (named) {
    $("crime").focus();
    return setStatus(`Your grievance mentions “${named}”. Take the name out: the court says the Plaintiff and the Accused, and the names you typed below stay on this device.`);
  }
  if (!$("consent").checked) {
    $("consent").focus();
    return setStatus("Tick the box first, so you know what goes public: your grievance and its verdict.");
  }
  const outrage = Number(document.querySelector('input[name="outrage"]:checked').value);
  // The private part of the form (names, photo) is never added here: it never leaves the device.
  const body = { crime, outrage, themes, jurisdiction: $("jurisdiction").value, consent: true };
  const file = $("file");
  file.disabled = true; // one case at a time: a double click would cost two verdicts
  file.classList.add("working");
  $("verdict").hidden = true;
  setStatus("The court is consulting the clay tablets…");
  // Only the visitor's choices are counted, never what they wrote.
  analytics.track("case_submitted", { outrage, themes, jurisdiction: body.jurisdiction, length: crime.length });
  const slow = setTimeout(() => setStatus("Waking the court. The first case after a nap can take a minute…"), 6000);
  try {
    const answer = await request("POST", "/api/v1/verdicts", body);
    render(answer);
    showRecordStatus(answer);
    system.load(true); // the chip and tally count this case
    $("consent").checked = false; // every case asks again
    const notes = answer.kind === "declined" ? [answer.message] : [];
    if (answer.kind === "verdict") analytics.track("verdict_shown", lawDetails(answer.law));
    else if (answer.kind === "contempt") {
      analytics.track("contempt_found", lawDetails(answer.law));
      notes.push("That isn’t a grievance, so the court holds you in contempt.");
    } else analytics.track("case_declined");
    if (typeof answer.cases_left === "number") notes.push(casesLeft(answer.cases_left));
    if (notes.length) setStatus(notes.join(" "));
  } catch (error) {
    analytics.track("court_unavailable", { status: error.status });
    if ([0, 502, 503].includes(error.status)) system.load(true); // the chip says what's wrong
    // 0: unreachable or too slow; 429: in recess or too many cases; 503: providers down.
    const closed = [0, 429, 503].includes(error.status);
    if (closed && (await showFamousCase(error.status === 429 ? "recess" : "down"))) {
      setStatus(`${error.message} Meanwhile, from the court’s archives:`);
    } else {
      setStatus(error.message);
    }
  } finally {
    clearTimeout(slow);
    file.disabled = false;
    file.classList.remove("working");
  }
});

// ---- The verdict
// `from` says where a ruling came from: "live", "famous" (the archive) or "record".
function render(ruling, from = "live", source = null) {
  if (ruling.kind === "declined") {
    decree.hide();
    setStatus(ruling.message);
    return;
  }
  const { verdict, law } = ruling;
  $("v-archive").hidden = from === "live";
  if (from === "famous") $("v-archive").textContent = `From the archives: “${source.crime}” (outrage ${source.outrage} of 5).`;
  if (from === "record") $("v-archive").textContent = `From the public record: “${source.crime}” (outrage ${source.outrage} of 5).`;
  $("archive-next").hidden = from !== "famous";
  $("v-record").hidden = true;
  live = from === "live" ? ruling : null;
  $("v-stamp").textContent = ruling.kind === "contempt" ? "Contempt" : "Guilty";
  fillText(ruling, from);
  $("v-law-text").textContent = law.text;
  const meta = $("v-law-meta");
  meta.replaceChildren(document.createTextNode(`${law.verbatim ? "Quoted from" : "Paraphrased from"} ${law.source}, ${law.citation}. ${law.jurisdiction_name}. `));
  if (law.source_url) {
    const link = make("a", "Read the source");
    link.href = law.source_url;
    link.rel = "noopener";
    meta.append(link);
  }
  traceId = (ruling.meta && ruling.meta.trace_id) || "";
  $("feedback").hidden = !traceId;
  setStatus("");
  $("verdict").hidden = false;
  decree.offer(ruling); // the verdict, ready to export as an image
  $("verdict").focus({ preventScroll: true });
  $("verdict").scrollIntoView({ behavior: "smooth", block: "start" });
}

// On the visitor's own screen, the verdict uses the names they kept on this device. Cases
// from the archive or the record stay as they are.
function fillText(ruling, from) {
  const names = decree.people();
  const filer = decree.plaintiff();
  const say = (text) => (from === "live" ? decree.personalize(text, names, filer) : text);
  const { verdict } = ruling;
  $("v-title").textContent = say(verdict.case_title);
  $("v-charge").textContent = say(verdict.charge);
  $("v-sentence").textContent = say(verdict.sentence);
  $("v-remarks").textContent = say(verdict.remarks);
  $("v-note").textContent = say(verdict.historical_note);
  const role = ruling.kind === "contempt" ? "the Petitioner" : "the Accused";
  $("v-private").textContent = `On your screen, this verdict uses the names you kept on this device. The public record says “${role}”.`;
  $("v-private").hidden = !(from === "live" && (names.length || filer));
}

// Whether `text` contains `name` as a whole word, in any script and any case.
function mentions(text, name) {
  if (name.length < 2) return false;
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^\\p{L}\\p{N}])${escaped}($|[^\\p{L}\\p{N}])`, "iu").test(text);
}

function showRecordStatus(answer) {
  const box = $("v-record");
  box.replaceChildren();
  box.hidden = !(answer.record || answer.record_note);
  if (answer.record_note) return box.append(make("p", answer.record_note));
  if (!answer.record) return;
  const { id, removal_key: key } = answer.record;
  const page = `${location.origin}${location.pathname}`;
  box.append(make("p", "Your grievance and its verdict are in the public record now, without the names and photo you kept on this device. Keep the removal link if you might want it gone later."));
  const actions = make("div", "", "actions");
  actions.append(
    copyButton("Copy its link", `${page}#case/${id}`),
    copyButton("Copy the removal link", `${page}#remove/${id}/${key}`),
    removeButton(id, key),
  );
  box.append(actions);
}

function copyButton(label, text) {
  const button = make("button", label, "quiet");
  button.type = "button";
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
    } catch {
      prompt("Copy this:", text);
    }
  });
  return button;
}

function removeButton(id, key) {
  const button = make("button", "Remove it", "quiet");
  button.type = "button";
  button.addEventListener("click", () => removeCase(id, key, button.parentElement.parentElement));
  return button;
}

async function removeCase(id, key, box = null) {
  if (!confirm("Remove this case from the public record? This can’t be undone.")) return;
  try {
    await request("POST", `/api/v1/records/${encodeURIComponent(id)}/remove`, { key });
    analytics.track("case_removed");
    if (box) box.replaceChildren(make("p", "Removed from the public record."));
    else setStatus("Removed from the public record.");
  } catch (error) {
    setStatus(error.message);
  }
}

// The Hall of Fame: real past verdicts, served with the site, for when the court can’t sit.
async function loadArchive() {
  if (archive) return archive;
  try {
    const response = await fetch("hall-of-fame.json");
    archive = response.ok ? (await response.json()).cases : [];
  } catch {
    return []; // offline: try again next time
  }
  return archive;
}

async function showFamousCase(reason) {
  const cases = await loadArchive();
  if (!cases.length) return false;
  let pick = Math.floor(Math.random() * cases.length);
  if (cases.length > 1 && pick === lastFamous) pick = (pick + 1) % cases.length;
  lastFamous = pick;
  const famous = cases[pick];
  render(famous.ruling, "famous", famous.case);
  analytics.track("famous_case_shown", { reason, law_id: famous.ruling.law.law_id });
  return true;
}

async function showTeaser() {
  const cases = await loadArchive();
  if (!cases.length) return;
  const { case: filed, ruling } = cases[Math.floor(Math.random() * cases.length)];
  $("teaser").textContent = `Lately in this court: “${filed.crime}” ${ruling.verdict.sentence}`;
  $("teaser").hidden = false;
}

function casesLeft(count) {
  if (count === 0) return "That was your last case today. The court will hear you again tomorrow.";
  return `You can file ${count} more ${count === 1 ? "case" : "cases"} today.`;
}

function lawDetails(law) {
  const { law_id, theme, jurisdiction, tier, verbatim } = law;
  return { law_id, theme, jurisdiction, tier, verbatim };
}

function setStatus(text) {
  $("status").textContent = text;
}

$("teaser").addEventListener("click", () => showFamousCase("teaser"));
$("archive-button").addEventListener("click", async () => {
  if (!(await showFamousCase("button"))) setStatus("The archives are empty for now.");
});
$("archive-next").addEventListener("click", () => showFamousCase("another"));
$("feedback").addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button || !traceId) return;
  try {
    const value = Number(button.dataset.value);
    await request("POST", "/api/v1/feedback", { trace_id: traceId, value });
    analytics.track("feedback_sent", { value });
    setStatus("Thank you. The court has noted your opinion.");
  } catch (error) {
    setStatus(error.message);
  }
});

// ---- Talking to the API
async function request(method, path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);
  try {
    const response = await fetch(window.TRIBUNAL_API + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw failure(explain(response.status, data), response.status);
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw failure("The court took too long to answer. Try again.", 0);
    if (error instanceof TypeError) throw failure("Couldn’t reach the court. Check your connection and try again.", 0);
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

// An Error that also carries the HTTP status: 0 when the court couldn’t be reached at all.
function failure(message, status) {
  return Object.assign(new Error(message), { status });
}

function explain(status, data) {
  if (status === 422 && typeof data.detail === "string") return data.detail;
  if (status === 422) return "Describe the crime in 10 to 600 characters.";
  if (typeof data.detail === "string") return data.detail;
  return `The court hit an error (${status}). Try again.`;
}

// ---- The rooms
const court = {
  show(ruling, from, source) {
    location.hash = "#court";
    render(ruling, from, source);
  },
};

function route() {
  const [room = "court", first = "", second = ""] = location.hash.slice(1).split("/");
  if (room === "remove" && first && second) {
    history.replaceState(null, "", "#court");
    removeCase(decodeURIComponent(first), decodeURIComponent(second));
    return route();
  }
  const shown = ["library", "law", "case"].includes(room) ? "library" : room === "system" ? "system" : "court";
  const before = ["court", "library", "system"].find((name) => !$(name).hidden);
  for (const name of ["court", "library", "system"]) $(name).hidden = name !== shown;
  for (const link of document.querySelectorAll(".rooms a, #chip")) {
    const target = link.dataset.room || "system";
    if (target === shown) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  if (shown !== before) window.scrollTo(0, 0);
  if (room === "library") library.open(first === "verdicts" ? "verdicts" : "laws");
  if (room === "law") library.open("laws", decodeURIComponent(first));
  if (room === "case") library.openCase(decodeURIComponent(first));
  if (room === "system") system.open();
}

window.addEventListener("hashchange", route);
route();
loadCatalog();
showTeaser();
system.load();