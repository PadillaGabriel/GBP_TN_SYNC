from __future__ import annotations

from io import BytesIO
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from PIL import Image, ImageOps, UnidentifiedImageError

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/normalized-image")
async def normalized_image(
    src: str = Query(..., min_length=8),
    size: int = Query(default=1600, ge=600, le=2200),
) -> StreamingResponse:
    """Devuelve una imagen cuadrada con padding blanco para Tienda Nube.

    No recorta ni deforma. Centra la imagen original dentro de un canvas uniforme.
    """

    parsed = urlparse(src)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="src debe ser URL http/https")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25)) as client:
            response = await client.get(src)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo descargar imagen origen: {type(exc).__name__}") from exc

    try:
        image = Image.open(BytesIO(response.content))
        image = ImageOps.exif_transpose(image)
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (size, size), "white")
        if image.mode in {"RGBA", "LA"}:
            layer = Image.new("RGBA", image.size, "white")
            layer.alpha_composite(image.convert("RGBA"))
            image = layer.convert("RGB")
        else:
            image = image.convert("RGB")
        x = (size - image.width) // 2
        y = (size - image.height) // 2
        canvas.paste(image, (x, y))
        output = BytesIO()
        canvas.save(output, format="JPEG", quality=92, optimize=True, progressive=True)
        output.seek(0)
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=415, detail="La URL origen no contiene una imagen válida") from exc

    return StreamingResponse(
        output,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )
