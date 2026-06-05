import logging


def configure_logging(level: str) -> None:
    """Configura logging estándar de la aplicación."""

    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
