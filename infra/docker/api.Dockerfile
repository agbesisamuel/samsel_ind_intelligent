# Local development image. Locked dependencies include checks; not a production release.
FROM python:3.13.12-slim-bookworm@sha256:a58daefb915e1e03ad48f3ca4df8832065412c5c35cacb9d39f4229184de12b6
# Exact supported Debian security fixes identified by the Sprint 10 image scan.
# Refresh these pins with a new SBOM/scan when the upstream repository supersedes them.
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    libcap2=1:2.66-4+deb12u3+b1 libgnutls30=3.7.9-2+deb12u7 \
    libpcre2-8-0=10.42-1+deb12u2 libssl3=3.0.22-1~deb12u1 \
    openssl=3.0.22-1~deb12u1 perl-base=5.36.0-7+deb12u4 \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace/apps/api
COPY apps/api/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock
# Installed pip is hash-locked/current. Remove the unused older offline bootstrap
# wheel, whose vendored libraries are otherwise shipped despite the updated runtime.
# Virtual environments in this image must use --without-pip and the installed pip.
RUN rm -f /usr/local/lib/python3.13/ensurepip/_bundled/pip-25.3-py3-none-any.whl
RUN useradd --create-home --uid 10001 sii
COPY --chown=sii:sii apps/api /workspace/apps/api
USER sii
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]
