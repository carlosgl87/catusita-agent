import os
import httpx
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

USE_MOCK = os.getenv("USE_SAP_MOCK", "true").lower() == "true"
SAP_URL = os.getenv("SAP_API_URL", "")
SAP_KEY = os.getenv("SAP_API_KEY", "")

# ---------------------------------------------------------------------------
# Datos mock — repuestos automotrices peruanos realistas
# ---------------------------------------------------------------------------

_MOCK_PRODUCTS = {
    "FIL-OIL-001": {"descripcion": "Filtro de aceite Toyota Hilux 2.4D", "marca": "Mann", "oem": "90915-YZZD2"},
    "FIL-OIL-002": {"descripcion": "Filtro de aceite Hyundai H1 2.5", "marca": "Bosch", "oem": "26300-42030"},
    "FIL-AIR-001": {"descripcion": "Filtro de aire Toyota Land Cruiser 4.0", "marca": "Sakura", "oem": "17801-0C010"},
    "FIL-AIR-002": {"descripcion": "Filtro de aire Nissan Frontier 2.5D", "marca": "Mann", "oem": "16546-EB300"},
    "FIL-FUEL-001": {"descripcion": "Filtro de combustible Mazda BT-50", "marca": "WIX", "oem": "SH01-20-490"},
    "PAD-FRT-001": {"descripcion": "Pastillas de freno delanteras Toyota Corolla", "marca": "Textar", "oem": "04465-02260"},
    "PAD-FRT-002": {"descripcion": "Pastillas de freno delanteras Kia Sportage", "marca": "Brembo", "oem": "58101-2VA10"},
    "DSC-FRT-001": {"descripcion": "Disco de freno delantero Toyota Hilux", "marca": "Bosch", "oem": "43512-0K080"},
    "BELT-TIM-001": {"descripcion": "Kit de distribución Hyundai Tucson 2.0", "marca": "Gates", "oem": "K015649XS"},
    "BELT-SER-001": {"descripcion": "Correa serpentina Toyota Yaris 1.5", "marca": "Dayco", "oem": "90916-02581"},
    "SPAR-001": {"descripcion": "Bujía NGK Iridium Toyota Land Cruiser", "marca": "NGK", "oem": "90919-01247"},
    "SPAR-002": {"descripcion": "Bujía Bosch Ford Ranger 2.5", "marca": "Bosch", "oem": "0242240593"},
    "SUSP-001": {"descripcion": "Amortiguador delantero Nissan Frontier KYB", "marca": "KYB", "oem": "343388"},
    "SUSP-002": {"descripcion": "Muñón de dirección Toyota Hilux", "marca": "Moog", "oem": "K8752T"},
    "COOL-001": {"descripcion": "Termostato Toyota 4Runner 4.0", "marca": "Gates", "oem": "90916-03087"},
    "COOL-002": {"descripcion": "Bomba de agua Hyundai Accent 1.4", "marca": "Aisin", "oem": "25100-26650"},
    "OIL-001": {"descripcion": "Aceite motor 15W40 Diesel Shell Rimula 5L", "marca": "Shell", "oem": "N/A"},
    "OIL-002": {"descripcion": "Aceite motor 5W30 Sintético Mobil 1 4L", "marca": "Mobil", "oem": "N/A"},
    "BATT-001": {"descripcion": "Batería 60Ah Bosch S4 075 Toyota Corolla", "marca": "Bosch", "oem": "0092S40750"},
    "LIGHT-001": {"descripcion": "Faro delantero Toyota Hilux 2016-2020", "marca": "TYC", "oem": "81110-0K390"},
}

_MOCK_STOCK = {
    "FIL-OIL-001": {"almacen_1": 145, "almacen_2": 83},
    "FIL-OIL-002": {"almacen_1": 62, "almacen_2": 41},
    "FIL-AIR-001": {"almacen_1": 28, "almacen_2": 15},
    "FIL-AIR-002": {"almacen_1": 34, "almacen_2": 22},
    "FIL-FUEL-001": {"almacen_1": 19, "almacen_2": 7},
    "PAD-FRT-001": {"almacen_1": 56, "almacen_2": 38},
    "PAD-FRT-002": {"almacen_1": 23, "almacen_2": 14},
    "DSC-FRT-001": {"almacen_1": 12, "almacen_2": 8},
    "BELT-TIM-001": {"almacen_1": 9, "almacen_2": 4},
    "BELT-SER-001": {"almacen_1": 31, "almacen_2": 19},
    "SPAR-001": {"almacen_1": 0, "almacen_2": 0},
    "SPAR-002": {"almacen_1": 88, "almacen_2": 54},
    "SUSP-001": {"almacen_1": 6, "almacen_2": 3},
    "SUSP-002": {"almacen_1": 4, "almacen_2": 2},
    "COOL-001": {"almacen_1": 17, "almacen_2": 9},
    "COOL-002": {"almacen_1": 11, "almacen_2": 6},
    "OIL-001": {"almacen_1": 210, "almacen_2": 180},
    "OIL-002": {"almacen_1": 95, "almacen_2": 67},
    "BATT-001": {"almacen_1": 22, "almacen_2": 11},
    "LIGHT-001": {"almacen_1": 5, "almacen_2": 2},
}

_MOCK_PRICES = {
    "FIL-OIL-001": {"lista": 28.50, "tienda": 0.72, "taller": 0.68, "consumidor": 0.82},
    "FIL-OIL-002": {"lista": 32.00, "tienda": 0.71, "taller": 0.67, "consumidor": 0.80},
    "FIL-AIR-001": {"lista": 45.00, "tienda": 0.73, "taller": 0.69, "consumidor": 0.83},
    "FIL-AIR-002": {"lista": 38.50, "tienda": 0.72, "taller": 0.68, "consumidor": 0.82},
    "FIL-FUEL-001": {"lista": 22.00, "tienda": 0.71, "taller": 0.67, "consumidor": 0.80},
    "PAD-FRT-001": {"lista": 95.00, "tienda": 0.68, "taller": 0.65, "consumidor": 0.78},
    "PAD-FRT-002": {"lista": 110.00, "tienda": 0.69, "taller": 0.65, "consumidor": 0.79},
    "DSC-FRT-001": {"lista": 145.00, "tienda": 0.67, "taller": 0.63, "consumidor": 0.77},
    "BELT-TIM-001": {"lista": 185.00, "tienda": 0.70, "taller": 0.66, "consumidor": 0.80},
    "BELT-SER-001": {"lista": 48.00, "tienda": 0.72, "taller": 0.68, "consumidor": 0.82},
    "SPAR-001": {"lista": 18.50, "tienda": 0.73, "taller": 0.69, "consumidor": 0.83},
    "SPAR-002": {"lista": 12.00, "tienda": 0.72, "taller": 0.68, "consumidor": 0.82},
    "SUSP-001": {"lista": 220.00, "tienda": 0.66, "taller": 0.62, "consumidor": 0.76},
    "SUSP-002": {"lista": 165.00, "tienda": 0.67, "taller": 0.63, "consumidor": 0.77},
    "COOL-001": {"lista": 35.00, "tienda": 0.71, "taller": 0.67, "consumidor": 0.81},
    "COOL-002": {"lista": 85.00, "tienda": 0.69, "taller": 0.65, "consumidor": 0.79},
    "OIL-001": {"lista": 68.00, "tienda": 0.74, "taller": 0.70, "consumidor": 0.85},
    "OIL-002": {"lista": 95.00, "tienda": 0.73, "taller": 0.69, "consumidor": 0.84},
    "BATT-001": {"lista": 380.00, "tienda": 0.68, "taller": 0.64, "consumidor": 0.78},
    "LIGHT-001": {"lista": 245.00, "tienda": 0.67, "taller": 0.63, "consumidor": 0.77},
}

# Factor de descuento por volumen aplicado sobre precio neto
_VOLUME_SCALE = [
    {"desde": 1,  "hasta": 9,   "descuento_adicional": 0.00},
    {"desde": 10, "hasta": 24,  "descuento_adicional": 0.02},
    {"desde": 25, "hasta": 49,  "descuento_adicional": 0.04},
    {"desde": 50, "hasta": 999, "descuento_adicional": 0.06},
]

_MOCK_ORDERS = {
    "PED-2025-001234": {
        "estado": "en_despacho",
        "cliente_ruc": "20512345678",
        "almacen_salida": "Miraflores",
        "guia_numero": "T001-00045231",
        "hora_salida": "2025-05-09T09:30:00",
        "entrega_estimada": "2025-05-09T14:00:00",
        "items": [{"sku": "FIL-OIL-001", "cantidad": 10}, {"sku": "PAD-FRT-001", "cantidad": 4}],
    },
    "PED-2025-001180": {
        "estado": "preparando",
        "cliente_ruc": "20601234567",
        "almacen_salida": "Ate",
        "guia_numero": None,
        "hora_salida": None,
        "entrega_estimada": "2025-05-09T17:00:00",
        "items": [{"sku": "BELT-TIM-001", "cantidad": 2}],
    },
    "PED-2025-001098": {
        "estado": "entregado",
        "cliente_ruc": "20512345678",
        "almacen_salida": "Miraflores",
        "guia_numero": "T001-00044890",
        "hora_salida": "2025-05-08T10:00:00",
        "entrega_estimada": "2025-05-08T15:00:00",
        "items": [{"sku": "OIL-001", "cantidad": 20}],
    },
}

_MOCK_CREDIT = {
    "20512345678": {
        "nombre": "Taller San Juan SRL",
        "limite_credito": 15000.00,
        "deuda_actual": 4850.00,
        "disponible": 10150.00,
        "maximo_18_meses": 15000.00,
        "letras_pendientes": [
            {"numero": "LET-2025-0412", "monto": 2400.00, "fecha_vcto": "2025-05-15", "estado": "pendiente"},
            {"numero": "LET-2025-0389", "monto": 2450.00, "fecha_vcto": "2025-05-30", "estado": "pendiente"},
        ],
        "calificacion_pago": "B+",
    },
    "20601234567": {
        "nombre": "Auto Repuestos Lima SAC",
        "limite_credito": 25000.00,
        "deuda_actual": 8200.00,
        "disponible": 16800.00,
        "maximo_18_meses": 25000.00,
        "letras_pendientes": [
            {"numero": "LET-2025-0401", "monto": 4100.00, "fecha_vcto": "2025-05-12", "estado": "vencido"},
            {"numero": "LET-2025-0402", "monto": 4100.00, "fecha_vcto": "2025-06-12", "estado": "pendiente"},
        ],
        "calificacion_pago": "C",
    },
}

_MOCK_DOCUMENTS = {
    "20512345678": [
        {
            "tipo": "factura", "numero": "F001-00089234", "pedido": "PED-2025-001098",
            "fecha": "2025-05-08", "monto": 1360.00, "estado_pago": "pendiente",
            "url_pdf": "https://docs.catusita.com/pdf/F001-00089234.pdf",
            "url_xml": "https://docs.catusita.com/xml/F001-00089234.xml",
        },
        {
            "tipo": "guia", "numero": "T001-00044890", "pedido": "PED-2025-001098",
            "fecha": "2025-05-08", "monto": 0, "estado_pago": "N/A",
            "url_pdf": "https://docs.catusita.com/pdf/T001-00044890.pdf",
            "url_xml": None,
        },
    ],
    "20601234567": [
        {
            "tipo": "factura", "numero": "F001-00089100", "pedido": "PED-2025-001180",
            "fecha": "2025-05-07", "monto": 370.00, "estado_pago": "pagado",
            "url_pdf": "https://docs.catusita.com/pdf/F001-00089100.pdf",
            "url_xml": "https://docs.catusita.com/xml/F001-00089100.xml",
        },
    ],
}

_MOCK_COLLECTIONS = {
    "ASE-001": {
        "asesor_nombre": "Luis García",
        "total_por_cobrar": 45800.00,
        "vencido": 4100.00,
        "al_dia": 41700.00,
        "letras": [
            {"cliente": "Auto Repuestos Lima SAC", "ruc": "20601234567", "monto": 4100.00,
             "fecha_vcto": "2025-05-12", "estado": "vencido", "dias_vcto": -3},
            {"cliente": "Taller San Juan SRL", "ruc": "20512345678", "monto": 2400.00,
             "fecha_vcto": "2025-05-15", "estado": "pendiente", "dias_vcto": 0},
            {"cliente": "Repuestos del Norte EIRL", "ruc": "20487654321", "monto": 3200.00,
             "fecha_vcto": "2025-05-20", "estado": "pendiente", "dias_vcto": 5},
        ],
    },
}


def _volume_discount(cantidad: int) -> float:
    for tier in _VOLUME_SCALE:
        if tier["desde"] <= cantidad <= tier["hasta"]:
            return tier["descuento_adicional"]
    return 0.0


class SAPClient:
    def __init__(self):
        self._http = None if USE_MOCK else httpx.AsyncClient(
            base_url=SAP_URL,
            headers={"X-API-Key": SAP_KEY},
            timeout=10.0,
        )

    # ------------------------------------------------------------------
    async def get_stock(self, sku_code: str, almacen_id: int = 0) -> dict:
        if USE_MOCK:
            return self._mock_stock(sku_code, almacen_id)
        resp = await self._http.get(f"/stock/{sku_code}", params={"almacen": almacen_id})
        resp.raise_for_status()
        return resp.json()

    def _mock_stock(self, sku_code: str, almacen_id: int) -> dict:
        prod = _MOCK_PRODUCTS.get(sku_code)
        if not prod:
            return {"error": f"SKU {sku_code} no encontrado"}
        s = _MOCK_STOCK.get(sku_code, {"almacen_1": 0, "almacen_2": 0})
        if almacen_id == 1:
            total = s["almacen_1"]
        elif almacen_id == 2:
            total = s["almacen_2"]
        else:
            total = s["almacen_1"] + s["almacen_2"]
        return {
            "sku_code": sku_code,
            "descripcion": prod["descripcion"],
            "marca": prod["marca"],
            "almacen_miraflores": s["almacen_1"],
            "almacen_ate": s["almacen_2"],
            "total": total,
            "bajo_stock": total < 10,
        }

    # ------------------------------------------------------------------
    async def get_prices(self, sku_code: str, tipo_cliente: str,
                         asesor_id: str = None, cantidad: int = 1,
                         zona: str = None) -> dict:
        if USE_MOCK:
            return self._mock_prices(sku_code, tipo_cliente, cantidad, zona)
        resp = await self._http.get(f"/prices/{sku_code}", params={
            "tipo_cliente": tipo_cliente, "asesor_id": asesor_id,
            "cantidad": cantidad, "zona": zona,
        })
        resp.raise_for_status()
        return resp.json()

    def _mock_prices(self, sku_code: str, tipo_cliente: str, cantidad: int, zona: str) -> dict:
        prod = _MOCK_PRODUCTS.get(sku_code)
        if not prod:
            return {"error": f"SKU {sku_code} no encontrado"}
        p = _MOCK_PRICES.get(sku_code, {"lista": 0, "tienda": 0.75, "taller": 0.70, "consumidor": 0.85})
        factor = p.get(tipo_cliente, p["taller"])
        precio_neto = round(p["lista"] * factor, 2)
        vol_desc = _volume_discount(cantidad)
        precio_vol = round(precio_neto * (1 - vol_desc), 2)
        factor_zona = 1.04 if zona and zona.lower() == "provincia" else 1.0
        precio_zona = round(precio_vol * factor_zona, 2)
        descuento_pct = round((1 - factor) * 100, 1)
        escala = []
        for tier in _VOLUME_SCALE:
            base = p["lista"] * factor * (1 - tier["descuento_adicional"]) * factor_zona
            escala.append({
                "desde": tier["desde"],
                "hasta": tier["hasta"] if tier["hasta"] < 999 else "+",
                "precio_unitario": round(base, 2),
            })
        return {
            "sku_code": sku_code,
            "descripcion": prod["descripcion"],
            "precio_lista": p["lista"],
            "precio_neto": precio_neto,
            "descuento_pct": descuento_pct,
            "precio_cantidad": precio_zona,
            "zona": zona or "Lima",
            "escala_volumenes": escala,
        }

    # ------------------------------------------------------------------
    async def get_order_status(self, pedido_id: str = None, ruc_cliente: str = None) -> dict:
        if USE_MOCK:
            return self._mock_order(pedido_id, ruc_cliente)
        params = {}
        if pedido_id:
            params["pedido_id"] = pedido_id
        if ruc_cliente:
            params["ruc"] = ruc_cliente
        resp = await self._http.get("/orders/status", params=params)
        resp.raise_for_status()
        return resp.json()

    def _mock_order(self, pedido_id: str, ruc_cliente: str) -> dict:
        if pedido_id:
            o = _MOCK_ORDERS.get(pedido_id)
            if not o:
                return {"error": f"Pedido {pedido_id} no encontrado"}
            return {"pedido_id": pedido_id, **o}
        if ruc_cliente:
            results = [
                {"pedido_id": pid, **data}
                for pid, data in _MOCK_ORDERS.items()
                if data["cliente_ruc"] == ruc_cliente
            ]
            return {"pedidos": results} if results else {"error": f"No hay pedidos para RUC {ruc_cliente}"}
        return {"error": "Se requiere pedido_id o ruc_cliente"}

    # ------------------------------------------------------------------
    async def get_credit(self, cliente_id: str, meses_historial: int = 18) -> dict:
        if USE_MOCK:
            c = _MOCK_CREDIT.get(cliente_id)
            return c if c else {"error": f"Cliente {cliente_id} no encontrado"}
        resp = await self._http.get(f"/credit/{cliente_id}", params={"meses": meses_historial})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    async def get_documents(self, cliente_id: str, pedido_id: str = None,
                            tipo_doc: str = "todos", formato: str = "pdf") -> dict:
        if USE_MOCK:
            docs = _MOCK_DOCUMENTS.get(cliente_id, [])
            if pedido_id:
                docs = [d for d in docs if d.get("pedido") == pedido_id]
            if tipo_doc != "todos":
                docs = [d for d in docs if d["tipo"] == tipo_doc]
            if formato == "pdf":
                docs = [{k: v for k, v in d.items() if k != "url_xml"} for d in docs]
            elif formato == "xml":
                docs = [{k: v for k, v in d.items() if k != "url_pdf"} for d in docs]
            return {"documentos": docs}
        resp = await self._http.get(f"/documents/{cliente_id}", params={
            "pedido_id": pedido_id, "tipo": tipo_doc, "formato": formato,
        })
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    async def get_restock_date(self, sku_code: str) -> dict:
        if USE_MOCK:
            prod = _MOCK_PRODUCTS.get(sku_code)
            if not prod:
                return {"error": f"SKU {sku_code} no encontrado"}
            s = _MOCK_STOCK.get(sku_code, {"almacen_1": 0, "almacen_2": 0})
            total = s["almacen_1"] + s["almacen_2"]
            fecha_ingreso = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            return {
                "sku_code": sku_code,
                "descripcion": prod["descripcion"],
                "stock_actual": total,
                "lotes_en_transito": [
                    {"cantidad": 50, "fecha_estimada": fecha_ingreso, "origen": "China"},
                ],
            }
        resp = await self._http.get(f"/stock/{sku_code}/restock")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    async def get_stock_aging(self, almacen_id: int = 0, dias_minimos: int = 90) -> dict:
        if USE_MOCK:
            items = [
                {"sku_code": "SUSP-002", "descripcion": "Muñón de dirección Toyota Hilux",
                 "almacen": "Miraflores", "cantidad": 4, "dias_en_almacen": 124},
                {"sku_code": "LIGHT-001", "descripcion": "Faro delantero Toyota Hilux",
                 "almacen": "Ate", "cantidad": 2, "dias_en_almacen": 112},
                {"sku_code": "BELT-TIM-001", "descripcion": "Kit de distribución Hyundai Tucson",
                 "almacen": "Miraflores", "cantidad": 3, "dias_en_almacen": 98},
            ]
            if almacen_id == 1:
                items = [i for i in items if i["almacen"] == "Miraflores"]
            elif almacen_id == 2:
                items = [i for i in items if i["almacen"] == "Ate"]
            items = [i for i in items if i["dias_en_almacen"] >= dias_minimos]
            return {"items": items, "almacen_filtro": almacen_id, "dias_minimos": dias_minimos}
        resp = await self._http.get("/stock/aging", params={"almacen": almacen_id, "dias_min": dias_minimos})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    async def get_collections_report(self, asesor_id: str, semana: str = None) -> dict:
        if USE_MOCK:
            data = _MOCK_COLLECTIONS.get(asesor_id)
            return data if data else {"error": f"Asesor {asesor_id} no encontrado en cobranzas"}
        resp = await self._http.get(f"/collections/{asesor_id}", params={"semana": semana})
        resp.raise_for_status()
        return resp.json()


sap = SAPClient()
