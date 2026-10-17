# AutoAudit — lógica de dominio y pruebas estructurales

AutoAudit diagnostica qué procesos de una PYME gastronómica o inmobiliaria conviene automatizar:
califica cada proceso, estima su ahorro y su ROI, y deja el informe listo para que un auditor
líder lo apruebe. Este repositorio contiene el incremento del sprint: los métodos críticos M1 a M5
diseñados en el **RTF3 — Diseño de Pruebas Estructurales** y sus pruebas de caja blanca.

## Estructura

```
src/autoaudit/
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
  funcionales/      caja negra del RTF4: casos CF-xxx derivados de las HU, no del código
tools/mutantes.py   prueba de mutación dirigida
```

La regla de capas (`servicios` depende de `dominio`, nunca al revés) la verifica import-linter.

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
| Solo funcionales de caja negra (RTF4) | `pytest tests/funcionales -v` |
| Reporte HTML de las funcionales | `pytest tests/funcionales --html=reportes/pruebas-funcionales.html --self-contained-html` |
| Cobertura de ramas (mínimo 85 %) | `coverage run -m pytest && coverage report` |
| Estilo y complejidad (C901 ≤ 10) | `ruff check . && ruff format --check .` |
| Tipos (modo estricto) | `mypy` |
| Regla de capas | `lint-imports` |
| Mutación dirigida | `python tools/mutantes.py` |

Estado actual: 163 pruebas (104 estructurales + 59 funcionales), 100 % de cobertura de líneas y ramas, 16/16 mutantes eliminados.

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
| HU-004 | CF-004-01 a 03 | reanudación en el primer bloque incompleto, lo válido se conserva |
| HU-006 | CF-006-01 a 03 | límites del índice 4,00/3,95/3,00/2,95, variabilidad 30/30,01, aislamiento de errores |
| HU-007 | CF-007-01 a 04 | ROI exacto, umbral 50,00/49,99, horas y costo inválidos, BAJO sin ROI |
| HU-008 | CF-008-01 a 03 | aprobación con registro, cinco guardas, no se entrega sin aprobar |

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
- Capas de presentación (FastAPI) e integración (SQLAlchemy, adaptador httpx de la pasarela con
  la prueba CP-PG-08 usando respx).
- Priorizador y generación del borrador del reporte.
