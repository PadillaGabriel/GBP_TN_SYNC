import { query } from "../core/dom.js";

export function initializeNavigation() {
  const section = document.body.dataset.section;
  if (section) {
    const item = query(`[data-nav="${section}"]`);
    item?.classList.add("active");
    item?.setAttribute("aria-current", "page");
  }

  const sidebar = query("#sidebar");
  const button = query("#menuBtn");
  if (!sidebar || !button) return;

  const close = () => {
    sidebar.classList.remove("open");
    button.setAttribute("aria-expanded", "false");
  };

  button.addEventListener("click", () => {
    const open = sidebar.classList.toggle("open");
    button.setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
  document.addEventListener("click", (event) => {
    const mobile = window.matchMedia("(max-width: 960px)").matches;
    if (
      mobile &&
      sidebar.classList.contains("open") &&
      !sidebar.contains(event.target) &&
      !button.contains(event.target)
    ) {
      close();
    }
  });
}
