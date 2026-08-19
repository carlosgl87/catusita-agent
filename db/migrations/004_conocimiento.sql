-- ─────────────────────────────────────────────────────────────────────────────
-- Los procesos de Catusita, y lo que falta de ellos.
-- ─────────────────────────────────────────────────────────────────────────────
--
-- De acá saca el orquestador CÓMO trabaja. No es un anexo de consulta: es la
-- fuente de su comportamiento. Todo proceso que ejecute tiene que estar acá, no
-- solo los casos raros. Lo que no está, el orquestador no lo sabe hacer.
--
-- La consecuencia es deliberada: el prompt se queda con lo transversal —quién
-- es, cómo habla, qué no puede revelar— y el comportamiento se edita como filas,
-- sin redeploy. Es lo que hoy no se puede: de los 23 pedidos de mejora en 30
-- días, 8 eran de comportamiento y cada uno obligó a tocar el prompt.
--
-- EMBEDDINGS: OpenAI `text-embedding-3-small`, 1536 dims. DECIDIDO.
--
-- Las columnas `vector(1536)` ya calzan: no hay nada que ajustar antes de correr
-- esta migración. Se descartó voyage-3 (partner de Anthropic) porque da 1024 y
-- habría obligado a cambiar las 6 columnas.
--
-- Cambiar de modelo más adelante obliga a RE-EMBEBER todo. Por eso cada fila
-- guarda su `modelo_emb`: es la única forma de saber cuáles quedaron viejas.
--
-- Antes de correrla, revisar el punto 0: el ALTER TABLE falla si hay filas
-- huérfanas en chat_messages.
--
--
-- ── UNA TABLA POR MULTIAGENTE, NO UNA COLUMNA QUE DISCRIMINE ─────────────────
--
-- La versión anterior de este archivo tenía UNA tabla `conocimiento` con una
-- columna `multiagente` que discriminaba. Se cambió a tabla por multiagente porque:
--
--   1. La frontera es física, no un WHERE. Un procedimiento interno de
--      vendedores no puede salir en una conversación de clientes. Con columna,
--      eso depende de que ningún query se olvide del filtro — una vez. Con
--      tablas separadas, el error deja de ser posible.
--
--   2. Van a divergir. Los procesos de vendedores se relacionan con el roster de
--      `vendedores`; los de clientes no tienen roster. Cada agente nuevo trae sus
--      propias relaciones, y una tabla común obliga a que todas quepan en el
--      mismo esquema.
--
--   3. Es coherente con el resto: tres multiagentes, tres contenedores, tres colas.
--
-- El costo es DDL repetido. Se paga a gusto: son tablas que van a divergir.
--
--
-- ── EL MODELO RELACIONAL ─────────────────────────────────────────────────────
--
--   vendedores
--       │ 1:N
--       ▼
--   chat_messages ──────────────┐
--       │ 1:N                   │ 1:N
--       ▼                       ▼
--   solicitud_proceso_    solicitud_proceso_
--     nuevo_vendedores      nuevo_clientes        (y _supervisores)
--       │ N:1                   │ N:1
--       ▼                       ▼
--   conocimiento_         conocimiento_
--     vendedores            clientes              (y _supervisores)
--
-- El ciclo que cierra todo:
--
--     consulta sin proceso -> solicitud -> alguien escribe el proceso
--        -> se cierra la solicitud apuntando a la fila de conocimiento
--
-- Por eso `resuelto_con` es una FK y no un booleano: una solicitud no se cierra
-- diciendo «ya está», se cierra señalando el procedimiento que la resolvió.


CREATE EXTENSION IF NOT EXISTS vector;


-- ─────────────────────────────────────────────────────────────────────────────
-- 0. Cerrar la relación que ya faltaba
-- ─────────────────────────────────────────────────────────────────────────────
--
-- `chat_messages.vendedor_id` y `vendedores.vendedor_id` son el mismo dato desde
-- que existen, pero nunca hubo FK: hoy se puede insertar un mensaje de un
-- vendedor que no existe y nadie se entera. Las solicitudes cuelgan de
-- chat_messages, así que esta cadena tiene que estar sana antes.
--
-- ON DELETE SET NULL y no CASCADE: si se da de baja a un asesor no se borra su
-- historial — es justamente lo que se quiere conservar.

-- Puede fallar si hay filas huérfanas. Revisar ANTES de correr la migración:
--     SELECT DISTINCT vendedor_id FROM chat_messages
--      WHERE vendedor_id IS NOT NULL
--        AND vendedor_id NOT IN (SELECT vendedor_id FROM vendedores);
-- Si devuelve filas: o se dan de alta esos vendedores, o se les pone NULL.
--
-- Envuelto en un DO porque ADD CONSTRAINT no tiene IF NOT EXISTS: sin esto, la
-- migración solo se puede correr una vez y revienta en el segundo intento.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chat_messages_vendedor_fk'
    ) THEN
        ALTER TABLE chat_messages
            ADD CONSTRAINT chat_messages_vendedor_fk
            FOREIGN KEY (vendedor_id) REFERENCES vendedores(vendedor_id)
            ON DELETE SET NULL;
    END IF;
END $$;


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Los procesos
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Un proceso se guarda en cuatro piezas, no en un bloque de texto:
--
--   titulo    qué proceso es
--   cuando    en qué situación aplica          <-- es lo ÚNICO que se embebe
--   pasos     cómo se resuelve
--   entrega   cómo se le presenta al usuario
--
-- Por qué solo `cuando` va al embedding: la consulta del usuario se parece a la
-- SITUACIÓN, no al procedimiento. Quien escribe «llegó abollado» no escribe
-- «tramitar devolución». Embeber los pasos mete ruido y hace que el proceso
-- correcto no salga.
--
-- Por qué `entrega` va aparte: cambia por su cuenta —el mismo procedimiento se
-- le explica distinto a un cliente que a un asesor— y es lo que más se va a
-- corregir con el uso.
--
-- `modelo_emb` por fila para saber qué filas quedaron viejas si algún día se
-- cambia de proveedor. Sin esto, un cambio de modelo deja vectores de dos
-- espacios distintos mezclados y las búsquedas se degradan sin que nada falle.

CREATE TABLE IF NOT EXISTS conocimiento_vendedores (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    area        VARCHAR(30),            -- NULL = aplica a todo el multiagente
    titulo      TEXT NOT NULL,
    cuando      TEXT NOT NULL,
    pasos       TEXT NOT NULL,
    entrega     TEXT,
    modelo_emb  VARCHAR(40) NOT NULL,
    embedding   vector(1536),           -- text-embedding-3-small
    activo      BOOLEAN NOT NULL DEFAULT true,
    creado_por  VARCHAR(60),
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conocimiento_clientes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    area        VARCHAR(30),
    titulo      TEXT NOT NULL,
    cuando      TEXT NOT NULL,
    pasos       TEXT NOT NULL,
    entrega     TEXT,
    modelo_emb  VARCHAR(40) NOT NULL,
    embedding   vector(1536),           -- text-embedding-3-small
    activo      BOOLEAN NOT NULL DEFAULT true,
    creado_por  VARCHAR(60),
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conocimiento_supervisores (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    area        VARCHAR(30),
    titulo      TEXT NOT NULL,
    cuando      TEXT NOT NULL,
    pasos       TEXT NOT NULL,
    entrega     TEXT,
    modelo_emb  VARCHAR(40) NOT NULL,
    embedding   vector(1536),           -- text-embedding-3-small
    activo      BOOLEAN NOT NULL DEFAULT true,
    creado_por  VARCHAR(60),
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- HNSW, no ivfflat. La versión anterior de esta tabla creaba un índice ivfflat
-- sobre una tabla VACÍA: ivfflat particiona el espacio mirando los datos que hay
-- al construirse, así que sin filas quedaba mal calibrado y recuperaba peor —
-- en silencio, sin errores. HNSW se construye incrementalmente y no le pasa.
CREATE INDEX IF NOT EXISTS conocimiento_vendedores_emb_idx
    ON conocimiento_vendedores USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS conocimiento_clientes_emb_idx
    ON conocimiento_clientes USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS conocimiento_supervisores_emb_idx
    ON conocimiento_supervisores USING hnsw (embedding vector_cosine_ops);

-- Búsqueda por texto: gana donde el embedding pierde (códigos, nombres propios).
CREATE INDEX IF NOT EXISTS conocimiento_vendedores_txt_idx ON conocimiento_vendedores
    USING gin (to_tsvector('spanish', titulo || ' ' || cuando || ' ' || pasos));
CREATE INDEX IF NOT EXISTS conocimiento_clientes_txt_idx ON conocimiento_clientes
    USING gin (to_tsvector('spanish', titulo || ' ' || cuando || ' ' || pasos));
CREATE INDEX IF NOT EXISTS conocimiento_supervisores_txt_idx ON conocimiento_supervisores
    USING gin (to_tsvector('spanish', titulo || ' ' || cuando || ' ' || pasos));


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Lo que el agente no supo hacer
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Se abre una solicitud por DOS caminos distintos, y la diferencia importa:
--
--   origen = 'sin_resultado'
--       Automático. `contexto` buscó y no trajo nada por encima del umbral.
--       Falta el proceso, o está pero su `cuando` no lo hace recuperable.
--
--   origen = 'rechazado'
--       Deliberado. SÍ se recuperó un proceso, pero al orquestador no le sirvió
--       y llamó a la tool para pedir uno nuevo. Es la señal más valiosa de las
--       dos: significa que hay un proceso que parece aplicar y no aplica.
--
-- Es la versión automática de lo que hoy se hace a mano en
-- mejoras/incidencias.json (23 pedidos en 30 días, recolectados a pulso). La
-- diferencia: acá no depende de que el asesor se acuerde de reportarlo.
--
-- `mensaje_id` en vez de copiar numero/session_id/vendedor: la solicitud la
-- causó UN mensaje concreto, y desde él se llega por join a quién preguntó,
-- cuándo y en qué conversación. Duplicar esas columnas sería tener el mismo dato
-- en dos lados pudiendo desincronizarse.
--
-- OJO AL IMPLEMENTAR: hoy webhooks/whatsapp.py corre el agente (línea ~469) y
-- recién después guarda los mensajes (~479). Con ese orden, `mensaje_id` todavía
-- no existe cuando se abre la solicitud. Hay que guardar el mensaje del usuario
-- ANTES de correr el agente — que además arregla algo que ya está mal: si el
-- agente revienta, hoy el mensaje del usuario se pierde de la BD.

CREATE TABLE IF NOT EXISTS solicitud_proceso_nuevo_vendedores (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    mensaje_id   UUID REFERENCES chat_messages(id) ON DELETE SET NULL,
    consulta     TEXT NOT NULL,          -- lo que escribió el usuario, tal cual

    -- El vector de la consulta. NO cuesta nada: `contexto` ya lo calculó para
    -- buscar. Guardarlo es lo que permite agrupar (ver abajo).
    embedding    vector(1536),           -- text-embedding-3-small
    modelo_emb   VARCHAR(40) NOT NULL,

    origen       VARCHAR(15) NOT NULL,   -- sin_resultado | rechazado
    mejor_sim    REAL,                   -- qué tan cerca estuvo lo mejor. NULL = nada
    motivo       TEXT,                   -- por qué no le sirvió (solo si 'rechazado')

    veces        INT NOT NULL DEFAULT 1,
    ultima_vez   TIMESTAMP DEFAULT NOW(),

    estado       VARCHAR(15) NOT NULL DEFAULT 'pendiente',
    resuelto_con UUID REFERENCES conocimiento_vendedores(id) ON DELETE SET NULL,
    resuelto_at  TIMESTAMP,

    created_at   TIMESTAMP DEFAULT NOW(),

    CONSTRAINT spn_vend_origen_chk CHECK (origen IN ('sin_resultado', 'rechazado')),
    CONSTRAINT spn_vend_estado_chk CHECK (estado IN ('pendiente', 'resuelto', 'descartado')),
    -- Si está resuelta, tiene que decir con qué. Es el ciclo entero: sin esto se
    -- puede marcar «resuelto» sin que exista el proceso.
    CONSTRAINT spn_vend_resuelta_chk CHECK (
        estado <> 'resuelto' OR (resuelto_con IS NOT NULL AND resuelto_at IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS solicitud_proceso_nuevo_clientes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mensaje_id   UUID REFERENCES chat_messages(id) ON DELETE SET NULL,
    consulta     TEXT NOT NULL,
    embedding    vector(1536),           -- text-embedding-3-small
    modelo_emb   VARCHAR(40) NOT NULL,
    origen       VARCHAR(15) NOT NULL,
    mejor_sim    REAL,
    motivo       TEXT,
    veces        INT NOT NULL DEFAULT 1,
    ultima_vez   TIMESTAMP DEFAULT NOW(),
    estado       VARCHAR(15) NOT NULL DEFAULT 'pendiente',
    resuelto_con UUID REFERENCES conocimiento_clientes(id) ON DELETE SET NULL,
    resuelto_at  TIMESTAMP,
    created_at   TIMESTAMP DEFAULT NOW(),
    CONSTRAINT spn_cli_origen_chk CHECK (origen IN ('sin_resultado', 'rechazado')),
    CONSTRAINT spn_cli_estado_chk CHECK (estado IN ('pendiente', 'resuelto', 'descartado')),
    CONSTRAINT spn_cli_resuelta_chk CHECK (
        estado <> 'resuelto' OR (resuelto_con IS NOT NULL AND resuelto_at IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS solicitud_proceso_nuevo_supervisores (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mensaje_id   UUID REFERENCES chat_messages(id) ON DELETE SET NULL,
    consulta     TEXT NOT NULL,
    embedding    vector(1536),           -- text-embedding-3-small
    modelo_emb   VARCHAR(40) NOT NULL,
    origen       VARCHAR(15) NOT NULL,
    mejor_sim    REAL,
    motivo       TEXT,
    veces        INT NOT NULL DEFAULT 1,
    ultima_vez   TIMESTAMP DEFAULT NOW(),
    estado       VARCHAR(15) NOT NULL DEFAULT 'pendiente',
    resuelto_con UUID REFERENCES conocimiento_supervisores(id) ON DELETE SET NULL,
    resuelto_at  TIMESTAMP,
    created_at   TIMESTAMP DEFAULT NOW(),
    CONSTRAINT spn_sup_origen_chk CHECK (origen IN ('sin_resultado', 'rechazado')),
    CONSTRAINT spn_sup_estado_chk CHECK (estado IN ('pendiente', 'resuelto', 'descartado')),
    CONSTRAINT spn_sup_resuelta_chk CHECK (
        estado <> 'resuelto' OR (resuelto_con IS NOT NULL AND resuelto_at IS NOT NULL)
    )
);

-- AGRUPAR, NO ACUMULAR. La misma carencia se va a disparar decenas de veces con
-- redacciones distintas («llegó abollado», «vino golpeado», «está chancado»). Si
-- cada una abre su solicitud, la lista es ilegible en una semana.
--
-- Antes de insertar hay que buscar una solicitud PENDIENTE cuyo embedding esté
-- cerca; si la hay, se le suma `veces` y se actualiza `ultima_vez`. Así `veces`
-- pasa a ser la cola de prioridades: el proceso que más falta es el más pedido.
CREATE INDEX IF NOT EXISTS spn_vendedores_emb_idx
    ON solicitud_proceso_nuevo_vendedores USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS spn_clientes_emb_idx
    ON solicitud_proceso_nuevo_clientes USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS spn_supervisores_emb_idx
    ON solicitud_proceso_nuevo_supervisores USING hnsw (embedding vector_cosine_ops);

-- La consulta del panel: qué falta, lo más pedido primero.
CREATE INDEX IF NOT EXISTS spn_vendedores_pend_idx
    ON solicitud_proceso_nuevo_vendedores (estado, veces DESC);
CREATE INDEX IF NOT EXISTS spn_clientes_pend_idx
    ON solicitud_proceso_nuevo_clientes (estado, veces DESC);
CREATE INDEX IF NOT EXISTS spn_supervisores_pend_idx
    ON solicitud_proceso_nuevo_supervisores (estado, veces DESC);
