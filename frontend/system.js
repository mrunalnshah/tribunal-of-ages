// The court's ledger: today's count in the chip on every page, a tally under the headline,
// and the System page. One request feeds all three, at most once a minute.
const system = (() => {
  const $ = (id) => document.getElementById(id);
  const SVG = "http://www.w3.org/2000/svg";
  const whole = new Intl.NumberFormat();
  const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
  let board = null; // the last ledger the API sent, or null
  let fetched = 0;

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag); // text only, never HTML
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function svg(tag, attributes, text = "") {
    const node = document.createElementNS(SVG, tag);
    for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
    if (text) node.textContent = text;
    return node;
  }

  // Is the court's server answering? /healthz says so without touching the database or an AI.
  // checking: the first look (a sleeping server takes about a minute to wake); open; full: the
  // day's cases are all heard; recess: the server isn't answering. The chip shows it on every page.
  let state = "checking";
  let timer = 0;
  let pending = null;

  function check() {
    pending ||= look().finally(() => { pending = null; });
    return pending;
  }

  async function look() {
    clearTimeout(timer);
    let answering = true;
    try {
      await request("GET", "/healthz");
    } catch {
      answering = false;
    }
    board = null;
    if (answering) {
      try {
        board = await request("GET", "/api/v1/stats");
      } catch {
        // open, but keeping no ledger right now: the chip still says the court is open
      }
    }
    fetched = Date.now();
    state = !answering ? "recess" : board && left() === 0 ? "full" : "open";
    paintChip();
    if (!$("system").hidden) paintPage();
    if (!document.hidden) timer = setTimeout(check, state === "recess" ? 20000 : 60000);
    return board;
  }

  async function load(fresh = false) {
    if (!fresh && state !== "checking" && Date.now() - fetched < 60000) return board;
    return check();
  }

  function left() {
    return Math.max(0, board.per_day - board.ledger.today);
  }

  function describe() {
    if (state === "checking") return "Opening the court…";
    if (state === "recess") return "In recess · reconnecting";
    if (state === "full") return "In recess until tomorrow";
    return board ? `Open · ${whole.format(board.ledger.today)} / ${whole.format(board.per_day)} today` : "Open";
  }

  function paintChip() {
    const text = describe();
    $("chip").dataset.state = state;
    $("chip-text").textContent = text;
    $("chip").setAttribute("aria-label", `System: ${text}`);
    const tally = $("tally");
    tally.hidden = state === "checking" || (state !== "recess" && !board);
    tally.textContent = state === "recess"
      ? "The court is in recess right now. The famous cases are still open to read."
      : board ? `${whole.format(board.ledger.all_time)} cases judged · ${whole.format(left())} left today` : "";
  }

  async function open() {
    analytics.track("system_opened");
    paintPage();
    loadUptime(); // from GitHub, not the API: it shows even while the server is down
    await load(true);
  }

  let uptime = null;
  let uptimeAt = 0;

  async function loadUptime() {
    if (!window.TRIBUNAL_UPTIME) return;
    if (!uptime || Date.now() - uptimeAt > 300000) {
      try {
        const response = await fetch(window.TRIBUNAL_UPTIME, { cache: "no-cache" });
        if (response.ok) {
          uptime = await response.json();
          uptimeAt = Date.now();
        }
      } catch {
        // keep the last history, or show none
      }
    }
    paintUptime();
  }

  function paintUptime() {
    $("uptime").hidden = !(uptime && uptime.days && uptime.days.length);
    if ($("uptime").hidden) return;
    const byDay = new Map(uptime.days.map((day) => [day.day, day]));
    const now = new Date();
    const bars = [];
    for (let back = 89; back >= 0; back -= 1) {
      const key = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - back)).toISOString().slice(0, 10);
      const day = byDay.get(key);
      const share = day ? day.up / day.checks : 0;
      const bar = el("span", !day ? "none" : share === 1 ? "up" : share >= 0.95 ? "partial" : "down");
      bar.title = day ? `${key}: ${day.up} of ${day.checks} checks passed` : `${key}: no checks`;
      bars.push(bar);
    }
    const { uptime_90d: quarter, uptime_30d: month } = uptime.summary;
    $("u-bars").replaceChildren(...bars);
    $("u-bars").setAttribute("aria-label", `Up ${quarter}% of the time over 90 days`);
    $("u-90").textContent = `${quarter}%`;
    $("u-30").textContent = `up over 90 days · ${month}% over the last 30`;
    const last = uptime.incidents && uptime.incidents[0];
    $("u-note").textContent = `Checked every 30 minutes from GitHub. ${last ? `Last incident: ${last.at.slice(0, 10)}.` : "No incidents yet."}`;
  }

  function paintPage() {
    const line = {
      checking: "Opening the court…",
      open: "The court is open",
      full: "In recess until tomorrow: today’s cases are all heard",
      recess: "In recess: the court’s server isn’t answering",
    }[state];
    $("s-state").dataset.state = state;
    $("s-state-text").textContent = line;
    const status = $("s-status");
    if (state === "checking" || state === "recess" || !board) {
      $("ledger").hidden = true;
      const again = el("button", "quiet", "Check now");
      again.type = "button";
      again.addEventListener("click", () => load(true));
      const why = {
        checking: "Opening the ledger. A court that has been asleep can take a minute to wake. ",
        recess: "It may be waking up or briefly down; this page checks again by itself. ",
      }[state] || "The court is open, but its ledger isn’t available right now. ";
      status.replaceChildren(document.createTextNode(why), again);
      return;
    }
    status.replaceChildren();
    $("ledger").hidden = false;
    $("s-all").textContent = whole.format(board.ledger.all_time);
    paintRing();
    paintKinds();
    paintDays();
    paintTokens();
    paintSaved();
    paintProviders();
  }

  function paintTokens() {
    const { tokens_today: today, tokens_all_time: total } = board.ledger;
    const budget = Math.max(1, board.tokens_per_day);
    const meter = el("div", "meter");
    const used = el("span");
    used.style.width = `${Math.min(100, (today / budget) * 100)}%`;
    meter.append(used);
    meter.setAttribute("role", "img");
    meter.setAttribute("aria-label", `${today} of ${budget} tokens used today`);
    const big = el("p", "big", `${compact.format(today)} `);
    big.append(el("span", "hint", `of ${compact.format(budget)} used today`));
    $("s-tokens").replaceChildren(big, meter, el("p", "hint", `${compact.format(total)} since the court opened`));
  }

  function paintRing() {
    const radius = 52;
    const length = 2 * Math.PI * radius;
    const used = Math.min(1, board.ledger.today / Math.max(1, board.per_day));
    const fill = svg("circle", {
      class: "fill", cx: 60, cy: 60, r: radius, transform: "rotate(-90 60 60)",
      "stroke-dasharray": length, "stroke-dashoffset": length,
    });
    const label = `${board.ledger.today} of ${board.per_day} cases judged today`;
    const picture = svg("svg", { viewBox: "0 0 120 120", role: "img", "aria-label": label });
    picture.append(
      svg("circle", { class: "track", cx: 60, cy: 60, r: radius }),
      fill,
      svg("text", { class: "big", x: 60, y: 63, "text-anchor": "middle" }, whole.format(left())),
      svg("text", { class: "small", x: 60, y: 82, "text-anchor": "middle" }, "left today"),
    );
    $("s-ring").replaceChildren(picture);
    requestAnimationFrame(() => fill.setAttribute("stroke-dashoffset", length * (1 - used)));
  }

  function paintKinds() {
    const { verdict, contempt, declined } = board.ledger.kinds;
    const total = Math.max(1, verdict + contempt + declined);
    const parts = [["a", "Verdicts", verdict], ["b", "Contempt of court", contempt], ["c", "Declined", declined]];
    const bar = el("div", "bar");
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", parts.map(([, name, count]) => `${name}: ${count}`).join(", "));
    bar.append(...parts.filter(([, , count]) => count).map(([key, name, count]) => {
      const part = el("span", key);
      part.style.width = `${(count / total) * 100}%`;
      part.title = `${name}: ${whole.format(count)}`;
      return part;
    }));
    const legend = el("ul", "legend");
    legend.append(...parts.map(([key, name, count]) => {
      const item = el("li");
      item.append(el("span", `swatch ${key}`), document.createTextNode(`${name} ${Math.round((count / total) * 100)}%`));
      return item;
    }));
    $("s-kinds").replaceChildren(bar, legend);
  }

  function paintDays() {
    const { days, today } = board.ledger;
    const top = Math.max(board.per_day, ...days.map((day) => day.cases), 1) * 1.12;
    const step = 600 / days.length;
    const y = (count) => 126 - (count / top) * 116;
    const chart = $("s-days");
    chart.setAttribute("aria-label", `Cases a day for the last ${days.length} days: ${today} today, with a daily limit of ${board.per_day}`);
    chart.replaceChildren(svg("line", { class: "base", x1: 0, x2: 600, y1: 126, y2: 126 }));
    days.forEach((day, index) => {
      const x = index * step + step * 0.18;
      const width = step * 0.64;
      const verdicts = day.cases - day.contempt;
      const column = svg("g", {});
      column.append(
        svg("title", {}, `${day.day}: ${verdicts} verdicts, ${day.contempt} contempt`),
        svg("rect", { class: "a", x, y: y(verdicts), width, height: 126 - y(verdicts), rx: 2 }),
        svg("rect", { class: "b", x, y: y(day.cases), width, height: y(verdicts) - y(day.cases), rx: 2 }),
      );
      chart.append(column);
    });
    chart.append(svg("line", { class: "cap", x1: 0, x2: 600, y1: y(board.per_day), y2: y(board.per_day) }));
    // Labels live outside the drawing, so they stay readable however small it gets.
    $("s-axis").replaceChildren(el("span", "", "30 days ago"), el("span", "limit", `Daily limit ${whole.format(board.per_day)}`), el("span", "", "Today"));
  }

  function paintSaved() {
    const { saved } = board;
    const tile = (tokens, title, note, explain) => {
      const box = el("div", "tile");
      box.title = explain;
      const big = el("p", "big", `≈ ${compact.format(tokens)} `);
      big.append(el("span", "hint", "tokens"));
      box.append(el("p", "label", title), big, el("p", "hint", note));
      return box;
    };
    $("s-saved").replaceChildren(
      tile(saved.refused_tokens, "Stopped at the door", `${whole.format(saved.refused)} requests never reached the AI`,
        "Requests refused before any AI call, for being too big, malformed or over a limit, times what an average case costs."),
      tile(saved.contempt_tokens, "Not a chatbot", `${whole.format(saved.contempt)} off-topic asks got contempt, not answers`,
        "An estimate: what answering those off-topic asks might have cost a chatbot."),
    );
  }

  function paintProviders() {
    const answered = board.ledger.providers_today;
    const total = Math.max(1, Object.values(answered).reduce((sum, count) => sum + count, 0));
    $("s-providers").replaceChildren(...board.providers.map((provider) => {
      const item = el("li");
      const name = provider.name.replace(/-/g, " ").replace(/^./, (first) => first.toUpperCase());
      const share = answered[provider.name] ? ` · ${Math.round((answered[provider.name] / total) * 100)}% today` : "";
      item.title = `${provider.model}: ${provider.ready ? "ready" : "resting until its quota returns"}`;
      item.append(el("span", provider.ready ? "state" : "state resting"), document.createTextNode(name + share));
      return item;
    }));
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) check(); // back on the tab: look again at once
  });

  return { load, open, laws: () => (board ? board.ledger.laws : []) };
})();
