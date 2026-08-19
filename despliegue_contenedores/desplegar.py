"""Crea y sincroniza los contenedores en Railway.

    python -m despliegue_contenedores.desplegar          # muestra qué haría
    python -m despliegue_contenedores.desplegar --aplicar

Sin `--aplicar` no toca nada: imprime el plan y sale. Es a propósito — esto
crea infraestructura que cuesta plata y toca un proyecto con clientes escribiendo.

── Qué NO hace ────────────────────────────────────────────────────────────────

No cambia el webhook de WAHA. Crear los servicios y hacer el corte son dos
cosas distintas, y mezclarlas convierte un `--aplicar` distraído en una caída de
producción.

Los servicios nuevos arrancan, se conectan a su cola y esperan. Nadie les manda
nada hasta que se cambie `WHATSAPP_HOOK_URL` a mano, mirando lo que se hace.

── Es idempotente ─────────────────────────────────────────────────────────────

Correrlo dos veces no duplica nada: si el servicio existe, sincroniza sus
variables; si no, lo crea. Se puede correr cada vez que se agrega una variable.
"""
import argparse
import json
import os
import subprocess
import sys

from dotenv import dotenv_values

from despliegue_contenedores.servicios import (
    FUENTE, MUERTOS, RAMA, REPO, SERVICIOS, desplegables,
)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _railway(args: list) -> tuple[int, str]:
    r = subprocess.run(["railway", *args], capture_output=True, text=True, shell=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _variables_de(servicio: str) -> dict:
    codigo, salida = _railway(["variables", "-s", servicio, "--json"])
    try:
        return json.loads(salida)
    except Exception:
        return {}


def _existentes() -> set:
    codigo, salida = _railway(["status", "--json"])
    try:
        d = json.loads(salida)
    except Exception:
        sys.exit("No se pudo leer el proyecto. ¿Estás logueado? -> railway login")
    return {e["node"]["name"] for e in d.get("services", {}).get("edges", [])}


def _valores() -> dict:
    """De dónde sale cada secreto.

    Casi todos se copian del servicio viejo, que los tiene todos y sigue en
    producción. `OPENAI_API_KEY` es la excepción: se agregó después de que ese
    servicio se configurara, así que sale del .env local.
    """
    base = _variables_de(FUENTE)
    local = dotenv_values(os.path.join(RAIZ, ".env"))
    for k, v in local.items():
        if v and not base.get(k):
            base[k] = v
    return base


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--aplicar", action="store_true",
                   help="crea y sincroniza de verdad. Sin esto solo muestra el plan.")
    p.add_argument("--servicio", help="solo este. Por defecto, todos los que estén listos.")
    args = p.parse_args()

    valores = _valores()
    if not valores:
        sys.exit(f"No se pudieron leer las variables de {FUENTE}.")

    hay = _existentes()
    plan = desplegables()
    if args.servicio:
        if args.servicio not in SERVICIOS:
            sys.exit(f"No conozco {args.servicio!r}. Están: {list(SERVICIOS)}")
        plan = {args.servicio: SERVICIOS[args.servicio]}

    print(f"repo {REPO} · rama {RAMA}")
    print(f"{'APLICANDO' if args.aplicar else 'PLAN (nada se toca, usá --aplicar)'}\n")

    for nombre, spec in plan.items():
        faltan = [k for k in spec["variables"] if not valores.get(k)]
        estado = "existe" if nombre in hay else "SE CREA"
        print(f"== {nombre}  [{estado}]")
        print(f"   {spec['rol']}")
        print(f"   dockerfile : {spec['dockerfile']}")
        print(f"   watch      : {spec['watch']}")
        print(f"   variables  : {len(spec['variables']) - len(faltan)}/{len(spec['variables'])}"
              + (f"   FALTAN: {faltan}" if faltan else ""))

        if faltan:
            # Un servicio a medias arranca y falla en el primer turno, que es la
            # peor forma de enterarse.
            print(f"   -> se saltea: conseguí esas variables primero\n")
            continue

        if not args.aplicar:
            print()
            continue

        pares = [f"{k}={valores[k]}" for k in spec["variables"]]
        pares.append(f"RAILWAY_DOCKERFILE_PATH={spec['dockerfile']}")

        if nombre not in hay:
            cmd = ["add", "--service", nombre, "--repo", REPO, "--branch", RAMA]
            for v in pares:
                cmd += ["-v", v]
            codigo, salida = _railway(cmd)
            print(f"   creado ({codigo})")
        else:
            for v in pares:
                _railway(["variables", "-s", nombre, "--skip-deploys", "--set", v])
            print(f"   variables sincronizadas ({len(pares)})")
        print()

    saltados = {n: s for n, s in SERVICIOS.items() if not s.get("listo", True)}
    if saltados and not args.servicio:
        print("Todavía no se despliegan:")
        for n in saltados:
            print(f"   {n}  — su código no está listo (ver servicios.py)")

    encendidos = [m for m in MUERTOS if m in hay]
    if encendidos:
        print(f"\nSiguen encendidos y no los usa nadie: {encendidos}")

    if not args.aplicar:
        print("\nPara aplicarlo:  python -m despliegue_contenedores.desplegar --aplicar")


if __name__ == "__main__":
    main()
