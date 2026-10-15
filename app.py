"""Intérprete de Python en el navegador.

Sirve un editor web y ejecuta el código recibido en un proceso de Python
independiente, con tiempo límite, para que un bucle infinito o un error
no bloqueen el servidor.
"""

import re
import subprocess
import sys
import time

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

TIEMPO_LIMITE = 5          # segundos máximos por ejecución
MAX_SALIDA = 20_000        # caracteres máximos devueltos al navegador

# Arranque que se ejecuta en el proceso hijo: muestra en la salida lo que se
# responde a cada input() (como en una terminal real) y ejecuta el código del
# usuario como "main.py", ocultando este arranque de los tracebacks.
ARRANQUE = """
import builtins, linecache, sys, traceback
# Registra el código para que los tracebacks muestren la línea que falla
linecache.cache["main.py"] = (len(sys.argv[1]), None, sys.argv[1].splitlines(True), "main.py")
_input = builtins.input
def input(prompt=""):
    valor = _input(prompt)
    print(valor)
    return valor
builtins.input = input
try:
    codigo = compile(sys.argv[1], "main.py", "exec")
except SyntaxError as e:
    traceback.print_exception(type(e), e, None)
    sys.exit(1)
try:
    exec(codigo, {"__name__": "__main__"})
except SystemExit:
    raise
except BaseException as e:
    traceback.print_exception(type(e), e, e.__traceback__.tb_next)
    sys.exit(1)
"""

ANSI = re.compile(r"\x1b\[[0-9;]*m")  # códigos de color de la terminal


@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/api/ejecutar", methods=["POST"])
def ejecutar():
    datos = request.get_json(force=True) or {}
    codigo = datos.get("code", "")
    entradas = datos.get("inputs", "")

    if not codigo.strip():
        return jsonify(ok=False, salida="No hay código que ejecutar.", tiempo=0)

    # Las entradas se pasan por stdin: cada línea responde a un input().
    # -I aísla el intérprete (ignora variables de entorno y el directorio actual)
    # y -X utf8 fuerza UTF-8 en la salida también en Windows.
    inicio_ms = time.perf_counter()
    try:
        proceso = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", "-c", ARRANQUE, codigo],
            input=entradas if entradas.endswith("\n") or not entradas else entradas + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=TIEMPO_LIMITE,
        )
    except subprocess.TimeoutExpired:
        return jsonify(
            ok=False,
            salida=f"⏱ Tiempo límite superado ({TIEMPO_LIMITE} s). ¿Hay un bucle infinito?",
            tiempo=TIEMPO_LIMITE * 1000,
        )

    tiempo = round((time.perf_counter() - inicio_ms) * 1000)
    salida = ANSI.sub("", proceso.stdout + proceso.stderr)
    if len(salida) > MAX_SALIDA:
        salida = salida[:MAX_SALIDA] + "\n… (salida recortada)"

    if not salida:
        salida = "(sin salida)" if proceso.returncode == 0 else f"Proceso terminado con código {proceso.returncode}"
    return jsonify(ok=proceso.returncode == 0, salida=salida, tiempo=tiempo)


if __name__ == "__main__":
    app.run(debug=True)
