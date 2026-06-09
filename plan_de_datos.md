# Plan de Datos — Hacer que el Mock SAP "obedezca" al QA

> Objetivo: que los datos del **Mock SAP** (`mockup-catusita`) garanticen, de forma
> **fija y reproducible**, todos los escenarios que exigen `QA_agente.md`,
> `plan_de_prueba.md` y la validación de cartera de `plan_de_implementacion.md`.
>
> Resultado final: un set de datos "congelado" que se le entrega al **QA humano** sin
> placeholders, y que no cambia entre reinicios del deploy.

---

## 1. El problema con los datos de hoy

Los datos viven **en memoria**, generados con `Faker(seed=42)` al arrancar
([mockup-catusita/data/seed.py](../mockup-catusita/data/seed.py)). Son deterministas, pero
son **aleatorios dentro de la semilla**: nadie eligió a propósito qué clientes, productos o
letras existen. Eso provoca que el QA no sea fiable:

| Escenario que el QA necesita | ¿Garantizado hoy? |
|------------------------------|-------------------|
| Un cliente llamado **"Transportes Andinos SAC"** (lo nombra el QA, línea 5) | ❌ No existe |
| Un cliente **de la cartera de V001** con datos conocidos | ⚠️ Existe pero con RUC/nombre aleatorio, hay que "descubrirlo" |
| Un cliente **que NO es de V001** (para probar el rechazo) | ⚠️ Hay que buscar uno de V002 a mano |
| Un producto **marca Fram, filtro de aceite, para Toyota Hilux** (QA línea 20) | ❌ Las marcas del mock son ACDelco, Bosch, Monroe… no Fram |
| Un producto **agotado** (stock = 0) conocido | ⚠️ Puede haber, pero no uno fijo/memorable |
| Una letra **que venza ESTA semana** | ❌ Los vencimientos son aleatorios; puede que ninguno caiga esta semana |
| Un cliente **con deuda vencida** y otro **al día** | ⚠️ Aleatorio |
| Equivalencia por **código OEM** (QA línea 24) | ❌ El mock no tiene códigos OEM |

**Conclusión:** hay que inyectar un conjunto pequeño de **datos ancla ("golden fixtures")**
con identificadores fijos y memorables, anclados a V001/V002, con fechas **relativas a hoy**
para que "esta semana" siempre se cumpla.

---

## 2. Estrategia

1. **No tocar la generación Faker existente** (los 200 clientes, 150 productos, etc. se quedan
   como ruido de fondo realista).
2. **Añadir un módulo de fixtures** `data/fixtures_qa.py` que, al final del `seed.py`, **agrega
   y/o sobre-escribe** registros con IDs fijos y los engancha a los índices.
3. **Anclar todo a V001** (el asesor de prueba, Luis García, `vendedor_id=V001`) y dejar **un
   cliente en V002** como "ajeno".
4. **Fechas relativas a `HOY`** (`date.today()`): las letras "por vencer esta semana" se calculan
   como `HOY + 3 días`, las "vencidas" como `HOY - X días`. Así el QA pasa cualquier día que se corra.
5. **Documentar el mapeo** fixture → caso de prueba, y generar el entregable `datos_qa.md` para el
   QA humano.

---

## 3. Catálogo de datos ancla (lo que hay que crear)

Valores fijos propuestos (memorables, sin colisión con Faker que usa RUCs aleatorios):

### 3.1 Clientes

| ID lógico | RUC (fijo) | Razón social | Vendedor | Estado | Para qué caso QA |
|-----------|-----------|--------------|----------|--------|------------------|
| `CLI_MIO_A` | `20100000001` | **Transportes Andinos SAC** | **V001** | activo | CA-2, CC-1, CC-3, PR-1, PD-1, AL-3 (cliente nombrado por el QA) |
| `CLI_MIO_B` | `20100000002` | Taller Mecánico Aguilar SAC | **V001** | activo | CC-2 (letra por vencer esta semana), CC-4 (deuda vencida) |
| `CLI_MIO_C` | `20100000003` | Distribuidora Repuestos Lima SAC | **V001** | activo | Cliente "al día" (sin deuda vencida) para contraste |
| `CLI_AJENO` | `20900000009` | Importadora del Sur SAC | **V002** | activo | CA-3, AL-2 (cliente que NO es de V001 → rechazo) |

> El RUC `20900000009` queda en la cartera de **V002**, NO de V001 — ese es el corazón del test de
> control de acceso. Además, "cliente 12345" (QA línea 6) se prueba como **id inválido/desconocido**.

### 3.2 Productos

| ID lógico | SKU (fijo) | Nombre | Stock | Compatibilidad | Para qué caso QA |
|-----------|-----------|--------|-------|----------------|------------------|
| `PROD_FRAM` | `FIL-FRA-0001` | Filtro de aceite Fram | 120 | Toyota (incl. Hilux) | SP-1 (filtro Fram para Toyota Hilux) |
| `PROD_OK` | `FIL-BOC-0001` | Filtro de aceite Bosch | 85 | Toyota, Nissan | SP-2 (stock conocido), PR-1 (precio lista) |
| `PROD_AGOTADO` | `FRE-BEN-0001` | Pastilla de freno Bendix | **0** | Toyota, Hyundai | SP-4 (reabastecimiento de agotado → derivar) |
| `PROD_OEM` | `FIL-FRA-0001` | (mismo Fram, con campo `oem`) | 120 | — | SP-5 (equivalencia por OEM) |

> Para `PROD_FRAM` hay que **añadir "Fram" a la lista de marcas** del mock (`MARCAS` /
> `MARCA_ABREV` en seed.py) o crearlo como fixture suelto con su SKU ya formado.
> Para `PROD_OEM` (SP-5) ver la sección 5 (ajuste de código opcional).

### 3.3 Vehículo (para placa/VIN)

| ID lógico | Placa (fija) | Marca/Modelo/Año | Propietario | Para qué caso QA |
|-----------|-------------|------------------|-------------|------------------|
| `VEH_HILUX` | `ABC-123` | Toyota Hilux 2019 | `CLI_MIO_A` | SP-1, identificar_vehiculo, buscar_catalogo con placa |

### 3.4 Pedidos y documentos (de `CLI_MIO_A` = Transportes Andinos SAC)

| ID lógico | pedido_id (fijo) | Estado | Factura / Guía | Para qué caso QA |
|-----------|------------------|--------|----------------|------------------|
| `PED_ENTREGADO` | `PED-000001` | entregado | `F001-000001` / `T001-000001` | PD-2, PD-5 (facturado), PG-1 (pagado), DO-1, DO-2 |
| `PED_TRANSITO` | `PED-000002` | en_transito | `F001-000002` / `T001-000002` | PD-1, PD-3 (ETA), PG-2 (pendiente) |

> Conviene crear **5 pedidos** para `CLI_MIO_A` para que "últimos 5 pedidos" (PD-1) tenga sentido.

### 3.5 Letras / cobranzas

| ID lógico | Cliente | Monto | Vencimiento | Estado | Para qué caso QA |
|-----------|---------|-------|-------------|--------|------------------|
| `LET_VENCIDA` | `CLI_MIO_B` | 4 500 | `HOY - 10 días` | vencida | CC-4 (deuda vencida), AL/derivación |
| `LET_ESTA_SEMANA` | `CLI_MIO_B` | 3 200 | `HOY + 3 días` | pendiente | CC-2 (letras por vencer esta semana) |
| `LET_FUTURA` | `CLI_MIO_A` | 6 000 | `HOY + 40 días` | pendiente | CC-3 (saldo pendiente), PG-3 (cuánto debe y vence) |
| (sin letras vencidas) | `CLI_MIO_C` | — | — | — | Cliente "al día" para contraste |

> **Clave:** los vencimientos se calculan con `date.today()`, NO con fechas absolutas, para que
> "esta semana" siempre se cumpla el día que el QA ejecute.

---

## 4. Implementación en el Mock SAP

**Archivo nuevo:** `mockup-catusita/data/fixtures_qa.py`

```python
"""Datos ancla deterministas para el QA del Agente Vendedores.

Se agregan DESPUÉS de la generación Faker para garantizar escenarios fijos.
Fechas relativas a HOY para que 'esta semana' / 'vencida' siempre apliquen.
"""
from datetime import date, timedelta
from data import seed

HOY = date.today()

# --- Clientes ancla ---
CLIENTES_QA = [
    {"ruc": "20100000001", "razon_social": "Transportes Andinos SAC",
     "tipo": "distribuidor", "vendedor_id": "V001", "estado": "activo",
     "direccion": "Av. Industrial 100, Ate", "telefono": "+511 900000001",
     "email": "contacto@transportesandinos.pe", "limite_credito": 50000,
     "dias_credito": 30, "fecha_registro": (HOY - timedelta(days=900)).isoformat()},
    # CLI_MIO_B, CLI_MIO_C (V001) y CLI_AJENO (V002) ... mismos campos
]

# --- Productos ancla (incluye Fram y un agotado) ---
PRODUCTOS_QA = [
    {"sku": "FIL-FRA-0001", "nombre": "Filtro de aceite Fram", "categoria": "filtros",
     "marca": "Fram", "precio_lista": 45.0, "precio_neto": 32.0, "stock": 120,
     "stock_minimo": 10, "unidad": "UND", "compatibilidad": ["Toyota"],
     "oem": ["90915-YZZD2", "FRM-OIL-77"]},
    {"sku": "FRE-BEN-0001", "nombre": "Pastilla de freno Bendix", "categoria": "frenos",
     "marca": "Bendix", "precio_lista": 180.0, "precio_neto": 130.0, "stock": 0,
     "stock_minimo": 8, "unidad": "UND", "compatibilidad": ["Toyota", "Hyundai"], "oem": []},
    # PROD_OK ...
]

# --- Vehículo, pedidos y letras ancla (fechas relativas a HOY) --- ...

def aplicar():
    """Inyecta las fixtures en las listas e índices de seed (idempotente)."""
    # Clientes
    seed.CLIENTES.extend(CLIENTES_QA)
    for c in CLIENTES_QA:
        seed.CLIENTES_POR_RUC[c["ruc"]] = c
        seed.CLIENTES_POR_VENDEDOR.setdefault(c["vendedor_id"], []).append(c)
    # Productos
    seed.PRODUCTOS.extend(PRODUCTOS_QA)
    for p in PRODUCTOS_QA:
        seed.PRODUCTOS_POR_SKU[p["sku"]] = p
    # Vehículo, pedidos, letras → extend + reconstruir índices PEDIDOS_POR_RUC / LETRAS_POR_RUC
    ...
```

**Enganche:** al final de [seed.py](../mockup-catusita/data/seed.py) (después de construir los
índices), añadir:

```python
from data import fixtures_qa  # noqa: E402
fixtures_qa.aplicar()
```

> Alternativa más limpia: llamar `fixtures_qa.aplicar()` desde el `startup` de `main.py`. Lo
> importante es que corra **una vez, después** de la generación Faker y de armar los índices.

### Puntos de cuidado al implementar
- Respetar **exactamente los nombres de campo** que ya usan las funciones (`razon_social`,
  `limite_credito`, `compatibilidad`, `numero_factura`, `numero_guia`, etc.) o las consultas
  romperán. Ver [data/clientes.py](../mockup-catusita/data/clientes.py),
  [data/pedidos.py](../mockup-catusita/data/pedidos.py),
  [data/vendedores.py](../mockup-catusita/data/vendedores.py).
- Reconstruir `PEDIDOS_POR_RUC` y `LETRAS_POR_RUC` tras agregar pedidos/letras ancla.
- Los pedidos ancla deben incluir `items`, `subtotal`, `igv`, `total` para no romper
  `get_historial` ni `get_documentos`.

---

## 5. Ajuste de código opcional en el mock (para SP-5: OEM)

La búsqueda actual `buscar_catalogo` solo mira `nombre` y `categoria`
([data/productos.py:62-88](../mockup-catusita/data/productos.py#L62-L88)). Para que la consulta
por **código OEM** (SP-5) funcione de verdad, extender la búsqueda para que también matchee el
campo `oem`:

```python
if q:
    ...
    resultados = [
        p for p in resultados
        if all(t in _normalizar(p["nombre"]) or t in _normalizar(p["categoria"])
               or any(t in _normalizar(o) for o in p.get("oem", []))
               for t in terminos)
    ]
```

> Si NO se hace este ajuste, SP-5 aún puede pasar con "no encontré equivalencia", pero no se
> prueba el camino feliz. **Recomendación:** hacerlo, es de bajo riesgo.

---

## 6. Mapeo final fixture → caso de prueba (rellena el `plan_de_prueba.md`)

Con estas fixtures, la tabla de "Preparación de datos" del `plan_de_prueba.md` queda fija:

| Variable del plan de prueba | Valor congelado |
|-----------------------------|-----------------|
| `RUC_MIO_A` | `20100000001` |
| `NOMBRE_MIO_A` | Transportes Andinos SAC |
| `RUC_MIO_B` | `20100000002` |
| `RUC_AJENO` | `20900000009` (cartera de V002) |
| `SKU_VALIDO` | `FIL-BOC-0001` |
| `SKU_AGOTADO` | `FRE-BEN-0001` |
| `PEDIDO_MIO` | `PED-000001` |
| `FACTURA_MIA` | `F001-000001` |
| Placa Toyota Hilux | `ABC-123` |
| Producto Fram | `FIL-FRA-0001` |

---

## 7. Entregable para el QA humano

Tras implementar las fixtures y reiniciar el Mock SAP, generar **`datos_qa.md`** (o `.csv`)
con la lista anterior + una verificación rápida vía API, para que el QA humano no tenga que
adivinar nada:

```bash
# Verificar que las fixtures están vivas
curl -H "X-API-Key: catusita-mock-key-2024" .../vendedor/V001/clientes      # debe incluir 20100000001
curl -H "X-API-Key: catusita-mock-key-2024" .../clientes/20100000001        # Transportes Andinos SAC
curl -H "X-API-Key: catusita-mock-key-2024" .../stock/FRE-BEN-0001          # stock = 0
curl -H "X-API-Key: catusita-mock-key-2024" .../cobranzas/20100000002       # letra esta semana + vencida
```

---

## 8. Orden de ejecución

1. Crear `mockup-catusita/data/fixtures_qa.py` con todas las fixtures (sección 3-4).
2. Enganchar `fixtures_qa.aplicar()` en `seed.py` (o `main.py`).
3. (Opcional) Ajustar `buscar_catalogo` para OEM (sección 5).
4. Probar localmente: `uvicorn main:app --reload` + los `curl` de la sección 7.
5. Deploy a Railway. Reverificar con los `curl`.
6. Rellenar las variables del `plan_de_prueba.md` (sección 6).
7. Generar `datos_qa.md` para el QA humano.
8. Recién entonces correr el `plan_de_prueba.md` completo.

---

## 9. Criterios de aceptación (Definition of Done)

- [ ] `GET /vendedor/V001/clientes` incluye `20100000001` (Transportes Andinos SAC), `…002` y `…003`.
- [ ] `GET /vendedor/V002/clientes` incluye `20900000009` y **V001 NO**.
- [ ] `GET /stock/FRE-BEN-0001` devuelve `stock: 0`.
- [ ] `GET /stock/FIL-FRA-0001` devuelve un filtro Fram con stock > 0 y compat Toyota.
- [ ] `GET /cobranzas/20100000002` tiene una letra `pendiente` que vence dentro de 7 días y una `vencida`.
- [ ] `GET /pedidos/20100000001` tiene ≥5 pedidos, uno `entregado` y uno `en_transito`, con factura y guía.
- [ ] `GET /vehiculo/ABC-123` devuelve Toyota Hilux con repuestos compatibles.
- [ ] Los valores son **idénticos tras reiniciar** el deploy (deterministas).
- [ ] La data Faker original sigue intacta (no se rompió ninguna consulta existente).
```
