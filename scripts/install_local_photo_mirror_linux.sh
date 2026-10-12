#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# GTI SESA — instalação do espelhamento não destrutivo de fotos no Linux.
# A rotina baixa somente image/*; não exclui nem sobrescreve arquivos locais divergentes.

ENABLE=0
if [[ "${1:-}" == "--enable" ]]; then ENABLE=1; fi
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
HOME_DIR="${HOME:?HOME não definido}"
CONFIG_DIR="$HOME_DIR/.config/gti-sesa"
ENV_FILE="$CONFIG_DIR/local-photo-mirror.env"
KEY_FILE="$CONFIG_DIR/drive-reader.json"
PHOTO_ROOT="$HOME_DIR/GTI-SESA/Fotos"
DRIVE_ROOT_ID="1N2hzxmtS9Brijx6vcP-nD-zS6sA8LRzS"
VENV="$REPO_ROOT/.venv"
UNIT_DIR="$HOME_DIR/.config/systemd/user"

mkdir -p "$CONFIG_DIR" "$PHOTO_ROOT" "$UNIT_DIR"
chmod 700 "$CONFIG_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<EOF
GOOGLE_SERVICE_ACCOUNT_FILE=$KEY_FILE
GOOGLE_DRIVE_ROOT_ID=$DRIVE_ROOT_ID
LOCAL_PHOTOS_ROOT=$PHOTO_ROOT
EOF
  chmod 600 "$ENV_FILE"
  echo "Configuração criada: $ENV_FILE"
fi

if [[ ! -f "$KEY_FILE" ]]; then
  echo "BLOQUEADO: credencial Google ausente."
  echo "Coloque o JSON da conta de serviço em: $KEY_FILE"
  echo "Não coloque a chave no repositório nem a envie pelo chat."
  echo "Depois execute novamente: bash scripts/install_local_photo_mirror_linux.sh --enable"
  exit 2
fi
chmod 600 "$KEY_FILE"

# Verifica apenas a estrutura do JSON; não imprime valores secretos.
python3 - "$KEY_FILE" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    obj = json.load(f)
required = ("type", "project_id", "private_key", "client_email", "token_uri")
missing = [key for key in required if not obj.get(key)]
if missing or obj.get("type") != "service_account":
    print("BLOQUEADO: JSON de conta de serviço inválido; campos ausentes/incorretos: " +
          ", ".join(missing or ["type=service_account"]))
    raise SystemExit(2)
print("Credencial: estrutura JSON válida (valores não exibidos).")
PY

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install "google-api-python-client==2.187.0" "google-auth==2.57.0"

cat > "$UNIT_DIR/gti-sesa-photo-mirror.service" <<EOF
[Unit]
Description=GTI SESA - espelhamento não destrutivo de fotografias do Drive
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=$ENV_FILE
WorkingDirectory=$REPO_ROOT
ExecStart=$VENV/bin/python $REPO_ROOT/scripts/download_drive_photos_local.py --download
NoNewPrivileges=true
PrivateTmp=true
UMask=0077
EOF

cat > "$UNIT_DIR/gti-sesa-photo-mirror.timer" <<'EOF'
[Unit]
Description=Executa o espelhamento de fotos GTI SESA a cada 5 minutos

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true
Unit=gti-sesa-photo-mirror.service

[Install]
WantedBy=timers.target
EOF

chmod 600 "$ENV_FILE"
systemctl --user daemon-reload

echo
echo "Destino local: $PHOTO_ROOT"
echo "Credencial: $KEY_FILE"
echo "Origem Drive: pasta raiz configurada no projeto"
echo "Modo padrão do downloader: simulação; o serviço usa --download após instalação."
echo "Segurança: Drive somente leitura; nenhum arquivo local divergente será sobrescrito."
echo
echo "Executando prévia sem baixar arquivos..."
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
"$VENV/bin/python" "$REPO_ROOT/scripts/download_drive_photos_local.py"

if [[ "$ENABLE" -eq 1 ]]; then
  systemctl --user enable --now gti-sesa-photo-mirror.timer
  echo "Timer habilitado: execução a cada 5 minutos."
  echo "Ver logs: journalctl --user -u gti-sesa-photo-mirror.service -n 100 --no-pager"
else
  echo "Timer ainda NÃO habilitado."
  echo "Revise a prévia; para ativar depois, execute:"
  echo "  bash scripts/install_local_photo_mirror_linux.sh --enable"
fi
