# Directorio de vendedores — SellerId real de Catusita

> Capturado del API real (`/api/client/CustomerbySeller`) el 2026-07-10.
> Sirve para mapear cada número de WhatsApp de un asesor a su `SellerId` real,
> y así la tool `consultar_cartera` devuelve SOLO su cartera (no la de Gerencia).

## Cómo funciona

- El endpoint `/api/client/CustomerbySeller?SellerId=<n>` filtra por vendedor.
- `SellerId` es un **id interno secuencial** (con huecos: 3, 10, 20… no existen).
- Cada `SellerId` mapea a un `codeSeller` (código de negocio) y su nombre. **El mapeo
  SellerId→codeSeller NO es lineal** (ej. SellerId 50 → codeSeller 0037).
- `SellerId=1` = bucket **"Gerencia Oficina"** (codeSeller 0000) → devuelve TODOS los
  clientes (3579). **Nunca usar para un vendedor.**

## Vendedores activos

| SellerId | codeSeller | Vendedor | # clientes |
|---:|:---|:---|---:|
| 2 | 0001 | Tarazona Davila Jefer | 85 |
| 5 | 0004 | Bayona Paiva Myriam | 143 |
| 6 | 0005 | Huaman Jara Daniel | 64 |
| 8 | 0011 | Bravo Crisanto David Esteban | 103 |
| 14 | 0025 | Gil Zuñiga Climaco | 78 |
| 15 | 0028 | Purihuaman De La Cruz Carlos | 113 |
| 16 | 0032 | Chavez Ariste Fernando | 144 |
| 21 | 0042 | Alarcon Altamirano Mayco | 151 |
| 22 | 0043 | Peña Alva Mariluz Milagros | 184 |
| 25 | 0046 | Escobar Salinas Miguel | 97 |
| 26 | 0048 | Velarde Konja Roberto | 33 |
| 27 | 0050 | Valle Atahuaman Toribio | 131 |
| 28 | 0051 | Saavedra Cicirello Jose Domingo | 294 |
| 29 | 0052 | Escobar Herrera Stephanny | 163 |
| 30 | 0062 | Celis Paredes Julio | 1 |
| 31 | 0063 | Mansilla Dias Jimmy Alfonso | 21 |
| 34 | 0083 | Meza Ramirez Julio | 37 |
| 40 | 0003 | Torres Quiñones Luis Alberto | 132 |
| 41 | C001 | Mostrador 1 | 94 |
| 44 | 0007 | Ruiz Revolledo Jose Luis | 45 |
| 45 | 0006 | Castro Elias Harol Armando | 82 |
| 46 | 0008 | Nora De La Fuente Gutierrez | 139 |
| 50 | 0037 | Revolledo Humala Paulo | 274 |
| 52 | 0055 | Lupaca Castañeda Gisela Yanet | 72 |
| 53 | 0009 | Quispe Tasa William | 185 |
| 55 | 0064 | Fernandez Perez Genesis Victoria | 84 |
| 56 | 0068 | Aparco Aparco Stefany Katherin | 26 |
| 57 | 0070 | Omar Velarde Durand | 65 |
| 58 | 0074 | Osorio Echevarria Roger Alcides | 171 |
| 60 | 0012 | Pinedo Peña Luz | 67 |

> Rango sondeado: SellerId 2–60. Puede haber más allá de 60. El máximo de clientes
> observado es 294 (Saavedra) → el cap de cartera del servicio se fija por encima.

## Pendiente (tarea de negocio)

Asignar cada **número de WhatsApp** de asesor a su `SellerId` de esta tabla, en
`shared/auth.py` (`_MOCK_ASESORES`). Hoy, para pruebas, todos apuntan a un SellerId
demo (env `SELLER_ID_DEMO`, default `2` = Tarazona, 85 clientes).
