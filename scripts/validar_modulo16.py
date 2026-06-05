from app.infrastructure.gbp.module16_registry import Module16Registry


def main() -> None:
    """Muestra métodos GBP y estado contractual actual."""

    registry = Module16Registry(strict=False)
    for metodo in registry.listar():
        print(f"{metodo.nombre}: {metodo.estado} - {metodo.observaciones}")


if __name__ == "__main__":
    main()
