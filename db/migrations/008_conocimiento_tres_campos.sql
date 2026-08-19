-- 008 — El RAG de procesos pasa de 4 campos a 3.
--
-- La 004 dejó `titulo`, `cuando`, `pasos` y `entrega`. Son cuatro donde
-- alcanzan tres, y la separación entre `pasos` y `entrega` sobra: al agente le
-- tiene que llegar UN procedimiento listo para ejecutar, no dos mitades que
-- alguien arma después.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- Los tres campos y qué hace cada uno
-- ─────────────────────────────────────────────────────────────────────────────
--
--   descripcion     Cómo lo PIDE el usuario. Su frase, con sus palabras.
--                   Es lo único que se embebe y lo único contra lo que se busca.
--
--   proceso         Qué significa eso para un vendedor de Catusita. El nombre
--                   interno de la situación, en el idioma de la empresa.
--
--   procedimiento   Qué hacer. Completo: qué áreas llamar, qué pedirle a cada
--                   una, y cómo se le responde al usuario.
--
-- La división no es cosmética: `descripcion` y `proceso` dicen LO MISMO en dos
-- idiomas distintos, y por eso hay dos columnas.
--
--     descripcion   "me llegó todo abollado, ¿qué hago?"
--     proceso       "Devolución por daño en transporte"
--
-- Buscar contra el segundo no funciona: nadie escribe «devolución por daño en
-- transporte» cuando le llegó una caja rota. Se mide y se nota — redactar el
-- campo embebido en idioma de manual bajó la similitud de 0.463 a 0.390 en la
-- misma consulta.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- Qué tiene que decir `procedimiento`
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Instrucciones de orquestación, no prosa. El orquestador no ejecuta tools:
-- delega en áreas pasándoles una consulta. Entonces el procedimiento se escribe
-- en esos términos:
--
--     1. Pedile a `pedidos` el estado y la guía con el número de pedido.
--     2. Si figura entregado, pedile a `facturacion` el PDF de la factura.
--     3. Contestá con el número de caso y los días hábiles.
--        NUNCA prometas una fecha exacta de reposición.
--
-- Así el procedimiento sobrevive a que cambien las tools de un área: nombra
-- áreas, que son estables, y no `consultar_stock`, que no lo es.
--
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Las tres tablas están vacías, así que no hay datos que migrar. Se renombra en
-- vez de recrear para no perder los índices HNSW ni las FK de las solicitudes.

-- ── vendedores ───────────────────────────────────────────────────────────────
ALTER TABLE conocimiento_vendedores RENAME COLUMN cuando TO descripcion;
ALTER TABLE conocimiento_vendedores RENAME COLUMN titulo TO proceso;
ALTER TABLE conocimiento_vendedores RENAME COLUMN pasos  TO procedimiento;
ALTER TABLE conocimiento_vendedores DROP COLUMN entrega;

-- ── clientes ─────────────────────────────────────────────────────────────────
ALTER TABLE conocimiento_clientes RENAME COLUMN cuando TO descripcion;
ALTER TABLE conocimiento_clientes RENAME COLUMN titulo TO proceso;
ALTER TABLE conocimiento_clientes RENAME COLUMN pasos  TO procedimiento;
ALTER TABLE conocimiento_clientes DROP COLUMN entrega;

-- ── supervisores ─────────────────────────────────────────────────────────────
ALTER TABLE conocimiento_supervisores RENAME COLUMN cuando TO descripcion;
ALTER TABLE conocimiento_supervisores RENAME COLUMN titulo TO proceso;
ALTER TABLE conocimiento_supervisores RENAME COLUMN pasos  TO procedimiento;
ALTER TABLE conocimiento_supervisores DROP COLUMN entrega;

-- Los índices de texto nombran las columnas viejas: hay que rehacerlos.
DROP INDEX IF EXISTS conocimiento_vendedores_txt_idx;
DROP INDEX IF EXISTS conocimiento_clientes_txt_idx;
DROP INDEX IF EXISTS conocimiento_supervisores_txt_idx;

CREATE INDEX conocimiento_vendedores_txt_idx ON conocimiento_vendedores
    USING gin (to_tsvector('spanish', proceso || ' ' || descripcion));
CREATE INDEX conocimiento_clientes_txt_idx ON conocimiento_clientes
    USING gin (to_tsvector('spanish', proceso || ' ' || descripcion));
CREATE INDEX conocimiento_supervisores_txt_idx ON conocimiento_supervisores
    USING gin (to_tsvector('spanish', proceso || ' ' || descripcion));

-- El índice de texto ya NO incluye `procedimiento`, a diferencia del anterior
-- que indexaba `pasos`. Es a propósito: la búsqueda —vectorial o por texto—
-- tiene que dar con la SITUACIÓN, y buscar dentro de los pasos hace que un
-- proceso aparezca porque menciona «factura» aunque trate de otra cosa.
