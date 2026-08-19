-- ─────────────────────────────────────────────────────────────────────────────
-- 005 — Cada multiagente con SU chat_messages y SU tabla.
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Hasta ahora había UNA `chat_messages` con una columna `canal` que discriminaba
-- 'vendedor' vs 'cliente'. Es el mismo problema que ya se corrigió en
-- `conocimiento`: la frontera dependía de que ningún query se olvidara del WHERE.
--
-- Queda así:
--
--     vendedores    -> chat_messages_vendedores    + roster `vendedores`
--     clientes      -> chat_messages_clientes      + roster `clientes`
--     supervisores  -> chat_messages_supervisores  + roster `supervisores`
--
-- Cada multiagente nombra ÚNICAMENTE sus dos tablas en su `backend.py`. El de
-- clientes no tiene escrito «vendedores» en ninguna parte de su paquete.
--
-- ── `chat_messages` NO SE TOCA ───────────────────────────────────────────────
--
-- Sigue viva, con sus 585 filas y sus índices. Esta migración no la altera ni la
-- borra. Es lo que la app desplegada escribe hoy, y se queda como está.
--
-- Las 585 filas se COPIAN a chat_messages_vendedores (son todas de ese canal:
-- `canal` valía 'vendedor' en el 100%) para que el histórico no arranque vacío.
-- Quedan en las dos tablas. Qué hacer con la original cuando el código nuevo
-- tome el tráfico es una decisión aparte, y no se toma acá.


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Los rosters que faltaban
-- ─────────────────────────────────────────────────────────────────────────────
--
-- `vendedores` ya existe (38 filas, creada en 003). Faltaban los otros dos.

-- Talleres, distribuidores y consumidor final. Se identifican por RUC, que es
-- con lo que se autentican — por eso el RUC es la PK y no un id inventado.
CREATE TABLE IF NOT EXISTS clientes (
    ruc         VARCHAR(20) PRIMARY KEY,
    nombre      VARCHAR(160),
    whatsapp    VARCHAR(40),
    tipo        VARCHAR(20),            -- taller | distribuidor | final
    activo      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Jefes de venta. Todavía sin alcance definido (ver supervisores/orquestador.py):
-- la tabla existe para que su chat tenga a quién apuntar.
CREATE TABLE IF NOT EXISTS supervisores (
    supervisor_id VARCHAR(20) PRIMARY KEY,
    nombre        VARCHAR(120),
    whatsapp      VARCHAR(40),
    activo        BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMP DEFAULT NOW()
);


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Un chat_messages por multiagente
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Mismas columnas que la original, con dos diferencias:
--
--   `canal`        se cae. Valía 'vendedor' en el 100% de las filas y ahora la
--                  TABLA es el canal, así que la columna no dice nada.
--
--   el dueño       deja de ser un VARCHAR suelto y pasa a ser FK a su roster.
--                  En la original, `vendedor_id` no tenía FK: se podía guardar
--                  un mensaje de un vendedor inexistente y nadie se enteraba.

CREATE TABLE IF NOT EXISTS chat_messages_vendedores (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numero      VARCHAR(40) NOT NULL,
    rol         VARCHAR(15) NOT NULL,       -- user | assistant
    contenido   TEXT NOT NULL,
    vendedor_id VARCHAR(20) REFERENCES vendedores(vendedor_id) ON DELETE SET NULL,
    -- Copia del nombre al momento del mensaje. Redundante con el JOIN al roster
    -- a propósito: conserva el histórico de filas cuyo vendedor ya no esté.
    vendedor_nombre VARCHAR(120),
    session_id  VARCHAR(40),
    tipo        VARCHAR(20) DEFAULT 'texto',
    tools       TEXT[] DEFAULT '{}',
    latencia_ms INTEGER,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages_clientes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numero      VARCHAR(40) NOT NULL,
    rol         VARCHAR(15) NOT NULL,
    contenido   TEXT NOT NULL,
    cliente_ruc VARCHAR(20) REFERENCES clientes(ruc) ON DELETE SET NULL,
    cliente_nombre VARCHAR(160),
    session_id  VARCHAR(40),
    tipo        VARCHAR(20) DEFAULT 'texto',
    tools       TEXT[] DEFAULT '{}',
    latencia_ms INTEGER,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages_supervisores (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numero        VARCHAR(40) NOT NULL,
    rol           VARCHAR(15) NOT NULL,
    contenido     TEXT NOT NULL,
    supervisor_id VARCHAR(20) REFERENCES supervisores(supervisor_id) ON DELETE SET NULL,
    supervisor_nombre VARCHAR(120),
    session_id    VARCHAR(40),
    tipo          VARCHAR(20) DEFAULT 'texto',
    tools         TEXT[] DEFAULT '{}',
    latencia_ms   INTEGER,
    created_at    TIMESTAMP DEFAULT NOW()
);

-- Los mismos índices que tiene chat_messages, replicados por tabla.
CREATE INDEX IF NOT EXISTS cmv_numero_ts_idx   ON chat_messages_vendedores (numero, created_at);
CREATE INDEX IF NOT EXISTS cmv_vendedor_ts_idx ON chat_messages_vendedores (vendedor_id, created_at);
CREATE INDEX IF NOT EXISTS cmv_tools_idx       ON chat_messages_vendedores USING gin (tools);

CREATE INDEX IF NOT EXISTS cmc_numero_ts_idx   ON chat_messages_clientes (numero, created_at);
CREATE INDEX IF NOT EXISTS cmc_ruc_ts_idx      ON chat_messages_clientes (cliente_ruc, created_at);
CREATE INDEX IF NOT EXISTS cmc_tools_idx       ON chat_messages_clientes USING gin (tools);

CREATE INDEX IF NOT EXISTS cms_numero_ts_idx   ON chat_messages_supervisores (numero, created_at);
CREATE INDEX IF NOT EXISTS cms_sup_ts_idx      ON chat_messages_supervisores (supervisor_id, created_at);
CREATE INDEX IF NOT EXISTS cms_tools_idx       ON chat_messages_supervisores USING gin (tools);


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Copiar el histórico a la tabla de vendedores
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Solo LEE de chat_messages. No la modifica.
--
-- ON CONFLICT DO NOTHING para poder re-correr esta copia más adelante y traer
-- únicamente lo que haya entrado en el medio, sin duplicar.

INSERT INTO chat_messages_vendedores
    (id, numero, rol, contenido, vendedor_id, vendedor_nombre,
     session_id, tipo, tools, latencia_ms, created_at)
SELECT
    id, numero, rol, contenido, vendedor_id, vendedor_nombre, session_id,
    COALESCE(tipo, 'texto'), COALESCE(tools, '{}'), latencia_ms, created_at
FROM chat_messages
ON CONFLICT (id) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Repuntar las solicitudes a su propio chat
-- ─────────────────────────────────────────────────────────────────────────────
--
-- En 004 las tres `solicitud_proceso_nuevo_*` apuntaban a `chat_messages`, que
-- era el único chat que había. Ahora cada una apunta al suyo — y esa es la
-- diferencia de fondo: una solicitud de clientes no puede referenciar un mensaje
-- de vendedores ni por error de tipeo.
--
-- Las tres están vacías, así que rehacer la FK no toca ningún dato.

ALTER TABLE solicitud_proceso_nuevo_vendedores
    DROP CONSTRAINT IF EXISTS solicitud_proceso_nuevo_vendedores_mensaje_id_fkey;
ALTER TABLE solicitud_proceso_nuevo_vendedores
    ADD CONSTRAINT spn_vend_mensaje_fk
    FOREIGN KEY (mensaje_id) REFERENCES chat_messages_vendedores(id) ON DELETE SET NULL;

ALTER TABLE solicitud_proceso_nuevo_clientes
    DROP CONSTRAINT IF EXISTS solicitud_proceso_nuevo_clientes_mensaje_id_fkey;
ALTER TABLE solicitud_proceso_nuevo_clientes
    ADD CONSTRAINT spn_cli_mensaje_fk
    FOREIGN KEY (mensaje_id) REFERENCES chat_messages_clientes(id) ON DELETE SET NULL;

ALTER TABLE solicitud_proceso_nuevo_supervisores
    DROP CONSTRAINT IF EXISTS solicitud_proceso_nuevo_supervisores_mensaje_id_fkey;
ALTER TABLE solicitud_proceso_nuevo_supervisores
    ADD CONSTRAINT spn_sup_mensaje_fk
    FOREIGN KEY (mensaje_id) REFERENCES chat_messages_supervisores(id) ON DELETE SET NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- Cómo queda
-- ─────────────────────────────────────────────────────────────────────────────
--
--   vendedores ──< chat_messages_vendedores ──< solicitud_proceso_nuevo_vendedores
--                                                     └──> conocimiento_vendedores
--
--   clientes ────< chat_messages_clientes ────< solicitud_proceso_nuevo_clientes
--                                                     └──> conocimiento_clientes
--
--   supervisores < chat_messages_supervisores < solicitud_proceso_nuevo_supervisores
--                                                     └──> conocimiento_supervisores
--
--   chat_messages   intacta, aparte, sin FKs nuevas
--
-- Tres columnas verticales que no se tocan entre sí. Ninguna FK cruza de una a
-- otra: es el mismo aislamiento que ya tenían los contenedores y las colas,
-- ahora también en la base.
