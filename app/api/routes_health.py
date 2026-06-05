from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Endpoint liviano para monitoreo."""

    return {"status": "ok"}
