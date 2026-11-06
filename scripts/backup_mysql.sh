#!/usr/bin/env bash
# MySQL 逻辑备份（mysqldump）。在部署机 cron 调用，例如：
#   0 3 * * * /opt/traesolo/scripts/backup_mysql.sh >> /var/log/traesolo-backup.log 2>&1
#
# 环境变量（或同目录旁 .env 由运维注入，勿提交真实密码）：
#   MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE
#   BACKUP_DIR（默认 ./backups/mysql）
#   RETAIN_DAYS（默认 7）

set -euo pipefail

MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-football}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"
MYSQL_DATABASE="${MYSQL_DATABASE:-football_analytics}"
BACKUP_DIR="${BACKUP_DIR:-./backups/mysql}"
RETAIN_DAYS="${RETAIN_DAYS:-7}"

if [[ -z "${MYSQL_PASSWORD}" ]]; then
  echo "MYSQL_PASSWORD is required" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
stamp="$(date +%Y%m%d_%H%M%S)"
out="${BACKUP_DIR}/${MYSQL_DATABASE}_${stamp}.sql.gz"

echo "[$(date -Iseconds)] dumping ${MYSQL_DATABASE} -> ${out}"
mysqldump \
  -h "${MYSQL_HOST}" -P "${MYSQL_PORT}" -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" \
  --single-transaction --routines --triggers --set-gtid-purged=OFF \
  "${MYSQL_DATABASE}" | gzip -c > "${out}"

echo "[$(date -Iseconds)] prune older than ${RETAIN_DAYS} days"
find "${BACKUP_DIR}" -type f -name "${MYSQL_DATABASE}_*.sql.gz" -mtime "+${RETAIN_DAYS}" -delete || true
echo "[$(date -Iseconds)] done"
