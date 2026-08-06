import { normalizeText, query, queryAll } from "../core/dom.js";

export function initializeTableSearch() {
  const input = query("#tableSearch");
  if (!input) return;

  input.addEventListener("input", () => {
    const search = normalizeText(input.value).toLocaleLowerCase("es");
    queryAll("#productRows tr").forEach((row) => {
      const content = row.textContent.toLocaleLowerCase("es");
      row.hidden = search !== "" && !content.includes(search);
    });
  });
}
