// Skins: each is one stylesheet in themes/, declared by a <link data-skin> in index.html. The
// switch is built from those links, so a new skin needs one file and one line, and no code.
// The choice is remembered on this device only, and never sent anywhere.
const skins = (() => {
  const KEY = "tribunal-skin";
  const root = document.documentElement;
  const list = [...document.querySelectorAll("link[data-skin]")].map((link) => ({
    id: link.dataset.skin,
    name: link.dataset.name || link.dataset.skin,
    decree: link.dataset.decree || "",
  }));

  function apply(id) {
    const skin = list.find((item) => item.id === id) || list[0];
    if (!skin) return;
    root.dataset.skin = skin.id;
    root.dataset.decree = skin.decree; // the decree design this skin opens with
    for (const button of document.querySelectorAll("#skins button")) {
      button.setAttribute("aria-pressed", String(button.dataset.skin === skin.id));
    }
    try {
      localStorage.setItem(KEY, skin.id);
    } catch {
      // private browsing: the choice just isn't remembered
    }
  }

  const box = document.getElementById("skins");
  box.replaceChildren(...list.map((skin) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.skin = skin.id;
    button.textContent = skin.name;
    button.addEventListener("click", () => {
      apply(skin.id);
      document.dispatchEvent(new CustomEvent("skin-changed")); // e.g. the decree picks its design
      analytics.track("skin_changed", { skin: skin.id });
    });
    return button;
  }));
  box.hidden = list.length < 2;
  apply(root.dataset.skin); // the script in <head> may already have restored a saved choice

  return { current: () => root.dataset.skin };
})();
