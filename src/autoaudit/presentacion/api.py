"""API FastAPI de AutoAudit (HU-001, HU-003, HU-004 y HU-008).

Los servicios llegan por `crear_app`, así que las pruebas usan los mismos dobles en memoria que
las funcionales. Toda excepción tipificada se traduce en un solo lugar (`ESTADO_HTTP`);
`tests/presentacion/test_api.py` falla si una subclase de `ErrorAutoAudit` queda sin mapear.
"""

from collections.abc import Mapping
from types import MappingProxyType
from uuid import UUID

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from autoaudit.dominio.errores import (
    ConfiguracionInvalidaError,
    ConflictoVersionError,
    DatosInvalidosError,
    ErrorAutoAudit,
    PasarelaNoDisponibleError,
    PasarelaRechazoError,
    TransicionInvalidaError,
)
from autoaudit.dominio.pagos import EstadoPago, EventoPasarela
from autoaudit.dominio.revision import Rol, Usuario
from autoaudit.servicios.cuestionario import ServicioCuestionario
from autoaudit.servicios.pagos import CodigoOrden, CodigoPago, ServicioPagos
from autoaudit.servicios.revision import ServicioRevision

ESTADO_HTTP: Mapping[type[ErrorAutoAudit], int] = MappingProxyType(
    {
        DatosInvalidosError: 422,
        TransicionInvalidaError: 409,
        ConflictoVersionError: 409,
        PasarelaRechazoError: 402,
        PasarelaNoDisponibleError: 503,
        ConfiguracionInvalidaError: 500,
    }
)
# Un código que pide un estado distinto al de su clase: el rol es autorización, no transición.
ESTADO_POR_CODIGO: Mapping[str, int] = MappingProxyType({"ROL_NO_AUTORIZADO": 403})

ESTADO_ORDEN: Mapping[CodigoOrden, int] = MappingProxyType(
    {
        CodigoOrden.CREADA: 201,
        CodigoOrden.YA_PAGADO: 409,
        CodigoOrden.RECHAZADA_PASARELA: 402,
        CodigoOrden.PASARELA_NO_DISPONIBLE: 503,
    }
)
ESTADO_WEBHOOK: Mapping[CodigoPago, int] = MappingProxyType(
    {CodigoPago.FIRMA_INVALIDA: 401, CodigoPago.ORDEN_HUERFANA: 404}
)  # los demás códigos son 200: la pasarela no debe reintentar un evento ya recibido


def estado_http(error: ErrorAutoAudit) -> int:
    return ESTADO_POR_CODIGO.get(error.codigo) or ESTADO_HTTP[type(error)]


class EventoEntrada(BaseModel):
    id: str
    referencia: str
    estado: EstadoPago
    motivo: str | None = None


class BloqueEntrada(BaseModel):
    respuestas: dict[str, str | None]


class AprobacionEntrada(BaseModel):
    version_esperada: int


def crear_app(
    pagos: ServicioPagos, cuestionario: ServicioCuestionario, revision: ServicioRevision
) -> FastAPI:
    app = FastAPI(title="AutoAudit")

    @app.exception_handler(ErrorAutoAudit)
    async def _error_tipificado(_: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, ErrorAutoAudit)  # noqa: S101 - FastAPI tipa el manejador así
        return JSONResponse({"codigo": error.codigo}, estado_http(error))

    @app.exception_handler(RequestValidationError)
    async def _solicitud_invalida(_: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, RequestValidationError)  # noqa: S101
        campos = [".".join(str(parte) for parte in e["loc"]) for e in error.errors()]
        return JSONResponse({"codigo": "SOLICITUD_INVALIDA", "campos": campos}, 422)

    @app.post("/diagnosticos/{diagnostico_id}/orden")
    def crear_orden(diagnostico_id: UUID) -> JSONResponse:
        r = pagos.crear_orden(diagnostico_id)
        orden_id = None if r.orden_id is None else str(r.orden_id)
        cuerpo = {"codigo": r.codigo, "orden_id": orden_id, "url_pago": r.url_pago}
        return JSONResponse(cuerpo, ESTADO_ORDEN[r.codigo])

    @app.post("/pagos/webhook")
    async def webhook(request: Request, x_firma: str = Header()) -> JSONResponse:
        cuerpo = await request.body()  # la firma se calcula sobre los bytes, no sobre el JSON
        try:
            e = EventoEntrada.model_validate_json(cuerpo)
        except ValidationError as error:
            raise RequestValidationError(error.errors()) from None
        evento = EventoPasarela(e.id, e.referencia, e.estado, e.motivo)
        r = pagos.procesar_confirmacion(evento, cuerpo, x_firma)
        return JSONResponse(
            {"codigo": r.codigo, "habilitado": r.habilitado}, ESTADO_WEBHOOK.get(r.codigo, 200)
        )

    @app.put("/diagnosticos/{diagnostico_id}/bloques/{indice}")
    def guardar_bloque(diagnostico_id: UUID, indice: int, entrada: BloqueEntrada) -> JSONResponse:
        r = cuestionario.guardar_bloque(diagnostico_id, indice, entrada.respuestas)
        v = r.validacion
        cuerpo = {
            "puede_avanzar": v.puede_avanzar,
            "pendientes": list(v.pendientes),
            "errores": dict(v.errores),
            "siguiente_bloque": r.siguiente_bloque,
        }
        return JSONResponse(cuerpo, 200 if v.puede_avanzar else 422)

    @app.post("/reportes/{reporte_id}/aprobacion")
    def aprobar(
        reporte_id: UUID,
        entrada: AprobacionEntrada,
        # ponytail: identidad por cabeceras hasta que exista autorizar() (M7, Sprint 5).
        x_usuario_id: UUID = Header(),
        x_rol: Rol = Header(),
    ) -> JSONResponse:
        reporte = revision.aprobar(
            reporte_id, Usuario(x_usuario_id, x_rol), entrada.version_esperada
        )
        aprobado_en = None if reporte.aprobado_en is None else reporte.aprobado_en.isoformat()
        cuerpo = {"estado": reporte.estado, "version": reporte.version, "aprobado_en": aprobado_en}
        return JSONResponse(cuerpo, 200)

    return app
