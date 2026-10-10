"""M4 · ValidadorBloque.validar — RTF3 Tablas 10 y 12, AC-003-1 a AC-003-4."""

from decimal import Decimal
from uuid import uuid4

import pytest

from autoaudit.dominio.cuestionario import (
    MAX_PREGUNTAS_POR_BLOQUE,
    Bloque,
    CodigoError,
    Pregunta,
    TipoRespuesta,
    ValidadorBloque,
    VersionCuestionario,
    punto_de_reanudacion,
)
from autoaudit.dominio.errores import ConfiguracionInvalidaError
from autoaudit.dominio.evaluacion import TipoProceso

validar = ValidadorBloque().validar


def bloque(*preguntas: Pregunta) -> Bloque:
    return Bloque(TipoProceso.RESERVAS, preguntas)


def horas(id_: str) -> Pregunta:
    return Pregunta(id_, TipoRespuesta.NUMERO, minimo=Decimal("0"), maximo=Decimal("744"))


def test_cp_m4_01_cero_iteraciones_avanza() -> None:
    assert validar(bloque(), {}).puede_avanzar is True


@pytest.mark.parametrize(
    ("pregunta", "crudo", "pendientes", "errores", "valores"),
    [
        pytest.param(horas("q1"), None, ("q1",), {}, {}, id="CP-M4-02-obligatoria-vacia"),
        pytest.param(
            Pregunta("q1", TipoRespuesta.TEXTO, obligatoria=False),
            "   ",
            (),
            {},
            {},
            id="CP-M4-03-opcional-vacia",
        ),
        pytest.param(horas("q1"), "800", (), {"q1": CodigoError.RANGO}, {}, id="CP-M4-04-rango"),
        pytest.param(horas("q1"), "12,5", (), {}, {"q1": Decimal("12.5")}, id="CP-M4-05-valida"),
    ],
)
def test_caminos_de_una_iteracion(
    pregunta: Pregunta,
    crudo: str | None,
    pendientes: tuple[str, ...],
    errores: dict[str, CodigoError],
    valores: dict[str, Decimal],
) -> None:
    resultado = validar(bloque(pregunta), {"q1": crudo})
    assert resultado.pendientes == pendientes
    assert resultado.errores == errores
    assert resultado.valores == valores
    assert resultado.puede_avanzar is (not pendientes and not errores)


def test_cp_m4_06_ac_003_1_el_ciclo_no_se_detiene_en_la_primera_falla() -> None:
    # Traza de la Tabla 12 del RTF3.
    resultado = validar(
        bloque(
            horas("q1"),
            horas("q2"),
            Pregunta("q3", TipoRespuesta.TEXTO, obligatoria=False),
            horas("q4"),
        ),
        {"q1": None, "q2": "800", "q3": "   ", "q4": "12,5"},
    )
    assert resultado.puede_avanzar is False
    assert resultado.pendientes == ("q1",)
    assert resultado.errores == {"q2": CodigoError.RANGO}
    assert resultado.valores == {"q4": Decimal("12.5")}


@pytest.mark.parametrize("n", [1, 2, 8, MAX_PREGUNTAS_POR_BLOQUE - 1, MAX_PREGUNTAS_POR_BLOQUE])
def test_cp_m4_07_ciclo_tipico_y_maximo(n: int) -> None:
    preguntas = tuple(horas(f"q{i}") for i in range(n))
    resultado = validar(bloque(*preguntas), {f"q{i}": "10" for i in range(n)})
    assert resultado.puede_avanzar is True
    assert len(resultado.valores) == n


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        pytest.param("NaN", CodigoError.TIPO, id="NaN"),
        pytest.param("Infinity", CodigoError.TIPO, id="Infinity"),
        pytest.param("abc", CodigoError.TIPO, id="texto"),
        pytest.param("1e3", CodigoError.RANGO, id="notacion-cientifica-1000"),
        pytest.param("-1", CodigoError.RANGO, id="debajo-del-minimo"),
        pytest.param(" 7 ", Decimal("7"), id="espacios"),
    ],
)
def test_cp_m4_09_ac_003_2_entradas_numericas_atipicas(
    crudo: str, esperado: CodigoError | Decimal
) -> None:
    resultado = validar(bloque(horas("q1")), {"q1": crudo})
    if isinstance(esperado, CodigoError):
        assert resultado.errores == {"q1": esperado}
    else:
        assert resultado.valores == {"q1": esperado}


@pytest.mark.parametrize("n", [0, MAX_PREGUNTAS_POR_BLOQUE + 1], ids=["vacio", "26-preguntas"])
def test_ac_003_3_no_se_publica_una_version_con_bloques_fuera_de_limite(n: int) -> None:
    preguntas = tuple(horas(f"q{i}") for i in range(n))
    with pytest.raises(ConfiguracionInvalidaError):
        VersionCuestionario(uuid4(), 1, (bloque(*preguntas),))


@pytest.mark.parametrize(
    ("completos", "esperado"),
    [
        pytest.param([False, False, False], 0, id="ninguno"),
        pytest.param([True, True, False], 2, id="dos-completos"),
        pytest.param([True, True, True], None, id="todos"),
    ],
)
def test_cp_m4_08_punto_de_reanudacion(completos: list[bool], esperado: int | None) -> None:
    assert punto_de_reanudacion(completos) == esperado
