#!/bin/bash
# Ночная копия базы, загруженных фото и папки /food. Храним 30 дней.
set -e
D=/opt/school93; B=/opt/backups; mkdir -p $B
STAMP=$(date +%Y-%m-%d)
sqlite3 $D/data/site.db ".backup '$B/site-$STAMP.db'"
tar -czf $B/files-$STAMP.tar.gz -C $D app/static/uploads food
find $B -type f -mtime +30 -delete
# Копия в объектное хранилище в РФ (раскомментировать после настройки rclone):
# rclone copy $B remote:school93-backup
