"""M5 · ServicioRevision.aprobar y TRANSICIONES — RTF3 Tablas 13 y 14, AC-008-1 a AC-008-5."""

from datetime import UTC, datetime
from itertools import product
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pytest_mock import MockerFixture

from autoaudit.dominio.errores import ConflictoVersionError, TransicionInvalidaError
from autoaudit.dominio.puertos import Bitacora
from autoaudit.dominio.revision import (
    TRANSICIONES,
    EstadoReporte,
    Reporte,
    Rol,
    Usuario,
    validar_transicion,
)
from autoaudit.servicios.revision import ServicioRevision
from tests.fakes import ReportesEnMemoria

AHORA = datetime(2026, 10, 10, 15, 30, tzinfo=UTC)
AUDITOR = Usuario(uuid4(), Rol.AUDITOR_LIDER)
CONSULTOR = Usuario(uuid4(), Rol.CONSULTOR_JUNIOR)
E = EstadoReporte


def reporte(estado: EstadoReporte = E.EN_REVISION, supuestos: str = "Datos declarados") -> Reporte:
    return Reporte(uuid4(), estado=estado, version=3, seccion_supuestos=supuestos)


@pytest.fixture
def bitacora(mocker: MockerFixture) -> Mock:
    return mocker.create_autospec(Bitacora, instance=True, spec_set=True)


def servicio(repo: ReportesEnMemoria, bitacora: Mock) -> ServicioRevision:
    return ServicioRevision(repo, bitacora, reloj=lambda: AHORA)


def test_cp_m5_01_ac_008_5_aprueba_y_deja_una_fila_en_bitacora(bitacora: Mock) -> None:
    repo = ReportesEnMemoria(reporte())

    aprobado = servicio(repo, bitacora).aprobar(repo.reporte.id, AUDITOR, version_esperada=3)

    assert aprobado.estado is E.APROBADO
    assert aprobado.version == 4
    assert aprobado.aprobado_por == AUDITOR.id
    bitacora.registrar.assert_called_once()
    evento, datos = bitacora.registrar.call_args.args
    assert evento == "TRANSICION_REPORTE"
    assert datos["usuario_id"] == AUDITOR.id
    assert (datos["estado_origen"], datos["estado_destino"]) == (E.EN_REVISION, E.APROBADO)
    assert datos["fecha"].tzinfo is not None


@pytest.mark.parametrize(
    ("usuario", "rep", "en_revision_manual", "codigo", "consultas_procesos"),
    [
        pytest.param(CONSULTOR, reporte(), False, "ROL_NO_AUTORIZADO", 0, id="CP-M5-02-C1"),
        pytest.param(AUDITOR, reporte(E.BORRADOR), False, "ESTADO_INVALIDO", 0, id="CP-M5-03-C2"),
        pytest.param(AUDITOR, reporte(), True, "PROCESOS_EN_REVISION_MANUAL", 1, id="CP-M5-04-C3"),
        pytest.param(
            AUDITOR, reporte(supuestos="   "), False, "SUPUESTOS_VACIOS", 1, id="CP-M5-05-C4"
        ),
    ],
)
def test_mcdc_guarda_de_aprobacion(
    bitacora: Mock,
    usuario: Usuario,
    rep: Reporte,
    en_revision_manual: bool,
    codigo: str,
    consultas_procesos: int,
) -> None:
    # AC-008-1 y AC-008-2: cada condición demuestra por sí sola que cambia el resultado,
    # y el cortocircuito evita consultar los procesos cuando C1 o C2 ya fallaron.
    repo = ReportesEnMemoria(rep, procesos_en_revision_manual=en_revision_manual)

    with pytest.raises(TransicionInvalidaError) as error:
        servicio(repo, bitacora).aprobar(rep.id, usuario, version_esperada=3)

    assert error.value.codigo == codigo
    assert repo.consultas_procesos == consultas_procesos
    assert repo.reporte.estado is rep.estado
    bitacora.registrar.assert_not_called()


def test_cp_m5_06_ac_008_3_version_desactualizada(bitacora: Mock) -> None:
    repo = ReportesEnMemoria(reporte())
    with pytest.raises(ConflictoVersionError):
        servicio(repo, bitacora).aprobar(repo.reporte.id, AUDITOR, version_esperada=2)
    assert repo.reporte.estado is E.EN_REVISION
    bitacora.registrar.assert_not_called()


@pytest.mark.parametrize(
    ("origen", "destino", "valida"),
    [
        pytest.param(E.BORRADOR, E.EN_REVISION, True, id="CP-M5-07"),
        pytest.param(E.EN_REVISION, E.EN_REVISION, True, id="CP-M5-08-edicion"),
        pytest.param(E.EN_REVISION, E.DEVUELTO, True, id="CP-M5-09a"),
        pytest.param(E.DEVUELTO, E.EN_REVISION, True, id="CP-M5-09b"),
        pytest.param(E.DEVUELTO, E.ANULADO, True, id="CP-M5-10"),
        pytest.param(E.APROBADO, E.ENTREGADO, True, id="CP-M5-11"),
        pytest.param(E.BORRADOR, E.ENTREGADO, False, id="CP-M5-12-RN003"),
        pytest.param(E.EN_REVISION, E.ENTREGADO, False, id="CP-M5-13-RN003"),
        pytest.param(E.ANULADO, E.EN_REVISION, False, id="CP-M5-14-estado-final"),
        pytest.param(E.APROBADO, E.EN_REVISION, False, id="CP-M5-15"),
    ],
)
def test_transiciones_de_la_tabla_14(
    origen: EstadoReporte, destino: EstadoReporte, valida: bool
) -> None:
    if valida:
        validar_transicion(origen, destino)
    else:
        with pytest.raises(TransicionInvalidaError):
            validar_transicion(origen, destino)


def test_ac_008_4_solo_se_aceptan_los_pares_de_transiciones() -> None:
    aceptados = set()
    for origen, destino in product(EstadoReporte, repeat=2):
        try:
            validar_transicion(origen, destino)
            aceptados.add((origen, destino))
        except TransicionInvalidaError:
            pass
    assert aceptados == {(o, d) for o, destinos in TRANSICIONES.items() for d in destinos}
    assert len(aceptados) == 7  # de los 36 pares posibles
