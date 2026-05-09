"""
Búsqueda semántica en catálogo. En dev usa búsqueda simple por palabras clave
(sin embeddings reales) para poder probarlo sin pgvector configurado.
"""
import os
from shared.sap_client import _MOCK_PRODUCTS, _MOCK_STOCK, _MOCK_PRICES
from agents.vehicle import identificar_vehiculo

USE_MOCK = os.getenv("USE_SAP_MOCK", "true").lower() == "true"


def _keyword_search(query: str, limit: int = 5) -> list:
    query_lower = query.lower()
    terms = query_lower.split()
    scored = []
    for sku, prod in _MOCK_PRODUCTS.items():
        texto = f"{prod['descripcion']} {prod['marca']} {prod['oem']}".lower()
        score = sum(1 for t in terms if t in texto)
        if score > 0:
            stock = _MOCK_STOCK.get(sku, {"almacen_1": 0, "almacen_2": 0})
            precio = _MOCK_PRICES.get(sku, {})
            scored.append({
                "sku_code": sku,
                "descripcion": prod["descripcion"],
                "marca": prod["marca"],
                "oem": prod["oem"],
                "stock_total": stock["almacen_1"] + stock["almacen_2"],
                "precio_lista": precio.get("lista", 0),
                "relevancia": score,
            })
    scored.sort(key=lambda x: x["relevancia"], reverse=True)
    return scored[:limit]


async def buscar_catalogo(query: str, placa: str = None, vin: str = None) -> dict:
    vehiculo = None
    if placa or vin:
        vehiculo = await identificar_vehiculo(placa=placa, vin=vin)
        if "error" not in vehiculo:
            query = f"{query} {vehiculo.get('marca','')} {vehiculo.get('modelo','')} {vehiculo.get('motor','')}"

    if USE_MOCK:
        resultados = _keyword_search(query)
    else:
        # En producción: generar embedding y buscar en pgvector
        from db.connection import get_pool
        pool = await get_pool()
        # embedding = await generate_embedding(query)
        # rows = await pool.fetch(...)
        resultados = _keyword_search(query)

    return {
        "query": query,
        "vehiculo": vehiculo,
        "resultados": resultados,
        "total": len(resultados),
    }


async def obtener_equivalencias(sku_code: str = None, codigo_oem: str = None) -> dict:
    if not sku_code and not codigo_oem:
        return {"error": "Se requiere sku_code o codigo_oem"}

    if sku_code:
        prod = _MOCK_PRODUCTS.get(sku_code)
        if not prod:
            return {"error": f"SKU {sku_code} no encontrado"}
        oem_buscar = prod["oem"]
    else:
        oem_buscar = codigo_oem

    equivalentes = [
        {
            "sku_code": sku,
            "descripcion": p["descripcion"],
            "marca": p["marca"],
            "oem": p["oem"],
            "stock_total": _MOCK_STOCK.get(sku, {"almacen_1": 0, "almacen_2": 0})["almacen_1"] +
                           _MOCK_STOCK.get(sku, {"almacen_1": 0, "almacen_2": 0})["almacen_2"],
        }
        for sku, p in _MOCK_PRODUCTS.items()
        if p["oem"] == oem_buscar or (sku_code and sku != sku_code and
                                       p["descripcion"].split()[0:3] == _MOCK_PRODUCTS.get(sku_code, {}).get("descripcion", "").split()[0:3])
    ]

    return {"codigo_buscado": oem_buscar or sku_code, "equivalencias": equivalentes}


async def obtener_ficha_tecnica(sku_code: str) -> dict:
    prod = _MOCK_PRODUCTS.get(sku_code)
    if not prod:
        return {"error": f"SKU {sku_code} no encontrado"}
    return {
        "sku_code": sku_code,
        "descripcion": prod["descripcion"],
        "marca": prod["marca"],
        "codigo_oem": prod["oem"],
        "url_pdf": f"https://docs.catusita.com/fichas/{sku_code}.pdf",
        "especificaciones": {
            "marca": prod["marca"],
            "codigo_oem": prod["oem"],
            "compatible_con": "Ver ficha técnica completa en el PDF adjunto",
        },
    }
