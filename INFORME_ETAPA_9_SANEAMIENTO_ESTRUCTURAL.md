# Etapa 9 — Saneamiento estructural y control de calidad

## Alcance ejecutado

Esta etapa se realizó sobre la versión funcional de la Etapa 8, sin agregar reglas de negocio nuevas ni modificar credenciales.

### Correcciones aplicadas

- Se configuró Ruff para reconocer como declarativas las llamadas de FastAPI (`Depends`, `Query`, `Form`, etc.), evitando falsos positivos `B008` sin desactivar la regla globalmente.
- Se reemplazó `timezone.utc` por `datetime.UTC` donde Ruff lo marcaba.
- Se corrigió una prueba con un conjunto duplicado.
- Se eliminó un argumento UTF-8 redundante.
- Se reemplazó `assert False` por `pytest.raises`, evitando que la validación desaparezca bajo `python -O`.
- Se reorganizaron los informes históricos en `docs/historico`.
- Se agregó `scripts/auditar_calidad.ps1` como puerta de calidad reproducible.
- Se eliminaron cachés Python y artefactos compilados antes del empaquetado.

## Revisión de arquitectura

Se verificó que la lógica denominada legacy que continúa presente tiene consumidores reales en el código actual. En particular, `obtener_catalogo_basico` todavía es utilizado por el servicio de auditoría GBP y por fallbacks del cliente GBP. No se eliminó porque hacerlo sin migrar esos consumidores rompería rutas de diagnóstico y auditoría.

Las rutas administrativas, técnicas y el programador comparten servicios y trabajos existentes, pero los archivos principales continúan siendo grandes. Su división física se considera un refactor posterior de alto impacto, no una eliminación segura de código muerto. Esta etapa prioriza preservar comportamiento e idempotencia.

## Validaciones ejecutadas en el entorno de entrega

- `python -m compileall -q app tests`: correcto.
- `pytest -q`: **83 pruebas aprobadas**.
- No se incluyeron `.env`, bases SQLite, `__pycache__` ni archivos `.pyc`.

## Validación local requerida

El entorno de construcción no dispone del ejecutable Ruff, por lo que la comprobación final debe ejecutarse localmente:

```powershell
.\scripts\auditar_calidad.ps1
```

La configuración fue corregida específicamente a partir del reporte de Ruff proporcionado. No se afirma un resultado Ruff limpio hasta ejecutar el comando con Ruff instalado en el entorno local.

## Deuda técnica deliberadamente conservada

- Cliente GBP histórico y catálogo básico: conservados porque aún tienen consumidores.
- Compatibilidades de Tiendanube: conservadas hasta verificar todas las rutas productivas y webhooks en ejecución real.
- División de archivos extensos: pendiente; requiere refactor incremental con pruebas por módulo.
- Orquestación de trabajos en proceso: funcional, pero todavía susceptible de separación física por dominio.

No se eliminó código basándose únicamente en coincidencias de texto o herramientas heurísticas.
