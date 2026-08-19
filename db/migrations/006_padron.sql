-- ─────────────────────────────────────────────────────────────────────────────
-- 006 — El padrón. Tres, uno por multiagente. Más el del dashboard.
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Cada multiagente tiene SU padrón: los números que le pertenecen. Los saca de
-- su propio roster y nadie más los toca.
--
--     vendedores    →  padron_vendedores
--     clientes      →  padron_clientes
--     supervisores  →  padron_supervisores
--
-- Y aparte, independiente de las tres, la vista del dashboard:
--
--     padron_dashboard
--
-- Cada agente la refresca al arrancar su contenedor. No es de nadie: es donde
-- se mira todo junto sin tener que abrir tres tablas.


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. El padrón de cada multiagente
-- ─────────────────────────────────────────────────────────────────────────────
--
-- `numero` es PK dentro de cada tabla: un número no puede estar dos veces en el
-- mismo padrón. Que esté en dos padrones distintos SÍ es posible — son tablas
-- separadas y ninguna sabe de la otra. Eso se detecta en `padron_dashboard`,
-- que es donde las tres se ven juntas.
--
-- Se guarda el id del roster (`vendedor_id`, `ruc`, `supervisor_id`) para poder
-- volver a la fila de origen sin adivinar por nombre.

CREATE TABLE IF NOT EXISTS padron_vendedores (
    numero         VARCHAR(40) PRIMARY KEY,
    vendedor_id    VARCHAR(20) REFERENCES vendedores(vendedor_id) ON DELETE CASCADE,
    nombre         VARCHAR(160),
    -- Se refresca en cada publicación. Una fila vieja = el agente dejó de
    -- publicar, o el número dejó de estar en el roster y no se limpió.
    actualizado_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS padron_clientes (
    numero         VARCHAR(40) PRIMARY KEY,
    ruc            VARCHAR(20) REFERENCES clientes(ruc) ON DELETE CASCADE,
    nombre         VARCHAR(160),
    actualizado_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS padron_supervisores (
    numero         VARCHAR(40) PRIMARY KEY,
    supervisor_id  VARCHAR(20) REFERENCES supervisores(supervisor_id) ON DELETE CASCADE,
    nombre         VARCHAR(160),
    actualizado_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ON DELETE CASCADE y no SET NULL: si das de baja del roster, el número deja de
-- pertenecerle. Un padrón con filas huérfanas mandaría mensajes a un agente que
-- ya no reconoce a esa persona.


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. El padrón del dashboard
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Independiente de las tres. No la lee ningún agente y no la usa el ruteo: es
-- para MIRAR. Cada contenedor la refresca al arrancar, con su parte.
--
-- La PK es (numero, multiagente) y no solo `numero`, a propósito: si el mismo
-- número está en dos padrones, acá aparecen LAS DOS FILAS. Con `numero` solo,
-- la segunda se rechazaría y el problema quedaría invisible.
--
-- Esta tabla no impide el choque — lo MUESTRA. Que es lo que se le pide a un
-- dashboard.

CREATE TABLE IF NOT EXISTS padron_dashboard (
    numero         VARCHAR(40) NOT NULL,
    multiagente    VARCHAR(20) NOT NULL,
    nombre         VARCHAR(160),
    -- Cuándo arrancó por última vez el contenedor que publicó esta fila.
    actualizado_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (numero, multiagente),
    CONSTRAINT padron_dashboard_ma_chk
        CHECK (multiagente IN ('vendedores', 'clientes', 'supervisores'))
);

CREATE INDEX IF NOT EXISTS padron_dash_ma_idx  ON padron_dashboard (multiagente);
CREATE INDEX IF NOT EXISTS padron_dash_act_idx ON padron_dashboard (actualizado_at);


-- ── Las dos consultas que justifican esta tabla ──────────────────────────────
--
-- Números reclamados por más de un multiagente (deberían ser cero):
--
--     SELECT numero, COUNT(*) n, array_agg(multiagente) quienes
--       FROM padron_dashboard
--      GROUP BY numero HAVING COUNT(*) > 1;
--
-- Agentes que dejaron de publicar (contenedor caído o sin reiniciar):
--
--     SELECT multiagente, MAX(actualizado_at) ultima, COUNT(*) numeros
--       FROM padron_dashboard
--      GROUP BY multiagente;


-- ── Cómo publica cada agente, al arrancar ────────────────────────────────────
--
--   1. Su padrón, desde su roster:
--
--        INSERT INTO padron_vendedores (numero, vendedor_id, nombre)
--        SELECT whatsapp, vendedor_id, nombre FROM vendedores
--         WHERE activo AND whatsapp IS NOT NULL AND whatsapp <> ''
--        ON CONFLICT (numero) DO UPDATE
--           SET vendedor_id = EXCLUDED.vendedor_id,
--               nombre      = EXCLUDED.nombre,
--               actualizado_at = NOW();
--
--        DELETE FROM padron_vendedores
--         WHERE numero <> ALL(<los que acaba de publicar>);
--
--   2. Su parte del dashboard — borra la suya y la reescribe. Solo la suya:
--
--        DELETE FROM padron_dashboard WHERE multiagente = 'vendedores';
--        INSERT INTO padron_dashboard (numero, multiagente, nombre)
--        SELECT numero, 'vendedores', nombre FROM padron_vendedores;
--
--   3. Espejo a Redis, que es lo que el router consulta en caliente.
--
-- El orden importa: Postgres primero, Redis después. Si el proceso muere en el
-- medio, Redis queda viejo y se corrige en la próxima publicación. Al revés,
-- Redis afirmaría algo que la fuente de verdad no respalda.
