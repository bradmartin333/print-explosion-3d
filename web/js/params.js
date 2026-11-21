// The Adjust panel: turns the design's settings into plain controls. Calls onEdit(name, value).

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node[k] = v;
  }
  node.append(...kids);
  return node;
}

function control(p, onEdit) {
  const id = `param-${p.name}`;
  const wrap = el("div", { class: "param" + (p.kind === "bool" ? " check" : "") });
  const label = el("label", { class: "name", htmlFor: id });
  const hint = p.description ? [el("span", { class: "hint", text: p.description })] : [];

  if (p.options.length) {
    const select = el("select", { id });
    for (const o of p.options) select.append(el("option", { value: String(o.value), text: o.label }));
    select.value = String(p.value);
    select.addEventListener("change", () => onEdit(p.name, select.value));
    label.textContent = p.label;
    wrap.append(label, ...hint, select);
  } else if (p.kind === "bool") {
    const box = el("input", { id, type: "checkbox", checked: !!p.value });
    box.addEventListener("change", () => onEdit(p.name, box.checked));
    label.append(box, p.label);
    wrap.append(label, ...hint);
  } else if (p.kind === "number") {
    label.textContent = p.label;
    const step = p.step ?? (Number.isInteger(p.value) ? 1 : 0.1);
    const num = el("input", { id, type: "number", value: p.value, step });
    if (p.min != null) num.min = p.min;
    if (p.max != null) num.max = p.max;
    const row = el("div", { class: "row" });
    let slider = null;
    if (p.min != null && p.max != null) {
      slider = el("input", { type: "range", min: p.min, max: p.max, step, value: p.value });
      slider.setAttribute("aria-label", p.label);
      row.append(slider);
    }
    row.append(num);
    const clamp = (v) => Math.min(p.max ?? Infinity, Math.max(p.min ?? -Infinity, v));
    slider?.addEventListener("input", () => { num.value = slider.value; onEdit(p.name, +slider.value); });
    num.addEventListener("change", () => {
      if (num.value === "" || Number.isNaN(+num.value)) { num.value = p.value; return; }
      const v = clamp(+num.value);
      num.value = v;
      if (slider) slider.value = v;
      onEdit(p.name, v);
    });
    wrap.append(label, ...hint, row);
  } else {
    label.textContent = p.label;
    const text = el("input", { id, type: "text", value: String(p.value) });
    if (p.max_length) text.maxLength = p.max_length;
    text.addEventListener("change", () => onEdit(p.name, text.value));
    wrap.append(label, ...hint, text);
  }
  return wrap;
}

export function renderParams(container, sections, onEdit) {
  container.replaceChildren();
  if (!sections?.length) {
    container.append(el("p", { class: "empty", text: "Once there's a design, its sizes and options show up here." }));
    return;
  }
  const showTitles = sections.length > 1 || sections[0].section.toLowerCase() !== "settings";
  for (const s of sections) {
    const box = el("div", { class: "param-section" });
    if (showTitles) box.append(el("h3", { text: s.section }));
    for (const p of s.params) box.append(control(p, onEdit));
    container.append(box);
  }
}
