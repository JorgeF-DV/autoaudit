"""Pruebas funcionales de caja negra — RTF4, matriz de casos CF-xxx.

Cada caso sale de un criterio de aceptación de las HU del RT2, no del código: particiones de
equivalencia, valores límite y escenarios de error. Se ejercita solo la API pública de los
servicios, con repositorios en memoria y la pasarela como doble (sin red).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pytest_mock import MockerFixture

from autoaudit.dominio.cuestionario import (
    Bloque,
    CodigoError,
    Pregunta,
    TipoRespuesta,
    ValidadorBloque,
    VersionCuestionario,
)
from autoaudit.dominio.errores import (
    ConflictoVersionError,
    ErrorAutoAudit,
    PasarelaNoDisponibleError,
    PasarelaRechazoError,
    TransicionInvalidaError,
)
from autoaudit.dominio.evaluacion import (
    CalculadoraImpacto,
    EvaluadorCriterios,
    NivelAutomatizacion,
    ParametrosEvaluacion,
    ProcesoEvaluado,
    TipoProceso,
)
from autoaudit.dominio.pagos import (
    Diagnostico,
    EstadoCaracterizacion,
    EstadoDiagnostico,
    EstadoPago,
    EventoPasarela,
    Referencia,
    ReglaHabilitacion,
)
from autoaudit.dominio.puertos import Bitacora, ClientePasarela, ColaTrabajos, Notificador
from autoaudit.dominio.revision import EstadoReporte, Reporte, Rol, Usuario, validar_transicion
from autoaudit.servicios.cuestionario import ResultadoGuardado, ServicioCuestionario
from autoaudit.servicios.motor import MotorAnalisis, ResultadoProceso
from autoaudit.servicios.pagos import CodigoOrden, CodigoPago, ResultadoPago, ServicioPagos
from autoaudit.servicios.revision import ServicioRevision
from tests.fakes import (
    CuestionarioEnMemoria,
    DiagnosticosEnMemoria,
    OrdenesEnMemoria,
    ReportesEnMemoria,
)

D = Decimal
N = NivelAutomatizacion
T0 = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)
AUDITOR = Usuario(uuid4(), Rol.AUDITOR_LIDER)


def _numero(id_: str, minimo: str, maximo: str | None = None) -> Pregunta:
    return Pregunta(
        id_, TipoRespuesta.NUMERO, minimo=D(minimo), maximo=None if maximo is None else D(maximo)
    )


# Un bloque por proceso operativo (HU-003): mismas preguntas, distinto proceso.
PREGUNTAS = (
    _numero("frecuencia", "1", "5"),
    _numero("volumen_mes", "0"),
    _numero("afirmaciones_estructura", "0", "4"),
    _numero("dependencia_humana", "0", "100"),
    _numero("variabilidad", "0", "100"),
    _numero("horas_mes", "0", "744"),
    _numero("costo_hora", "0"),
    Pregunta("observaciones", TipoRespuesta.TEXTO, obligatoria=False),
)
PROCESOS = (TipoProceso.RESERVAS, TipoProceso.FACTURACION, TipoProceso.ATENCION_CLIENTE)
VERSION = VersionCuestionario(uuid4(), 1, tuple(Bloque(p, PREGUNTAS) for p in PROCESOS))

# Respuestas de un proceso muy automatizable: F=5, V=5, E=5, D=5 → índice 5.00, nivel ALTO.
RESPUESTAS_ALTO: dict[str, str | None] = {
    "frecuencia": "5",
    "volumen_mes": "600",
    "afirmaciones_estructura": "4",
    "dependencia_humana": "10",
    "variabilidad": "10",
    "horas_mes": "100",
    "costo_hora": "20000",
}


def parametros(costo_implementacion: str = "8000000") -> ParametrosEvaluacion:
    costos = {(t, n): D(costo_implementacion) for t in TipoProceso for n in (N.ALTO, N.MEDIO)}
    return ParametrosEvaluacion(costos_implementacion=costos)


def motor(costo_implementacion: str = "8000000") -> MotorAnalisis:
    p = parametros(costo_implementacion)
    return MotorAnalisis(EvaluadorCriterios(p), CalculadoraImpacto(p))


def proceso(
    frecuencia: int | None = 5,
    volumen: int = 600,
    afirmaciones: int = 4,
    dependencia: str = "10",
    variabilidad: str = "10",
    horas: str = "100",
    costo: str = "20000",
) -> ProcesoEvaluado:
    return ProcesoEvaluado(
        TipoProceso.RESERVAS,
        frecuencia,
        volumen,
        afirmaciones,
        D(dependencia),
        D(variabilidad),
        D(horas),
        D(costo),
    )


def proceso_desde(tipo: TipoProceso, valores: Mapping[str, Decimal | str]) -> ProcesoEvaluado:
    def n(clave: str) -> Decimal:
        valor = valores[clave]
        assert isinstance(valor, Decimal)
        return valor

    return ProcesoEvaluado(
        tipo,
        int(n("frecuencia")),
        int(n("volumen_mes")),
        int(n("afirmaciones_estructura")),
        n("dependencia_humana"),
        n("variabilidad"),
        n("horas_mes"),
        n("costo_hora"),
    )


def evaluar_uno(p: ProcesoEvaluado, costo_implementacion: str = "8000000") -> ResultadoProceso:
    return motor(costo_implementacion).evaluar([p])[0]


@dataclass
class App:
    pagos: ServicioPagos
    cuestionario: ServicioCuestionario
    diagnostico: Diagnostico
    cuestionarios: CuestionarioEnMemoria
    pasarela: Mock
    notificador: Mock
    cola: Mock

    def confirmar(self, estado: EstadoPago, evento_id: str = "E1") -> ResultadoPago:
        evento = EventoPasarela(evento_id, "R1", estado, motivo="FONDOS_INSUFICIENTES")
        return self.pagos.procesar_confirmacion(evento, b"{}", "firma")

    def pagar(self) -> ResultadoPago:
        assert self.pagos.crear_orden(self.diagnostico.id).codigo is CodigoOrden.CREADA
        return self.confirmar(EstadoPago.APROBADO)

    def responder(self, indice: int, respuestas: Mapping[str, str | None]) -> ResultadoGuardado:
        return self.cuestionario.guardar_bloque(self.diagnostico.id, indice, respuestas)


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


# ── Flujo completo ───────────────────────────────────────────────────────────────────────────


def test_cf_e2e_01_camino_feliz_de_la_contratacion_al_reporte_aprobado(
    app: App, bitacora: Mock
) -> None:
    assert app.pagar().habilitado

    siguientes = [app.responder(i, RESPUESTAS_ALTO).siguiente_bloque for i in range(3)]
    assert siguientes == [1, 2, None]
    assert app.diagnostico.estado is EstadoDiagnostico.COMPLETO
    app.cola.encolar.assert_called_once_with(str(app.diagnostico.id))

    procesos = [
        proceso_desde(b.proceso, app.cuestionarios.valores[i])
        for i, b in enumerate(VERSION.bloques)
    ]
    resultados = motor().evaluar(procesos)
    for r in resultados:
        assert r.evaluacion is not None and r.evaluacion.nivel is N.ALTO
        assert r.estimacion is not None and r.estimacion.recomendada

    reporte = Reporte(
        app.diagnostico.id, estado=EstadoReporte.EN_REVISION, seccion_supuestos="Datos del gerente"
    )
    revision = ServicioRevision(ReportesEnMemoria(reporte), bitacora, reloj=lambda: T0)
    aprobado = revision.aprobar(reporte.id, AUDITOR, version_esperada=1)
    assert aprobado.estado is EstadoReporte.APROBADO
    validar_transicion(aprobado.estado, EstadoReporte.ENTREGADO)  # ya se puede entregar


# ── HU-001 · Contratación y pago ─────────────────────────────────────────────────────────────


def test_cf_001_01_pago_aprobado_habilita_preguntas_y_notifica(app: App) -> None:
    resultado = app.pagar()

    assert resultado.codigo is CodigoPago.APROBADO
    assert resultado.habilitado
    assert app.diagnostico.estado is EstadoDiagnostico.PREGUNTAS_HABILITADAS
    app.notificador.encolar.assert_called_once_with("PAGO_APROBADO", app.diagnostico.id)


@pytest.mark.parametrize(
    "estado",
    [None, EstadoPago.PENDIENTE, EstadoPago.RECHAZADO],
    ids=["sin_pagar", "pendiente", "rechazado"],
)
def test_cf_001_02_sin_pago_aprobado_no_se_puede_responder(
    app: App, estado: EstadoPago | None
) -> None:
    if estado is not None:
        app.pagos.crear_orden(app.diagnostico.id)
        app.confirmar(estado)

    with pytest.raises(TransicionInvalidaError, match="PREGUNTAS_NO_HABILITADAS"):
        app.responder(0, RESPUESTAS_ALTO)


def test_cf_001_03_pago_aprobado_sin_caracterizacion_no_habilita(app: App) -> None:
    app.diagnostico.estado_caracterizacion = EstadoCaracterizacion.INCOMPLETA

    resultado = app.pagar()

    assert resultado.codigo is CodigoPago.APROBADO
    assert not resultado.habilitado


def test_cf_001_04_firma_invalida_no_cambia_la_orden(app: App) -> None:
    app.pagos.crear_orden(app.diagnostico.id)
    app.pasarela.verificar_firma.return_value = False

    assert app.confirmar(EstadoPago.APROBADO).codigo is CodigoPago.FIRMA_INVALIDA
    assert app.diagnostico.ordenes[0].estado is EstadoPago.PENDIENTE
    app.notificador.encolar.assert_not_called()


def test_cf_001_05_diagnostico_ya_pagado_no_se_cobra_dos_veces(app: App) -> None:
    app.pagar()

    assert app.pagos.crear_orden(app.diagnostico.id).codigo is CodigoOrden.YA_PAGADO


def test_cf_001_06_evento_repetido_se_procesa_una_sola_vez(app: App) -> None:
    app.pagar()

    assert app.confirmar(EstadoPago.APROBADO).codigo is CodigoPago.DUPLICADO
    app.notificador.encolar.assert_called_once()


def test_cf_001_07_pasarela_caida_agota_los_reintentos(app: App) -> None:
    app.pasarela.crear_cobro.side_effect = PasarelaNoDisponibleError("TIMEOUT")

    resultado = app.pagos.crear_orden(app.diagnostico.id)

    assert resultado.codigo is CodigoOrden.PASARELA_NO_DISPONIBLE
    assert app.pasarela.crear_cobro.call_count == 4


def test_cf_001_08_pasarela_rechaza_el_cobro(app: App) -> None:
    app.pasarela.crear_cobro.side_effect = PasarelaRechazoError("TARJETA_INVALIDA")

    resultado = app.pagos.crear_orden(app.diagnostico.id)

    assert resultado.codigo is CodigoOrden.RECHAZADA_PASARELA
    assert app.pasarela.crear_cobro.call_count == 1


# ── HU-003 · Preguntas guiadas por bloque ────────────────────────────────────────────────────


def test_cf_003_01_bloque_completo_avanza_aunque_falte_la_opcional(habilitada: App) -> None:
    resultado = habilitada.responder(0, RESPUESTAS_ALTO)

    assert resultado.validacion.puede_avanzar
    assert resultado.siguiente_bloque == 1


@pytest.mark.parametrize("vacia", ["", "   ", None], ids=["vacia", "espacios", "ausente"])
def test_cf_003_02_obligatoria_vacia_no_deja_avanzar(habilitada: App, vacia: str | None) -> None:
    resultado = habilitada.responder(0, {**RESPUESTAS_ALTO, "horas_mes": vacia})

    assert not resultado.validacion.puede_avanzar
    assert resultado.validacion.pendientes == ("horas_mes",)
    assert resultado.siguiente_bloque == 0


@pytest.mark.parametrize(
    ("pregunta", "valor", "error"),
    [
        ("horas_mes", "0", None),
        ("horas_mes", "744", None),
        ("horas_mes", "744.01", CodigoError.RANGO),
        ("horas_mes", "-1", CodigoError.RANGO),
        ("frecuencia", "1", None),
        ("frecuencia", "5", None),
        ("frecuencia", "0", CodigoError.RANGO),
        ("frecuencia", "6", CodigoError.RANGO),
        ("afirmaciones_estructura", "4", None),
        ("afirmaciones_estructura", "5", CodigoError.RANGO),
    ],
)
def test_cf_003_03_valores_limite_de_cada_pregunta(
    habilitada: App, pregunta: str, valor: str, error: CodigoError | None
) -> None:
    resultado = habilitada.responder(0, {**RESPUESTAS_ALTO, pregunta: valor})

    assert resultado.validacion.errores.get(pregunta) == error
    assert resultado.validacion.puede_avanzar is (error is None)


@pytest.mark.parametrize("valor", ["abc", "12a", "NaN", "Infinity"])
def test_cf_003_04_texto_en_pregunta_numerica_es_error_de_tipo(habilitada: App, valor: str) -> None:
    resultado = habilitada.responder(0, {**RESPUESTAS_ALTO, "horas_mes": valor})

    assert resultado.validacion.errores == {"horas_mes": CodigoError.TIPO}


def test_cf_003_05_acepta_coma_decimal(habilitada: App) -> None:
    resultado = habilitada.responder(0, {**RESPUESTAS_ALTO, "horas_mes": "12,5"})

    assert resultado.validacion.valores["horas_mes"] == D("12.5")


# ── HU-004 · Guardado y reanudación ──────────────────────────────────────────────────────────


def test_cf_004_01_reanuda_en_el_primer_bloque_incompleto(habilitada: App) -> None:
    habilitada.responder(0, RESPUESTAS_ALTO)

    assert habilitada.responder(2, RESPUESTAS_ALTO).siguiente_bloque == 1


def test_cf_004_02_conserva_lo_valido_aunque_el_bloque_no_avance(habilitada: App) -> None:
    habilitada.responder(0, {**RESPUESTAS_ALTO, "horas_mes": ""})

    guardado = habilitada.cuestionarios.valores[0]
    assert guardado["frecuencia"] == D("5")
    assert "horas_mes" not in guardado
    assert habilitada.cuestionarios.completos[0] is False


def test_cf_004_03_ultimo_bloque_completa_el_diagnostico_y_lo_encola(habilitada: App) -> None:
    for i in range(3):
        habilitada.responder(i, RESPUESTAS_ALTO)

    assert habilitada.diagnostico.estado is EstadoDiagnostico.COMPLETO
    habilitada.cola.encolar.assert_called_once_with(str(habilitada.diagnostico.id))


# ── HU-006 · Nivel de automatización ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("frecuencia", "volumen", "afirmaciones", "dependencia", "indice", "nivel"),
    [
        (4, 200, 3, "20", "4.00", N.ALTO),  # límite inferior de ALTO
        (4, 500, 3, "40", "3.95", N.MEDIO),  # justo debajo de ALTO
        (5, 500, 4, "40", "4.50", N.MEDIO),  # índice alto pero dependencia humana > 20 %
        (3, 50, 2, "40", "3.00", N.MEDIO),  # límite inferior de MEDIO
        (2, 50, 2, "20", "2.95", N.BAJO),  # justo debajo de MEDIO
    ],
)
def test_cf_006_01_valores_limite_del_indice_de_automatizacion(
    frecuencia: int,
    volumen: int,
    afirmaciones: int,
    dependencia: str,
    indice: str,
    nivel: NivelAutomatizacion,
) -> None:
    r = evaluar_uno(proceso(frecuencia, volumen, afirmaciones, dependencia))

    assert r.evaluacion is not None
    assert r.evaluacion.indice == D(indice)
    assert r.evaluacion.nivel is nivel


@pytest.mark.parametrize(("variabilidad", "nivel"), [("30", N.ALTO), ("30.01", N.NO_APTO)])
def test_cf_006_02_variabilidad_mayor_al_30_es_no_apto(
    variabilidad: str, nivel: NivelAutomatizacion
) -> None:
    r = evaluar_uno(proceso(variabilidad=variabilidad))

    assert r.evaluacion is not None and r.evaluacion.nivel is nivel


def test_cf_006_03_proceso_incompleto_va_a_revision_sin_detener_los_demas() -> None:
    incompleto, completo = proceso(frecuencia=None), proceso()

    resultados = motor().evaluar([incompleto, completo])

    assert resultados[0].motivo == "DATOS_INCOMPLETOS"
    assert incompleto.requiere_revision_manual
    assert resultados[1].evaluacion is not None and resultados[1].evaluacion.nivel is N.ALTO


# ── HU-007 · ROI por proceso ─────────────────────────────────────────────────────────────────


def test_cf_007_01_roi_con_horas_y_costo_hora_del_cliente() -> None:
    # 100 h x 70 % = 70 h/mes; 70 h x $20.000 = $1.400.000/mes; $16.800.000/año vs $8.000.000.
    e = evaluar_uno(proceso()).estimacion

    assert e is not None
    assert e.horas_ahorradas_mes == D("70.00")
    assert e.ahorro_anual == D("16800000.00")
    assert e.roi == D("110.00")
    assert e.recuperacion_meses == D("5.7")
    assert e.recomendada


@pytest.mark.parametrize(
    ("costo_implementacion", "roi", "recomendada"),
    [("11200000", "50.00", True), ("11201000", "49.99", False)],
)
def test_cf_007_02_umbral_de_recomendacion_roi_50(
    costo_implementacion: str, roi: str, recomendada: bool
) -> None:
    e = evaluar_uno(proceso(), costo_implementacion).estimacion

    assert e is not None
    assert e.roi == D(roi)
    assert e.recomendada is recomendada


@pytest.mark.parametrize(
    ("horas", "costo", "motivo"),
    [
        ("744", "20000", None),
        ("744.01", "20000", "HORAS_FUERA_DE_RANGO"),
        ("0", "20000", "HORAS_NO_POSITIVAS"),
        ("100", "0", "COSTO_HORA_INVALIDO"),
    ],
)
def test_cf_007_03_datos_economicos_invalidos_van_a_revision(
    horas: str, costo: str, motivo: str | None
) -> None:
    r = evaluar_uno(proceso(horas=horas, costo=costo))

    assert r.motivo == motivo
    assert (r.estimacion is not None) is (motivo is None)


def test_cf_007_04_proceso_no_automatizable_no_tiene_roi() -> None:
    r = evaluar_uno(proceso(frecuencia=1, volumen=5, afirmaciones=0, dependencia="100"))

    assert r.evaluacion is not None and r.evaluacion.nivel is N.BAJO
    assert r.estimacion is None


# ── HU-008 · Revisión y aprobación del reporte ───────────────────────────────────────────────


def test_cf_008_01_auditor_aprueba_y_queda_registrado(bitacora: Mock) -> None:
    repo = ReportesEnMemoria(
        Reporte(uuid4(), estado=EstadoReporte.EN_REVISION, seccion_supuestos="Supuestos")
    )

    aprobado = ServicioRevision(repo, bitacora, reloj=lambda: T0).aprobar(
        repo.reporte.id, AUDITOR, version_esperada=1
    )

    assert aprobado.estado is EstadoReporte.APROBADO
    assert (aprobado.aprobado_por, aprobado.aprobado_en) == (AUDITOR.id, T0)
    bitacora.registrar.assert_called_once()


@pytest.mark.parametrize(
    ("rol", "estado", "manual", "supuestos", "version", "error", "codigo"),
    [
        (
            Rol.CONSULTOR_JUNIOR,
            "EN_REVISION",
            False,
            "S",
            1,
            TransicionInvalidaError,
            "ROL_NO_AUTORIZADO",
        ),
        (Rol.GERENTE, "EN_REVISION", False, "S", 1, TransicionInvalidaError, "ROL_NO_AUTORIZADO"),
        (Rol.AUDITOR_LIDER, "BORRADOR", False, "S", 1, TransicionInvalidaError, "ESTADO_INVALIDO"),
        (
            Rol.AUDITOR_LIDER,
            "EN_REVISION",
            True,
            "S",
            1,
            TransicionInvalidaError,
            "PROCESOS_EN_REVISION_MANUAL",
        ),
        (
            Rol.AUDITOR_LIDER,
            "EN_REVISION",
            False,
            "  ",
            1,
            TransicionInvalidaError,
            "SUPUESTOS_VACIOS",
        ),
        (
            Rol.AUDITOR_LIDER,
            "EN_REVISION",
            False,
            "S",
            2,
            ConflictoVersionError,
            "VERSION_DESACTUALIZADA",
        ),
    ],
    ids=["consultor", "gerente", "borrador", "revision_manual", "sin_supuestos", "version_vieja"],
)
def test_cf_008_02_aprobacion_rechazada_no_cambia_el_reporte(
    bitacora: Mock,
    rol: Rol,
    estado: str,
    manual: bool,
    supuestos: str,
    version: int,
    error: type[ErrorAutoAudit],
    codigo: str,
) -> None:
    repo = ReportesEnMemoria(
        Reporte(uuid4(), estado=EstadoReporte(estado), seccion_supuestos=supuestos), manual
    )
    servicio = ServicioRevision(repo, bitacora, reloj=lambda: T0)

    with pytest.raises(error, match=codigo):
        servicio.aprobar(repo.reporte.id, Usuario(uuid4(), rol), version_esperada=version)
    assert repo.reporte.estado is EstadoReporte(estado)
    bitacora.registrar.assert_not_called()


@pytest.mark.parametrize("origen", ["BORRADOR", "EN_REVISION", "DEVUELTO"])
def test_cf_008_03_no_se_entrega_un_reporte_sin_aprobar(origen: str) -> None:
    with pytest.raises(TransicionInvalidaError, match="TRANSICION_NO_PERMITIDA"):
        validar_transicion(EstadoReporte(origen), EstadoReporte.ENTREGADO)
