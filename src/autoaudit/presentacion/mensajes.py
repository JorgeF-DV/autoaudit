"""Lo que el usuario lee en pantalla para cada código (RTF4 v2, observaciones 2 a 4).

El `codigo` sigue en el cuerpo para el portal y las pruebas de API; el `mensaje` es lo único que
se muestra. Los textos no nombran estados internos, códigos HTTP ni excepciones:
`tests/funcionales/test_mensajes.py` falla si un código queda sin texto o si un texto los filtra.
"""

from collections.abc import Mapping
from types import MappingProxyType

GENERICO = "No pudimos completar la acción. Intenta de nuevo en unos minutos."
_PROBLEMA_INTERNO = (
    "Tuvimos un problema al preparar tu diagnóstico. Ya lo estamos revisando; intenta más tarde."
)

MENSAJES: Mapping[str, str] = MappingProxyType(
    {
        # HU-001 · Pago
        "CREADA": "Te llevamos a la pasarela para completar el pago.",
        "YA_PAGADO": "Este diagnóstico ya está pagado. No se hará un nuevo cobro.",
        "RECHAZADA_PASARELA": (
            "La entidad de pago rechazó la transacción. Revisa tus datos o usa otro medio de pago."
        ),
        "PASARELA_NO_DISPONIBLE": (
            "La pasarela de pagos no responde. No se hizo ningún cobro; intenta de nuevo en unos "
            "minutos."
        ),
        # HU-003 y HU-004 · Cuestionario
        "PREGUNTAS_NO_HABILITADAS": (
            "Las preguntas se habilitan cuando se confirme tu pago y completes la caracterización "
            "de tu negocio."
        ),
        "BLOQUE_INEXISTENTE": (
            "Ese bloque de preguntas no existe. Vuelve al cuestionario para seguir donde ibas."
        ),
        "OBLIGATORIA": "Esta pregunta es obligatoria.",
        "TIPO": "Escribe solo un número, por ejemplo 12,5.",
        "RANGO": "El valor está fuera del rango permitido para esta pregunta.",
        "SOLICITUD_INVALIDA": "Revisa los datos del formulario e inténtalo de nuevo.",
        # HU-006 y HU-007 · Análisis y ROI
        "DATOS_INCOMPLETOS": "Faltan datos de este proceso; un auditor lo revisará contigo.",
        "HORAS_NO_POSITIVAS": "Las horas al mes deben ser mayores que cero.",
        "HORAS_FUERA_DE_RANGO": (
            "Un mes tiene como máximo 744 horas. Revisa el valor que escribiste."
        ),
        "COSTO_HORA_INVALIDO": "El costo por hora debe ser mayor que cero.",
        # HU-008 · Aprobación y entrega
        "ROL_NO_AUTORIZADO": "Solo el auditor líder puede aprobar este reporte.",
        "ESTADO_INVALIDO": "Este reporte no está en revisión, así que todavía no se puede aprobar.",
        "PROCESOS_EN_REVISION_MANUAL": (
            "Hay procesos pendientes de revisión manual. Resuélvelos antes de aprobar."
        ),
        "SUPUESTOS_VACIOS": "Completa la sección de supuestos antes de aprobar el reporte.",
        "VERSION_DESACTUALIZADA": (
            "Otra persona modificó este reporte. Recarga la página para ver la versión actual."
        ),
        "TRANSICION_NO_PERMITIDA": "El reporte solo se puede entregar después de ser aprobado.",
        # Parámetros del sistema: el cliente no puede corregirlos, solo esperar.
        "BLOQUE_FUERA_DE_LIMITE": _PROBLEMA_INTERNO,
        "PESOS_INVALIDOS": _PROBLEMA_INTERNO,
        "PESOS_NO_SUMAN_UNO": _PROBLEMA_INTERNO,
        "COSTO_IMPLEMENTACION": _PROBLEMA_INTERNO,
    }
)


def mensaje(codigo: str) -> str:
    return MENSAJES.get(codigo, GENERICO)
