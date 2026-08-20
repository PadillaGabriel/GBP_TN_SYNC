from pathlib import Path


def test_jobs_panel_usa_polling_adaptativo_y_suspension_por_visibilidad():
    source = Path("app/static/enterprise/features/jobs.js").read_text(encoding="utf-8")

    assert "ACTIVE_POLL_INTERVAL_MS = 2000" in source
    assert "IDLE_POLL_INTERVAL_MS = 60000" in source
    assert "ERROR_POLL_INTERVAL_MS = 15000" in source
    assert "window.setTimeout" in source
    assert "window.setInterval" not in source
    assert "document.hidden" in source
    assert 'document.addEventListener("visibilitychange"' in source
    assert "if (polling || document.hidden) return" in source
