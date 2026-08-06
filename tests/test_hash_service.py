from app.aplicacion.servicios.servicio_hash import stable_hash


def test_stable_hash_no_depende_del_orden_de_claves() -> None:
    first = stable_hash({"b": 2, "a": 1})
    second = stable_hash({"a": 1, "b": 2})

    assert first == second
