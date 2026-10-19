#!/usr/bin/env bash
set -euo pipefail
umask 077

app_dir="/opt/apps/aster"
backup_dir="$app_dir/backups"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
docker compose --project-directory "$app_dir" -f "$app_dir/deploy/compose.production.yml" \
  exec -T postgres pg_dump -U aster -d aster -Fc > "$backup_dir/postgres-$stamp.dump"
find "$backup_dir" -type f -name 'postgres-*.dump' -mtime +14 -delete
echo "Created $backup_dir/postgres-$stamp.dump"
