// The chat transcript. Plain DOM; no code or technical text ever reaches it.

const GREETING =
  "Hi! What would you like to make today? Tell me about it, or share a photo of something you'd like to copy.";

export function createChat(root, { onChoice }) {
  const scroll = () => { root.scrollTop = root.scrollHeight; };

  function bubble(kind, text) {
    const div = document.createElement("div");
    div.className = `msg ${kind}`;
    if (text) div.append(document.createTextNode(text));
    root.append(div);
    return div;
  }

  function addChip(div) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = "Design updated";
    div.append(document.createElement("br"), chip);
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
  }

  function addAssistant(text, { chip = false, choices = [] } = {}) {
    const div = bubble("assistant", text);
    if (chip) addChip(div);
    addChoices(choices);
    scroll();
  }

  function addInfo(text) { bubble("info", text); scroll(); }

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
      else if (e.role === "info") addInfo(e.text);
      else addAssistant(e.text, { chip: !!e.chip, choices: i === display.length - 1 ? e.choices : [] });
    });
  }

  return { show, addUser, addAssistant, addInfo, pending };
}
