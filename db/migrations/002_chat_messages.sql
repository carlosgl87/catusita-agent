-- Tabla plana para el panel de chats: un registro por mensaje, agrupado por número.
-- Independiente de conversations/messages (que fragmentan por turno). Persistente.
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numero VARCHAR(40) NOT NULL,
    rol VARCHAR(15) NOT NULL,           -- 'user' | 'assistant'
    contenido TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_numero_ts
    ON chat_messages (numero, created_at);
