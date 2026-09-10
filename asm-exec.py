#!/usr/bin/env python3
"""
asm-exec: resuelve un secreto de AWS Secrets Manager y lo inyecta en un comando
hijo (como argumento y/o variable de entorno), sin que el valor pase nunca por
la salida que un agente de IA (o cualquier proceso que capture stdout/stderr)
pueda leer.

La llamada a `aws secretsmanager get-secret-value` corre en un subproceso
interno con stdout/stderr capturados y jamas volcados a la terminal. Solo la
salida del COMANDO HIJO (el que de verdad se quiere ejecutar, ej. curl) se deja
pasar tal cual al llamador.

Uso:
    python asm-exec.py --secret-id <secret-id> [--env-var <NOMBRE_VAR>] \
        [--json-key <clave>] [--profile <perfil-aws>] [--region <region>] \
        -- <comando> [args...]

Ejemplo:
    python asm-exec.py --secret-id myapp/api-key --placeholder "{{SECRET}}" \
        -- curl -s -H "Authorization: Bearer {{SECRET}}" \
        "https://api.example.com/v1/resource/123"

El comando hijo se ejecuta SIEMPRE sin shell (subprocess con lista de argumentos,
shell=False) - el token "{{SECRET}}" se reemplaza literalmente en cada argumento
antes de ejecutar. Esto evita que la shell externa (bash) o interna (cmd.exe en
Windows) intenten expandir un "$VAR"/"%VAR%" de forma inconsistente entre
plataformas: con shell=True en Windows, subprocess invoca cmd.exe, que no
expande sintaxis "$VAR" de bash, produciendo fugas o fallos silenciosos segun
el sistema operativo.
"""
import argparse
import json
import os
import subprocess
import sys


def resolver_secreto(secret_id: str, profile: str | None, region: str | None, json_key: str | None) -> str:
    cmd = ["aws", "secretsmanager", "get-secret-value", "--secret-id", secret_id]
    if profile:
        cmd += ["--profile", profile]
    if region:
        cmd += ["--region", region]
    cmd += ["--query", "SecretString", "--output", "text"]

    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        sys.stderr.write("asm-exec: fallo al resolver el secreto (detalle omitido por seguridad)\n")
        sys.exit(resultado.returncode)

    valor = resultado.stdout.strip()

    if json_key:
        try:
            data = json.loads(valor)
        except json.JSONDecodeError:
            sys.stderr.write("asm-exec: el secreto no es JSON valido, no se puede extraer json-key\n")
            sys.exit(1)
        if json_key not in data:
            sys.stderr.write(f"asm-exec: la clave '{json_key}' no existe en el secreto\n")
            sys.exit(1)
        valor = str(data[json_key])

    return valor


def main() -> None:
    parser = argparse.ArgumentParser(description="Resuelve un secreto de Secrets Manager y ejecuta un comando con el valor inyectado, sin usar ninguna shell.")
    parser.add_argument("--secret-id", required=True)
    parser.add_argument("--env-var", default=None, help="Nombre de la variable de entorno donde se inyecta el valor (opcional, para procesos que leen su propio entorno)")
    parser.add_argument("--placeholder", default="{{SECRET}}", help="Token literal a reemplazar en cada argumento del comando hijo por el valor resuelto (default: {{SECRET}})")
    parser.add_argument("--json-key", default=None, help="Si el secreto es JSON, extraer solo esta clave")
    parser.add_argument("--profile", default=None, help="Perfil de AWS CLI a usar (default: el perfil configurado por defecto del entorno)")
    parser.add_argument("--region", default=None, help="Region de AWS a usar (default: la region configurada por defecto del entorno)")
    parser.add_argument("comando", nargs=argparse.REMAINDER, help="Comando a ejecutar tras --")

    args = parser.parse_args()

    comando = args.comando
    if comando and comando[0] == "--":
        comando = comando[1:]

    if not comando:
        sys.stderr.write("asm-exec: falta el comando a ejecutar (usar -- antes del comando)\n")
        sys.exit(1)

    valor = resolver_secreto(args.secret_id, args.profile, args.region, args.json_key)

    # Sustitucion literal del placeholder en cada argumento - nunca via shell,
    # para evitar que $VAR o %VAR% se expandan (o dejen de expandirse) de forma
    # distinta segun la shell externa (bash) o interna (cmd.exe en Windows).
    comando_final = [arg.replace(args.placeholder, valor) for arg in comando]

    env = os.environ.copy()
    if args.env_var:
        env[args.env_var] = valor

    proceso = subprocess.run(comando_final, env=env, shell=False)

    sys.exit(proceso.returncode)


if __name__ == "__main__":
    main()
