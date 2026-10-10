"""Máquina de estados del reporte (RN003, RTF3 Figura 8)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID, uuid4

from autoaudit.dominio.errores import TransicionInvalidaError


class EstadoReporte(StrEnum):
    BORRADOR = "BORRADOR"
    EN_REVISION = "EN_REVISION"
    DEVUELTO = "DEVUELTO"
    APROBADO = "APROBADO"
    ENTREGADO = "ENTREGADO"
    ANULADO = "ANULADO"


class Rol(StrEnum):
    GERENTE = "GERENTE"
    CONSULTOR_JUNIOR = "CONSULTOR_JUNIOR"
    AUDITOR_LIDER = "AUDITOR_LIDER"


@dataclass(frozen=True)
class Usuario:
    id: UUID
    rol: Rol


@dataclass
class Reporte:
    diagnostico_id: UUID
    id: UUID = field(default_factory=uuid4)
    estado: EstadoReporte = EstadoReporte.BORRADOR
    version: int = 1
    seccion_supuestos: str = ""
    aprobado_por: UUID | None = None
    aprobado_en: datetime | None = None


_E = EstadoReporte
# Única fuente de transiciones permitidas; inmutable en ejecución.
TRANSICIONES: Mapping[EstadoReporte, frozenset[EstadoReporte]] = MappingProxyType(
    {
        _E.BORRADOR: frozenset({_E.EN_REVISION}),
        _E.EN_REVISION: frozenset({_E.EN_REVISION, _E.DEVUELTO, _E.APROBADO}),
        _E.DEVUELTO: frozenset({_E.EN_REVISION, _E.ANULADO}),
        _E.APROBADO: frozenset({_E.ENTREGADO}),
        _E.ENTREGADO: frozenset(),
        _E.ANULADO: frozenset(),
    }
)


def validar_transicion(origen: EstadoReporte, destino: EstadoReporte) -> None:
    if destino not in TRANSICIONES[origen]:
        raise TransicionInvalidaError("TRANSICION_NO_PERMITIDA")
