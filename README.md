# asm-exec

Resuelve un secreto de AWS Secrets Manager en runtime e inyecta su valor a un
comando hijo, sin que ese valor pase nunca por la salida que un agente de IA
(o cualquier proceso que capture stdout/stderr) pueda leer.

## Por que existe

Cuando un agente de IA (Claude Code, o cualquier asistente con acceso a shell)
necesita usar una credencial almacenada en AWS Secrets Manager, la forma obvia
es ejecutar `aws secretsmanager get-secret-value` directamente. El problema es
que el resultado de ese comando - el secreto en texto plano - queda en la
salida que el agente captura y en muchos casos conserva como parte de su
contexto de conversación, quedando expuesto a logs, historiales o al propio
modelo.

`asm-exec` resuelve el secreto en un subproceso interno con stdout/stderr
capturados y nunca impresos, y solo deja pasar al llamador la salida del
**comando hijo** (por ejemplo, la respuesta de un `curl`). El valor del secreto
en sí nunca aparece en ninguna salida visible.

## Como funciona

1. Ejecuta `aws secretsmanager get-secret-value` en un subproceso, capturando
   stdout/stderr sin imprimirlos.
2. Si el secreto es JSON, permite extraer una sola clave con `--json-key` en
   vez de exponer el objeto completo.
3. Sustituye un token configurable (`{{SECRET}}` por defecto) por el valor
   resuelto en cada argumento del comando hijo, y opcionalmente lo inyecta
   también como variable de entorno con `--env-var`.
4. Ejecuta el comando hijo siempre con `shell=False` (lista de argumentos, sin
   invocar ninguna shell). Esto es deliberado: con `shell=True` en Windows,
   `subprocess` invoca `cmd.exe`, que no expande sintaxis `$VAR` de bash - la
   sustitución vía shell externa/interna se comporta de forma inconsistente
   entre plataformas y puede filtrar o fallar en silencio según el sistema.

## Uso

```bash
python asm-exec.py \
  --secret-id myapp/api-key --placeholder "{{SECRET}}" \
  --profile <perfil-aws> --region <region> -- \
  curl -s -H "Authorization: Bearer {{SECRET}}" \
  "https://api.example.com/v1/resource/123"
```

| Flag | Descripción |
|---|---|
| `--secret-id` | ID o ARN del secreto en Secrets Manager (obligatorio) |
| `--json-key` | Si el `SecretString` es JSON (ej. `{"apiKey":"..."}`), extrae solo esa clave en vez de pasar el JSON completo |
| `--placeholder` | Token a reemplazar en cada argumento del comando hijo (default `{{SECRET}}`) |
| `--env-var` | Además del placeholder, inyecta el valor como variable de entorno del proceso hijo - útil si el programa invocado lee su propio entorno en vez de recibir el valor como argumento |
| `--profile` / `--region` | Perfil y región de AWS CLI a usar (default: los configurados por defecto en el entorno) |

Un agente de IA puede invocar este script directamente vía su herramienta de
shell sin violar la regla de "nunca ejecutar `get-secret-value` directamente":
el valor jamás aparece en la salida que el agente captura, solo se usa
internamente para construir el comando hijo.

## Limitación conocida

El valor resuelto queda visible en el `argv` del proceso hijo a nivel de
sistema operativo (por ejemplo vía `ps aux` en el mismo host) mientras el
comando corre. Esta es una limitación inherente a cualquier mecanismo de
inyección vía variable de entorno o línea de comandos, no exclusiva de este
script. Es aceptable para llamadas puntuales desde una sesión interactiva; no
para servicios de larga duración - en ese caso corresponde resolver el secreto
directamente en el runtime de la aplicación (patrón estándar de
`get_secret_value`, sin necesidad de este wrapper).

## Requisitos

- Python 3.10+ (usa el operador `|` en type hints)
- AWS CLI v2 instalado y configurado (`aws configure` o variables de entorno
  estándar de AWS)
- Permisos IAM de `secretsmanager:GetSecretValue` sobre el secreto a resolver

## Autor

Matías Allende
[LinkedIn](https://www.linkedin.com/in/matiasallende/) · matias.allende.contreras@gmail.com

## Licencia

MIT. Ver [LICENSE](LICENSE).
