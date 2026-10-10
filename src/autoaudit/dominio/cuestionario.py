"""Validación de respuestas por bloque (M4, HU-003) y punto de reanudación (HU-004)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from uuid import UUID

from autoaudit.dominio.errores import ConfiguracionInvalidaError
from autoaudit.dominio.evaluacion import TipoProceso

MAX_PREGUNTAS_POR_BLOQUE = 25


class TipoRespuesta(StrEnum):
    NUMERO = "NUMERO"
    TEXTO = "TEXTO"


class CodigoError(StrEnum):
    TIPO = "TIPO"
    RANGO = "RANGO"


@dataclass(frozen=True)
class Pregunta:
    id: str
    tipo: TipoRespuesta
    obligatoria: bool = True
    minimo: Decimal | None = None
    maximo: Decimal | None = None


@dataclass(frozen=True)
class Bloque:
    proceso: TipoProceso
    preguntas: tuple[Pregunta, ...]


@dataclass(frozen=True)
class VersionCuestionario:
    """Versión publicada e inmutable: un diagnóstico en curso la congela (HU-005)."""

    id: UUID
    numero: int
    bloques: tuple[Bloque, ...]

    def __post_init__(self) -> None:
        if any(not 1 <= len(b.preguntas) <= MAX_PREGUNTAS_POR_BLOQUE for b in self.bloques):
            raise ConfiguracionInvalidaError("BLOQUE_FUERA_DE_LIMITE")


@dataclass(frozen=True)
class ResultadoValidacion:
    puede_avanzar: bool
    pendientes: tuple[str, ...]
    errores: Mapping[str, CodigoError]
    valores: Mapping[str, Decimal | str]


class _RespuestaInvalidaError(Exception):
    def __init__(self, codigo: CodigoError) -> None:
        super().__init__(codigo)
        self.codigo = codigo


def _convertir(pregunta: Pregunta, texto: str) -> Decimal | str:
    if pregunta.tipo is TipoRespuesta.TEXTO:
        return texto
    try:
        valor = Decimal(texto.replace(",", "."))
    except InvalidOperation:
        raise _RespuestaInvalidaError(CodigoError.TIPO) from None
    if not valor.is_finite():  # Decimal acepta "NaN" e "Infinity" como texto válido
        raise _RespuestaInvalidaError(CodigoError.TIPO)
    debajo = pregunta.minimo is not None and valor < pregunta.minimo
    encima = pregunta.maximo is not None and valor > pregunta.maximo
    if debajo or encima:
        raise _RespuestaInvalidaError(CodigoError.RANGO)
    return valor


class ValidadorBloque:
    """M4. Cinco decisiones (ciclo, vacía, obligatoria, tipo/rango, salida), V(G) = 6."""

    def validar(self, bloque: Bloque, respuestas: Mapping[str, str | None]) -> ResultadoValidacion:
        pendientes: list[str] = []
        errores: dict[str, CodigoError] = {}
        valores: dict[str, Decimal | str] = {}
        # Sin break ni return dentro del ciclo: se reportan todas las fallas en una sola pasada.
        for pregunta in bloque.preguntas:  # P1
            texto = (respuestas.get(pregunta.id) or "").strip()
            if not texto:  # P2
                if pregunta.obligatoria:  # P3
                    pendientes.append(pregunta.id)
                continue
            try:
                valores[pregunta.id] = _convertir(pregunta, texto)
            except _RespuestaInvalidaError as error:  # P4
                errores[pregunta.id] = error.codigo
        return ResultadoValidacion(
            puede_avanzar=not pendientes and not errores,  # P5
            pendientes=tuple(pendientes),
            errores=errores,
            valores=valores,
        )


def punto_de_reanudacion(bloques_completos: Sequence[bool]) -> int | None:
    """Índice del primer bloque incompleto, o None si todos están completos."""
    return next((i for i, completo in enumerate(bloques_completos) if not completo), None)
