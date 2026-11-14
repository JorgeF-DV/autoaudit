"""Mensajes que ve el usuario (RTF4 v2, observaciones 3 y 4).

Toda respuesta de error lleva un texto para la pantalla. Estas pruebas garantizan que ningún
código llegue al portal sin texto y que ningún texto exponga detalles internos al gerente.
"""

import re
from pathlib import Path

import pytest

from autoaudit.dominio.cuestionario import CodigoError
from autoaudit.presentacion.mensajes import GENERICO, MENSAJES, mensaje
from autoaudit.servicios.pagos import CodigoOrden

SRC = Path(__file__).resolve().parents[2] / "src" / "autoaudit"
CODIGOS_LANZADOS = {
    codigo
    for archivo in SRC.rglob("*.py")
    for codigo in re.findall(r'Error\("([A-Z_]+)"\)', archivo.read_text(encoding="utf-8"))
}
CODIGOS_DE_PANTALLA = (
    CODIGOS_LANZADOS
    | set(CodigoOrden)
    | {c for c in CodigoError if c in ("TIPO", "RANGO")}
    | {"OBLIGATORIA", "SOLICITUD_INVALIDA"}
)
# Lo que un gerente no debe leer: constantes, códigos HTTP, jerga de programación.
TECNICO = re.compile(r"[A-Z]{3,}_|\bHTTP\b|\b[45]\d\d\b|excepci|error|null|none|webhook", re.I)


def test_cada_codigo_que_llega_a_la_pantalla_tiene_mensaje() -> None:
    assert CODIGOS_LANZADOS, "la búsqueda de códigos no encontró nada"
    assert CODIGOS_DE_PANTALLA - set(MENSAJES) == set()


@pytest.mark.parametrize("codigo", sorted(MENSAJES))
def test_el_mensaje_no_expone_detalles_internos(codigo: str) -> None:
    assert not TECNICO.search(MENSAJES[codigo])


def test_un_codigo_desconocido_muestra_el_mensaje_generico() -> None:
    assert mensaje("CODIGO_NUEVO") == GENERICO
