import { initializeConfirmations } from "./features/confirmations.js";
import { initializeExports } from "./features/exportaciones.js";
import { initializeJobs } from "./features/jobs.js";
import { initializeNavigation } from "./features/navigation.js";
import { initializeOrders } from "./features/pedidos.js";
import { initializeTableSearch } from "./features/table-search.js";

function initialize() {
  initializeNavigation();
  initializeTableSearch();
  initializeJobs();
  initializeExports();
  initializeOrders();
  initializeConfirmations();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initialize, { once: true });
} else {
  initialize();
}
