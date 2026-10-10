"""RN001 · ReglaHabilitacion.preguntas_habilitadas — MC/DC de dos condiciones (AC-001-3)."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from autoaudit.dominio.pagos import (
    Diagnostico,
    EstadoCaracterizacion,
    OrdenPago,
    ReglaHabilitacion,
)

COMPLETA, INCOMPLETA = EstadoCaracterizacion.COMPLETA, EstadoCaracterizacion.INCOMPLETA


def diagnostico(caracterizacion: EstadoCaracterizacion, pago_aprobado: bool) -> Diagnostico:
    d = Diagnostico(uuid4(), estado_caracterizacion=caracterizacion)
    orden = OrdenPago(d.id, Decimal("350000"), "clave", datetime.now(UTC))
    if pago_aprobado:
        orden.aprobar()
    d.ordenes.append(orden)
    return d


@pytest.mark.parametrize(
    ("caracterizacion", "pago_aprobado", "habilitado"),
    [
        pytest.param(COMPLETA, True, True, id="V-V-habilita"),
        pytest.param(INCOMPLETA, True, False, id="F-V-demuestra-caracterizacion"),
        pytest.param(COMPLETA, False, False, id="V-F-demuestra-pago"),
    ],
)
def test_mcdc_rn001(
    caracterizacion: EstadoCaracterizacion, pago_aprobado: bool, habilitado: bool
) -> None:
    regla = ReglaHabilitacion()
    assert regla.preguntas_habilitadas(diagnostico(caracterizacion, pago_aprobado)) is habilitado
