CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('asesor', 'cliente')),
    whatsapp_number VARCHAR(20) UNIQUE,
    ruc VARCHAR(20) UNIQUE,
    nombre VARCHAR(100),
    linea_asignada VARCHAR(50),
    nivel_acceso VARCHAR(20) DEFAULT 'basico',
    activo BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    canal VARCHAR(20) DEFAULT 'whatsapp',
    agente_tipo VARCHAR(20) NOT NULL CHECK (agente_tipo IN ('vendedor', 'cliente')),
    numero_whatsapp VARCHAR(20),
    iniciada_at TIMESTAMP DEFAULT NOW(),
    ultima_actividad TIMESTAMP DEFAULT NOW(),
    activa BOOLEAN DEFAULT true
);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    rol VARCHAR(15) NOT NULL CHECK (rol IN ('user', 'assistant', 'tool')),
    contenido TEXT NOT NULL,
    tool_name VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numero_reclamo VARCHAR(20) UNIQUE NOT NULL,
    conversation_id UUID REFERENCES conversations(id),
    pedido_id VARCHAR(50),
    motivo TEXT,
    estado VARCHAR(20) DEFAULT 'pendiente',
    asesor_notificado BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE knowledge_base (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo VARCHAR(30),
    titulo TEXT,
    contenido TEXT,
    metadata JSONB,
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ON knowledge_base USING ivfflat (embedding vector_cosine_ops);
