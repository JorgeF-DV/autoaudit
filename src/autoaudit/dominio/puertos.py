"""Puertos que los servicios reciben por constructor. La capa de integración los implementa;
las pruebas los reemplazan por dobles (RTF3, sección 6.1)."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from autoaudit.dominio.cuestionario import VersionCuestionario
from autoaudit.dominio.pagos import Diagnostico, EstadoPago, OrdenPago, Referencia
from autoaudit.dominio.revision import Reporte


class ClientePasarela(Protocol):
    def crear_cobro(self, orden: OrdenPago, clave_idempotencia: str) -> Referencia: ...

    def consultar_estado(self, referencia: str) -> EstadoPago: ...

    def verificar_firma(self, cuerpo: bytes, firma: str) -> bool: ...


class RepositorioDiagnosticos(Protocol):
    def obtener(self, diagnostico_id: UUID) -> Diagnostico: ...

    def guardar(self, diagnostico: Diagnostico) -> None: ...


class RepositorioOrdenes(Protocol):
    def buscar_por_referencia(self, referencia: str) -> OrdenPago | None: ...

    def pendientes(self) -> Sequence[OrdenPago]: ...

    def guardar(self, orden: OrdenPago) -> None: ...


class RepositorioCuestionario(Protocol):
    def version(self, version_id: UUID) -> VersionCuestionario: ...

    def guardar_bloque(
        self,
        diagnostico_id: UUID,
        indice: int,
        valores: Mapping[str, Decimal | str],
        completo: bool,
    ) -> None: ...

    def bloques_completos(self, diagnostico_id: UUID) -> Sequence[bool]: ...


class RepositorioReportes(Protocol):
    def obtener(self, reporte_id: UUID) -> Reporte: ...

    def hay_procesos_en_revision_manual(self, diagnostico_id: UUID) -> bool: ...

    def guardar(self, reporte: Reporte) -> None: ...


class Notificador(Protocol):
    def encolar(self, plantilla: str, diagnostico_id: UUID) -> None: ...


class ColaTrabajos(Protocol):
    def encolar(self, diagnostico_id: str) -> None: ...


class Bitacora(Protocol):
    def registrar(self, evento: str, datos: Mapping[str, object]) -> None: ...
