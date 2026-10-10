"""Contratación y confirmación del pago (HU-001, RTF3 Figuras 4, 11 y 12)."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from autoaudit.dominio.errores import PasarelaNoDisponibleError, PasarelaRechazoError
from autoaudit.dominio.pagos import (
    EstadoDiagnostico,
    EstadoPago,
    EventoPasarela,
    OrdenPago,
    ReglaHabilitacion,
)
from autoaudit.dominio.puertos import (
    Bitacora,
    ClientePasarela,
    Notificador,
    RepositorioDiagnosticos,
    RepositorioOrdenes,
)

INTENTOS_COBRO = 4  # 1 intento + 3 reintentos con espera de 1, 2 y 4 segundos
CONCILIAR_DESDE = timedelta(minutes=30)
EXPIRAR_DESDE = timedelta(hours=24)


class CodigoPago(StrEnum):
    FIRMA_INVALIDA = "FIRMA_INVALIDA"
    ORDEN_HUERFANA = "ORDEN_HUERFANA"
    DUPLICADO = "DUPLICADO"
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    PENDIENTE = "PENDIENTE"


class CodigoOrden(StrEnum):
    CREADA = "CREADA"
    YA_PAGADO = "YA_PAGADO"
    RECHAZADA_PASARELA = "RECHAZADA_PASARELA"
    PASARELA_NO_DISPONIBLE = "PASARELA_NO_DISPONIBLE"


@dataclass(frozen=True)
class ResultadoPago:
    codigo: CodigoPago
    orden_id: UUID | None = None
    habilitado: bool = False


@dataclass(frozen=True)
class ResultadoOrden:
    codigo: CodigoOrden
    orden_id: UUID | None = None
    url_pago: str | None = None


class ServicioPagos:
    def __init__(
        self,
        pasarela: ClientePasarela,
        ordenes: RepositorioOrdenes,
        diagnosticos: RepositorioDiagnosticos,
        notificador: Notificador,
        bitacora: Bitacora,
        regla: ReglaHabilitacion,
        valor_diagnostico: Decimal,
        reloj: Callable[[], datetime],
        esperar: Callable[[float], None] = time.sleep,
    ) -> None:
        self._pasarela = pasarela
        self._ordenes = ordenes
        self._diagnosticos = diagnosticos
        self._notificador = notificador
        self._bitacora = bitacora
        self._regla = regla
        self._valor = valor_diagnostico
        self._reloj = reloj
        self._esperar = esperar

    def crear_orden(self, diagnostico_id: UUID) -> ResultadoOrden:
        diagnostico = self._diagnosticos.obtener(diagnostico_id)
        if diagnostico.orden_aprobada() is not None:  # RN011: pago único
            return ResultadoOrden(CodigoOrden.YA_PAGADO)

        orden = OrdenPago(diagnostico.id, self._valor, uuid4().hex, self._reloj())
        diagnostico.ordenes.append(orden)
        self._ordenes.guardar(orden)
        for intento in range(INTENTOS_COBRO):
            try:
                # La misma clave en todos los intentos evita cobros duplicados en la pasarela.
                referencia = self._pasarela.crear_cobro(orden, orden.clave_idempotencia)
            except PasarelaRechazoError:
                orden.rechazar("RECHAZADA_POR_PASARELA")
                self._ordenes.guardar(orden)
                return ResultadoOrden(CodigoOrden.RECHAZADA_PASARELA, orden.id)
            except PasarelaNoDisponibleError:
                if intento < INTENTOS_COBRO - 1:
                    self._esperar(2**intento)
                continue
            orden.referencia_pasarela = referencia.id
            self._ordenes.guardar(orden)
            return ResultadoOrden(CodigoOrden.CREADA, orden.id, referencia.url)
        return ResultadoOrden(CodigoOrden.PASARELA_NO_DISPONIBLE, orden.id)

    def procesar_confirmacion(
        self, evento: EventoPasarela, cuerpo: bytes, firma: str
    ) -> ResultadoPago:
        """M2. Seis decisiones, V(G) = 7. La firma se verifica antes de cualquier consulta."""
        if not self._pasarela.verificar_firma(cuerpo, firma):  # P1
            self._bitacora.registrar("INCIDENTE_FIRMA", {"evento": evento.id})
            return ResultadoPago(CodigoPago.FIRMA_INVALIDA)
        orden = self._ordenes.buscar_por_referencia(evento.referencia)
        if orden is None:  # P2
            self._bitacora.registrar("EVENTO_HUERFANO", {"evento": evento.id})
            return ResultadoPago(CodigoPago.ORDEN_HUERFANA)
        if evento.id in orden.eventos_procesados:  # P3
            return ResultadoPago(CodigoPago.DUPLICADO, orden.id)

        orden.eventos_procesados.add(evento.id)
        resultado = self._aplicar_estado(orden, evento.estado, evento.motivo)  # P4 a P6
        self._ordenes.guardar(orden)
        return resultado

    def conciliar_pendientes(self) -> int:
        """Consulta las órdenes sin confirmar tras 30 min y expira las que superan 24 h."""
        ahora, actualizadas = self._reloj(), 0
        for orden in self._ordenes.pendientes():
            edad = ahora - orden.creada_en
            if edad < CONCILIAR_DESDE:
                continue
            estado = EstadoPago.PENDIENTE
            if orden.referencia_pasarela is not None:
                try:
                    estado = self._pasarela.consultar_estado(orden.referencia_pasarela)
                except PasarelaNoDisponibleError:
                    continue  # se reintenta en la siguiente ejecución
            if estado is not EstadoPago.PENDIENTE:
                self._aplicar_estado(orden, estado, None)
            elif edad >= EXPIRAR_DESDE:
                orden.expirar()
            else:
                continue
            self._ordenes.guardar(orden)
            actualizadas += 1
        return actualizadas

    def _aplicar_estado(
        self, orden: OrdenPago, estado: EstadoPago, motivo: str | None
    ) -> ResultadoPago:
        if estado is EstadoPago.APROBADO:  # P4
            orden.aprobar()
            diagnostico = self._diagnosticos.obtener(orden.diagnostico_id)
            habilitado = self._regla.preguntas_habilitadas(diagnostico)
            if habilitado:  # P6
                diagnostico.estado = EstadoDiagnostico.PREGUNTAS_HABILITADAS
                self._diagnosticos.guardar(diagnostico)
            self._notificador.encolar("PAGO_APROBADO", diagnostico.id)
            return ResultadoPago(CodigoPago.APROBADO, orden.id, habilitado)
        if estado is EstadoPago.RECHAZADO:  # P5
            orden.rechazar(motivo or "RECHAZADO_POR_ENTIDAD")
            return ResultadoPago(CodigoPago.RECHAZADO, orden.id)
        return ResultadoPago(CodigoPago.PENDIENTE, orden.id)
