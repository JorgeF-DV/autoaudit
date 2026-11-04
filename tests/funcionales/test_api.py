"""Pruebas de integración de la capa HTTP — RTF4, casos CF-API y mapeo de excepciones.

Mismo enfoque de caja negra que tests/funcionales, pero por HTTP: se envía JSON y cabeceras y se
verifican el código de estado y el cuerpo. Los servicios usan los dobles en memoria de las
funcionales, así que ninguna prueba sale a la red.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from autoaudit.dominio.errores import (
    ErrorAutoAudit,
    PasarelaNoDisponibleError,
    PasarelaRechazoError,
)
from autoaudit.dominio.puertos import Bitacora
from autoaudit.dominio.revision import EstadoReporte, Reporte
from autoaudit.presentacion.api import ESTADO_HTTP, ESTADO_POR_CODIGO, crear_app
from autoaudit.servicios.revision import ServicioRevision
from tests.fakes import ReportesEnMemoria
from tests.funcionales.escenario import AUDITOR, RESPUESTAS_ALTO, T0, App

# El bucle de asyncio del TestClient abre un socketpair local; cualquier otro destino sigue
# bloqueado por pytest-socket.
pytestmark = pytest.mark.allow_hosts(["127.0.0.1"])


def _subclases(clase: type[ErrorAutoAudit]) -> set[type[ErrorAutoAudit]]:
    directas = set(clase.__subclasses__())
    return directas.union(*(_subclases(c) for c in directas))


@dataclass
class Api:
    http: TestClient
    app: App
    reporte: Reporte

    @property
    def aplicacion(self) -> FastAPI:
        assert isinstance(self.http.app, FastAPI)
        return self.http.app

    @property
    def diagnostico(self) -> str:
        return str(self.app.diagnostico.id)

    def webhook(self, cuerpo: str, firma: str = "firma") -> tuple[int, dict[str, object]]:
        r = self.http.post("/pagos/webhook", content=cuerpo, headers={"X-Firma": firma})
        return r.status_code, r.json()

    def pagar(self) -> None:
        assert self.http.post(f"/diagnosticos/{self.diagnostico}/orden").status_code == 201
        assert self.webhook(EVENTO_APROBADO)[0] == 200

    def bloque(self, indice: object, respuestas: object) -> tuple[int, dict[str, object]]:
        r = self.http.put(
            f"/diagnosticos/{self.diagnostico}/bloques/{indice}", json={"respuestas": respuestas}
        )
        return r.status_code, r.json()

    def aprobar(self, rol: str, version: int = 1) -> tuple[int, dict[str, object]]:
        r = self.http.post(
            f"/reportes/{self.reporte.id}/aprobacion",
            json={"version_esperada": version},
            headers={"X-Usuario-Id": str(AUDITOR.id), "X-Rol": rol},
        )
        return r.status_code, r.json()


EVENTO_APROBADO = '{"id": "E1", "referencia": "R1", "estado": "APROBADO"}'


@pytest.fixture
def api(app: App, mocker: MockerFixture) -> Iterator[Api]:
    reporte = Reporte(
        app.diagnostico.id, estado=EstadoReporte.EN_REVISION, seccion_supuestos="Datos del gerente"
    )
    bitacora = mocker.create_autospec(Bitacora, instance=True, spec_set=True)
    revision = ServicioRevision(ReportesEnMemoria(reporte), bitacora, reloj=lambda: T0)
    with TestClient(crear_app(app.pagos, app.cuestionario, revision)) as http:
        yield Api(http, app, reporte)


# ── Mapeo de excepciones tipificadas a HTTP (manejador global) ─────────────────────────────────


def test_mapeo_cubre_todas_las_excepciones_tipificadas() -> None:
    """Una excepción nueva sin estado HTTP rompe esta prueba antes de llegar a producción."""
    assert set(ESTADO_HTTP) == _subclases(ErrorAutoAudit)


CASOS_MAPEO = [(c, "CODIGO_DE_PRUEBA", e) for c, e in ESTADO_HTTP.items()] + [
    (c, codigo, e) for codigo, e in ESTADO_POR_CODIGO.items() for c in _subclases(ErrorAutoAudit)
]


@pytest.mark.parametrize(
    ("clase", "codigo", "estado"),
    CASOS_MAPEO,
    ids=[f"{c.__name__}-{codigo}" for c, codigo, _ in CASOS_MAPEO],
)
def test_manejador_global_traduce_cada_excepcion(
    api: Api, clase: type[ErrorAutoAudit], codigo: str, estado: int
) -> None:
    def falla() -> None:
        raise clase(codigo)

    api.aplicacion.add_api_route("/falla", falla)
    respuesta = api.http.get("/falla")

    assert (respuesta.status_code, respuesta.json()) == (estado, {"codigo": codigo})


# ── HU-001 · Orden de pago y webhook ─────────────────────────────────────────────────────────


def test_cf_api_001_01_crear_orden_devuelve_201_con_la_url_de_pago(api: Api) -> None:
    r = api.http.post(f"/diagnosticos/{api.diagnostico}/orden")

    assert r.status_code == 201
    assert r.json()["url_pago"] == "https://pasarela.test/R1"


def test_cf_api_001_02_webhook_aprobado_habilita_y_repetido_no_reprocesa(api: Api) -> None:
    api.http.post(f"/diagnosticos/{api.diagnostico}/orden")

    assert api.webhook(EVENTO_APROBADO) == (200, {"codigo": "APROBADO", "habilitado": True})
    assert api.webhook(EVENTO_APROBADO) == (200, {"codigo": "DUPLICADO", "habilitado": False})


def test_cf_api_001_03_segunda_orden_de_un_diagnostico_pagado_es_409(api: Api) -> None:
    api.pagar()

    r = api.http.post(f"/diagnosticos/{api.diagnostico}/orden")

    assert (r.status_code, r.json()["codigo"]) == (409, "YA_PAGADO")


@pytest.mark.parametrize(
    ("falla", "estado", "codigo"),
    [
        (PasarelaNoDisponibleError("TIMEOUT"), 503, "PASARELA_NO_DISPONIBLE"),
        (PasarelaRechazoError("TARJETA_INVALIDA"), 402, "RECHAZADA_PASARELA"),
    ],
    ids=["caida", "rechazo"],
)
def test_cf_api_001_04_fallas_de_la_pasarela(
    api: Api, falla: ErrorAutoAudit, estado: int, codigo: str
) -> None:
    api.app.pasarela.crear_cobro.side_effect = falla

    r = api.http.post(f"/diagnosticos/{api.diagnostico}/orden")

    assert (r.status_code, r.json()["codigo"]) == (estado, codigo)


def test_cf_api_001_05_webhook_con_firma_invalida_es_401(api: Api) -> None:
    api.http.post(f"/diagnosticos/{api.diagnostico}/orden")
    api.app.pasarela.verificar_firma.return_value = False

    assert api.webhook(EVENTO_APROBADO)[0] == 401
    api.app.notificador.encolar.assert_not_called()


def test_cf_api_001_06_webhook_de_una_orden_desconocida_es_404(api: Api) -> None:
    cuerpo = '{"id": "E9", "referencia": "NO_EXISTE", "estado": "APROBADO"}'

    assert api.webhook(cuerpo) == (404, {"codigo": "ORDEN_HUERFANA", "habilitado": False})


@pytest.mark.parametrize(
    "cuerpo",
    [
        "no es json",
        '{"id": "E1", "referencia": "R1"}',
        '{"id": "E1", "referencia": "R1", "estado": "X"}',
    ],
    ids=["no_json", "sin_estado", "estado_desconocido"],
)
def test_cf_api_001_07_webhook_mal_formado_es_422(api: Api, cuerpo: str) -> None:
    estado, respuesta = api.webhook(cuerpo)

    assert (estado, respuesta["codigo"]) == (422, "SOLICITUD_INVALIDA")


def test_cf_api_001_08_webhook_sin_cabecera_de_firma_es_422(api: Api) -> None:
    r = api.http.post("/pagos/webhook", content=EVENTO_APROBADO)

    assert r.status_code == 422
    assert r.json() == {"codigo": "SOLICITUD_INVALIDA", "campos": ["header.x-firma"]}


# ── HU-003 y HU-004 · Bloques de preguntas ───────────────────────────────────────────────────


def test_cf_api_003_01_bloque_sin_pago_es_409(api: Api) -> None:
    assert api.bloque(0, RESPUESTAS_ALTO) == (409, {"codigo": "PREGUNTAS_NO_HABILITADAS"})


def test_cf_api_003_02_bloque_valido_avanza(api: Api) -> None:
    api.pagar()

    estado, cuerpo = api.bloque(0, RESPUESTAS_ALTO)

    assert (estado, cuerpo["puede_avanzar"], cuerpo["siguiente_bloque"]) == (200, True, 1)


def test_cf_api_003_03_bloque_con_obligatoria_vacia_y_rango_es_422(api: Api) -> None:
    api.pagar()

    estado, cuerpo = api.bloque(0, {**RESPUESTAS_ALTO, "horas_mes": "", "frecuencia": "6"})

    assert estado == 422
    assert (cuerpo["pendientes"], cuerpo["errores"]) == (["horas_mes"], {"frecuencia": "RANGO"})


@pytest.mark.parametrize("indice", [-1, 3], ids=["menos_uno", "uno_despues_del_ultimo"])
def test_cf_api_004_01_indice_fuera_de_rango_es_422(api: Api, indice: int) -> None:
    api.pagar()

    assert api.bloque(indice, RESPUESTAS_ALTO) == (422, {"codigo": "BLOQUE_INEXISTENTE"})


@pytest.mark.parametrize(
    ("indice", "respuestas", "campo"),
    [("uno", RESPUESTAS_ALTO, "path.indice"), (0, ["5"], "body.respuestas")],
    ids=["indice_texto", "respuestas_lista"],
)
def test_cf_api_004_02_forma_invalida_es_422_con_el_campo(
    api: Api, indice: object, respuestas: object, campo: str
) -> None:
    api.pagar()

    estado, cuerpo = api.bloque(indice, respuestas)

    assert (estado, cuerpo["codigo"], cuerpo["campos"]) == (422, "SOLICITUD_INVALIDA", [campo])


# ── HU-008 · Aprobación del reporte ──────────────────────────────────────────────────────────


def test_cf_api_008_01_auditor_lider_aprueba(api: Api) -> None:
    estado, cuerpo = api.aprobar("AUDITOR_LIDER")

    assert (estado, cuerpo["estado"], cuerpo["version"]) == (200, "APROBADO", 2)
    assert cuerpo["aprobado_en"] == T0.isoformat()


@pytest.mark.parametrize(
    ("rol", "version", "estado", "codigo"),
    [
        ("CONSULTOR_JUNIOR", 1, 403, "ROL_NO_AUTORIZADO"),
        ("GERENTE", 1, 403, "ROL_NO_AUTORIZADO"),
        ("AUDITOR_LIDER", 2, 409, "VERSION_DESACTUALIZADA"),
    ],
    ids=["consultor", "gerente", "version_vieja"],
)
def test_cf_api_008_02_aprobacion_rechazada(
    api: Api, rol: str, version: int, estado: int, codigo: str
) -> None:
    assert api.aprobar(rol, version) == (estado, {"codigo": codigo})
    assert api.reporte.estado is EstadoReporte.EN_REVISION


def test_cf_api_008_03_rol_inexistente_es_422(api: Api) -> None:
    estado, cuerpo = api.aprobar("ADMIN")

    assert (estado, cuerpo["campos"]) == (422, ["header.x-rol"])
