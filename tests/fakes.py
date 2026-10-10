"""Repositorios en memoria para las pruebas de servicios (sin base de datos ni red)."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from uuid import UUID

from autoaudit.dominio.cuestionario import VersionCuestionario
from autoaudit.dominio.pagos import Diagnostico, EstadoPago, OrdenPago
from autoaudit.dominio.revision import Reporte


class DiagnosticosEnMemoria:
    def __init__(self, *diagnosticos: Diagnostico) -> None:
        self.datos = {d.id: d for d in diagnosticos}

    def obtener(self, diagnostico_id: UUID) -> Diagnostico:
        return self.datos[diagnostico_id]

    def guardar(self, diagnostico: Diagnostico) -> None:
        self.datos[diagnostico.id] = diagnostico


class OrdenesEnMemoria:
    def __init__(self, *ordenes: OrdenPago) -> None:
        self.datos = {o.id: o for o in ordenes}
        self.guardados = 0

    def buscar_por_referencia(self, referencia: str) -> OrdenPago | None:
        return next((o for o in self.datos.values() if o.referencia_pasarela == referencia), None)

    def pendientes(self) -> Sequence[OrdenPago]:
        return [o for o in self.datos.values() if o.estado is EstadoPago.PENDIENTE]

    def guardar(self, orden: OrdenPago) -> None:
        self.datos[orden.id] = orden
        self.guardados += 1


class CuestionarioEnMemoria:
    def __init__(self, version: VersionCuestionario) -> None:
        self._version = version
        self.completos = [False] * len(version.bloques)
        self.valores: dict[int, Mapping[str, Decimal | str]] = {}

    def version(self, version_id: UUID) -> VersionCuestionario:
        assert version_id == self._version.id
        return self._version

    def guardar_bloque(
        self,
        diagnostico_id: UUID,
        indice: int,
        valores: Mapping[str, Decimal | str],
        completo: bool,
    ) -> None:
        self.valores[indice] = valores
        self.completos[indice] = completo

    def bloques_completos(self, diagnostico_id: UUID) -> Sequence[bool]:
        return self.completos


class ReportesEnMemoria:
    def __init__(self, reporte: Reporte, procesos_en_revision_manual: bool = False) -> None:
        self.reporte = reporte
        self.procesos_en_revision_manual = procesos_en_revision_manual
        self.consultas_procesos = 0

    def obtener(self, reporte_id: UUID) -> Reporte:
        return self.reporte

    def hay_procesos_en_revision_manual(self, diagnostico_id: UUID) -> bool:
        self.consultas_procesos += 1
        return self.procesos_en_revision_manual

    def guardar(self, reporte: Reporte) -> None:
        self.reporte = reporte
