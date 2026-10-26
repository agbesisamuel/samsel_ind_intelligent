"""Generate local-only CA/server fixtures into dedicated volumes; never install trust on the host.

Runs as the isolated TLS-init service with no network. CA private key is discarded;
server keys are readable only by their service UID. Existing material is preserved.
"""

import ipaddress
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def main():
    """Create bounded-expiry synthetic certificates only in the fixed mounted volume paths."""
    if os.environ.get("SII_ENV") != "local":
        raise SystemExit("TLS fixtures require local mode")
    public, private = Path("/tls-public"), Path("/tls-private")
    # Persistent simulator spool has a separate non-secret volume owned by the app UID.
    os.chown("/simulator", 10001, 10001)
    if (public / "ca.crt").exists():
        for name in ["rabbitmq", "device-api"]:
            cert = x509.load_pem_x509_certificate((private / name / "tls.crt").read_bytes())
            if cert.not_valid_after_utc <= datetime.now(UTC) + timedelta(days=1):
                raise SystemExit("Local certificate expired; use a reviewed fixture rotation")
            if not (private / name / "tls.key").exists():
                raise SystemExit("Incomplete local TLS fixture; refusing silent replacement")
        print("Existing local TLS fixtures preserved")
        return
    if any(private.iterdir()):
        raise SystemExit("Partial TLS fixture exists; refusing to overwrite")
    now = datetime.now(UTC)
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SII synthetic local CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False
        )
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    for name, uid in [("rabbitmq", 999), ("device-api", 10001)]:
        directory = private / name
        directory.mkdir(mode=0o700)
        server_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
            .issuer_name(subject)
            .public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=90))
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName(name),
                        x509.DNSName("localhost"),
                        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                    ]
                ),
                critical=False,
            )
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False
            )
            .add_extension(
                x509.KeyUsage(True, False, True, False, False, False, False, False, False),
                critical=True,
            )
            .sign(key, hashes.SHA256())
        )
        (directory / "tls.key").write_bytes(
            server_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        (directory / "tls.crt").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        for item in [directory, directory / "tls.key", directory / "tls.crt"]:
            os.chown(item, uid, uid)
            item.chmod(0o700 if item.is_dir() else 0o400)
    # Publish CA only after complete server material exists. No CA private key is retained.
    (public / "ca.crt").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (public / "ca.crt").chmod(0o444)
    print("Generated local-only TLS fixtures; no keys or trust roots exported to host")


if __name__ == "__main__":
    main()
