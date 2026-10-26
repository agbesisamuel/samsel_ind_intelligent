#!/bin/sh
# Local-only S3 startup. Hex credentials allow safe JSON generation without eval.
# Fail before starting a listener if setup was skipped; never allow anonymous mode.
set -eu
umask 077
[ "${SII_ENV:-}" = local ] || { echo 'Object store requires local environment.' >&2; exit 1; }
for value in "${S3_ACCESS_KEY:-}" "${S3_SECRET_KEY:-}"; do
    case "$value" in ''|*[!0-9a-f]*) echo 'Run setup: invalid S3 credentials.' >&2; exit 1;; esac
    [ "${#value}" -eq 64 ] || { echo 'Run setup: invalid S3 credentials.' >&2; exit 1; }
done
# Ephemeral, private config is regenerated on every start, so .env rotation applies.
printf '{"identities":[{"name":"local-foundation","credentials":[{"accessKey":"%s","secretKey":"%s"}],"actions":["Admin","Read","Write","List","Tagging"]}]}' \
    "$S3_ACCESS_KEY" "$S3_SECRET_KEY" > /tmp/sii-s3.json
mkdir -p /data/master /data/volume
# Master/filer/volume HTTP and gRPC stay on loopback: no unauthenticated S3 bypass.
# No IAM management, WebDAV, UI, catalog, telemetry or automatic bucket creation.
# Each bucket can allocate a collection of several sparse volumes. Eight slots
# cannot hold both application evidence and integration probes; 32 stays bounded
# at 128 MiB per volume and preserves all existing collection data on upgrade.
exec weed server -ip=127.0.0.1 -ip.bind=127.0.0.1 \
    -dir=/data/volume -master.dir=/data/master -master.telemetry=false \
    -master.volumeSizeLimitMB=128 -volume.max=32 -filer \
    -s3 -s3.ip.bind=0.0.0.0 -s3.port=8333 -s3.config=/tmp/sii-s3.json \
    -s3.iam=false -s3.port.iceberg=0 -s3.port.lance=0 \
    -s3.autoCreateBucket=false -s3.allowDeleteBucketNotEmpty=false
