#!/usr/bin/env bash
set -Eeuo pipefail
umask 027
export LC_ALL=C

SOURCE=/workspace/results
READ_ONLY=/srv/baseia-results-ro
DUMP_BASE=/workspace/artifact-dump
RESERVE_BYTES=$((20 * 1024 * 1024 * 1024))

fail() {
    printf 'FAILED=%s\n' "$1"
    printf '%s\n' "$1" >"${BUILD:-${DUMP_BASE}}/FAILED.txt" 2>/dev/null || true
    exit 1
}

[[ -n "${POD_ID:-}" ]] || fail "POD_ID nao informado"
[[ -d "${SOURCE}/tasks" ]] || fail "diretorio de tasks ausente"
if pgrep -af \
    'persistent_results|router_with_persistence|mineru-api|mineru_router|uvicorn.*mineru' \
    >/dev/null; then
    fail "processo escritor MinerU encontrado"
fi

mkdir -p "${READ_ONLY}" "${DUMP_BASE}"
if ! mountpoint -q "${READ_ONLY}"; then
    if mount --bind "${SOURCE}" "${READ_ONLY}" 2>/dev/null; then
        mount -o remount,bind,ro "${READ_ONLY}"
    else
        READ_ONLY="${SOURCE}"
    fi
fi
if [[ "${READ_ONLY}" != "${SOURCE}" ]]; then
    mount -o remount,bind,ro "${READ_ONLY}"
    findmnt -no OPTIONS "${READ_ONLY}" | tr ',' '\n' | grep -qx ro \
        || fail "bind mount nao ficou somente leitura"
    READ_PROTECTION="kernel-read-only-bind"
else
    READ_PROTECTION="read-only-procedure-with-before-after-inventory"
fi

SOURCE_BYTES="$(du -sb "${READ_ONLY}" | awk '{print $1}')"
AVAILABLE_BYTES="$(df -B1 --output=avail "${DUMP_BASE}" | tail -1 | tr -d ' ')"
(( AVAILABLE_BYTES > SOURCE_BYTES + RESERVE_BYTES )) \
    || fail "espaco insuficiente para dump com reserva de 20 GiB"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BUILD="${DUMP_BASE}/.building-${POD_ID}-${STAMP}"
READY="${DUMP_BASE}/ready-${POD_ID}-${STAMP}"
mkdir -p "${BUILD}"

inventory() {
    find "${READ_ONLY}" -xdev -type f \
        -printf '%P\t%s\t%T@\n' | sort
}

inventory >"${BUILD}/FILES.before.tsv"
FILE_COUNT="$(wc -l <"${BUILD}/FILES.before.tsv")"
INVENTORY_SHA256="$(
    sha256sum "${BUILD}/FILES.before.tsv" | awk '{print $1}'
)"

tar --numeric-owner --acls --xattrs --one-file-system \
    -C "${READ_ONLY}" -I 'zstd -T8 -1' -cf - . \
    | split --bytes=20G --numeric-suffixes=0 --suffix-length=3 \
        - "${BUILD}/mineru-results.tar.zst.part-"

inventory >"${BUILD}/FILES.after.tsv"
cmp -s "${BUILD}/FILES.before.tsv" "${BUILD}/FILES.after.tsv" \
    || fail "origem mudou durante o snapshot"

cd "${BUILD}"
sha256sum mineru-results.tar.zst.part-* >SHA256SUMS
cat mineru-results.tar.zst.part-* | zstd -t -q
ARCHIVE_BYTES="$(
    du -cb mineru-results.tar.zst.part-* | tail -1 | awk '{print $1}'
)"

cat >manifest.json <<JSON
{
  "pod_id": "${POD_ID}",
  "created_at": "${STAMP}",
  "source": "${SOURCE}",
  "source_bytes": ${SOURCE_BYTES},
  "source_file_count": ${FILE_COUNT},
  "source_inventory_sha256": "${INVENTORY_SHA256}",
  "read_protection": "${READ_PROTECTION}",
  "archive_bytes": ${ARCHIVE_BYTES},
  "part_size": "20G",
  "compression": "zstd -1, 8 threads",
  "validation": "inventory-before-after, sha256-parts, zstd-test"
}
JSON
sha256sum manifest.json FILES.before.tsv FILES.after.tsv >>SHA256SUMS
find "${BUILD}" -type d -exec chmod 0755 {} +
find "${BUILD}" -type f -exec chmod 0644 {} +
sync -f "${DUMP_BASE}"
mv "${BUILD}" "${READY}"
sync -f "${DUMP_BASE}"

PASSWORD="$(openssl rand -hex 18)"
PASSWORD_HASH="$(openssl passwd -6 "${PASSWORD}")"
printf 'baseia:%s\n' "${PASSWORD_HASH}" >"${DUMP_BASE}/.htpasswd"
chown root:nogroup "${DUMP_BASE}/.htpasswd"
chmod 0640 "${DUMP_BASE}/.htpasswd"
cat >"${DUMP_BASE}/.access-${POD_ID}" <<ACCESS
username=baseia
password=${PASSWORD}
ready_dir=${READY}
ACCESS
chmod 0600 "${DUMP_BASE}/.access-${POD_ID}"

cat >/etc/nginx/baseia-artifacts.conf <<NGINX
user nobody nogroup;
pid /run/nginx-baseia-artifacts.pid;
error_log /var/log/nginx/baseia-artifacts-error.log;
events { worker_connections 1024; }
http {
    access_log /var/log/nginx/baseia-artifacts-access.log;
    sendfile on;
    sendfile_max_chunk 2m;
    tcp_nopush on;
    gzip off;
    server {
        listen 8000;
        server_name _;
        auth_basic "BaseIA artifacts";
        auth_basic_user_file ${DUMP_BASE}/.htpasswd;
        root ${READY};
        autoindex on;
        autoindex_exact_size off;
        charset utf-8;
        max_ranges 1;
        add_header Accept-Ranges bytes always;
        location / {
            try_files \$uri \$uri/ =404;
            limit_except GET HEAD { deny all; }
        }
    }
}
NGINX

nginx -t -c /etc/nginx/baseia-artifacts.conf
if [[ -s /run/nginx-baseia-artifacts.pid ]] \
    && kill -0 "$(cat /run/nginx-baseia-artifacts.pid)" 2>/dev/null; then
    nginx -c /etc/nginx/baseia-artifacts.conf -s reload
else
    nginx -c /etc/nginx/baseia-artifacts.conf
fi
curl -fsS -u "baseia:${PASSWORD}" http://127.0.0.1:8000/ >/dev/null

printf 'READY=%s\n' "${READY}"
printf 'SOURCE_BYTES=%s\n' "${SOURCE_BYTES}"
printf 'ARCHIVE_BYTES=%s\n' "${ARCHIVE_BYTES}"
printf 'FILE_COUNT=%s\n' "${FILE_COUNT}"
printf 'INVENTORY_SHA256=%s\n' "${INVENTORY_SHA256}"
