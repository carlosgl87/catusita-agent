-- ─────────────────────────────────────────────────────────────────────────────
-- 007 — El padrón vive solo en Redis. Se caen las tablas de la 006.
-- ─────────────────────────────────────────────────────────────────────────────
--
-- La 006 creó cuatro tablas para el padrón: una por multiagente más una vista
-- consolidada para el dashboard. Era demasiada máquina para lo que resuelve.
--
-- El padrón es un mapa `numero -> multiagente` que cada agente reconstruye
-- entero al arrancar, en un segundo, leyendo su roster. No necesita historia, no
-- necesita reconciliación, y no necesita sobrevivir a un reinicio de Redis —
-- porque si Redis se reinicia, los agentes lo repueblan al arrancar.
--
-- Todo lo que la 006 agregaba (dos fechas, altas/bajas/cambios, detección de
-- choques en una tabla aparte) resolvía problemas que solo existen si el padrón
-- es un dato persistente. No lo es: es un índice derivado del roster.
--
-- La fuente de verdad sigue siendo el roster de cada uno —`vendedores`,
-- `clientes`, `supervisores`— que no se toca acá.
--
-- Queda pendiente para más adelante: la vista del dashboard, cuando haya algo
-- que mirar. Hoy los tres padrones están vacíos porque ningún worker arrancó.

DROP TABLE IF EXISTS padron_dashboard;
DROP TABLE IF EXISTS padron_vendedores;
DROP TABLE IF EXISTS padron_clientes;
DROP TABLE IF EXISTS padron_supervisores;
