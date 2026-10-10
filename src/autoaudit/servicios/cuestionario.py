"""Guardado de un bloque de respuestas y reanudación (RTF3, Figura 5)."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from autoaudit.dominio.cuestionario import (
    ResultadoValidacion,
    ValidadorBloque,
    punto_de_reanudacion,
)
from autoaudit.dominio.errores import TransicionInvalidaError
from autoaudit.dominio.pagos import EstadoDiagnostico, ReglaHabilitacion
from autoaudit.dominio.puertos import ColaTrabajos, RepositorioCuestionario, RepositorioDiagnosticos


@dataclass(frozen=True)
class ResultadoGuardado:
    validacion: ResultadoValidacion
    siguiente_bloque: int | None


class ServicioCuestionario:
    def __init__(
        self,
        diagnosticos: RepositorioDiagnosticos,
        cuestionarios: RepositorioCuestionario,
        cola: ColaTrabajos,
        regla: ReglaHabilitacion,
        validador: ValidadorBloque,
    ) -> None:
        self._diagnosticos = diagnosticos
        self._cuestionarios = cuestionarios
        self._cola = cola
        self._regla = regla
        self._validador = validador

    def guardar_bloque(
        self, diagnostico_id: UUID, indice: int, respuestas: Mapping[str, str | None]
    ) -> ResultadoGuardado:
        diagnostico = self._diagnosticos.obtener(diagnostico_id)
        # Defensa ante una petición directa a la API que se salte el portal.
        if not self._regla.preguntas_habilitadas(diagnostico):
            raise TransicionInvalidaError("PREGUNTAS_NO_HABILITADAS")

        version = self._cuestionarios.version(diagnostico.version_cuestionario_id)
        validacion = self._validador.validar(version.bloques[indice], respuestas)
        # Lo válido se guarda aunque el bloque no avance (RNF-06).
        self._cuestionarios.guardar_bloque(
            diagnostico.id, indice, validacion.valores, validacion.puede_avanzar
        )
        if not validacion.puede_avanzar:
            return ResultadoGuardado(validacion, indice)

        siguiente = punto_de_reanudacion(self._cuestionarios.bloques_completos(diagnostico.id))
        if siguiente is None:
            diagnostico.estado = EstadoDiagnostico.COMPLETO
            self._diagnosticos.guardar(diagnostico)
            self._cola.encolar(str(diagnostico.id))
        return ResultadoGuardado(validacion, siguiente)
