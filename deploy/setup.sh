#!/bin/bash
# Первичная установка на чистый сервер Ubuntu 24.04. Запускать от root: bash setup.sh
set -e
apt-get update -y
apt-get install -y python3-venv python3-pip sqlite3 rsync debian-keyring debian-archive-keyring apt-transport-https curl git
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
apt-get update -y && apt-get install -y caddy
id school93 >/dev/null 2>&1 || useradd -r -m -d /opt/school93 school93
# код копируем без базы, ключа, меню и загруженных фото: на сервере их не трогаем никогда
rsync -a --exclude data/site.db --exclude 'data/site.db-*' --exclude data/secret.key --exclude food/ --exclude app/static/uploads/ --exclude .venv/ ./ /opt/school93/
mkdir -p /opt/school93/food /opt/school93/app/static/uploads && chown -R school93:school93 /opt/school93
timedatectl set-timezone Europe/Moscow || true
cd /opt/school93
sudo -u school93 python3 -m venv .venv
sudo -u school93 .venv/bin/pip install -q -r requirements.txt
if [ ! -f data/site.db ]; then
  read -r -s -p "Придумайте пароль администратора сайта (не короче 8 символов): " S93PW; echo
  [ ${#S93PW} -ge 8 ] || { echo "Слишком короткий пароль"; exit 1; }
  sudo -u school93 env S93_ADMIN_PASSWORD="$S93PW" .venv/bin/python -m app.seed data/files.csv
fi
cp deploy/school93.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now school93
cp deploy/Caddyfile /etc/caddy/Caddyfile && systemctl reload caddy
cp deploy/backup.sh /usr/local/bin/school93-backup && chmod +x /usr/local/bin/school93-backup
(crontab -l 2>/dev/null; echo "30 3 * * * /usr/local/bin/school93-backup") | sort -u | crontab -
echo "Готово. Сайт работает. Вход в админку: логин admin и пароль, который вы задали. Обновлять сайт: sudo bash deploy/update.sh"
