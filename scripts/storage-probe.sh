#!/bin/sh
# Bounded local S3 checks using curl's maintained SigV4 implementation.
# health only lists buckets. smoke creates a unique synthetic bucket/object, tests
# authorization and round-trip integrity, then deletes only that owned test data.
# Never print credentials, response bodies, object lists or curl diagnostics.
set -eu
umask 077
mode=${1:-health}
case "$mode" in health|smoke) ;; *) echo 'Expected health or smoke.' >&2; exit 1;; esac
[ "${SII_ENV:-}" = local ] || exit 1
endpoint=http://127.0.0.1:8333
# Integration smoke must traverse the same proxy boundary as application clients.
[ "$mode" = health ] || endpoint=http://object-store:8333

# Credentials go through stdin, never through a shell evaluation or curl argv.
request() {
    printf 'user = "%s:%s"\n' "$S3_ACCESS_KEY" "$S3_SECRET_KEY" |
        curl --config - --aws-sigv4 aws:amz:us-east-1:s3 --silent \
            --connect-timeout 3 --max-time 10 --output /dev/null \
            --write-out '%{http_code}' "$@"
}
expect() {
    # Identify a failed operation without printing credentials, bodies or object names.
    if [ "$1" != "$2" ]; then
        case "$1" in [0-9][0-9][0-9]) echo "HTTP status: $1" >&2 ;; esac
        echo "FAIL S3 probe at ${phase:-initialization} (details redacted)" >&2
        exit 1
    fi
}
phase=authenticated-list
expect "$(request "$endpoint/")" 200
[ "$mode" = smoke ] || exit 0

# Prove authentication fails closed for both anonymous and invalid signed requests.
phase=anonymous-list
expect "$(curl --silent --max-time 10 -o /dev/null -w '%{http_code}' "$endpoint/")" 403
phase=invalid-signature
expect "$(printf 'user = "invalid:invalid"\n' | curl --config - --silent --max-time 10 \
    --aws-sigv4 aws:amz:us-east-1:s3 -o /dev/null -w '%{http_code}' "$endpoint/")" 403
bucket=sii-smoke-$(cat /proc/sys/kernel/random/uuid)
phase=create-bucket
expect "$(request -X PUT "$endpoint/$bucket")" 200
# Cleanup is armed only after we created this unique bucket. Never recursively delete.
cleanup() {
    request -X DELETE "$endpoint/$bucket/probe.txt" >/dev/null || true
    request -X DELETE "$endpoint/$bucket" >/dev/null || true
}
trap cleanup EXIT HUP INT TERM
phase=put-object
expect "$(request -X PUT --data-binary 'sii-synthetic-storage-probe' "$endpoint/$bucket/probe.txt")" 200
phase=anonymous-object
expect "$(curl --silent --max-time 10 -o /dev/null -w '%{http_code}' "$endpoint/$bucket/probe.txt")" 403
phase=get-object
body=$(printf 'user = "%s:%s"\n' "$S3_ACCESS_KEY" "$S3_SECRET_KEY" |
    curl --config - --aws-sigv4 aws:amz:us-east-1:s3 --silent --fail \
        --connect-timeout 3 --max-time 10 "$endpoint/$bucket/probe.txt")
expect "$body" sii-synthetic-storage-probe
phase=delete-object
expect "$(request -X DELETE "$endpoint/$bucket/probe.txt")" 204
phase=delete-bucket
expect "$(request -X DELETE "$endpoint/$bucket")" 204
trap - EXIT HUP INT TERM
echo 'PASS S3 authentication, anonymous/invalid denial, object round-trip and cleanup'
