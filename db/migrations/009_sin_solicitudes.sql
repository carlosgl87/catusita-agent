-- 009 — Se van las tablas de solicitudes.
--
-- La 004 creó `solicitud_proceso_nuevo_{vendedores,clientes,supervisores}`: el
-- agente abría un ticket solo cuando el RAG no encontraba proceso para una
-- consulta.
--
-- ── Por qué se cae la idea ───────────────────────────────────────────────────
--
-- El nodo `contexto` corre en TODOS los turnos, y la mayoría no necesitan
-- ningún procedimiento. Medido sobre mensajes reales de conversación:
--
--     "hola"  "gracias, buen dia"  "ok dale"  "buenas"  "jajaja"  "si"
--         -> 7 mensajes, 7 tickets abiertos
--
-- Cada saludo quedaba registrado como una carencia de proceso. La lista existía
-- para poder priorizar qué procedimiento escribir, y con ese ruido dejaba de
-- ser legible en el primer día de uso.
--
-- Se podía filtrar —esperar al final del turno y abrir el ticket solo si el
-- orquestador había delegado en un área— pero eso es detectar carencias mirando
-- un mensaje a la vez, que es la peor posición para hacerlo. Ese análisis se
-- hace sobre las conversaciones completas y fuera del camino de la respuesta.
--
-- ── Qué queda en su lugar ────────────────────────────────────────────────────
--
-- Nada, del lado del agente. Si el RAG no encuentra un proceso confiable,
-- `conocimiento` contesta "No hay ningún proceso escrito para esto" y el
-- orquestador atiende igual, con sus áreas y su criterio. No escribe nada.
--
-- Los procesos siguen entrando por `backend.cargar()`, que es una acción
-- humana. El sistema nunca se escribe sus propios procedimientos.
--
-- Las tres tablas están vacías: nunca corrieron en producción.

DROP TABLE IF EXISTS solicitud_proceso_nuevo_vendedores;
DROP TABLE IF EXISTS solicitud_proceso_nuevo_clientes;
DROP TABLE IF EXISTS solicitud_proceso_nuevo_supervisores;
