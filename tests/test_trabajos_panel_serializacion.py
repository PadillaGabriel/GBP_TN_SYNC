from app.infraestructura.persistencia.modelos import SyncJobModel
from app.infraestructura.persistencia.repositorios.trabajos_sincronizacion import (
    RepositorioTrabajosSincronizacion,
)


def test_serializador_aplana_progreso_para_panel():
    job = SyncJobModel(
        id=77,
        tipo="IMPORTAR_TODO_TN",
        estado="EN_PROCESO",
        error_mensaje='{"mensaje":"Procesando lote","porcentaje":42,"procesados":21,"total":50,"errores":1}',
    )

    data = RepositorioTrabajosSincronizacion.__new__(RepositorioTrabajosSincronizacion).serializar(job)

    assert data is not None
    assert data["progreso_porcentaje"] == 42
    assert data["mensaje"] == "Procesando lote"
    assert data["procesados"] == 21
    assert data["total"] == 50
    assert data["errores"] == 1
    assert data["progreso"]["porcentaje"] == 42
