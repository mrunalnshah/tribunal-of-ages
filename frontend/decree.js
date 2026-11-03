// The decree: a verdict drawn as an image to download or share, entirely in the browser.
// Designs come from decree-themes.json, so a new one needs no code. The names a visitor types
// and the photo they add are drawn into the picture and go nowhere else: no request, no
// analytics, no storage. Redrawing the photo also leaves its metadata, such as GPS, behind.
const decree = (() => {
  const W = 1080;
  const H = 1350; // 4:5, the shape most social apps show uncropped
  const M = 120; // the margin inside the border
  const $ = (id) => document.getElementById(id);
  let themes = [];
  let ruling = null;
  let picked = ""; // a design the visitor chose stays chosen for later verdicts
  let photo = null; // the visitor's picture, decoded in memory only, until removed or reload

  async function loadThemes() {
    if (themes.length) return themes;
    try {
      const response = await fetch("decree-themes.json");
      themes = response.ok ? (await response.json()).themes.map(withDefaults) : [];
    } catch {
      themes = []; // offline: the decree panel simply stays hidden
    }
    return themes;
  }

  // A design needs only an id, a name, a title, two paper colors and an ink color. Everything
  // else falls back to these, so a simple design is one short line of JSON.
  function withDefaults(theme) {
    const accent = theme.accent || theme.ink;
    const plain = { suits: [], texture: "none", border: "double", portrait: "circle", seal: accent };
    return { ...plain, font: "Georgia, 'Times New Roman', serif", ...theme, accent };
  }

  // app.js calls this with every verdict it shows, live or from the archive.
  async function offer(nextRuling) {
    ruling = nextRuling;
    const list = await loadThemes();
    $("decree").hidden = !list.length;
    if (!list.length) return;
    const skin = list.find((theme) => theme.id === document.documentElement.dataset.decree);
    const suited = skin || list.find((theme) => theme.suits.includes(ruling.law.theme)) || list[0];
    $("decree-theme").replaceChildren(...list.map((theme) => new Option(theme.name, theme.id)));
    $("decree-theme").value = list.some((theme) => theme.id === picked) ? picked : suited.id;
    draw();
  }

  function hide() {
    $("decree").hidden = true;
    ruling = null;
  }

  // The private part of the form: read here, drawn into the picture, never sent anywhere.
  function people() {
    return $("accused").value.split(",").map((name) => name.trim()).filter(Boolean).slice(0, 3);
  }

  function plaintiff() {
    return $("plaintiff").value.trim();
  }

  function nobody() {
    return ruling && ruling.kind === "contempt" ? "The Petitioner" : "The Accused";
  }

  function joined(names) {
    return names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
  }

  // The judge is told to call the parties “the Plaintiff” and “the Accused” (verdict_v1.md),
  // which is what makes this safe: “The Accused shall repay thirtyfold” becomes “Dave shall
  // repay thirtyfold”. The names come from fields that never leave this device.
  function personalize(text, names, plaintiff = "") {
    let out = plaintiff ? text.replace(/\bthe (Plaintiff|Petitioner)\b/gi, plaintiff) : text;
    if (!names.length) return out;
    if (names.length > 1) {
      const plural = { is: "are", has: "have", was: "were", does: "do" };
      out = out.replace(/\b(the Accused) (is|has|was|does)\b/gi, (_, who, verb) => `${who} ${plural[verb.toLowerCase()]}`);
    }
    return out.replace(/\bthe Accused\b/gi, joined(names));
  }

  function theme() {
    return themes.find((item) => item.id === $("decree-theme").value) || themes[0];
  }

  function draw() {
    if (!ruling) return;
    const style = theme();
    // In contempt, the visitor is the one in the dock: their own name, or "the Petitioner".
    const names = ruling.kind === "contempt" ? [plaintiff()].filter(Boolean) : people();
    const ctx = $("decree-canvas").getContext("2d");
    const rand = seeded(`${style.id}|${ruling.verdict.case_title}`);
    paper(ctx, style, rand);
    border(ctx, style);
    portrait(ctx, style);
    words(ctx, style, names);
    seal(ctx, style);
    const who = names.length ? joined(names) : nobody();
    $("decree-canvas").setAttribute("aria-label", `Decree${photo ? ", with a photo" : ""}: ${who}, `
      + `${ruling.kind === "contempt" ? "held in" : "guilty of"} ${ruling.verdict.charge}. Sentence: ${personalize(ruling.verdict.sentence, names, plaintiff())}`);
  }

  // A small seeded random generator, so a verdict's texture looks the same every time.
  function seeded(text) {
    let seed = [...text].reduce((h, ch) => Math.imul(h ^ ch.charCodeAt(0), 2654435761) >>> 0, 2166136261);
    return () => {
      seed = (seed + 0x6d2b79f5) >>> 0;
      let t = seed;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function paper(ctx, style, rand) {
    const gradient = ctx.createLinearGradient(0, 0, W, H);
    gradient.addColorStop(0, style.paper[0]);
    gradient.addColorStop(1, style.paper[1]);
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, W, H);
    ctx.save();
    ctx.strokeStyle = style.ink;
    ctx.fillStyle = style.ink;
    if (style.texture === "speckle") {
      for (let i = 0; i < 2600; i++) {
        ctx.globalAlpha = 0.03 + rand() * 0.09;
        ctx.fillRect(rand() * W, rand() * H, 1 + rand() * 2.5, 1 + rand() * 2.5);
      }
    } else if (style.texture === "fibers") {
      for (let i = 0; i < 260; i++) {
        ctx.globalAlpha = 0.03 + rand() * 0.05;
        ctx.lineWidth = 1 + rand() * 3;
        const along = rand() < 0.5;
        const at = rand() * (along ? H : W);
        ctx.beginPath();
        ctx.moveTo(along ? 0 : at, along ? at : 0);
        ctx.lineTo(along ? W : at + rand() * 20 - 10, along ? at + rand() * 20 - 10 : H);
        ctx.stroke();
      }
    } else if (style.texture === "veins") {
      for (let i = 0; i < 16; i++) {
        ctx.globalAlpha = 0.04 + rand() * 0.08;
        ctx.lineWidth = 0.8 + rand() * 2.2;
        ctx.beginPath();
        ctx.moveTo(-50, rand() * H);
        ctx.bezierCurveTo(W * 0.3, rand() * H, W * 0.7, rand() * H, W + 50, rand() * H);
        ctx.stroke();
      }
    } else if (style.texture === "grain") {
      for (let i = 0; i < 1400; i++) {
        ctx.globalAlpha = 0.02 + rand() * 0.05;
        const x = rand() * W;
        const y = rand() * H;
        ctx.fillRect(x, y, 3 + rand() * 6, 1);
      }
    }
    ctx.restore();
    const edge = ctx.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.75);
    edge.addColorStop(0, "rgba(0, 0, 0, 0)");
    edge.addColorStop(1, "rgba(0, 0, 0, 0.22)");
    ctx.fillStyle = edge;
    ctx.fillRect(0, 0, W, H);
  }

  function border(ctx, style) {
    ctx.save();
    ctx.strokeStyle = style.accent;
    ctx.fillStyle = style.accent;
    if (style.border === "bold") {
      ctx.lineWidth = 18;
      ctx.strokeRect(36, 36, W - 72, H - 72);
      ctx.lineWidth = 3;
      ctx.strokeRect(62, 62, W - 124, H - 124);
    } else {
      ctx.lineWidth = 4;
      ctx.strokeRect(44, 44, W - 88, H - 88);
      if (style.border === "double") {
        ctx.lineWidth = 1.5;
        ctx.strokeRect(60, 60, W - 120, H - 120);
      } else if (style.border === "wedges") {
        for (let x = 74; x < W - 60; x += 34) {
          wedge(ctx, x, 60, 1);
          wedge(ctx, x, H - 60, -1);
        }
      } else if (style.border === "dots") {
        for (let x = 70; x <= W - 70; x += 26) dot(ctx, x, 60);
        for (let x = 70; x <= W - 70; x += 26) dot(ctx, x, H - 60);
        for (let y = 86; y <= H - 86; y += 26) dot(ctx, 60, y);
        for (let y = 86; y <= H - 86; y += 26) dot(ctx, W - 60, y);
      }
    }
    ctx.restore();
  }

  function wedge(ctx, x, y, direction) {
    ctx.beginPath();
    ctx.moveTo(x - 9, y);
    ctx.lineTo(x + 9, y);
    ctx.lineTo(x, y + 14 * direction);
    ctx.closePath();
    ctx.fill();
  }

  function dot(ctx, x, y) {
    ctx.beginPath();
    ctx.arc(x, y, 3.2, 0, Math.PI * 2);
    ctx.fill();
  }

  // Read a photo the visitor picked, keeping only a small square copy of its pixels in memory.
  async function choosePhoto(file) {
    const status = $("decree-photo-status");
    status.textContent = "";
    if (!file) return;
    if (!file.type.startsWith("image/") || file.size > 15_000_000) {
      status.textContent = "Choose an image file under 15 MB.";
    } else {
      try {
        photo = square(await decode(file));
        status.textContent = "Photo added. It stays on this device.";
      } catch {
        status.textContent = "That image couldn’t be read here. Try a JPG or a PNG.";
      }
    }
    $("decree-photo").value = ""; // let go of the file itself: only the copy above remains
    $("decree-photo-remove").hidden = !photo;
    draw();
  }

  async function decode(file) {
    if (window.createImageBitmap) return createImageBitmap(file, { imageOrientation: "from-image" });
    const url = URL.createObjectURL(file);
    try {
      const img = new Image();
      img.src = url;
      await img.decode();
      return img;
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  // The middle square, a little above centre in tall photos, where faces usually are.
  function square(image) {
    const width = image.width;
    const height = image.height;
    const side = Math.min(width, height);
    const size = Math.min(side, 600); // a decree never needs more
    const copy = document.createElement("canvas");
    copy.width = size;
    copy.height = size;
    const top = height > width ? (height - side) * 0.35 : (height - side) / 2;
    copy.getContext("2d").drawImage(image, (width - side) / 2, top, side, side, 0, 0, size, size);
    image.close?.();
    return copy;
  }

  function frame(style) {
    const oval = style.portrait === "oval";
    const w = oval ? 210 : 236;
    const h = oval ? 270 : 236;
    return { x: W - M + 34 - w, y: 126, w, h };
  }

  function portrait(ctx, style) {
    if (!photo) return;
    const { x, y, w, h } = frame(style);
    const outline = () => {
      ctx.beginPath();
      if (style.portrait === "circle") ctx.arc(x + w / 2, y + h / 2, w / 2, 0, Math.PI * 2);
      else if (style.portrait === "oval") ctx.ellipse(x + w / 2, y + h / 2, w / 2, h / 2, 0, 0, Math.PI * 2);
      else ctx.rect(x, y, w, h); // "square": a mugshot
    };
    ctx.save();
    ctx.shadowColor = "rgba(0, 0, 0, 0.35)";
    ctx.shadowBlur = 18;
    ctx.fillStyle = style.paper[0];
    outline();
    ctx.fill();
    ctx.restore();
    ctx.save();
    outline();
    ctx.clip();
    const side = Math.max(w, h); // the copy is square: cover the frame
    ctx.drawImage(photo, x + (w - side) / 2, y + (h - side) / 2, side, side);
    ctx.restore();
    ctx.save();
    ctx.lineWidth = 9;
    ctx.strokeStyle = style.accent;
    outline();
    ctx.stroke();
    ctx.restore();
  }

  // Lay the text out top to bottom, shrinking it until it fits above the seal. Lines that
  // start beside the photo are shorter, so no text ever runs under it.
  function words(ctx, style, names) {
    const filer = plaintiff();
    const v = ruling.verdict;
    const law = ruling.law;
    const quote = law.text.length > 320 ? `${law.text.slice(0, 317).trimEnd()}…` : law.text;
    const source = `${law.verbatim ? "Quoted from" : "Paraphrased from"} ${law.source}, ${law.citation}`;
    const blocks = [
      { label: "", text: "THE TRIBUNAL OF AGES", size: 30, weight: "bold", color: style.accent, gap: 18, spaced: true },
      { label: "", text: style.title, size: 92, weight: "bold", gap: 14 },
      { label: "", text: personalize(v.case_title, names, filer), size: 38, italic: true, gap: 46 },
      { label: ruling.kind === "contempt" ? "Held in contempt" : "The accused", text: names.length ? joined(names) : nobody(), size: 58, weight: "bold", gap: 34 },
      { label: "The charge", text: personalize(v.charge, names, filer), size: 34, gap: 34 },
      { label: "The sentence", text: personalize(v.sentence, names, filer), size: 36, gap: 34 },
      { label: "Under the law", text: `“${quote}”`, size: 28, italic: true, gap: 10 },
      { label: "", text: source, size: 24, color: style.accent, gap: 0 },
    ];
    const beside = photo ? frame(style) : null;
    const bottom = H - 330; // the seal and the date live below this line
    let scale = 1;
    let laid = layout(ctx, style, blocks, scale, beside);
    while (laid.end > bottom && scale > 0.55) {
      scale -= 0.05;
      laid = layout(ctx, style, blocks, scale, beside);
    }
    ctx.textBaseline = "top";
    for (const block of laid.blocks) {
      if (block.label) {
        ctx.font = `bold ${Math.round(20 * scale)}px ${style.font}`;
        ctx.fillStyle = style.accent;
        spaced(ctx, block.label.toUpperCase(), M, block.y, 4);
      }
      ctx.font = block.font;
      ctx.fillStyle = block.color || style.ink;
      block.lines.forEach((line, i) => {
        const y = block.textY + i * block.lineHeight;
        if (block.spaced) spaced(ctx, line, M, y, 6);
        else ctx.fillText(line, M, y);
      });
    }
    const issued = new Date().toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
    ctx.font = `italic 28px ${style.font}`;
    ctx.fillStyle = style.ink;
    ctx.fillText(`Issued on ${issued}`, M, H - 250);
    ctx.font = `bold 26px ${style.font}`;
    ctx.fillText("By order of the Tribunal", M, H - 210);
    ctx.globalAlpha = 0.75;
    ctx.font = `20px ${style.font}`;
    ctx.fillText("For entertainment only. Not a real legal document.", M, H - 118);
    ctx.globalAlpha = 1;
  }

  function layout(ctx, style, blocks, scale, beside) {
    let y = 150;
    const out = blocks.map((block) => {
      const size = Math.round(block.size * scale);
      const font = `${block.italic ? "italic " : ""}${block.weight || "normal"} ${size}px ${style.font}`;
      ctx.font = font;
      const narrow = beside && y < beside.y + beside.h + 16;
      const width = W - 2 * M - (narrow ? beside.w + 10 : 0) - (block.spaced ? 120 : 0);
      const lines = wrap(ctx, block.text, width);
      const lineHeight = Math.round(size * 1.28);
      const start = y;
      const textY = y + (block.label ? Math.round(30 * scale) : 0);
      y = textY + lines.length * lineHeight + Math.round(block.gap * scale);
      return { ...block, font, lines, lineHeight, y: start, textY };
    });
    return { blocks: out, end: y };
  }

  function wrap(ctx, text, width) {
    const lines = [];
    let line = "";
    for (const word of text.split(/\s+/).filter(Boolean)) {
      const next = line ? `${line} ${word}` : word;
      if (line && ctx.measureText(next).width > width) {
        lines.push(line);
        line = word;
      } else {
        line = next;
      }
    }
    if (line) lines.push(line);
    return lines;
  }

  // Letter-spaced capitals, drawn one character at a time so every browser spaces them alike.
  function spaced(ctx, text, x, y, spacing) {
    let at = x;
    for (const ch of text) {
      ctx.fillText(ch, at, y);
      at += ctx.measureText(ch).width + spacing;
    }
  }

  function seal(ctx, style) {
    const cx = W - 230;
    const cy = H - 225;
    const r = 96;
    ctx.save();
    ctx.fillStyle = style.seal;
    ctx.beginPath();
    for (let i = 0; i < 36; i++) { // a wax seal's wavy rim
      const angle = (i / 36) * Math.PI * 2;
      const radius = r + (i % 2 ? 6 : 0);
      ctx.lineTo(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius);
    }
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = style.paper[0];
    ctx.globalAlpha = 0.85;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(cx, cy, r - 14, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = style.paper[0];
    ctx.font = `bold 15px ${style.font}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const ring = "• TRIBUNAL OF AGES • SEALED ";
    [...ring].forEach((ch, i) => { // the court's name around the rim
      const angle = (i / ring.length) * Math.PI * 2 - Math.PI / 2;
      ctx.save();
      ctx.translate(cx + Math.cos(angle) * (r - 30), cy + Math.sin(angle) * (r - 30));
      ctx.rotate(angle + Math.PI / 2);
      ctx.fillText(ch, 0, 0);
      ctx.restore();
    });
    ctx.lineWidth = 4; // a balance in the middle
    ctx.beginPath();
    ctx.moveTo(cx, cy - 34);
    ctx.lineTo(cx, cy + 26);
    ctx.moveTo(cx - 30, cy + 26);
    ctx.lineTo(cx + 30, cy + 26);
    ctx.moveTo(cx - 36, cy - 22);
    ctx.lineTo(cx + 36, cy - 22);
    ctx.stroke();
    for (const side of [-1, 1]) {
      ctx.beginPath();
      ctx.arc(cx + side * 36, cy - 4, 14, 0, Math.PI);
      ctx.stroke();
    }
    ctx.restore();
  }

  function fileName() {
    const slug = ruling.verdict.case_title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    return `decree-${slug.slice(0, 40) || "tribunal"}.png`;
  }

  function image() {
    return new Promise((resolve) => $("decree-canvas").toBlob(resolve, "image/png"));
  }

  function exported(how) {
    analytics.track("decree_exported", { theme: theme().id, people: people().length, photo: Boolean(photo), how });
  }

  for (const id of ["accused", "plaintiff"]) $(id).addEventListener("input", () => requestAnimationFrame(draw));
  document.addEventListener("skin-changed", () => {
    if (ruling) offer(ruling); // a new skin brings its own design, unless the visitor chose one
  });
  $("decree-photo").addEventListener("change", (event) => choosePhoto(event.target.files[0]));
  $("decree-photo-remove").addEventListener("click", () => {
    photo = null;
    $("decree-photo-remove").hidden = true;
    $("decree-photo-status").textContent = "Photo removed.";
    draw();
  });
  $("decree-theme").addEventListener("change", () => {
    picked = $("decree-theme").value;
    draw();
  });
  $("decree-download").addEventListener("click", async () => {
    const blob = await image();
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const link = Object.assign(document.createElement("a"), { href: url, download: fileName() });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    exported("download");
  });
  // Phones can hand the image straight to another app; browsers that can't, don't see the button.
  const probe = new File([""], "decree.png", { type: "image/png" });
  $("decree-share").hidden = !(navigator.canShare && navigator.canShare({ files: [probe] }));
  $("decree-share").addEventListener("click", async () => {
    const blob = await image();
    if (!blob) return;
    try {
      await navigator.share({ files: [new File([blob], fileName(), { type: "image/png" })] });
      exported("share");
    } catch {
      // the visitor closed the share sheet: nothing to do
    }
  });

  return { offer, hide, personalize, people, plaintiff };
})();
