"""ServicioPagos con dobles de pytest-mock — RTF3 Tablas 8 y 21, AC-001-1 a AC-001-6.

La pasarela, el notificador, la bitácora y `esperar` son dobles: ninguna prueba toca la red
(pytest corre con --disable-socket) ni espera segundos reales entre reintentos.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, call
from uuid import uuid4

import pytest
from pytest_mock import MockerFixture

from autoaudit.dominio.errores import PasarelaNoDisponibleError, PasarelaRechazoError
from autoaudit.dominio.pagos import (
    Diagnostico,
    EstadoCaracterizacion,
    EstadoDiagnostico,
    EstadoPago,
    EventoPasarela,
    OrdenPago,
    Referencia,
    ReglaHabilitacion,
)
from autoaudit.dominio.puertos import Bitacora, ClientePasarela, Notificador
from autoaudit.servicios.pagos import CodigoOrden, CodigoPago, ResultadoPago, ServicioPagos
from tests.fakes import DiagnosticosEnMemoria, OrdenesEnMemoria

T0 = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


@dataclass
class Escenario:
    servicio: ServicioPagos
    pasarela: Mock
    notificador: Mock
    bitacora: Mock
    esperar: Mock
    diagnostico: Diagnostico
    orden: OrdenPago
    ordenes: OrdenesEnMemoria
    reloj: list[datetime] = field(default_factory=lambda: [T0])


@pytest.fixture
def escenario(mocker: MockerFixture) -> Escenario:
    diagnostico = Diagnostico(uuid4(), estado_caracterizacion=EstadoCaracterizacion.COMPLETA)
    orden = OrdenPago(diagnostico.id, Decimal("350000"), "clave-1", T0, referencia_pasarela="R1")
    diagnostico.ordenes.append(orden)
    pasarela = mocker.create_autospec(ClientePasarela, instance=True, spec_set=True)
    pasarela.verificar_firma.return_value = True
    notificador = mocker.create_autospec(Notificador, instance=True, spec_set=True)
    bitacora = mocker.create_autospec(Bitacora, instance=True, spec_set=True)
    esperar = mocker.Mock()
    ordenes = OrdenesEnMemoria(orden)
    reloj = [T0]
    servicio = ServicioPagos(
        pasarela=pasarela,
        ordenes=ordenes,
        diagnosticos=DiagnosticosEnMemoria(diagnostico),
        notificador=notificador,
        bitacora=bitacora,
        regla=ReglaHabilitacion(),
        valor_diagnostico=Decimal("350000"),
        reloj=lambda: reloj[0],
        esperar=esperar,
    )
    return Escenario(
        servicio, pasarela, notificador, bitacora, esperar, diagnostico, orden, ordenes, reloj
    )


def evento(estado: EstadoPago, id_: str = "E1", referencia: str = "R1") -> EventoPasarela:
    return EventoPasarela(id_, referencia, estado, motivo="FONDOS_INSUFICIENTES")


def confirmar(e: Escenario, ev: EventoPasarela) -> ResultadoPago:
    return e.servicio.procesar_confirmacion(ev, b'{"evento": "..."}', "firma")


# --- M2: procesar_confirmacion (Tabla 8) -------------------------------------------------


def test_cp_m2_01_ac_001_1_firma_invalida(escenario: Escenario, mocker: MockerFixture) -> None:
    escenario.pasarela.verificar_firma.return_value = False
    buscar = mocker.spy(escenario.ordenes, "buscar_por_referencia")

    resultado = confirmar(escenario, evento(EstadoPago.APROBADO))

    assert resultado.codigo is CodigoPago.FIRMA_INVALIDA
    buscar.assert_not_called()
    assert escenario.ordenes.guardados == 0
    assert escenario.orden.estado is EstadoPago.PENDIENTE
    escenario.bitacora.registrar.assert_called_once_with("INCIDENTE_FIRMA", {"evento": "E1"})


def test_cp_m2_02_orden_huerfana(escenario: Escenario) -> None:
    resultado = confirmar(escenario, evento(EstadoPago.APROBADO, referencia="NO-EXISTE"))
    assert resultado.codigo is CodigoPago.ORDEN_HUERFANA
    escenario.bitacora.registrar.assert_called_once_with("EVENTO_HUERFANO", {"evento": "E1"})


def test_cp_m2_03_ac_001_2_evento_duplicado_no_tiene_doble_efecto(escenario: Escenario) -> None:
    primero = confirmar(escenario, evento(EstadoPago.APROBADO))
    segundo = confirmar(escenario, evento(EstadoPago.APROBADO))

    assert primero.codigo is CodigoPago.APROBADO
    assert segundo.codigo is CodigoPago.DUPLICADO
    escenario.notificador.encolar.assert_called_once()
    assert escenario.orden.eventos_procesados == {"E1"}


def test_cp_m2_04_aprobado_con_caracterizacion_completa_habilita(escenario: Escenario) -> None:
    resultado = confirmar(escenario, evento(EstadoPago.APROBADO))

    assert resultado.codigo is CodigoPago.APROBADO
    assert resultado.habilitado is True
    assert escenario.orden.estado is EstadoPago.APROBADO
    assert escenario.diagnostico.estado is EstadoDiagnostico.PREGUNTAS_HABILITADAS


def test_cp_m2_05_aprobado_con_caracterizacion_incompleta_no_habilita(
    escenario: Escenario,
) -> None:
    escenario.diagnostico.estado_caracterizacion = EstadoCaracterizacion.INCOMPLETA

    resultado = confirmar(escenario, evento(EstadoPago.APROBADO))

    assert resultado.habilitado is False
    assert escenario.orden.estado is EstadoPago.APROBADO
    assert escenario.diagnostico.estado is EstadoDiagnostico.CREADO


def test_cp_m2_06_rechazado_permite_crear_otra_orden(escenario: Escenario) -> None:
    resultado = confirmar(escenario, evento(EstadoPago.RECHAZADO))

    assert resultado.codigo is CodigoPago.RECHAZADO
    assert escenario.orden.motivo_rechazo == "FONDOS_INSUFICIENTES"
    assert escenario.diagnostico.orden_aprobada() is None


def test_cp_m2_07_pendiente_queda_para_conciliar(escenario: Escenario) -> None:
    resultado = confirmar(escenario, evento(EstadoPago.PENDIENTE))
    assert resultado.codigo is CodigoPago.PENDIENTE
    assert escenario.orden.estado is EstadoPago.PENDIENTE


# --- crear_orden con la pasarela simulada (Tabla 21, Figura 12) ---------------------------


def test_cp_pg_01_ac_001_4_pasarela_caida(escenario: Escenario) -> None:
    escenario.pasarela.crear_cobro.side_effect = PasarelaNoDisponibleError("TIMEOUT")
    escenario.diagnostico.ordenes.clear()

    resultado = escenario.servicio.crear_orden(escenario.diagnostico.id)

    assert resultado.codigo is CodigoOrden.PASARELA_NO_DISPONIBLE
    assert escenario.pasarela.crear_cobro.call_count == 4
    assert escenario.esperar.call_args_list == [call(1), call(2), call(4)]
    assert escenario.diagnostico.ordenes[0].estado is EstadoPago.PENDIENTE


def test_cp_pg_02_falla_transitoria(escenario: Escenario) -> None:
    escenario.pasarela.crear_cobro.side_effect = [
        PasarelaNoDisponibleError("TIMEOUT"),
        PasarelaNoDisponibleError("TIMEOUT"),
        Referencia("R9", "https://pasarela.example/pagar/R9"),
    ]
    escenario.diagnostico.ordenes.clear()

    resultado = escenario.servicio.crear_orden(escenario.diagnostico.id)

    assert resultado.codigo is CodigoOrden.CREADA
    assert resultado.url_pago == "https://pasarela.example/pagar/R9"
    assert escenario.pasarela.crear_cobro.call_count == 3
    assert escenario.esperar.call_args_list == [call(1), call(2)]
    assert escenario.diagnostico.ordenes[0].referencia_pasarela == "R9"


def test_cp_pg_03_rechazo_no_se_reintenta(escenario: Escenario) -> None:
    escenario.pasarela.crear_cobro.side_effect = PasarelaRechazoError("422")
    escenario.diagnostico.ordenes.clear()

    resultado = escenario.servicio.crear_orden(escenario.diagnostico.id)

    assert resultado.codigo is CodigoOrden.RECHAZADA_PASARELA
    assert escenario.pasarela.crear_cobro.call_count == 1
    escenario.esperar.assert_not_called()


def test_cp_pg_04_misma_clave_de_idempotencia_en_todos_los_intentos(
    escenario: Escenario,
) -> None:
    escenario.pasarela.crear_cobro.side_effect = PasarelaNoDisponibleError("TIMEOUT")
    escenario.diagnostico.ordenes.clear()

    escenario.servicio.crear_orden(escenario.diagnostico.id)

    claves = {c.args[1] for c in escenario.pasarela.crear_cobro.call_args_list}
    assert claves == {escenario.diagnostico.ordenes[0].clave_idempotencia}


def test_ac_001_5_diagnostico_ya_pagado_no_crea_cobro(escenario: Escenario) -> None:
    escenario.orden.aprobar()

    resultado = escenario.servicio.crear_orden(escenario.diagnostico.id)

    assert resultado.codigo is CodigoOrden.YA_PAGADO
    escenario.pasarela.crear_cobro.assert_not_called()


# --- conciliar_pendientes con reloj controlado -------------------------------------------


@pytest.mark.parametrize(
    ("transcurrido", "estado_final", "actualizadas"),
    [
        pytest.param(timedelta(minutes=29), EstadoPago.PENDIENTE, 0, id="29-min-espera"),
        pytest.param(timedelta(hours=23, minutes=59), EstadoPago.PENDIENTE, 0, id="23h59-vigente"),
        pytest.param(timedelta(hours=24), EstadoPago.EXPIRADA, 1, id="AC-001-6-24h-expira"),
    ],
)
def test_conciliacion_y_expiracion(
    escenario: Escenario, transcurrido: timedelta, estado_final: EstadoPago, actualizadas: int
) -> None:
    escenario.pasarela.consultar_estado.return_value = EstadoPago.PENDIENTE
    escenario.reloj[0] = T0 + transcurrido

    assert escenario.servicio.conciliar_pendientes() == actualizadas
    assert escenario.orden.estado is estado_final


def test_cp_pg_06_confirmacion_tardia(escenario: Escenario) -> None:
    escenario.pasarela.consultar_estado.side_effect = [EstadoPago.PENDIENTE, EstadoPago.APROBADO]

    escenario.reloj[0] = T0 + timedelta(minutes=30)
    assert escenario.servicio.conciliar_pendientes() == 0
    escenario.reloj[0] = T0 + timedelta(minutes=35)
    assert escenario.servicio.conciliar_pendientes() == 1

    assert escenario.orden.estado is EstadoPago.APROBADO
    assert escenario.diagnostico.estado is EstadoDiagnostico.PREGUNTAS_HABILITADAS


def test_cp_pg_07_pasarela_caida_durante_la_conciliacion(escenario: Escenario) -> None:
    escenario.pasarela.consultar_estado.side_effect = PasarelaNoDisponibleError("TIMEOUT")
    escenario.reloj[0] = T0 + timedelta(hours=25)

    assert escenario.servicio.conciliar_pendientes() == 0
    assert escenario.orden.estado is EstadoPago.PENDIENTE


def test_orden_sin_referencia_expira_sin_consultar_la_pasarela(escenario: Escenario) -> None:
    escenario.orden.referencia_pasarela = None
    escenario.reloj[0] = T0 + timedelta(hours=24)

    assert escenario.servicio.conciliar_pendientes() == 1
    assert escenario.orden.estado is EstadoPago.EXPIRADA
    escenario.pasarela.consultar_estado.assert_not_called()
