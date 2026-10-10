"""Jerarquía de excepciones tipificadas (RTF3, Tabla 3). Cada una lleva un `codigo` estable."""


class ErrorAutoAudit(Exception):  # noqa: N818 - nombre fijado en el diseño (RTF3, Figura 3)
    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


class DatosInvalidosError(ErrorAutoAudit):
    """Datos del cliente incompletos o fuera de rango: el proceso pasa a revisión manual."""


class ConfiguracionInvalidaError(ErrorAutoAudit):
    """Parámetro mal cargado: afecta a todos los procesos, no se captura en el motor."""


class TransicionInvalidaError(ErrorAutoAudit):
    """Transición de estado no permitida o guarda de aprobación incumplida."""


class ConflictoVersionError(ErrorAutoAudit):
    """Otro usuario modificó el reporte (control de concurrencia optimista)."""


class PasarelaNoDisponibleError(ErrorAutoAudit):
    """Tiempo de espera o fallo de conexión con la pasarela: se reintenta."""


class PasarelaRechazoError(ErrorAutoAudit):
    """La pasarela rechazó el cobro (respuesta 4xx): no se reintenta."""
