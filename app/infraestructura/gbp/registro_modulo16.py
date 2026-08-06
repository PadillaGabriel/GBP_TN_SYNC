from dataclasses import dataclass
from enum import StrEnum

from app.dominio.errores import MetodoNoValidadoError


class EstadoMetodoGBP(StrEnum):
    """Estado contractual de un método GBP."""

    PERMITIDO = "permitido"
    PROHIBIDO = "prohibido"
    NO_USAR_HASTA_VALIDAR = "no_usar_hasta_validar"


@dataclass(frozen=True)
class MetodoGBP:
    """Definición auditable de método GBP."""

    nombre: str
    estado: EstadoMetodoGBP
    modulo: str | None = None
    observaciones: str = ""


class RegistroModulo16:
    """Registro explícito de métodos habilitados para Módulo 16.

    Todo método queda bloqueado por defecto hasta validación formal.
    """

    def __init__(self, *, strict: bool = True) -> None:
        self.strict = strict
        self._metodos: dict[str, MetodoGBP] = {
            "listar_productos_publicables": MetodoGBP(
                nombre="listar_productos_publicables",
                estado=EstadoMetodoGBP.NO_USAR_HASTA_VALIDAR,
                observaciones="Pendiente validar contra documentación real del Módulo 16.",
            ),
            "obtener_producto_completo": MetodoGBP(
                nombre="obtener_producto_completo",
                estado=EstadoMetodoGBP.NO_USAR_HASTA_VALIDAR,
                observaciones="Pendiente validar contra documentación real del Módulo 16.",
            ),
            "obtener_stock": MetodoGBP(
                nombre="obtener_stock",
                estado=EstadoMetodoGBP.NO_USAR_HASTA_VALIDAR,
                observaciones="Pendiente validar contra documentación real del Módulo 16.",
            ),
        }

    def validar(self, nombre_metodo: str) -> None:
        """Bloquea métodos no confirmados para evitar deuda contractual."""

        metodo = self._metodos.get(nombre_metodo)
        if metodo is None:
            raise MetodoNoValidadoError(
                f"Método GBP no registrado: {nombre_metodo}. NO USAR HASTA VALIDAR."
            )
        if metodo.estado != EstadoMetodoGBP.PERMITIDO and self.strict:
            raise MetodoNoValidadoError(
                f"Método GBP {nombre_metodo} está en estado {metodo.estado}."
            )

    def listar(self) -> list[MetodoGBP]:
        """Devuelve métodos registrados y estado contractual."""

        return list(self._metodos.values())
