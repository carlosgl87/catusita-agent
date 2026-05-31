import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SAP_BASE_URL = os.getenv("SAP_BASE_URL", "https://mock-sap-catusita-production.up.railway.app")
SAP_API_KEY = os.getenv("SAP_API_KEY", "catusita-mock-key-2024")


class SAPClient:
    def __init__(self):
        self._http = httpx.AsyncClient(
            base_url=SAP_BASE_URL,
            headers={"X-API-Key": SAP_API_KEY},
            timeout=10.0,
        )

    async def _get(self, path: str, params: dict = None) -> dict:
        """Helper para GET con manejo de errores uniforme."""
        try:
            resp = await self._http.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": f"No encontrado: {path}"}
            return {"error": f"Error del servidor SAP: {e.response.status_code}"}
        except httpx.RequestError:
            return {"error": "No se pudo conectar al servidor SAP. Inténtalo en unos minutos."}

    async def get_stock(self, sku_code: str) -> dict:
        return await self._get(f"/stock/{sku_code}")

    async def get_precios(self, sku_code: str, tipo: str = None) -> dict:
        params = {"tipo": tipo} if tipo else None
        return await self._get(f"/precios/{sku_code}", params=params)

    async def get_pedidos(self, cliente_ruc: str, estado: str = None, limite: int = None) -> dict:
        params = {}
        if estado:
            params["estado"] = estado
        if limite:
            params["limite"] = limite
        return await self._get(f"/pedidos/{cliente_ruc}", params=params or None)

    async def get_credito(self, cliente_ruc: str) -> dict:
        return await self._get(f"/credito/{cliente_ruc}")

    async def get_cobranzas(self, cliente_ruc: str, estado: str = None) -> dict:
        params = {"estado": estado} if estado else None
        return await self._get(f"/cobranzas/{cliente_ruc}", params=params)

    async def get_documentos(self, cliente_ruc: str, tipo: str = None) -> dict:
        params = {"tipo": tipo} if tipo else None
        return await self._get(f"/documentos/{cliente_ruc}", params=params)

    async def get_cliente(self, ruc: str) -> dict:
        return await self._get(f"/clientes/{ruc}")

    async def get_historial(self, cliente_ruc: str, meses: int = None) -> dict:
        params = {"meses": meses} if meses else None
        return await self._get(f"/historial/{cliente_ruc}", params=params)

    async def get_vehiculo(self, placa_o_vin: str) -> dict:
        return await self._get(f"/vehiculo/{placa_o_vin}")

    async def get_catalogo(self, q: str = None, categoria: str = None,
                            marca: str = None, con_stock: bool = None) -> dict:
        params = {}
        if q:
            params["q"] = q
        if categoria:
            params["categoria"] = categoria
        if marca:
            params["marca"] = marca
        if con_stock is not None:
            params["con_stock"] = str(con_stock).lower()
        return await self._get("/catalogo", params=params or None)

    async def get_cartera_vendedor(self, vendedor_id: str,
                                    estado: str = None, tipo: str = None) -> dict:
        params = {}
        if estado:
            params["estado"] = estado
        if tipo:
            params["tipo"] = tipo
        return await self._get(f"/vendedor/{vendedor_id}/clientes", params=params or None)


sap = SAPClient()
