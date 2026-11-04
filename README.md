# AutoAudit — lógica de dominio y pruebas estructurales

AutoAudit diagnostica qué procesos de una PYME gastronómica o inmobiliaria conviene automatizar:
califica cada proceso, estima su ahorro y su ROI, y deja el informe listo para que un auditor
líder lo apruebe. Este repositorio contiene el incremento del sprint: los métodos críticos M1 a M5
diseñados en el **RTF3 — Diseño de Pruebas Estructurales** y sus pruebas de caja blanca.

## Estructura

```
src/autoaudit/
  presentacion/     api.py: rutas FastAPI y manejador global ESTADO_HTTP (excepción → código HTTP)
  dominio/          reglas y cálculos sin entrada/salida (no importa servicios, red ni BD)
    evaluacion.py   M1 EvaluadorCriterios.clasificar · M3 CalculadoraImpacto.estimar
    cuestionario.py M4 ValidadorBloque.validar · punto_de_reanudacion
    pagos.py        OrdenPago, Diagnostico, ReglaHabilitacion (RN001)
    revision.py     Reporte y TRANSICIONES (RN003)
    puertos.py      interfaces Protocol que los servicios reciben por constructor
    errores.py      excepciones tipificadas con `codigo`
  servicios/        casos de uso que coordinan dominio y puertos
    motor.py        ciclo del motor con aislamiento de errores por proceso
    cuestionario.py guardado de bloques y encolado del análisis
    pagos.py        M2 procesar_confirmacion · crear_orden con reintentos · conciliación
    revision.py     M5 aprobar con guarda compuesta y bitácora
tests/              espejo de src/; dobles en memoria en tests/fakes.py
  funcionales/      caja negra del RTF4: casos CF-xxx (servicios) y CF-API-xxx (HTTP con TestClient)
tools/mutantes.py   prueba de mutación dirigida
```

import-linter verifica dos contratos: las capas van `presentacion → servicios → dominio`, nunca
al revés, y ni el dominio ni los servicios importan `fastapi`, `starlette` o `pydantic`.

## Instalación

Requiere Python 3.11 o superior.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install   # ruff y mypy antes de cada commit
```

## Cómo verificar

| Qué | Comando |
|---|---|
| Pruebas (sin red: `--disable-socket`) | `pytest` |
| Solo funcionales de caja negra y API (RTF4) | `pytest tests/funcionales -v` |
| Reporte HTML de las funcionales | `pytest tests/funcionales --html=reportes/pruebas-funcionales.html --self-contained-html` |
| Cobertura de ramas (mínimo 85 %) | `coverage run -m pytest && coverage report` |
| Estilo y complejidad (C901 ≤ 10) | `ruff check . && ruff format --check .` |
| Tipos (modo estricto) | `mypy` |
| Regla de capas | `lint-imports` |
| Mutación dirigida (todos / solo módulos críticos) | `python tools/mutantes.py` · `python tools/mutantes.py M1 M3 M5` |

Estado actual: 201 pruebas (104 estructurales + 61 funcionales de servicios + 36 de API), 100 % de
cobertura de líneas y ramas, 17/17 mutantes eliminados.

En cada push y PR el CI corre estilo, tipos, capas, pruebas con cobertura y el reporte HTML. La
mutación copia el repositorio una vez por mutante, así que no bloquea los PR: corre cada noche
sobre M1, M3 y M5 y bajo demanda (*Run workflow*) sobre los módulos que se indiquen.

## Trazabilidad con el RTF3 y JIRA

Los nombres de las pruebas incluyen los códigos del RTF3 (`CP-…` caminos, `AC-…` criterios de
aceptación), así que cada fila de las tablas del documento se puede buscar en `tests/`.

| HU | Módulo | Código | Pruebas | JIRA |
|---|---|---|---|---|
| HU-006 | M1 | `dominio/evaluacion.py` · `servicios/motor.py` | CP-M1-01 a 06, AC-006-1 a 6, fronteras Tabla 15 | SCRUM-21 |
| HU-007 | M3 | `dominio/evaluacion.py` | CP-M3-01 a 07, AC-007-1 a 6, errores de la Tabla 23 | SCRUM-22 |
| HU-003 | M4 | `dominio/cuestionario.py` · `servicios/cuestionario.py` | CP-M4-01 a 09, traza Tabla 12, AC-003-1 a 4 | SCRUM-23 |
| HU-001 | M2 | `dominio/pagos.py` · `servicios/pagos.py` | CP-M2-01 a 07, CP-PG-01 a 07, AC-001-1 a 6 | SCRUM-24 |
| HU-008 | M5 | `dominio/revision.py` · `servicios/revision.py` | CP-M5-01 a 15, AC-008-1 a 5 | SCRUM-25 |

## Pruebas funcionales de caja negra (RTF4)

`tests/funcionales/test_caja_negra.py` prueba los servicios solo por su API pública. Cada caso
nace de un criterio de aceptación del RT2 y se diseña con particiones de equivalencia, valores
límite y escenarios de error. El CI publica el reporte HTML como artefacto de cada ejecución.

| HU | Casos | Qué cubren |
|---|---|---|
| Flujo completo | CF-E2E-01 | pago → bloques → análisis → ROI → aprobación |
| HU-001 | CF-001-01 a 08 | pago aprobado/pendiente/rechazado, firma inválida, doble cobro, pasarela caída |
| HU-003 | CF-003-01 a 05 | bloque completo, obligatorias vacías, límites 0/744/744,01, tipo inválido, coma decimal |
| HU-004 | CF-004-01 a 04 | reanudación en el primer bloque incompleto, lo válido se conserva, índice −1 y 3 |
| HU-006 | CF-006-01 a 03 | límites del índice 4,00/3,95/3,00/2,95, variabilidad 30/30,01, aislamiento de errores |
| HU-007 | CF-007-01 a 04 | ROI exacto, umbral 50,00/49,99, horas y costo inválidos, BAJO sin ROI |
| HU-008 | CF-008-01 a 03 | aprobación con registro, cinco guardas, no se entrega sin aprobar |

### Pruebas de API (`tests/funcionales/test_api.py`)

`presentacion/api.py` traduce cada excepción tipificada en un solo diccionario, `ESTADO_HTTP`. La
prueba `test_mapeo_cubre_todas_las_excepciones_tipificadas` compara ese diccionario con todas las
subclases de `ErrorAutoAudit`: si alguien agrega una excepción sin decidir su código HTTP, el CI
falla. Los casos CF-API repiten por HTTP los escenarios de HU-001, 003, 004 y 008 y verifican el
código de estado y el cuerpo `{"codigo": ...}`. El módulo solo permite conexiones a 127.0.0.1 (el
bucle de asyncio del `TestClient` las necesita); cualquier otro destino sigue bloqueado.

| Excepción | HTTP |
|---|---|
| `DatosInvalidosError` | 422 |
| `TransicionInvalidaError` (`ROL_NO_AUTORIZADO` → 403) | 409 |
| `ConflictoVersionError` | 409 |
| `PasarelaRechazoError` | 402 |
| `PasarelaNoDisponibleError` | 503 |
| `ConfiguracionInvalidaError` | 500 |

## Decisiones de diseño que las pruebas protegen

- **`Decimal` desde texto en todo valor que se compara con un umbral.** Con `float`, pesos de
  0,35/0,35/0,15/0,15 y puntajes (3, 3, 1, 5) suman `2.9999999999999996` y el proceso cae en BAJO
  en vez de MEDIO (`test_ac_006_5_…`).
- **El ROI se compara ya redondeado**, para que el cliente nunca vea «50,00 %» junto a «no
  recomendada».
- **Puertos inyectados por constructor.** La pasarela, la cola, la bitácora y la función `esperar`
  se reemplazan en las pruebas con `mocker.create_autospec(..., spec_set=True)`: los reintentos se
  prueban sin esperar segundos reales y ninguna prueba toca la red.
- **`try` dentro del ciclo, no alrededor.** Un proceso con datos incompletos se aísla y el resto se
  evalúa (`test_ac_006_6_…`).

## Pendiente para el siguiente sprint

- M6 `vigilarSLA` (minutos hábiles y festivos) y M7 `autorizar`.
- Capa de integración (SQLAlchemy, adaptador httpx de la pasarela con la prueba CP-PG-08 usando
  respx) y la colección de Postman ejecutada con Newman contra ese despliegue (Sprint 5).
- Autenticación real con `autorizar()` (M7): hoy el rol llega por la cabecera `X-Rol`.
- Priorizador y generación del borrador del reporte.
