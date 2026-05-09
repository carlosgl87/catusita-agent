"""
Script de prueba del orquestador desde la terminal.
No requiere WhatsApp, base de datos ni Redis.

Uso:
    python test_terminal.py [vendedor|cliente]
"""
from dotenv import load_dotenv
load_dotenv()

import asyncio
import sys
from orchestrator.router import run_agent

PERFIL_ASESOR = {
    "user_id": "test-asesor-001",
    "tipo": "asesor",
    "nombre": "Luis García",
    "linea_asignada": "filtros y lubricantes",
    "nivel_acceso": "completo",
    "asesor_id": "ASE-001",
    "conversation_id": "conv-test-001",
    "autenticado": True,
}

PERFIL_CLIENTE = {
    "user_id": "test-cliente-001",
    "tipo": "cliente",
    "nombre": "Taller San Juan",
    "ruc": "20512345678",
    "nivel_acceso": "basico",
    "conversation_id": "conv-test-002",
    "autenticado": True,
}

EJEMPLOS_ASESOR = [
    "¿Cuánto stock hay del filtro FIL-OIL-001?",
    "Dame el precio neto del FIL-OIL-001 para un taller, 20 unidades",
    "¿Cuál es la situación crediticia del cliente 20512345678?",
    "Muéstrame las letras próximas a vencer esta semana",
    "¿Qué productos llevan más de 90 días en almacén?",
    "Busca filtros de aceite para Toyota Hilux",
]

EJEMPLOS_CLIENTE = [
    "¿Hay stock del filtro FIL-OIL-001?",
    "¿Cuál es el estado de mi pedido PED-2025-001234?",
    "Necesito la factura de mi pedido PED-2025-001098",
    "Quiero poner un reclamo por el pedido PED-2025-001234, llegó un producto equivocado",
    "Busca pastillas de freno para Toyota Corolla placa GHI-321",
]


async def chat_loop(perfil: dict):
    tipo = perfil["tipo"]
    ejemplos = EJEMPLOS_ASESOR if tipo == "asesor" else EJEMPLOS_CLIENTE
    historial = []

    print(f"\n{'='*60}")
    print(f"  Catu — Agente {'Vendedores' if tipo == 'asesor' else 'Clientes'}")
    print(f"  Usuario: {perfil['nombre']}")
    print(f"{'='*60}")
    print("Comandos: 'salir' para terminar, 'limpiar' para nueva conversación")
    print(f"\nEjemplos de consulta:")
    for i, ej in enumerate(ejemplos, 1):
        print(f"  {i}. {ej}")
    print()

    while True:
        try:
            entrada = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            break

        if not entrada:
            continue
        if entrada.lower() == "salir":
            print("Hasta luego.")
            break
        if entrada.lower() == "limpiar":
            historial = []
            print("Conversación reiniciada.\n")
            continue

        # Permitir seleccionar ejemplo por número
        if entrada.isdigit():
            idx = int(entrada) - 1
            if 0 <= idx < len(ejemplos):
                entrada = ejemplos[idx]
                print(f"Tú: {entrada}")

        print("Catu: ", end="", flush=True)
        try:
            respuesta = await run_agent(entrada, perfil, historial)
            print(respuesta)

            historial.append({"role": "user", "content": entrada})
            historial.append({"role": "assistant", "content": respuesta})
            # Mantener solo los últimos 10 turnos
            if len(historial) > 20:
                historial = historial[-20:]
        except Exception as e:
            print(f"[Error: {e}]")
        print()


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "vendedor"
    perfil = PERFIL_ASESOR if modo.startswith("v") else PERFIL_CLIENTE
    asyncio.run(chat_loop(perfil))
