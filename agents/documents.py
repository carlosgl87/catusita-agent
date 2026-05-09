from shared.sap_client import sap


async def obtener_documentos(cliente_id: str, pedido_id: str = None,
                              tipo_doc: str = "todos", formato: str = "pdf") -> dict:
    return await sap.get_documents(cliente_id, pedido_id, tipo_doc, formato)
