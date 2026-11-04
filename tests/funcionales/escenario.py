"""Datos y armado de servicios compartidos por las pruebas funcionales (servicios y API)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

from autoaudit.dominio.cuestionario import Bloque, Pregunta, TipoRespuesta, VersionCuestionario
from autoaudit.dominio.evaluacion import (
    CalculadoraImpacto,
    EvaluadorCriterios,
    NivelAutomatizacion,
    ParametrosEvaluacion,
    ProcesoEvaluado,
    TipoProceso,
)
from autoaudit.dominio.pagos import Diagnostico, EstadoPago, EventoPasarela
from autoaudit.dominio.revision import Rol, Usuario
from autoaudit.servicios.cuestionario import ResultadoGuardado, ServicioCuestionario
from autoaudit.servicios.motor import MotorAnalisis, ResultadoProceso
from autoaudit.servicios.pagos import CodigoOrden, ResultadoPago, ServicioPagos
from tests.fakes import CuestionarioEnMemoria

D = Decimal
N = NivelAutomatizacion
T0 = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)
AUDITOR = Usuario(uuid4(), Rol.AUDITOR_LIDER)


def _numero(id_: str, minimo: str, maximo: str | None = None) -> Pregunta:
    return Pregunta(
        id_, TipoRespuesta.NUMERO, minimo=D(minimo), maximo=None if maximo is None else D(maximo)
    )


# Un bloque por proceso operativo (HU-003): mismas preguntas, distinto proceso.
PREGUNTAS = (
    _numero("frecuencia", "1", "5"),
    _numero("volumen_mes", "0"),
    _numero("afirmaciones_estructura", "0", "4"),
    _numero("dependencia_humana", "0", "100"),
    _numero("variabilidad", "0", "100"),
    _numero("horas_mes", "0", "744"),
    _numero("costo_hora", "0"),
    Pregunta("observaciones", TipoRespuesta.TEXTO, obligatoria=False),
)
PROCESOS = (TipoProceso.RESERVAS, TipoProceso.FACTURACION, TipoProceso.ATENCION_CLIENTE)
VERSION = VersionCuestionario(uuid4(), 1, tuple(Bloque(p, PREGUNTAS) for p in PROCESOS))

# Respuestas de un proceso muy automatizable: F=5, V=5, E=5, D=5 → índice 5.00, nivel ALTO.
RESPUESTAS_ALTO: dict[str, str | None] = {
    "frecuencia": "5",
    "volumen_mes": "600",
    "afirmaciones_estructura": "4",
    "dependencia_humana": "10",
    "variabilidad": "10",
    "horas_mes": "100",
    "costo_hora": "20000",
}


def parametros(costo_implementacion: str = "8000000") -> ParametrosEvaluacion:
    costos = {(t, n): D(costo_implementacion) for t in TipoProceso for n in (N.ALTO, N.MEDIO)}
    return ParametrosEvaluacion(costos_implementacion=costos)


def motor(costo_implementacion: str = "8000000") -> MotorAnalisis:
    p = parametros(costo_implementacion)
    return MotorAnalisis(EvaluadorCriterios(p), CalculadoraImpacto(p))


def proceso(
    frecuencia: int | None = 5,
    volumen: int = 600,
    afirmaciones: int = 4,
    dependencia: str = "10",
    variabilidad: str = "10",
    horas: str = "100",
    costo: str = "20000",
) -> ProcesoEvaluado:
    return ProcesoEvaluado(
        TipoProceso.RESERVAS,
        frecuencia,
        volumen,
        afirmaciones,
        D(dependencia),
        D(variabilidad),
        D(horas),
        D(costo),
    )


def proceso_desde(tipo: TipoProceso, valores: Mapping[str, Decimal | str]) -> ProcesoEvaluado:
    def n(clave: str) -> Decimal:
        valor = valores[clave]
        assert isinstance(valor, Decimal)
        return valor

    return ProcesoEvaluado(
        tipo,
        int(n("frecuencia")),
        int(n("volumen_mes")),
        int(n("afirmaciones_estructura")),
        n("dependencia_humana"),
        n("variabilidad"),
        n("horas_mes"),
        n("costo_hora"),
    )


def evaluar_uno(p: ProcesoEvaluado, costo_implementacion: str = "8000000") -> ResultadoProceso:
    return motor(costo_implementacion).evaluar([p])[0]


@dataclass
class App:
    pagos: ServicioPagos
    cuestionario: ServicioCuestionario
    diagnostico: Diagnostico
    cuestionarios: CuestionarioEnMemoria
    pasarela: Mock
    notificador: Mock
    cola: Mock

    def confirmar(self, estado: EstadoPago, evento_id: str = "E1") -> ResultadoPago:
        evento = EventoPasarela(evento_id, "R1", estado, motivo="FONDOS_INSUFICIENTES")
        return self.pagos.procesar_confirmacion(evento, b"{}", "firma")

    def pagar(self) -> ResultadoPago:
        assert self.pagos.crear_orden(self.diagnostico.id).codigo is CodigoOrden.CREADA
        return self.confirmar(EstadoPago.APROBADO)

    def responder(self, indice: int, respuestas: Mapping[str, str | None]) -> ResultadoGuardado:
        return self.cuestionario.guardar_bloque(self.diagnostico.id, indice, respuestas)
