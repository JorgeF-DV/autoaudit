"""M1 · EvaluadorCriterios.clasificar — RTF3 Tablas 7 y 15, AC-006-1 a AC-006-5."""

from decimal import Decimal
from itertools import product

import pytest

from autoaudit.dominio.errores import ConfiguracionInvalidaError, DatosInvalidosError
from autoaudit.dominio.evaluacion import (
    Criterio,
    EvaluadorCriterios,
    NivelAutomatizacion,
    ParametrosEvaluacion,
    ProcesoEvaluado,
    TipoProceso,
)

# Respuesta cruda que produce cada puntaje (1..5) en las escalas de la Tabla 4.
VOLUMEN = {5: 500, 4: 200, 3: 50, 2: 10, 1: 5}
DEPENDENCIA = {
    5: Decimal("10"),
    4: Decimal("20"),
    3: Decimal("30"),
    2: Decimal("50"),
    1: Decimal("70"),
}

ALTO, MEDIO, BAJO, NO_APTO = (
    NivelAutomatizacion.ALTO,
    NivelAutomatizacion.MEDIO,
    NivelAutomatizacion.BAJO,
    NivelAutomatizacion.NO_APTO,
)


def proceso(f: int, v: int, e: int, d: int, variabilidad: str = "10") -> ProcesoEvaluado:
    return ProcesoEvaluado(
        tipo=TipoProceso.RESERVAS,
        frecuencia=f,
        volumen_mes=VOLUMEN[v],
        afirmaciones_estructura=e - 1,
        dependencia_humana=DEPENDENCIA[d],
        variabilidad=Decimal(variabilidad),
        horas_mes=Decimal("40"),
        costo_hora=Decimal("12000"),
    )


@pytest.fixture
def evaluador() -> EvaluadorCriterios:
    return EvaluadorCriterios(ParametrosEvaluacion(costos_implementacion={}))


def test_cp_m1_01_datos_incompletos_lanza_error_tipificado(evaluador: EvaluadorCriterios) -> None:
    incompleto = proceso(5, 5, 5, 5)
    incompleto.horas_mes = None
    with pytest.raises(DatosInvalidosError) as error:
        evaluador.clasificar(incompleto)
    assert error.value.codigo == "DATOS_INCOMPLETOS"


@pytest.mark.parametrize(
    ("puntajes", "variabilidad", "indice", "nivel"),
    [
        pytest.param((5, 5, 5, 5), "35", None, NO_APTO, id="CP-M1-02-variabilidad-precede-indice"),
        pytest.param((5, 4, 5, 5), "10", Decimal("4.80"), ALTO, id="CP-M1-03"),
        pytest.param((5, 5, 5, 3), "10", Decimal("4.50"), MEDIO, id="CP-M1-04-ia-alto-d-bajo"),
        pytest.param((4, 3, 3, 3), "10", Decimal("3.30"), MEDIO, id="CP-M1-05"),
        pytest.param((2, 2, 2, 2), "10", Decimal("2.00"), BAJO, id="CP-M1-06"),
    ],
)
def test_caminos_basicos_m1(
    evaluador: EvaluadorCriterios,
    puntajes: tuple[int, int, int, int],
    variabilidad: str,
    indice: Decimal | None,
    nivel: NivelAutomatizacion,
) -> None:
    resultado = evaluador.clasificar(proceso(*puntajes, variabilidad=variabilidad))
    assert resultado.indice == indice
    assert resultado.nivel is nivel


@pytest.mark.parametrize(
    ("puntajes", "variabilidad", "nivel"),
    [
        pytest.param((4, 4, 4, 4), "10", ALTO, id="ia-4.00-limite-ALTO"),
        pytest.param((4, 3, 4, 4), "10", MEDIO, id="ia-3.80-debajo-ALTO"),
        pytest.param((3, 3, 3, 3), "10", MEDIO, id="ia-3.00-limite-MEDIO"),
        pytest.param((3, 2, 3, 3), "10", BAJO, id="ia-2.80-debajo-MEDIO"),
        pytest.param((5, 5, 5, 4), "10", ALTO, id="d-20pct-limite-ALTO"),
        pytest.param((5, 5, 5, 5), "29", ALTO, id="variabilidad-29-se-evalua"),
        pytest.param((5, 5, 5, 5), "30", ALTO, id="variabilidad-30-se-evalua"),
        pytest.param((5, 5, 5, 5), "30.01", NO_APTO, id="variabilidad-30.01-NO_APTO"),
    ],
)
def test_fronteras_tabla_15(
    evaluador: EvaluadorCriterios,
    puntajes: tuple[int, int, int, int],
    variabilidad: str,
    nivel: NivelAutomatizacion,
) -> None:
    assert evaluador.clasificar(proceso(*puntajes, variabilidad=variabilidad)).nivel is nivel


def test_ac_006_2_indice_exacto_en_la_frontera(evaluador: EvaluadorCriterios) -> None:
    resultado = evaluador.clasificar(proceso(4, 4, 4, 4))
    assert resultado.indice == Decimal("4.00")
    assert resultado.nivel is ALTO


def test_ac_006_3_las_625_combinaciones_dan_un_solo_nivel_y_decimal(
    evaluador: EvaluadorCriterios,
) -> None:
    for f, v, e, d in product(range(1, 6), repeat=4):
        resultado = evaluador.clasificar(proceso(f, v, e, d))
        assert resultado.nivel in (ALTO, MEDIO, BAJO)
        assert isinstance(resultado.indice, Decimal)
        assert resultado.puntajes == (f, v, e, d)


@pytest.mark.parametrize(
    "pesos",
    [
        pytest.param({c: 0.25 for c in Criterio}, id="pesos-float"),
        pytest.param({c: Decimal("0.30") for c in Criterio}, id="suma-1.20"),
        pytest.param({Criterio.F: Decimal("1.00")}, id="faltan-criterios"),
    ],
)
def test_ac_006_4_parametros_invalidos_se_rechazan(pesos: dict[Criterio, Decimal]) -> None:
    with pytest.raises(ConfiguracionInvalidaError):
        ParametrosEvaluacion(costos_implementacion={}, pesos=pesos)


def test_ac_006_5_vertical_con_pesos_que_fallan_en_float() -> None:
    # Con float: 0.35*3 + 0.35*3 + 0.15*1 + 0.15*5 = 2.9999999999999996 -> BAJO (incorrecto).
    pesos = {
        Criterio.F: Decimal("0.35"),
        Criterio.V: Decimal("0.35"),
        Criterio.E: Decimal("0.15"),
        Criterio.D: Decimal("0.15"),
    }
    evaluador = EvaluadorCriterios(ParametrosEvaluacion(costos_implementacion={}, pesos=pesos))
    resultado = evaluador.clasificar(proceso(3, 3, 1, 5))
    assert resultado.indice == Decimal("3.00")
    assert resultado.nivel is MEDIO
