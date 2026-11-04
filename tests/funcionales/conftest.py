"""Fixtures de las pruebas funcionales: servicios con repositorios en memoria y dobles."""

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from autoaudit.dominio.cuestionario import ValidadorBloque
from autoaudit.dominio.pagos import (
    Diagnostico,
    EstadoCaracterizacion,
    Referencia,
    ReglaHabilitacion,
)
from autoaudit.dominio.puertos import Bitacora, ClientePasarela, ColaTrabajos, Notificador
from autoaudit.servicios.cuestionario import ServicioCuestionario
from autoaudit.servicios.pagos import ServicioPagos
from tests.fakes import CuestionarioEnMemoria, DiagnosticosEnMemoria, OrdenesEnMemoria
from tests.funcionales.escenario import T0, VERSION, App, D


@pytest.fixture
def app(mocker: MockerFixture) -> App:
    diagnostico = Diagnostico(VERSION.id, estado_caracterizacion=EstadoCaracterizacion.COMPLETA)
    diagnosticos = DiagnosticosEnMemoria(diagnostico)
    pasarela = mocker.create_autospec(ClientePasarela, instance=True, spec_set=True)
    pasarela.crear_cobro.return_value = Referencia("R1", "https://pasarela.test/R1")
    pasarela.verificar_firma.return_value = True
    notificador = mocker.create_autospec(Notificador, instance=True, spec_set=True)
    cola = mocker.create_autospec(ColaTrabajos, instance=True, spec_set=True)
    regla = ReglaHabilitacion()
    pagos = ServicioPagos(
        pasarela=pasarela,
        ordenes=OrdenesEnMemoria(),
        diagnosticos=diagnosticos,
        notificador=notificador,
        bitacora=mocker.create_autospec(Bitacora, instance=True, spec_set=True),
        regla=regla,
        valor_diagnostico=D("350000"),
        reloj=lambda: T0,
        esperar=mocker.Mock(),
    )
    cuestionarios = CuestionarioEnMemoria(VERSION)
    cuestionario = ServicioCuestionario(diagnosticos, cuestionarios, cola, regla, ValidadorBloque())
    return App(pagos, cuestionario, diagnostico, cuestionarios, pasarela, notificador, cola)


@pytest.fixture
def habilitada(app: App) -> App:
    """Diagnóstico pagado y caracterizado: precondición de HU-003 y HU-004."""
    assert app.pagar().habilitado
    return app


@pytest.fixture
def bitacora(mocker: MockerFixture) -> Mock:
    return mocker.create_autospec(Bitacora, instance=True, spec_set=True)
