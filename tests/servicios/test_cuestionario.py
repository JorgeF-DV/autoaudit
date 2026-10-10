"""ServicioCuestionario.guardar_bloque — Figura 5, CP-M4-08 y AC-003-4."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pytest_mock import MockerFixture

from autoaudit.dominio.cuestionario import (
    Bloque,
    Pregunta,
    TipoRespuesta,
    ValidadorBloque,
    VersionCuestionario,
)
from autoaudit.dominio.errores import TransicionInvalidaError
from autoaudit.dominio.evaluacion import TipoProceso
from autoaudit.dominio.pagos import (
    Diagnostico,
    EstadoCaracterizacion,
    EstadoDiagnostico,
    OrdenPago,
    ReglaHabilitacion,
)
from autoaudit.dominio.puertos import ColaTrabajos
from autoaudit.servicios.cuestionario import ServicioCuestionario
from tests.fakes import CuestionarioEnMemoria, DiagnosticosEnMemoria

PREGUNTA = Pregunta("horas", TipoRespuesta.NUMERO, maximo=Decimal("744"))
VERSION = VersionCuestionario(
    uuid4(), 1, tuple(Bloque(TipoProceso.RESERVAS, (PREGUNTA,)) for _ in range(3))
)


def diagnostico_habilitado(habilitado: bool = True) -> Diagnostico:
    estado = EstadoCaracterizacion.COMPLETA if habilitado else EstadoCaracterizacion.INCOMPLETA
    d = Diagnostico(VERSION.id, estado_caracterizacion=estado)
    orden = OrdenPago(d.id, Decimal("350000"), "clave", datetime.now(UTC))
    orden.aprobar()
    d.ordenes.append(orden)
    return d


@pytest.fixture
def cola(mocker: MockerFixture) -> Mock:
    return mocker.create_autospec(ColaTrabajos, instance=True, spec_set=True)


def servicio(
    diagnostico: Diagnostico, cuestionario: CuestionarioEnMemoria, cola: Mock
) -> ServicioCuestionario:
    return ServicioCuestionario(
        DiagnosticosEnMemoria(diagnostico),
        cuestionario,
        cola,
        ReglaHabilitacion(),
        ValidadorBloque(),
    )


def test_sin_habilitacion_rechaza_la_peticion(cola: Mock) -> None:
    d = diagnostico_habilitado(False)
    with pytest.raises(TransicionInvalidaError) as error:
        servicio(d, CuestionarioEnMemoria(VERSION), cola).guardar_bloque(d.id, 0, {"horas": "8"})
    assert error.value.codigo == "PREGUNTAS_NO_HABILITADAS"


def test_bloque_con_errores_guarda_lo_valido_y_no_avanza(cola: Mock) -> None:
    d, repo = diagnostico_habilitado(), CuestionarioEnMemoria(VERSION)
    resultado = servicio(d, repo, cola).guardar_bloque(d.id, 1, {"horas": "800"})
    assert resultado.siguiente_bloque == 1
    assert repo.completos == [False, False, False]
    cola.encolar.assert_not_called()


def test_cp_m4_08_reanuda_en_el_primer_bloque_incompleto(cola: Mock) -> None:
    d, repo = diagnostico_habilitado(), CuestionarioEnMemoria(VERSION)
    resultado = servicio(d, repo, cola).guardar_bloque(d.id, 1, {"horas": "8"})
    assert resultado.siguiente_bloque == 0
    cola.encolar.assert_not_called()


def test_ac_003_4_ultimo_bloque_completa_y_encola_una_vez(cola: Mock) -> None:
    d, repo = diagnostico_habilitado(), CuestionarioEnMemoria(VERSION)
    svc = servicio(d, repo, cola)
    for indice in range(3):
        resultado = svc.guardar_bloque(d.id, indice, {"horas": "8"})
    assert resultado.siguiente_bloque is None
    assert d.estado is EstadoDiagnostico.COMPLETO
    cola.encolar.assert_called_once_with(str(d.id))
