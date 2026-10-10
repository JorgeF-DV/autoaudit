"""Revisión y aprobación del reporte (HU-008, RN003, RN010)."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from autoaudit.dominio.errores import ConflictoVersionError, TransicionInvalidaError
from autoaudit.dominio.puertos import Bitacora, RepositorioReportes
from autoaudit.dominio.revision import (
    EstadoReporte,
    Reporte,
    Rol,
    Usuario,
    validar_transicion,
)


class ServicioRevision:
    def __init__(
        self,
        reportes: RepositorioReportes,
        bitacora: Bitacora,
        reloj: Callable[[], datetime],
    ) -> None:
        self._reportes = reportes
        self._bitacora = bitacora
        self._reloj = reloj

    def aprobar(self, reporte_id: UUID, usuario: Usuario, version_esperada: int) -> Reporte:
        """M5. Equivale a C1 and C2 and C3 and C4 en cortocircuito, pero cada cláusula
        lanza su propio código para que la prueba MC/DC sepa qué condición falló.
        C3 es la única que consulta la base de datos, por eso va después de C1 y C2."""
        reporte = self._reportes.obtener(reporte_id)
        if usuario.rol is not Rol.AUDITOR_LIDER:  # C1
            raise TransicionInvalidaError("ROL_NO_AUTORIZADO")
        if reporte.estado is not EstadoReporte.EN_REVISION:  # C2
            raise TransicionInvalidaError("ESTADO_INVALIDO")
        if self._reportes.hay_procesos_en_revision_manual(reporte.diagnostico_id):  # C3
            raise TransicionInvalidaError("PROCESOS_EN_REVISION_MANUAL")
        if not reporte.seccion_supuestos.strip():  # C4 · RN010
            raise TransicionInvalidaError("SUPUESTOS_VACIOS")
        if reporte.version != version_esperada:  # control de concurrencia optimista
            raise ConflictoVersionError("VERSION_DESACTUALIZADA")

        ahora = self._reloj()
        self._transicionar(reporte, EstadoReporte.APROBADO, usuario, ahora)
        reporte.aprobado_por, reporte.aprobado_en = usuario.id, ahora
        self._reportes.guardar(reporte)
        return reporte

    def _transicionar(
        self, reporte: Reporte, destino: EstadoReporte, usuario: Usuario, ahora: datetime
    ) -> None:
        validar_transicion(reporte.estado, destino)
        origen = reporte.estado
        reporte.estado = destino
        reporte.version += 1
        self._bitacora.registrar(
            "TRANSICION_REPORTE",
            {
                "reporte_id": reporte.id,
                "usuario_id": usuario.id,
                "estado_origen": origen,
                "estado_destino": destino,
                "fecha": ahora,
            },
        )
