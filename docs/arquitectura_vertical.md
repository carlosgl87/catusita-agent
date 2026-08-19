# Arquitectura — router lógico, dos multiagentes, un área por agente

Estado: **esqueleto creado, sin lógica migrada**. El código viejo sigue corriendo
intacto en `orchestrator/`, `agents/` y `shared/`.

## La forma

```
WAHA ─► webhook ─► ROUTER (lógico, conoce los números)
                       ├─► supervisor VENDEDORES ─► 6 áreas ─► validar ─► respuesta
                       └─► supervisor CLIENTES   ─► 5 áreas ─► validar ─► respuesta
```

Tres decisiones, en orden de importancia:

1. **Vendedores y clientes son proyectos distintos.** No comparten agentes, ni
   prompts, ni acceso a datos. Solo `plataforma/` y el `router/`.
2. **El router es lógico, no un LLM**, y **falla cerrado**.
3. **Dentro de cada multiagente, un agente por área de negocio**, y el supervisor es
   el único que coordina.

## 1 · Dos multiagentes

```
plataforma/          único compartido: estado, contexto, validar, llm, redis, db
router/              decide a qué multiagente entra el mensaje
vendedores/          grafo, supervisor y 6 áreas propias
clientes/            grafo, supervisor y 5 áreas propias
```

| | vendedores | clientes |
|---|---|---|
| Público | asesores internos | talleres, distribuidores, consumidor final |
| Áreas | multiagentes, vehiculos, clientes, pedidos, facturacion, compatibilidad | multiagentes, vehiculos, compatibilidad, postventa, recomendaciones |
| Tools internas | 12 | 8 |

`productos`, `vehiculos` y `compatibilidad` aparecen en los dos, pero **no son el
mismo código**. El público determina qué dato es seguro devolver:

| Área | vendedores | clientes |
|---|---|---|
| `productos` | precio neto, stock por almacén | solo lista, sin ubicación |
| `vehiculos` | SUNARP completo, **incluido propietario** | marca, modelo, año. **Sin propietario** |

`clientes/agentes/productos/backend.py` **no mapea el campo `precio_neto`**. No
puede filtrarlo porque no tiene el código para traerlo. Eso es una frontera; un
prompt que dice «no muestres precios netos» es una sugerencia.

## 2 · El router

Vive arriba de los dos supervisores. WAHA entra por un solo webhook.

**Es lógico, no un LLM.** Un modelo que se equivoca acá le da precio neto y cartera
a alguien de afuera; esa decisión no se delega. Además tarda microsegundos, no
cuesta tokens y se puede testear exhaustivamente porque es una tabla.

El canal es **WAHA** (self-hosted, automatiza WhatsApp Web), no la Cloud API.
La señal de «por dónde entró» es la **sesión**, no un `phone_number_id`.

**Exige dos señales para llegar a vendedores:**

1. el número del remitente está en el registro de asesores
2. el mensaje llegó por la sesión de WAHA del número interno

Se piden las dos a propósito: si un asesor le escribe al número público, entra
como cliente. El canal define el alcance, no el cargo.

**Falla cerrado.** Cualquier caso raro —número sin registrar, sesión desconocida,
LID que no se pudo traducir, registro caído, entrada basura— va a `clientes`.

### El estado de hoy

En la ruta que corre en producción (`/webhook/waha`) **no hay resolución de canal
en absoluto**:

```python
agente_tipo = "vendedor"  # por ahora solo el canal de vendedores
```

Todo el que le escriba al número conectado entra como asesor. Sumado a
`USE_AUTH_MOCK=true`, queda autenticado como V001.

Y el webhook valida de forma opcional:

```python
if expected and waha_key != expected:   # si WAHA_WEBHOOK_TOKEN está vacío, no valida
    raise HTTPException(401)
```

Sin esa variable, el webhook acepta cualquier POST de internet — y como hace
`create_task` inmediato, cualquiera puede disparar corridas del agente contra la
cuenta de Anthropic.

> El handler de Kapso (`/webhook/whatsapp`) tiene un `_resolver_agente_tipo` que
> falla hacia `vendedor`, pero esa ruta no está en uso (`WHATSAPP_PROVIDER=waha`).

**Dos canales exigen dos sesiones de WAHA**, cada una con su número. Hoy corre una
sola (`WAHA_SESSION=default`), así que el multiagente de clientes no tiene por dónde
entrar hasta que se levante la segunda.

`router/tests/test_router.py` cubre los ocho casos de entrada rara —incluido el LID
sin traducir— y el de registro caído. Ninguno puede terminar en `vendedores`.

## 3 · Un agente por área

El corte es por **contexto**, no por tool. Cada agente cubre un área que se explica
sola y maneja una entidad. Puede tener varias tools mientras compartan vocabulario.

> La prueba: ¿un solo prompt las explica sin crecer? Si sí, es un área.

| Área | Entidad | Contesta | Modelo |
|---|---|---|---|
| `productos` | SKU | ¿qué pieza es, existe, cuánto vale? | Haiku |
| `vehiculos` | placa / VIN | ¿qué auto es esta placa? | Sonnet |
| `clientes` | RUC | ¿quién es y está en mi cartera? | Haiku |
| `pedidos` | pedido / factura | ¿dónde está, ya llegó? | Haiku |
| `facturacion` | documento | ¿está pagada?, mándame el PDF | Haiku |
| `postventa` | reclamo | quiero reclamar | Haiku |
| `compatibilidad` | multiagente × vehículo | ¿le calza? | Sonnet |
| `recomendaciones` | cliente × catálogo | ¿qué más me sirve? | Sonnet |

Cada área elige **su propio modelo**: lookup dirigido → Haiku; razonamiento real
(visión de SUNARP, equivalencias) → Sonnet. Hoy todo pasa por el mismo modelo caro.

### El supervisor solo coordina

Las áreas **no se hablan entre sí**. Si a `facturacion` le falta el N° de documento,
vuelve al supervisor diciendo qué necesita. Eso es un supervisor; lo otro sería un
swarm, que se justifica cuando el usuario *conversa con* un agente muchos turnos.
Acá nadie conversa con `pedidos`: le pregunta y le contesta.

Se fuerza en el constructor de cada grafo, no por prompt:

- de cada área sale **una sola arista**, y va a `supervisor`
- ningún área tiene arista a otra área
- ningún área tiene arista a `END` — si no, se saltaría `validar`

`verificar_topologia()` comprueba las tres y corre en los tests.

### Lo que gana el supervisor

Su prompt hoy son seis manuales de área engrapados: **7.483 caracteres de system +
4.085 de descripciones de tools ≈ 2.900 tokens fijos en cada llamada**, casi todos
irrelevantes para la pregunta. Con áreas ve 6 agentes en vez de 12 tools, y cada
manual carga solo cuando su área corre:

| Hoy, en el prompt del supervisor | Se muda a |
|---|---|
| «si SUNARP está caído USA INMEDIATAMENTE consultar_placa_yahuar» | `vehiculos` |
| «primero consultar_pedidos, luego consultar_despacho» | `pedidos` |
| «cuando mencione un cliente por nombre parcial NUNCA le pidas el RUC…» | `clientes` |

## Anatomía de un área

| Archivo | Qué contiene |
|---|---|
| `__init__.py` | Contrato público: `MODELO`, `NODO`, `TOOLS` |
| `prompt.py` | Su system prompt. Solo carga cuando corre |
| `agente.py` | Su subgrafo, con estado propio |
| `tools.py` | Sus tools internas — el supervisor no las ve |
| `servicio.py` | Lógica. Python normal, sin LangChain ni HTTP |
| `backend.py` | Sus endpoints, su timeout, **su mapeo** |
| `contratos.py` | Modelos de entrada/salida |
| `acceso.py` | Solo `vendedores/clientes`: control de cartera |
| `tests/` | Sus pruebas, con `backend.py` mockeado |

## Las reglas

1. **Nadie importa el interior de otra área**, y **nada de clientes importa código
   de vendedores** — hay un test que lo verifica leyendo el árbol. Única excepción
   dentro de un multiagente: `vendedores/agentes/clientes/acceso.py`, que es código
   determinista, no un handoff.
2. **Cada área es dueña de su acceso a datos.** No hay cliente SAP compartido.
3. **El grafo no nombra ninguna área.** Las pide al registro de su multiagente.

## Estado verificado

- `vendedores`: 6 áreas, 12 tools internas
- `clientes`: 5 áreas, 8 tools internas
- Test de aislamiento entre multiagentes: pasa
- Tests del router: 11, en `skip` hasta implementar `resolver`

## Mapa de migración

| Origen | Destino |
|---|---|
| `shared/sap_client.py` | se disuelve en el `backend.py` de cada área |
| `agents/stock,prices,imagenes,buscador_subagente` | `*/agentes/productos/` |
| `agents/vehicle.py` + `yahuar_subagente` + `shared/yahuar.py` | `vendedores/agentes/vehiculos/` |
| `agents/cartera.py` + `orchestrator/access.py` | `vendedores/agentes/clientes/` |
| `agents/orders.py` | `vendedores/agentes/pedidos/` |
| `agents/documents.py` | `vendedores/agentes/facturacion/` |
| `agents/claims.py` | `clientes/agentes/postventa/` |
| `orchestrator/lc_tools.py` | se reparte en el `tools.py` de cada área |
| `orchestrator/prompts.py` | la parte transversal a cada `supervisor.py`; el resto a los `prompt.py` |
| `orchestrator/nodes/validar.py` | `plataforma/nodos/validar.py`, con reglas por multiagente |
| `orchestrator/context.py` | `plataforma/nodos/contexto.py` |
| `shared/auth.py::_MOCK_ASESORES` | `router/numeros.py` |
| `webhooks/whatsapp.py:471` (`agente_tipo = "vendedor"`) | `router/router.py` |
| `webhooks/whatsapp.py::_resolver_agente_tipo` (Kapso, sin uso) | se descarta |

Orden sugerido: **el router primero** (es la frontera de seguridad y hoy está mal),
después `vendedores/multiagentes` de punta a punta para fijar el patrón, después el
resto de vendedores, y al final el multiagente de clientes.

## Colas

El webhook responde 200 al instante y hace el trabajo en `asyncio.create_task`:
una cola **en memoria**, que se pierde con el proceso. Tres huecos:

1. **El trabajo muere con el proceso.** Cada deploy (`rsync` + `docker restart`)
   corta las conversaciones en vuelo. Con SUNARP tardando 20-60s la ventana es amplia.
2. **No hay idempotencia en la ruta de WAHA.** El `X-Idempotency-Key` existe solo
   en el handler de Kapso. Si WAHA reenvía un evento, se duplica la corrida y la
   respuesta al usuario.
3. **No hay orden por conversación.** Tres mensajes seguidos del mismo número son
   tres corridas concurrentes sobre el mismo historial de Redis.

Propuesta: el webhook solo encola (ARQ sobre el Redis que ya existe), un worker
consume, y **dos colas separadas por latencia** — que es la misma división del
despliegue:

| Cola | Qué corre | Consumidor |
|---|---|---|
| `rapida` | stock, precios, pedidos, cartera, documentos | worker del app |
| `lenta` | SUNARP (20-60s), YAHUAR | contenedores aparte |

El debounce ya está inventado: el acumulador Redis de YAHUAR
(`acumular_mensaje` + timestamp) es el patrón que falta para todas las
conversaciones — esperar ~3s de silencio, unir los fragmentos, correr el agente
una vez.

**Cuidado al reintentar:** el trabajo manda WhatsApps y escribe reclamos. Un
reintento ciego los duplica. Marcar «ya respondí» *antes* de enviar.

## Despliegue

Todo corre en **Railway**, deploy por `git push` a `main`. Hoy son tres servicios:
`catusita-agent`, `waha` y `mock-sap` (+ Redis y Postgres).

> `deploy.sh` apunta a un Droplet con `rsync`/`ssh`. Está obsoleto y confunde:
> conviene borrarlo o marcarlo como no usado.

Eso ya te da el modelo de contenedor-por-servicio. Un servicio nuevo en Railway
es *mismo repo, otro start command* — así que la pregunta «¿cada agente su propio
Docker?» sale barata en infra y sigue siendo mala idea por LangGraph:
`Command(goto=...)` no cruza procesos.

Lo que sí conviene agregar:

```
Railway
├── catusita-agent          el webhook. Solo valida, dedupe y ENCOLA
├── catusita-worker         mismo repo · arq worker · cola rápida
├── catusita-worker-lento   mismo repo · arq worker · cola lenta (SUNARP, YAHUAR)
├── waha                    sesión WhatsApp Web  ⚠ NECESITA VOLUMEN
├── tools-agente-catusita   (reemplaza al mock-sap)
├── redis
└── postgres
```

Los tres primeros son el mismo repo con distinto comando de arranque. Separar el
worker lento es lo que evita que una consulta de stock espere detrás de un SUNARP
de 60 segundos.

**Kubernetes: no.** Railway *es* el orquestador. Migrar significaría perder el
deploy por `git push`, el Postgres y el Redis administrados, y cargar con el
clúster. Para este tamaño es un paso atrás.

### Dos trampas de Railway

1. **El filesystem es efímero.** WAHA guarda la sesión de WhatsApp Web en disco;
   sin un volumen montado, cada redeploy pierde la sesión y hay que reescanear el
   QR. Verificar que el servicio `waha` tenga volumen.
2. **`git push` a `main` redespliega.** Cada push corta las conversaciones en
   vuelo — más seguido que en un Droplet. Es el argumento más fuerte para sacar el
   trabajo de `asyncio.create_task` y meterlo en una cola durable.

## Pendientes

- **El turno extra.** Una consulta simple pasa de 2 llamadas al LLM a 4, porque el
  área también piensa. Se compensa con Haiku en las áreas de lookup, pero hay que
  medirlo en WhatsApp real.
- **Clave de Redis por multiagente**, para que el historial no cruce.
- **`pre_resolver`**: quedó anotado como segunda etapa de `contexto.py`.
- **`compatibilidad` y `recomendaciones`**: carpeta y contrato, falta definir datos.
