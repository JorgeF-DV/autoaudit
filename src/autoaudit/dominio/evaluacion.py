"""Automatizabilidad (M1, RN006) e impacto económico (M3, RN004 y RN007).

Todo valor que se compara contra un umbral es `Decimal` construido desde `str`: con `float`,
pesos como 0,35/0,35/0,15/0,15 y puntajes (3, 3, 1, 5) suman 2.9999999999999996 y el proceso
cae en BAJO en vez de MEDIO (RTF3, sección 5.3).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import NamedTuple

from autoaudit.dominio.errores import ConfiguracionInvalidaError, DatosInvalidosError

CENTAVO = Decimal("0.01")
HORAS_MES_MAXIMAS = Decimal("744")  # horas de un mes de 31 días


class Criterio(StrEnum):
    F = "F"  # frecuencia
    V = "V"  # volumen
    E = "E"  # estructura
    D = "D"  # dependencia de criterio humano


class NivelAutomatizacion(StrEnum):
    NO_APTO = "NO_APTO"
    BAJO = "BAJO"
    MEDIO = "MEDIO"
    ALTO = "ALTO"


class TipoProceso(StrEnum):
    ATENCION_CLIENTE = "ATENCION_CLIENTE"
    RESERVAS = "RESERVAS"
    FACTURACION = "FACTURACION"
    PROSPECTOS = "PROSPECTOS"


@dataclass
class ProcesoEvaluado:
    """Respuestas del gerente sobre un proceso; `None` significa «sin responder»."""

    tipo: TipoProceso
    frecuencia: int | None  # puntaje F ya en escala 1..5
    volumen_mes: int | None  # casos atendidos al mes
    afirmaciones_estructura: int | None  # 0..4 respuestas afirmativas
    dependencia_humana: Decimal | None  # % de casos que requieren decisión humana
    variabilidad: Decimal | None  # % de casos fuera del flujo habitual
    horas_mes: Decimal | None
    costo_hora: Decimal | None
    requiere_revision_manual: bool = False


class Puntajes(NamedTuple):
    f: int
    v: int
    e: int
    d: int

    def por_criterio(self) -> dict[Criterio, int]:
        return {Criterio.F: self.f, Criterio.V: self.v, Criterio.E: self.e, Criterio.D: self.d}


@dataclass(frozen=True)
class ResultadoEvaluacion:
    puntajes: Puntajes
    indice: Decimal | None
    nivel: NivelAutomatizacion


@dataclass(frozen=True)
class EstimacionEconomica:
    horas_ahorradas_mes: Decimal
    ahorro_anual: Decimal
    costo_implementacion: Decimal
    roi: Decimal
    recuperacion_meses: Decimal
    recomendada: bool


def _pesos_por_defecto() -> dict[Criterio, Decimal]:
    return {
        Criterio.F: Decimal("0.30"),
        Criterio.V: Decimal("0.20"),
        Criterio.E: Decimal("0.25"),
        Criterio.D: Decimal("0.25"),
    }


def _factores_por_defecto() -> dict[NivelAutomatizacion, Decimal]:
    return {NivelAutomatizacion.ALTO: Decimal("0.70"), NivelAutomatizacion.MEDIO: Decimal("0.40")}


@dataclass(frozen=True)
class ParametrosEvaluacion:
    """Umbrales y pesos por vertical (RNF-05): se cambian con datos, no con código."""

    costos_implementacion: Mapping[tuple[TipoProceso, NivelAutomatizacion], Decimal]
    pesos: Mapping[Criterio, Decimal] = field(default_factory=_pesos_por_defecto)
    factor_reduccion: Mapping[NivelAutomatizacion, Decimal] = field(
        default_factory=_factores_por_defecto
    )
    umbral_variabilidad: Decimal = Decimal("30")
    umbral_alto: Decimal = Decimal("4.00")
    umbral_medio: Decimal = Decimal("3.00")
    dependencia_minima_alto: int = 4
    roi_minimo: Decimal = Decimal("50")

    def __post_init__(self) -> None:
        if set(self.pesos) != set(Criterio) or not all(
            isinstance(peso, Decimal) for peso in self.pesos.values()
        ):
            raise ConfiguracionInvalidaError("PESOS_INVALIDOS")
        if sum(self.pesos.values()) != Decimal("1.00"):
            raise ConfiguracionInvalidaError("PESOS_NO_SUMAN_UNO")

    def costo_implementacion(self, tipo: TipoProceso, nivel: NivelAutomatizacion) -> Decimal:
        return self.costos_implementacion.get((tipo, nivel), Decimal("0"))


def _escala_volumen(casos_mes: int) -> int:
    for minimo, puntaje in ((500, 5), (200, 4), (50, 3), (10, 2)):
        if casos_mes >= minimo:
            return puntaje
    return 1


def _escala_dependencia(porcentaje: Decimal) -> int:
    for maximo, puntaje in ((10, 5), (20, 4), (40, 3), (60, 2)):
        if porcentaje <= maximo:
            return puntaje
    return 1


class EvaluadorCriterios:
    """M1 · RN006. Cinco decisiones (P1 a P5), V(G) = 6 (RTF3, Figura 10)."""

    def __init__(self, parametros: ParametrosEvaluacion) -> None:
        self._p = parametros

    def clasificar(self, proceso: ProcesoEvaluado) -> ResultadoEvaluacion:
        frecuencia, volumen = proceso.frecuencia, proceso.volumen_mes
        afirmaciones, dependencia = proceso.afirmaciones_estructura, proceso.dependencia_humana
        variabilidad = proceso.variabilidad
        if (  # P1
            frecuencia is None
            or volumen is None
            or afirmaciones is None
            or dependencia is None
            or variabilidad is None
            or proceso.horas_mes is None
            or proceso.costo_hora is None
        ):
            raise DatosInvalidosError("DATOS_INCOMPLETOS")

        puntajes = Puntajes(
            frecuencia, _escala_volumen(volumen), 1 + afirmaciones, _escala_dependencia(dependencia)
        )
        if variabilidad > self._p.umbral_variabilidad:  # P2: el filtro precede al índice
            return ResultadoEvaluacion(puntajes, None, NivelAutomatizacion.NO_APTO)

        ia = sum(
            (self._p.pesos[c] * n for c, n in puntajes.por_criterio().items()), Decimal("0")
        ).quantize(CENTAVO)
        if ia >= self._p.umbral_alto:  # P3
            alto = puntajes.d >= self._p.dependencia_minima_alto  # P4
            nivel = NivelAutomatizacion.ALTO if alto else NivelAutomatizacion.MEDIO
        elif ia >= self._p.umbral_medio:  # P5
            nivel = NivelAutomatizacion.MEDIO
        else:
            nivel = NivelAutomatizacion.BAJO
        return ResultadoEvaluacion(puntajes, ia, nivel)


class CalculadoraImpacto:
    """M3 · RN004 y RN007. Seis decisiones, V(G) = 7. Ninguna división ocurre antes de P5."""

    def __init__(self, parametros: ParametrosEvaluacion) -> None:
        self._p = parametros

    def estimar(
        self, proceso: ProcesoEvaluado, resultado: ResultadoEvaluacion
    ) -> EstimacionEconomica | None:
        nivel = resultado.nivel
        if nivel not in (NivelAutomatizacion.ALTO, NivelAutomatizacion.MEDIO):  # P1
            return None
        horas, costo_hora = proceso.horas_mes, proceso.costo_hora
        if horas is None or horas <= 0:  # P2
            raise DatosInvalidosError("HORAS_NO_POSITIVAS")
        if horas > HORAS_MES_MAXIMAS:  # P3
            raise DatosInvalidosError("HORAS_FUERA_DE_RANGO")
        if costo_hora is None or costo_hora <= 0:  # P4
            raise DatosInvalidosError("COSTO_HORA_INVALIDO")
        costo_impl = self._p.costo_implementacion(proceso.tipo, nivel)
        if costo_impl <= 0:  # P5
            raise ConfiguracionInvalidaError("COSTO_IMPLEMENTACION")

        horas_ahorradas = horas * self._p.factor_reduccion[nivel]
        ahorro_mensual = horas_ahorradas * costo_hora
        ahorro_anual = (ahorro_mensual * 12).quantize(CENTAVO)
        # Se compara el ROI ya redondeado: es el mismo valor que ve el cliente en el informe.
        roi = ((ahorro_anual - costo_impl) / costo_impl * 100).quantize(CENTAVO, ROUND_HALF_UP)
        recuperacion = (costo_impl / ahorro_mensual).quantize(Decimal("0.1"), ROUND_HALF_UP)
        return EstimacionEconomica(
            horas_ahorradas_mes=horas_ahorradas.quantize(CENTAVO),
            ahorro_anual=ahorro_anual,
            costo_implementacion=costo_impl,
            roi=roi,
            recuperacion_meses=recuperacion,
            recomendada=roi >= self._p.roi_minimo,  # P6
        )
