"""Recepción — la puerta de entrada.

    WhatsApp ──► recepcion ──► cola ──► vendedores | clientes | supervisores

Es el cuarto servicio y el único que mira a internet. Los tres multiagentes no
tienen puerto abierto: solo leen de su cola.

── Qué hace ───────────────────────────────────────────────────────────────────

    webhook.py     recibe de WAHA, valida el token, descarta duplicados
    router.py      decide a qué multiagente va — manda el padrón, falla a `clientes`
    padron.py      lee `numero -> multiagente` de Redis, que publican los agentes
    acumulador.py  junta los fragmentos de un mismo turno antes de encolar
    main.py        drena los turnos vencidos y devuelve las respuestas
    waha.py        lo único que le habla a WhatsApp

── Qué NO hace ────────────────────────────────────────────────────────────────

No corre agentes. No toca Postgres. No sabe qué es un SKU, un RUC ni una
cartera. Si mañana se cambia WhatsApp por otro canal, solo cambia este servicio.

── Por qué existe separado ────────────────────────────────────────────────────

WAHA espera un 200 en milisegundos y una corrida del agente tarda segundos. En
el mismo proceso, WAHA da el webhook por caído, reintenta, y cada reintento
dispara otra corrida. Esa es la única frontera de proceso del sistema, y esta es
la de este lado.
"""
