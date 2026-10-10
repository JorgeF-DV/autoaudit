"""Orden de pago, diagnóstico y regla de habilitación de preguntas (RN001, RN011)."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4


class EstadoPago(StrEnum):
    PENDIENTE = "PENDIENTE"
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    EXPIRADA = "EXPIRADA"


class EstadoCaracterizacion(StrEnum):
    INCOMPLETA = "INCOMPLETA"
    COMPLETA = "COMPLETA"


class EstadoDiagnostico(StrEnum):
    CREADO = "CREADO"
    PREGUNTAS_HABILITADAS = "PREGUNTAS_HABILITADAS"
    COMPLETO = "COMPLETO"


@dataclass
class OrdenPago:
    diagnostico_id: UUID
    valor: Decimal
    clave_idempotencia: str
    creada_en: datetime
    id: UUID = field(default_factory=uuid4)
    estado: EstadoPago = EstadoPago.PENDIENTE
    referencia_pasarela: str | None = None
    motivo_rechazo: str | None = None
    eventos_procesados: set[str] = field(default_factory=set)

    def aprobar(self) -> None:
        self.estado = EstadoPago.APROBADO

    def rechazar(self, motivo: str) -> None:
        self.estado = EstadoPago.RECHAZADO
        self.motivo_rechazo = motivo

    def expirar(self) -> None:
        self.estado = EstadoPago.EXPIRADA


@dataclass
class Diagnostico:
    version_cuestionario_id: UUID
    id: UUID = field(default_factory=uuid4)
    estado: EstadoDiagnostico = EstadoDiagnostico.CREADO
    estado_caracterizacion: EstadoCaracterizacion = EstadoCaracterizacion.INCOMPLETA
    ordenes: list[OrdenPago] = field(default_factory=list)

    def orden_aprobada(self) -> OrdenPago | None:
        return next((o for o in self.ordenes if o.estado is EstadoPago.APROBADO), None)


@dataclass(frozen=True)
class Referencia:
    id: str
    url: str


@dataclass(frozen=True)
class EventoPasarela:
    id: str
    referencia: str
    estado: EstadoPago
    motivo: str | None = None


class ReglaHabilitacion:
    """RN001 en un solo punto: la consultan el pago aprobado y el envío de la caracterización."""

    def preguntas_habilitadas(self, diagnostico: Diagnostico) -> bool:
        return (
            diagnostico.estado_caracterizacion is EstadoCaracterizacion.COMPLETA
            and diagnostico.orden_aprobada() is not None
        )
