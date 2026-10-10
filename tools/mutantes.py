"""Prueba de mutación dirigida: introduce errores realistas y verifica que alguna prueba falle.

Complementa a mutmut (que no corre en Windows). Cada mutante es un error que el RTF3 señala
como probable: comparaciones de frontera, la doble anualización y el factor equivocado de la
Tabla 23, un `break` en el ciclo de M4, la pérdida de idempotencia, etc.

Uso, desde la raíz del repositorio:  python tools/mutantes.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

MUTANTES = [
    ("dominio/evaluacion.py", "if ia >= self._p.umbral_alto:", "if ia > self._p.umbral_alto:",
     "M1: >= por > en el umbral ALTO"),
    ("dominio/evaluacion.py", "elif ia >= self._p.umbral_medio:", "elif ia > self._p.umbral_medio:",
     "M1: >= por > en el umbral MEDIO"),
    ("dominio/evaluacion.py", "if variabilidad > self._p.umbral_variabilidad:",
     "if variabilidad >= self._p.umbral_variabilidad:", "M1: > por >= en la variabilidad"),
    ("dominio/evaluacion.py", "alto = puntajes.d >= self._p.dependencia_minima_alto", "alto = True",
     "M1: ignora la dependencia humana (P4)"),
    ("dominio/evaluacion.py", 'NivelAutomatizacion.ALTO: Decimal("0.70")',
     'NivelAutomatizacion.ALTO: Decimal("0.40")', "M3: factor de MEDIO en ALTO (Tabla 23, B)"),
    ("dominio/evaluacion.py", "ahorro_anual = (ahorro_mensual * 12)",
     "ahorro_anual = (ahorro_mensual * 12 * 12)", "M3: doble anualización (Tabla 23, A)"),
    ("dominio/evaluacion.py", "recomendada=roi >= self._p.roi_minimo",
     "recomendada=roi > self._p.roi_minimo", "M3: >= por > en el ROI mínimo"),
    ("dominio/evaluacion.py", "if horas > HORAS_MES_MAXIMAS:", "if horas >= HORAS_MES_MAXIMAS:",
     "M3: > por >= en 744 horas"),
    ("dominio/cuestionario.py", "pendientes.append(pregunta.id)\n",
     "pendientes.append(pregunta.id)\n                    break\n",
     "M4: break en la primera pendiente"),
    ("dominio/cuestionario.py", "if not valor.is_finite():", "if False:",
     "M4: acepta NaN e Infinity"),
    ("dominio/pagos.py", "and diagnostico.orden_aprobada() is not None",
     "or diagnostico.orden_aprobada() is not None", "RN001: and por or"),
    ("servicios/pagos.py", "if evento.id in orden.eventos_procesados:", "if False:",
     "M2: sin idempotencia"),
    ("servicios/pagos.py", "self._esperar(2**intento)", "self._esperar(2)",
     "Reintentos con espera constante"),
    ("servicios/pagos.py", "crear_cobro(orden, orden.clave_idempotencia)",
     "crear_cobro(orden, uuid4().hex)", "Clave de idempotencia distinta por intento"),
    ("servicios/revision.py", "if usuario.rol is not Rol.AUDITOR_LIDER:", "if False:",
     "M5: no verifica el rol (C1)"),
    ("servicios/revision.py", "if not reporte.seccion_supuestos.strip():",
     "if not reporte.seccion_supuestos:", "M5: acepta supuestos en blanco (C4)"),
]  # fmt: skip


def probar(archivo: str, original: str, mutado: str, copia: Path) -> bool:
    """Retorna True si la suite detecta el mutante (alguna prueba falla)."""
    shutil.rmtree(copia, ignore_errors=True)
    ignorar = shutil.ignore_patterns(".venv", ".git", "*_cache", "__pycache__", ".hypothesis")
    shutil.copytree(RAIZ, copia, ignore=ignorar)
    ruta = copia / "src" / "autoaudit" / archivo
    texto = ruta.read_text(encoding="utf-8")
    if original not in texto:
        raise SystemExit(f"El código cambió y el mutante ya no aplica: {archivo}: {original!r}")
    ruta.write_text(texto.replace(original, mutado, 1), encoding="utf-8")
    entorno = dict(os.environ, PYTHONPATH=str(copia / "src"))
    comando = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]
    return subprocess.run(comando, cwd=copia, env=entorno, capture_output=True).returncode != 0  # noqa: S603


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        vivos = 0
        for archivo, original, mutado, nombre in MUTANTES:
            detectado = probar(archivo, original, mutado, Path(tmp) / "copia")
            vivos += not detectado
            print(f"{'eliminado' if detectado else 'VIVO':10} {nombre}")
    print(f"\n{len(MUTANTES) - vivos}/{len(MUTANTES)} mutantes eliminados")
    return 1 if vivos else 0


if __name__ == "__main__":
    raise SystemExit(main())
