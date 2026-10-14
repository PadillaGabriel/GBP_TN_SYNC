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
  const backdrop = query("#sidebarBackdrop");
  if (!sidebar || !button || !backdrop) return;
  let previousFocus = null;
  const isMobile = () => window.matchMedia("(max-width: 960px)").matches;
  const close = () => {
    const wasOpen = sidebar.classList.contains("open");
    sidebar.classList.remove("open");
    backdrop.hidden = true;
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-label", "Abrir navegación");
    document.body.classList.remove("nav-open");
    if (wasOpen && isMobile()) (previousFocus || button).focus();
  };
  const open = () => {
    previousFocus = document.activeElement;
    sidebar.classList.add("open");
    backdrop.hidden = false;
    button.setAttribute("aria-expanded", "true");
    button.setAttribute("aria-label", "Cerrar navegación");
    document.body.classList.add("nav-open");
    sidebar.querySelector("a")?.focus();
  };

  button.addEventListener("click", () => sidebar.classList.contains("open") ? close() : open());
  backdrop.addEventListener("click", close);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
    if (event.key === "Tab" && isMobile() && sidebar.classList.contains("open")) {
      const elements = [...sidebar.querySelectorAll("a[href]")];
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  window.matchMedia("(max-width: 960px)").addEventListener("change", (event) => {
    if (!event.matches) close();
  });
  sidebar.querySelectorAll("a[href]").forEach((link) => link.addEventListener("click", close));
}

export function initializeTheme() {
  const button = query("#themeToggle");
  if (!button) return;
  const key = "silmar-panel-theme";
  let preferred = "auto";
  try { preferred = localStorage.getItem(key) || "auto"; } catch { /* Storage may be unavailable. */ }
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
  const apply = () => {
    const dark = preferred === "dark" || (preferred === "auto" && systemDark.matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    button.setAttribute("aria-label", dark ? "Activar tema claro" : "Activar tema oscuro");
    button.title = dark ? "Tema claro" : "Tema oscuro";
    button.querySelector("span").textContent = dark ? "☀" : "◐";
  };
  button.addEventListener("click", () => {
    preferred = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    try { localStorage.setItem(key, preferred); } catch { /* Non-persistent mode. */ }
    apply();
  });
  systemDark.addEventListener("change", () => { if (preferred === "auto") apply(); });
  apply();
}
