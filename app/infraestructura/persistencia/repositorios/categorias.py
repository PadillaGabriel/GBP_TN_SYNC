from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.infraestructura.persistencia.modelos import (
    CategoriaNormalizacionModel,
    ProductoFuenteModel,
)
from app.infraestructura.tienda_nube.utilidades_categorias import normalize_category_key


class RepositorioNormalizacionCategorias:
    """Diccionario comercial persistente para normalizar categorías GBP."""

    TIPOS = {"categoria", "subcategoria"}

    def __init__(self, db: Session) -> None:
        self.db = db

    def resolver(
        self,
        tipo: str,
        valor_origen: str | None,
        categoria_padre_canonica: str | None = None,
    ) -> str | None:
        valor = str(valor_origen or "").strip()
        if not valor:
            return None
        tipo_norm = self._tipo(tipo)
        clave = normalize_category_key(valor)
        contexto = (
            normalize_category_key(categoria_padre_canonica)
            if tipo_norm == "subcategoria"
            else ""
        )
        # Primero alias contextual; luego alias general de respaldo.
        candidatos = [contexto]
        if contexto:
            candidatos.append("")
        for contexto_busqueda in candidatos:
            model = self.db.scalar(
                select(CategoriaNormalizacionModel).where(
                    CategoriaNormalizacionModel.tipo == tipo_norm,
                    CategoriaNormalizacionModel.clave_origen == clave,
                    CategoriaNormalizacionModel.contexto_padre == contexto_busqueda,
                    CategoriaNormalizacionModel.activo.is_(True),
                )
            )
            if model is not None:
                return model.valor_canonico
        return valor

    def guardar(
        self,
        *,
        tipo: str,
        valor_origen: str,
        valor_canonico: str,
        categoria_padre_canonica: str | None = None,
        observacion: str | None = None,
        activo: bool = True,
    ) -> CategoriaNormalizacionModel:
        tipo_norm = self._tipo(tipo)
        origen = str(valor_origen or "").strip()
        canonico = str(valor_canonico or "").strip()
        if not origen or not canonico:
            raise ValueError("valor_origen y valor_canonico son obligatorios")
        contexto = (
            normalize_category_key(categoria_padre_canonica)
            if tipo_norm == "subcategoria"
            else ""
        )
        clave_origen = normalize_category_key(origen)
        model = self.db.scalar(
            select(CategoriaNormalizacionModel).where(
                CategoriaNormalizacionModel.tipo == tipo_norm,
                CategoriaNormalizacionModel.clave_origen == clave_origen,
                CategoriaNormalizacionModel.contexto_padre == contexto,
            )
        )
        if model is None:
            model = CategoriaNormalizacionModel(
                tipo=tipo_norm,
                valor_origen=origen,
                clave_origen=clave_origen,
                contexto_padre=contexto,
                categoria_padre_canonica=(
                    str(categoria_padre_canonica or "").strip() or None
                ),
                valor_canonico=canonico,
                clave_canonica=normalize_category_key(canonico),
            )
            self.db.add(model)
        else:
            model.valor_origen = origen
            model.valor_canonico = canonico
            model.clave_canonica = normalize_category_key(canonico)
            model.categoria_padre_canonica = (
                str(categoria_padre_canonica or "").strip() or None
            )
        model.observacion = str(observacion or "").strip() or None
        model.activo = bool(activo)
        self.db.commit()
        self.db.refresh(model)
        return model

    def eliminar(self, alias_id: int) -> bool:
        result = self.db.execute(
            delete(CategoriaNormalizacionModel).where(
                CategoriaNormalizacionModel.id == alias_id
            )
        )
        self.db.commit()
        return bool(result.rowcount)

    def listar(self, *, limit: int = 500) -> list[CategoriaNormalizacionModel]:
        return list(
            self.db.scalars(
                select(CategoriaNormalizacionModel)
                .order_by(
                    CategoriaNormalizacionModel.tipo.asc(),
                    CategoriaNormalizacionModel.valor_canonico.asc(),
                    CategoriaNormalizacionModel.valor_origen.asc(),
                )
                .limit(limit)
            ).all()
        )

    def contar(self) -> int:
        return int(
            self.db.scalar(select(func.count(CategoriaNormalizacionModel.id))) or 0
        )

    def origenes_gbp(self, *, limit: int = 1000) -> dict[str, list[dict[str, object]]]:
        categorias = self.db.execute(
            select(
                ProductoFuenteModel.categoria_nombre,
                func.count(ProductoFuenteModel.id),
            )
            .where(ProductoFuenteModel.categoria_nombre.is_not(None))
            .group_by(ProductoFuenteModel.categoria_nombre)
            .order_by(func.count(ProductoFuenteModel.id).desc())
            .limit(limit)
        ).all()
        subcategorias = self.db.execute(
            select(
                ProductoFuenteModel.categoria_nombre,
                ProductoFuenteModel.subcategoria_nombre,
                func.count(ProductoFuenteModel.id),
            )
            .where(ProductoFuenteModel.subcategoria_nombre.is_not(None))
            .group_by(
                ProductoFuenteModel.categoria_nombre,
                ProductoFuenteModel.subcategoria_nombre,
            )
            .order_by(func.count(ProductoFuenteModel.id).desc())
            .limit(limit)
        ).all()
        return {
            "categorias": [
                {"valor": str(valor), "productos": int(cantidad)}
                for valor, cantidad in categorias
                if str(valor or "").strip()
            ],
            "subcategorias": [
                {
                    "categoria": str(categoria or ""),
                    "valor": str(valor),
                    "productos": int(cantidad),
                }
                for categoria, valor, cantidad in subcategorias
                if str(valor or "").strip()
            ],
        }

    @classmethod
    def _tipo(cls, tipo: str) -> str:
        normalizado = str(tipo or "").strip().lower()
        if normalizado not in cls.TIPOS:
            raise ValueError(f"tipo inválido: {tipo}")
        return normalizado
