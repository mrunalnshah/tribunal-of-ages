// The library: every law the court can cite, shelved with the site in laws.json, and every
// verdict it has given, from the Hall of Fame and the public record. Only the record and the
// "cited in" counts need the API, so the laws open even while it sleeps.
const library = (() => {
  const $ = (id) => document.getElementById(id);
  const PAGE = 24;
  let laws = null;
  let counts = {};
  let shown = PAGE;
  let theme = "";
  let older = null; // where the next page of the public record starts
  let famous = null;

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag); // text only, never HTML: visitors wrote some of it
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function tab(section) {
    const isLaws = section === "laws";
    $("tab-laws").setAttribute("aria-selected", String(isLaws));
    $("tab-verdicts").setAttribute("aria-selected", String(!isLaws));
    $("laws-panel").hidden = !isLaws;
    $("verdicts-panel").hidden = isLaws;
  }

  async function open(section = "laws", lawId = "") {
    tab(section);
    analytics.track("library_opened", { section });
    if (section === "verdicts") return showVerdicts("recent");
    await loadLaws();
    if (lawId) focusLaw(lawId);
    else renderLaws();
    paintPodium();
  }

  // The laws verdicts cite most, the winner in the middle; each opens the law itself.
  async function paintPodium() {
    await system.load();
    const top = system.laws().map((cited) => ({ ...cited, law: (laws || []).find((law) => law.law_id === cited.law_id) }))
      .filter((cited) => cited.law).slice(0, 3);
    $("podium").hidden = top.length === 0;
    const order = top.length === 3 ? [top[1], top[0], top[2]] : top;
    $("podium-steps").replaceChildren(...order.map((cited) => {
      const first = cited === top[0];
      const step = el("button", first ? "step first" : "step");
      step.type = "button";
      step.title = cited.law.text;
      step.append(
        el("span", "medal", String(top.indexOf(cited) + 1)),
        el("span", "where", cited.law.jurisdiction_name),
        el("strong", "", cited.law.citation),
        el("span", "times", `cited ${cited.times} ${cited.times === 1 ? "time" : "times"}`),
      );
      step.addEventListener("click", () => { location.hash = `#law/${encodeURIComponent(cited.law.law_id)}`; });
      return step;
    }));
  }

  // ---- Laws
  async function loadLaws() {
    if (laws) return;
    $("laws-status").textContent = "Taking the laws down from the shelves…";
    try {
      const response = await fetch("laws.json");
      laws = response.ok ? (await response.json()).laws : [];
    } catch {
      laws = [];
    }
    if (!laws.length) {
      $("laws-status").textContent = "The shelves are empty right now. Try again later.";
      return;
    }
    buildFilters();
    request("GET", "/api/v1/records/counts").then((found) => {
      counts = found;
      renderLaws();
    }).catch(() => {}); // without counts, the laws still show
  }

  function themeName(id) {
    const known = typeof catalog === "object" && catalog?.themes.find((item) => item.id === id);
    return known ? known.name : id.charAt(0).toUpperCase() + id.slice(1);
  }

  function buildFilters() {
    const chip = (id, label) => {
      const button = el("button", "chip", label);
      button.type = "button";
      button.setAttribute("aria-pressed", String(id === theme));
      button.addEventListener("click", () => {
        theme = id;
        shown = PAGE;
        for (const other of $("law-themes").children) other.setAttribute("aria-pressed", String(other === button));
        renderLaws();
      });
      return button;
    };
    const themes = [...new Set(laws.map((law) => law.theme))];
    $("law-themes").replaceChildren(chip("", "All"), ...themes.map((id) => chip(id, themeName(id))));
    const realms = [...new Map(laws.map((law) => [law.jurisdiction, law.jurisdiction_name]))];
    realms.sort((a, b) => a[1].localeCompare(b[1]));
    $("law-realm").replaceChildren(new Option("Every realm", ""), ...realms.map(([id, name]) => new Option(name, id)));
  }

  function matches(law, words) {
    const text = [law.citation, law.text, law.jurisdiction_name, law.source, law.punishment, ...law.categories]
      .join(" ").toLowerCase();
    return words.every((word) => text.includes(word));
  }

  function renderLaws() {
    if (!laws || !laws.length) return;
    const words = $("law-search").value.toLowerCase().split(/\s+/).filter(Boolean);
    const realm = $("law-realm").value;
    const found = laws.filter((law) => (!theme || law.theme === theme)
      && (!realm || law.jurisdiction === realm) && matches(law, words));
    $("laws-status").textContent = found.length
      ? `${found.length} ${found.length === 1 ? "law" : "laws"}`
      : "No law matches that. Try another word.";
    $("law-list").replaceChildren(...found.slice(0, shown).map(lawCard));
    $("laws-more").hidden = found.length <= shown;
  }

  function lawCard(law) {
    const card = el("article", "entry");
    card.id = `law-${law.law_id}`;
    const tier = law.tier ? ` · outrage ${law.tier} of 5` : "";
    card.append(
      el("p", "where", `${law.jurisdiction_name} · ${law.citation}`),
      el("blockquote", "", `“${law.text}”`),
      el("p", "meta", `${law.verbatim ? "Quoted from" : "Paraphrased from"} ${law.source}${tier}`),
    );
    const actions = el("div", "actions");
    const cited = counts[law.law_id] || 0;
    if (cited) {
      const button = el("button", "quiet", `${cited} ${cited === 1 ? "verdict cites" : "verdicts cite"} it`);
      button.type = "button";
      button.addEventListener("click", () => showCases(law, button));
      actions.append(button);
    }
    const link = el("a", "", "Link to this law");
    link.href = `#law/${encodeURIComponent(law.law_id)}`;
    actions.append(link);
    card.append(actions);
    return card;
  }

  async function showCases(law, button) {
    button.disabled = true;
    try {
      const records = await request("GET", `/api/v1/records?law=${encodeURIComponent(law.law_id)}&limit=5`);
      const list = el("ul", "cases");
      list.append(...records.map((record) => {
        const item = el("li");
        const link = el("a", "", `“${record.crime}”`);
        link.href = `#case/${record.id}`;
        item.append(link, document.createTextNode(` ${record.ruling.verdict.sentence}`));
        return item;
      }));
      button.replaceWith(list);
      analytics.track("law_opened", { law_id: law.law_id });
    } catch (error) {
      button.disabled = false;
      button.textContent = error.message;
    }
  }

  function focusLaw(lawId) {
    theme = "";
    $("law-search").value = "";
    $("law-realm").value = "";
    const index = laws.findIndex((law) => law.law_id === lawId);
    shown = Math.max(PAGE, index + 1);
    renderLaws();
    const card = document.getElementById(`law-${lawId}`);
    if (!card) return;
    card.classList.add("highlight");
    card.scrollIntoView({ block: "center" });
  }

  // ---- Verdicts
  async function showVerdicts(kind) {
    $("show-recent").setAttribute("aria-pressed", String(kind === "recent"));
    $("show-famous").setAttribute("aria-pressed", String(kind === "famous"));
    $("verdict-list").replaceChildren();
    $("verdicts-more").hidden = true;
    older = null;
    if (kind === "famous") return showFamous();
    return showRecent();
  }

  async function showRecent() {
    $("verdicts-status").textContent = "Fetching the public record…";
    try {
      const before = older ? `&before=${encodeURIComponent(older)}` : "";
      const records = await request("GET", `/api/v1/records?limit=12${before}`);
      $("verdict-list").append(...records.map((record) => caseCard(record)));
      older = records.length ? records[records.length - 1].created_at : older;
      $("verdicts-more").hidden = records.length < 12;
      const total = $("verdict-list").children.length;
      $("verdicts-status").textContent = total
        ? "The newest cases first, word for word as they were filed."
        : "No cases in the public record yet. File the first one in the court.";
    } catch (error) {
      $("verdicts-status").textContent = `${error.message} The famous cases are still here.`;
    }
  }

  async function showFamous() {
    if (!famous) {
      try {
        const response = await fetch("hall-of-fame.json");
        famous = response.ok ? (await response.json()).cases : [];
      } catch {
        famous = [];
      }
    }
    $("verdicts-status").textContent = famous.length ? "The court’s most celebrated cases." : "The archive is empty for now.";
    $("verdict-list").replaceChildren(...famous.map((item) => caseCard({ ...item.case, ruling: item.ruling }, item)));
  }

  async function openCase(id) {
    tab("verdicts");
    $("show-recent").setAttribute("aria-pressed", "true");
    $("show-famous").setAttribute("aria-pressed", "false");
    $("verdicts-more").hidden = true;
    $("verdicts-status").textContent = "Fetching the case…";
    try {
      const record = await request("GET", `/api/v1/records/${encodeURIComponent(id)}`);
      const card = caseCard(record);
      card.classList.add("highlight");
      $("verdict-list").replaceChildren(card);
      const all = el("button", "more", "See every recent verdict");
      all.type = "button";
      all.addEventListener("click", () => { location.hash = "#library/verdicts"; });
      $("verdict-list").append(all);
      $("verdicts-status").textContent = "";
    } catch (error) {
      $("verdicts-status").textContent = error.message;
      $("verdict-list").replaceChildren();
    }
  }

  function when(iso) {
    const seconds = (new Date(iso) - Date.now()) / 1000;
    const format = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    for (const [unit, size] of [["year", 31536000], ["month", 2592000], ["day", 86400], ["hour", 3600], ["minute", 60]]) {
      if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit);
    }
    return "just now";
  }

  // One case: from the public record when it has an id, or from the Hall of Fame.
  function caseCard(record, famousItem = null) {
    const { verdict, law } = record.ruling;
    const card = el("article", "entry");
    if (record.id) card.id = `case-${record.id}`;
    const filed = (record.ruling.kind === "contempt" ? "Contempt of court · " : "")
      + (record.created_at ? `${when(record.created_at)} · ` : "From the archives · ");
    card.append(
      el("p", "where", `${filed}outrage ${record.outrage} of 5`),
      el("blockquote", "", `“${record.crime}”`),
      el("h3", "", verdict.case_title),
      el("p", "", verdict.sentence),
    );
    const meta = el("p", "meta", law.verbatim ? "Under " : "Paraphrasing ");
    const lawLink = el("a", "", `${law.jurisdiction_name}, ${law.citation}`);
    lawLink.href = `#law/${encodeURIComponent(law.law_id)}`;
    meta.append(lawLink);
    const actions = el("div", "actions");
    const open = el("button", "quiet", "Open it in the court");
    open.type = "button";
    open.addEventListener("click", () => court.show(record.ruling, famousItem ? "famous" : "record", record));
    actions.append(open);
    if (record.id) {
      const link = el("a", "", "Link");
      link.href = `#case/${record.id}`;
      const report = el("button", "quiet", "Report");
      report.type = "button";
      report.addEventListener("click", () => reportCase(record, report));
      actions.append(link, report);
    }
    card.append(meta, actions);
    return card;
  }

  async function reportCase(record, button) {
    if (!confirm("Report this case? Cases with enough reports are hidden until they’re reviewed.")) return;
    try {
      await request("POST", `/api/v1/records/${encodeURIComponent(record.id)}/report`);
      button.replaceWith(el("span", "hint", "Reported. Thank you."));
      analytics.track("case_reported");
    } catch (error) {
      button.textContent = error.message;
    }
  }

  let typing;
  $("law-search").addEventListener("input", () => {
    clearTimeout(typing);
    typing = setTimeout(() => {
      shown = PAGE;
      renderLaws();
    }, 150);
  });
  $("law-realm").addEventListener("change", () => {
    shown = PAGE;
    renderLaws();
  });
  $("laws-more").addEventListener("click", () => {
    shown += PAGE;
    renderLaws();
  });
  $("verdicts-more").addEventListener("click", showRecent);
  $("tab-laws").addEventListener("click", () => { location.hash = "#library"; });
  $("tab-verdicts").addEventListener("click", () => { location.hash = "#library/verdicts"; });
  $("show-recent").addEventListener("click", () => showVerdicts("recent"));
  $("show-famous").addEventListener("click", () => showVerdicts("famous"));

  return { open, openCase };
})();