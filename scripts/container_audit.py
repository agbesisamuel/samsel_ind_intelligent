"""Scan exported local images without Docker socket access or source/secret mounts.

Full findings are retained; exit status denotes scanner execution, not a clean
security gate. Review severity, package reachability and vendor evidence explicitly.
The fixed project image list includes infrastructure and both application images.
"""

import argparse
import json
import subprocess

from dev import COMPOSE, ROOT, require_local

SCANNER = (
    "aquasec/trivy:0.76.0@sha256:2416d1f74045b57274df1a340eee6b510cacd73c66a6ccb8da092b117eb7d222"
)
SERVICES = [
    "api",
    "web",
    "object-store-backend",
    "object-store",
    "postgres",
    "rabbitmq",
    "redis",
    "smtp",
]


def main():
    """Export each unique project image and preserve reproducible non-secret scan evidence."""
    require_local()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--services", nargs="+", choices=SERVICES, default=SERVICES)
    selected = parser.parse_args().services
    destination = ROOT / ".artifacts" / "container-audit"
    destination.mkdir(parents=True, exist_ok=True)
    cache = ROOT / ".artifacts" / "security" / "trivy-cache"
    cache.mkdir(parents=True, exist_ok=True)
    summary_file = destination / "summary.json"
    summary = json.loads(summary_file.read_text()) if summary_file.exists() else []
    for service in selected:
        container = (
            subprocess.check_output([*COMPOSE, "ps", "-q", service], cwd=ROOT).decode().strip()
        )
        # Compose's image ID can be an old multi-platform index removed by a rebuild.
        # Resolve the service's actual configured ref, then scan the current local
        # image at that ref. Do not rebuild images concurrently with this command.
        image = (
            subprocess.check_output(
                ["docker", "inspect", "--format", "{{.Config.Image}}", container], cwd=ROOT
            )
            .decode()
            .strip()
        )
        image_id = (
            subprocess.check_output(
                ["docker", "image", "inspect", "--format", "{{.Id}}", image], cwd=ROOT
            )
            .decode()
            .strip()
        )
        archive = destination / f"{service}.tar"
        subprocess.run(["docker", "image", "save", image, "-o", str(archive)], check=True)
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{destination}:/scan",
                "-v",
                f"{cache}:/cache",
                SCANNER,
                "image",
                "--input",
                f"/scan/{service}.tar",
                "--scanners",
                "vuln",
                "--parallel",
                "2",
                "--format",
                "json",
                "--output",
                f"/scan/{service}.json",
                "--cache-dir",
                "/cache",
                "--disable-telemetry",
                "--skip-version-check",
            ],
            check=True,
        )
        findings = json.loads((destination / f"{service}.json").read_text())
        severities = {}
        for result in findings.get("Results", []):
            for vulnerability in result.get("Vulnerabilities", []):
                level = vulnerability["Severity"]
                severities[level] = severities.get(level, 0) + 1
        summary = [row for row in summary if row["service"] != service]
        summary.append(
            {
                "service": service,
                "image": image_id,
                "reference": image,
                "package_findings": severities,
            }
        )
        summary_file.write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary[-1]), flush=True)


if __name__ == "__main__":
    main()
