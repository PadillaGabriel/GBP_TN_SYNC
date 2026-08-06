export function query(selector, root = document) {
  return root.querySelector(selector);
}

export function queryAll(selector, root = document) {
  return Array.from(root.querySelectorAll(selector));
}

export function requireElement(selector, description) {
  const element = query(selector);
  if (!element) {
    throw new Error(`No se encontró ${description}.`);
  }
  return element;
}

export function normalizeText(value) {
  return String(value ?? "").trim();
}

export function renderResult(element, payload) {
  element.textContent =
    typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
}
