# Rediseño integral del panel enterprise

## Alcance

Se reemplazó la pantalla administrativa monolítica por una interfaz modular desde cero. El backend operativo existente se conserva y el nuevo panel actúa como capa de presentación sobre los mismos casos de uso y repositorios.

## Nuevas páginas

- Centro de operaciones
- Catálogo de productos
- Importación individual y masiva
- Sincronización de stock
- Pedidos Tiendanube → GBP
- Exportaciones GBP
- Centro de trabajos
- Auditoría
- Configuración segura

## Arquitectura

- `app/presentacion/rutas_panel.py`: rutas visuales sin lógica de negocio.
- `app/templates/enterprise/`: plantillas separadas por dominio.
- `app/static/enterprise/`: sistema visual y comportamiento común.
- Las acciones reutilizan endpoints operativos existentes, evitando duplicar orquestación.

## Compatibilidad

El panel anterior se conserva temporalmente bajo `/admin/panel-legacy` exclusivamente como contingencia técnica. La entrada oficial es `/admin/panel`.

## Seguridad

El entregable excluye `.env`, bases locales, cachés, archivos compilados y `.git`. La vista de configuración nunca muestra credenciales.
