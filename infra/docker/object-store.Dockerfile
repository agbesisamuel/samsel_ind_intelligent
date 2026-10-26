# Maintained S3 replacement; upstream binary is pinned by release and registry digest.
FROM chrislusf/seaweedfs:4.48@sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d
# Named-volume initialization inherits this ownership; never mount legacy MinIO data.
RUN addgroup -g 10001 sii && adduser -D -u 10001 -G sii sii && mkdir -p /data && chown -R sii:sii /data
COPY scripts/storage-entrypoint.sh scripts/storage-probe.sh /opt/sii/
USER 10001:10001
WORKDIR /data
ENTRYPOINT ["/bin/sh", "/opt/sii/storage-entrypoint.sh"]
