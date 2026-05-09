#!/bin/bash
# deploy.sh — Sube y reinicia catusita-agent en un Droplet de Digital Ocean
# Uso:
#   ./deploy.sh <IP_DEL_DROPLET>
#   DROPLET_IP=1.2.3.4 ./deploy.sh

set -e

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DROPLET_IP="${1:-${DROPLET_IP:-}}"
DROPLET_USER="${DROPLET_USER:-root}"
APP_DIR="/opt/catusita-agent"
IMAGE_NAME="catusita-agent"
CONTAINER_NAME="catusita-agent"

# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------
if [ -z "$DROPLET_IP" ]; then
  echo "ERROR: Especifica la IP del Droplet."
  echo "  Uso: ./deploy.sh <IP>  o  DROPLET_IP=1.2.3.4 ./deploy.sh"
  exit 1
fi

if ! command -v rsync &> /dev/null; then
  echo "ERROR: rsync no está instalado. Instálalo con: brew install rsync (Mac) o apt install rsync (Linux)"
  exit 1
fi

echo ""
echo "========================================"
echo "  Deploy catusita-agent"
echo "  Droplet: ${DROPLET_USER}@${DROPLET_IP}"
echo "  Directorio remoto: ${APP_DIR}"
echo "========================================"
echo ""

# ---------------------------------------------------------------------------
# Paso 1 — Verificar que el .env existe en el Droplet
# ---------------------------------------------------------------------------
echo "[1/4] Verificando .env en el Droplet..."
if ! ssh "${DROPLET_USER}@${DROPLET_IP}" "test -f ${APP_DIR}/.env"; then
  echo ""
  echo "AVISO: No se encontró ${APP_DIR}/.env en el Droplet."
  echo "Cópialo con:"
  echo "  ssh ${DROPLET_USER}@${DROPLET_IP} 'mkdir -p ${APP_DIR}'"
  echo "  scp .env ${DROPLET_USER}@${DROPLET_IP}:${APP_DIR}/.env"
  echo ""
  read -r -p "¿Continuar de todas formas? [s/N] " resp
  if [[ ! "$resp" =~ ^[sS]$ ]]; then
    echo "Deploy cancelado."
    exit 1
  fi
else
  echo "  .env encontrado OK"
fi

# ---------------------------------------------------------------------------
# Paso 2 — Sincronizar código fuente al Droplet (excluye .env y cachés)
# ---------------------------------------------------------------------------
echo ""
echo "[2/4] Sincronizando código fuente..."
ssh "${DROPLET_USER}@${DROPLET_IP}" "mkdir -p ${APP_DIR}"

rsync -az --delete \
  --exclude='.env' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.py[cod]' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='*.egg-info' \
  . "${DROPLET_USER}@${DROPLET_IP}:${APP_DIR}/"

echo "  Código sincronizado OK"

# ---------------------------------------------------------------------------
# Paso 3 — Construir imagen Docker en el Droplet
# ---------------------------------------------------------------------------
echo ""
echo "[3/4] Construyendo imagen Docker en el Droplet..."
ssh "${DROPLET_USER}@${DROPLET_IP}" "
  set -e
  cd ${APP_DIR}
  docker build --no-cache -t ${IMAGE_NAME} .
"
echo "  Imagen construida OK"

# ---------------------------------------------------------------------------
# Paso 4 — Detener el contenedor anterior y levantar el nuevo
# ---------------------------------------------------------------------------
echo ""
echo "[4/4] Reiniciando contenedor..."
ssh "${DROPLET_USER}@${DROPLET_IP}" "
  set -e

  # Detener y eliminar el contenedor anterior si existe
  if docker ps -a --format '{{.Names}}' | grep -q '^${CONTAINER_NAME}$'; then
    echo '  Deteniendo contenedor anterior...'
    docker stop ${CONTAINER_NAME} || true
    docker rm ${CONTAINER_NAME}
  fi

  # Levantar nuevo contenedor
  docker run -d \
    --name ${CONTAINER_NAME} \
    --restart unless-stopped \
    -p 8080:8080 \
    --env-file ${APP_DIR}/.env \
    ${IMAGE_NAME}

  echo '  Contenedor iniciado OK'
  echo ''
  echo '  Logs de arranque (15s):'
  sleep 3
  docker logs --tail 30 ${CONTAINER_NAME}
"

# ---------------------------------------------------------------------------
# Resultado final
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "  Deploy completado"
echo "  API disponible en: http://${DROPLET_IP}:8080"
echo "  Health check:      http://${DROPLET_IP}:8080/health"
echo "  Webhook WhatsApp:  http://${DROPLET_IP}:8080/webhook/whatsapp"
echo "========================================"
echo ""
echo "Comandos útiles en el Droplet:"
echo "  Ver logs en vivo:  ssh ${DROPLET_USER}@${DROPLET_IP} 'docker logs -f ${CONTAINER_NAME}'"
echo "  Reiniciar:         ssh ${DROPLET_USER}@${DROPLET_IP} 'docker restart ${CONTAINER_NAME}'"
echo "  Detener:           ssh ${DROPLET_USER}@${DROPLET_IP} 'docker stop ${CONTAINER_NAME}'"
