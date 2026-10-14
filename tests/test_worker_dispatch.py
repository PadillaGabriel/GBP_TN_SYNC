"""Dispatch de handlers en worker separado, sin llamadas externas."""
import json

import pytest

from app.procesos import worker


@pytest.mark.asyncio
async def test_worker_preserva_parametros_del_job(monkeypatch):
    seen = []

    async def fake_handler(*, job_id: int, batch_limit: int, concurrency: int):
        seen.append((job_id, batch_limit, concurrency))

    monkeypatch.setitem(worker.COMMANDS, "AUDITAR_TODO_GBP", fake_handler)
    await worker.ejecutar(77, "AUDITAR_TODO_GBP", json.dumps({"batch_limit": 80, "concurrency": 2}))
    assert seen == [(77, 80, 2)]


@pytest.mark.asyncio
async def test_worker_rechaza_tipo_desconocido():
    with pytest.raises(ValueError, match="Tipo de job no admitido"):
        await worker.ejecutar(100, "BORRAR_TODO", "{}")
