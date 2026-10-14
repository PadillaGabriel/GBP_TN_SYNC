import { normalizeText, query, queryAll } from "../core/dom.js";

export function initializeTableSearch() {
  const input = query("#tableSearch");
  if (!input) return;
  const rows = queryAll("#productRows tr[data-product-row]");
  const count = query("#productSearchCount");
  const empty = query("#productSearchEmpty");
  const filter = () => {
    const search = normalizeText(input.value).toLocaleLowerCase("es");
    let visible = 0;
    rows.forEach((row) => {
      const matches = !search || row.textContent.toLocaleLowerCase("es").includes(search);
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    if (empty) empty.hidden = visible > 0 || rows.length === 0;
    if (count) count.textContent = `${visible} de ${rows.length} registros de esta página`;
  };
  input.addEventListener("input", filter);
}
