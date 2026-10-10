"""Ciclo de MotorAnalisis — AC-006-6 y aislamiento de errores por iteración (RTF3, 5.3)."""

from decimal import Decimal

import pytest

from autoaudit.dominio.errores import ConfiguracionInvalidaError
from autoaudit.dominio.evaluacion import (
    CalculadoraImpacto,
    EvaluadorCriterios,
    NivelAutomatizacion,
    ParametrosEvaluacion,
    ProcesoEvaluado,
    TipoProceso,
)
from autoaudit.servicios.motor import MotorAnalisis

TIPO = TipoProceso.RESERVAS


def motor(costo_impl: str = "4000000") -> MotorAnalisis:
    costos = {(TIPO, nivel): Decimal(costo_impl) for nivel in NivelAutomatizacion}
    parametros = ParametrosEvaluacion(costos_implementacion=costos)
    return MotorAnalisis(EvaluadorCriterios(parametros), CalculadoraImpacto(parametros))


def proceso(horas: str | None = "80") -> ProcesoEvaluado:
    return ProcesoEvaluado(
        tipo=TIPO,
        frecuencia=5,
        volumen_mes=200,
        afirmaciones_estructura=4,
        dependencia_humana=Decimal("10"),
        variabilidad=Decimal("10"),
        horas_mes=None if horas is None else Decimal(horas),
        costo_hora=Decimal("15000"),
    )


def test_ac_006_6_un_proceso_incompleto_no_detiene_el_ciclo() -> None:
    procesos = [proceso(), proceso(horas=None), proceso()]

    resultados = motor().evaluar(procesos)

    assert len(resultados) == len(procesos)  # invariante del ciclo
    assert [p.requiere_revision_manual for p in procesos] == [False, True, False]
    assert resultados[1].evaluacion is None
    assert resultados[1].motivo == "DATOS_INCOMPLETOS"
    assert resultados[2].estimacion is not None
    assert resultados[2].estimacion.recomendada is True


def test_error_de_configuracion_se_propaga() -> None:
    with pytest.raises(ConfiguracionInvalidaError):
        motor(costo_impl="0").evaluar([proceso()])
