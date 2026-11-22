// The chat transcript. Plain DOM; no code or technical text ever reaches it.

const NOTICE_MS = 8000;
const RESOLVED_MS = 2500;
const GREETING =
  "What would you like to make? Describe it, or share a photo.";

export function createChat(root, { onChoice }) {
  const scroll = () => { root.scrollTop = root.scrollHeight; };

  function bubble(kind, text) {
    const div = document.createElement("div");
    div.className = `msg ${kind}`;
    if (text) div.append(document.createTextNode(text));
    root.append(div);
    return div;
  }

  const clearChoices = () => root.querySelectorAll(".choices").forEach((n) => n.remove());

  function addChoices(choices) {
    if (!choices?.length) return;
    const row = document.createElement("div");
    row.className = "choices";
    for (const c of choices) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = c;
      b.addEventListener("click", () => onChoice(c));
      row.append(b);
    }
    root.append(row);
  }

  function addUser(text, previews = [], photoCount = 0) {
    clearChoices();
    const div = bubble("user");
    if (previews.length) {
      const photos = document.createElement("div");
      photos.className = "photos";
      for (const src of previews) {
        const img = document.createElement("img");
        img.src = src;
        img.alt = "A photo you shared";
        photos.append(img);
      }
      div.append(photos);
    } else if (photoCount) {
      const tag = document.createElement("div");
      tag.className = "photo-tag";
      tag.textContent = photoCount === 1 ? "📷 A photo" : `📷 ${photoCount} photos`;
      div.append(tag);
    }
    if (text) div.append(document.createTextNode(text));
    scroll();
    return div;
  }

  function addAssistant(text, { choices = [] } = {}) {
    bubble("assistant", text);
    addChoices(choices);
    scroll();
  }

  // A problem (red) stays until something of the same `key` works, then it says so and fades.
  // A notice (grey) is just a heads-up and fades by itself.
  const fade = (div) => { div.classList.add("leaving"); setTimeout(() => div.remove(), 450); };

  function addInfo(text, { key = "other", notice = false } = {}) {
    const div = bubble(notice ? "info notice" : "info", text);
    div.dataset.key = key;
    if (notice) setTimeout(() => fade(div), NOTICE_MS);
    scroll();
    return div;
  }

  function resolve(...keys) {
    const found = [...root.querySelectorAll(".msg.info:not(.notice):not(.resolved)")]
      .filter((d) => keys.includes(d.dataset.key));
    found.slice(0, -1).forEach((d) => d.remove()); // one "that worked" is plenty
    const last = found.at(-1);
    if (!last) return;
    last.classList.add("resolved");
    last.textContent = "✓ That worked";
    setTimeout(() => fade(last), RESOLVED_MS);
  }

  // A reply that is still arriving: shows the status, then streamed text.
  function pending(statusText = "Thinking…") {
    const div = bubble("assistant pending", statusText);
    scroll();
    return {
      status(t) { if (!div.dataset.streaming) div.textContent = t; },
      text(t) {
        if (!t) return;
        div.dataset.streaming = "1";
        div.classList.remove("pending");
        div.textContent = t;
        scroll();
      },
      remove() { div.remove(); },
    };
  }

  function show(display) {
    root.replaceChildren();
    if (!display?.length) { addAssistant(GREETING); return; }
    display.forEach((e, i) => {
      if (e.role === "user") addUser(e.text, [], (e.images || []).length);
      else if (e.role === "info") addInfo(e.text, { key: "ai" });
      else addAssistant(e.text, { choices: i === display.length - 1 ? e.choices : [] });
    });
  }

  return { show, addUser, addAssistant, addInfo, resolve, pending };
}
