#!/bin/bash
# Обновление кода на сервере. База, ключ сессий, меню и фото остаются как были. Запускать от root из папки с новой версией.
set -e
/usr/local/bin/school93-backup
rsync -a --exclude data/site.db --exclude 'data/site.db-*' --exclude data/secret.key --exclude food/ --exclude app/static/uploads/ --exclude .venv/ ./ /opt/school93/
chown -R school93:school93 /opt/school93
cd /opt/school93 && sudo -u school93 .venv/bin/pip install -q -r requirements.txt
systemctl restart school93
echo "Обновлено. Перед обновлением снята резервная копия в /opt/backups."
