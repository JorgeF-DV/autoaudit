"""M3 · CalculadoraImpacto.estimar — RTF3 Tablas 9, 15 y 23, AC-007-1 a AC-007-6."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from autoaudit.dominio.errores import ConfiguracionInvalidaError, DatosInvalidosError
from autoaudit.dominio.evaluacion import (
    CalculadoraImpacto,
    NivelAutomatizacion,
    ParametrosEvaluacion,
    ProcesoEvaluado,
    Puntajes,
    ResultadoEvaluacion,
    TipoProceso,
)

ALTO, MEDIO = NivelAutomatizacion.ALTO, NivelAutomatizacion.MEDIO
TIPO = TipoProceso.FACTURACION


def calculadora(costo_impl: str, nivel: NivelAutomatizacion) -> CalculadoraImpacto:
    return CalculadoraImpacto(
        ParametrosEvaluacion(costos_implementacion={(TIPO, nivel): Decimal(costo_impl)})
    )


def proceso(horas: str | None, costo_hora: str | None) -> ProcesoEvaluado:
    return ProcesoEvaluado(
        tipo=TIPO,
        frecuencia=5,
        volumen_mes=500,
        afirmaciones_estructura=4,
        dependencia_humana=Decimal("10"),
        variabilidad=Decimal("10"),
        horas_mes=None if horas is None else Decimal(horas),
        costo_hora=None if costo_hora is None else Decimal(costo_hora),
    )


def resultado(nivel: NivelAutomatizacion) -> ResultadoEvaluacion:
    return ResultadoEvaluacion(Puntajes(5, 5, 5, 5), Decimal("5.00"), nivel)


@pytest.mark.parametrize(
    "nivel",
    [
        pytest.param(NivelAutomatizacion.BAJO, id="CP-M3-01-BAJO"),
        pytest.param(NivelAutomatizacion.NO_APTO, id="AC-007-5-NO_APTO"),
    ],
)
def test_nivel_no_automatizable_retorna_none(nivel: NivelAutomatizacion) -> None:
    assert calculadora("4000000", ALTO).estimar(proceso("80", "15000"), resultado(nivel)) is None


@pytest.mark.parametrize(
    ("horas", "costo_hora", "codigo"),
    [
        pytest.param("0", "15000", "HORAS_NO_POSITIVAS", id="CP-M3-02"),
        pytest.param(None, "15000", "HORAS_NO_POSITIVAS", id="horas-sin-responder"),
        pytest.param("745", "15000", "HORAS_FUERA_DE_RANGO", id="CP-M3-03-AC-007-4"),
        pytest.param("80", "0", "COSTO_HORA_INVALIDO", id="CP-M3-04"),
        pytest.param("80", None, "COSTO_HORA_INVALIDO", id="costo-sin-responder"),
    ],
)
def test_entradas_invalidas_lanzan_error_tipificado(
    horas: str | None, costo_hora: str | None, codigo: str
) -> None:
    with pytest.raises(DatosInvalidosError) as error:
        calculadora("4000000", ALTO).estimar(proceso(horas, costo_hora), resultado(ALTO))
    assert error.value.codigo == codigo


def test_cp_m3_05_costo_cero_falla_antes_de_dividir() -> None:
    # AC-007-3: si llegara a dividir, decimal lanzaría DivisionByZero en vez de este error.
    with pytest.raises(ConfiguracionInvalidaError) as error:
        calculadora("0", ALTO).estimar(proceso("80", "15000"), resultado(ALTO))
    assert error.value.codigo == "COSTO_IMPLEMENTACION"


def test_cp_m3_05_costo_no_configurado_cuenta_como_cero() -> None:
    sin_costos = CalculadoraImpacto(ParametrosEvaluacion(costos_implementacion={}))
    with pytest.raises(ConfiguracionInvalidaError):
        sin_costos.estimar(proceso("80", "15000"), resultado(ALTO))


def test_cp_m3_06_ac_007_1_proceso_viable() -> None:
    est = calculadora("4000000", ALTO).estimar(proceso("80", "15000"), resultado(ALTO))
    assert est is not None
    assert est.horas_ahorradas_mes == Decimal("56.00")
    assert est.ahorro_anual == Decimal("10080000.00")
    assert est.roi == Decimal("152.00")
    assert est.recuperacion_meses == Decimal("4.8")
    assert est.recomendada is True


def test_cp_m3_07_ac_007_2_proceso_no_viable() -> None:
    est = calculadora("3000000", MEDIO).estimar(proceso("10", "12000"), resultado(MEDIO))
    assert est is not None
    assert est.ahorro_anual == Decimal("576000.00")
    assert est.roi == Decimal("-80.80")
    assert est.recomendada is False


def test_ac_007_4_744_horas_es_valido() -> None:
    assert calculadora("4000000", ALTO).estimar(proceso("744", "15000"), resultado(ALTO))


@pytest.mark.parametrize(
    ("costo_impl", "roi", "recomendada"),
    [
        pytest.param("2800190", Decimal("49.99"), False, id="roi-49.99-no-recomendada"),
        pytest.param("2800000", Decimal("50.00"), True, id="roi-50.00-recomendada"),
        pytest.param("2800075", Decimal("50.00"), True, id="roi-49.996-redondea-a-50.00"),
    ],
)
def test_ac_007_5_frontera_de_roi(costo_impl: str, roi: Decimal, recomendada: bool) -> None:
    est = calculadora(costo_impl, ALTO).estimar(proceso("50", "10000"), resultado(ALTO))
    assert est is not None
    assert est.ahorro_anual == Decimal("4200000.00")
    assert est.roi == roi
    assert est.recomendada is recomendada


def test_tabla_23_error_b_factor_medio_haria_descartar_el_proceso_viable() -> None:
    # El mismo proceso ALTO de CP-M3-06 evaluado con el factor de MEDIO da ROI 44 %:
    # si la rama de factorReduccion se confundiera, la PYME descartaría $10.080.000/año.
    est = calculadora("4000000", MEDIO).estimar(proceso("80", "15000"), resultado(MEDIO))
    assert est is not None
    assert est.roi == Decimal("44.00")
    assert est.recomendada is False


@given(
    horas=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("744"), places=2),
    costo_hora=st.decimals(min_value=Decimal("1000"), max_value=Decimal("200000"), places=0),
    nivel=st.sampled_from([ALTO, MEDIO]),
)
def test_ac_007_6_propiedad_del_ahorro_anual(
    horas: Decimal, costo_hora: Decimal, nivel: NivelAutomatizacion
) -> None:
    calc = calculadora("5000000", nivel)
    est = calc.estimar(proceso(str(horas), str(costo_hora)), resultado(nivel))
    factor = {ALTO: Decimal("0.70"), MEDIO: Decimal("0.40")}[nivel]
    assert est is not None
    assert est.ahorro_anual == (horas * factor * costo_hora * 12).quantize(Decimal("0.01"))
    assert est.recomendada is (est.roi >= Decimal("50"))
