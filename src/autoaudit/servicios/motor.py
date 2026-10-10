"""Ciclo del motor de análisis (RTF3, Figura 6): un proceso inválido no detiene a los demás."""

from collections.abc import Sequence
from dataclasses import dataclass

from autoaudit.dominio.errores import DatosInvalidosError
from autoaudit.dominio.evaluacion import (
    CalculadoraImpacto,
    EstimacionEconomica,
    EvaluadorCriterios,
    ProcesoEvaluado,
    ResultadoEvaluacion,
)


@dataclass(frozen=True)
class ResultadoProceso:
    proceso: ProcesoEvaluado
    evaluacion: ResultadoEvaluacion | None
    estimacion: EstimacionEconomica | None
    motivo: str | None = None


class MotorAnalisis:
    def __init__(self, evaluador: EvaluadorCriterios, calculadora: CalculadoraImpacto) -> None:
        self._evaluador = evaluador
        self._calculadora = calculadora

    def evaluar(self, procesos: Sequence[ProcesoEvaluado]) -> list[ResultadoProceso]:
        resultados: list[ResultadoProceso] = []
        for proceso in procesos:
            # El try va dentro del for: si envolviera el ciclo, el primer error abortaría el resto.
            # ConfiguracionInvalidaError no se captura: afecta a todos los procesos por igual.
            try:
                evaluacion = self._evaluador.clasificar(proceso)
                estimacion = self._calculadora.estimar(proceso, evaluacion)
            except DatosInvalidosError as error:
                proceso.requiere_revision_manual = True
                resultados.append(ResultadoProceso(proceso, None, None, error.codigo))
                continue
            resultados.append(ResultadoProceso(proceso, evaluacion, estimacion))
        return resultados
