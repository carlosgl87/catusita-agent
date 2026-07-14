-- Estadísticas: se enriquece chat_messages con dimensiones para filtrar/agrupar,
-- y se agrega el roster de vendedores (para "sin uso" y el filtro).

ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS vendedor_id     VARCHAR(20);
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS vendedor_nombre VARCHAR(120);
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS canal           VARCHAR(20) DEFAULT 'vendedor';
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS session_id      VARCHAR(40);
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS tipo            VARCHAR(20) DEFAULT 'texto';
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS tools           TEXT[] DEFAULT '{}';
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS latencia_ms     INTEGER;

CREATE INDEX IF NOT EXISTS idx_cm_vendedor ON chat_messages (vendedor_id, created_at);
CREATE INDEX IF NOT EXISTS idx_cm_tools    ON chat_messages USING GIN (tools);

-- Roster maestro de vendedores (para "sin uso" y el dropdown de filtro).
CREATE TABLE IF NOT EXISTS vendedores (
    vendedor_id VARCHAR(20) PRIMARY KEY,   -- SellerId (ej. "28")
    codigo      VARCHAR(20),               -- codeSeller (ej. "0051")
    nombre      VARCHAR(120),
    whatsapp    VARCHAR(40),               -- número/LID asignado
    n_clientes  INTEGER,
    activo      BOOLEAN DEFAULT true
);
