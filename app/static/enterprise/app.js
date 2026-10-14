import { initializeCategories } from "./features/categorias.js";
import { initializeExports } from "./features/exportaciones.js";
import { initializeJobs } from "./features/jobs.js";
import { initializeNavigation, initializeTheme } from "./features/navigation.js";
import { initializeOrders } from "./features/pedidos.js";
import { initializeProductActions } from "./features/product-actions.js";
import { initializeTableSearch } from "./features/table-search.js";

function initialize() {
  initializeNavigation();
  initializeTheme();
  initializeTableSearch();
  initializeJobs();
  initializeExports();
  initializeOrders();
  initializeProductActions();
  initializeCategories();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initialize, { once: true });
} else {
  initialize();
}
