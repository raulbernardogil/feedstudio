"""Load the public demo into a running Feed Studio (standard library only).

    python demo/seed_demo.py                       # API at http://localhost:8080
    python demo/seed_demo.py --api http://localhost:8000 --token SECRET
    python demo/seed_demo.py --upload              # use the local demo_feed.xml instead of the HTTPS URL

It creates:
- source "Tienda demo" reading the fictional feed from its HTTPS URL on GitHub,
  refreshed automatically every 2 hours (Europe/Madrid);
- channel "Google Merchant Center" with automatic publication;
- the two demo rules ("Añadir descripcion vacia", "Añadir premium");
- a first full run (download → rules → validation → publication).

Nothing is created if a source named "Tienda demo" already exists.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEMO_URL = "https://raw.githubusercontent.com/raulbernardogil/feedstudio/main/demo/demo_feed.xml"
SOURCE_NAME = "Tienda demo"

CHANNEL = {
    "name": "Google Merchant Center",
    "kind": "google",
    "auto_publish": True,
    "settings": {"title": "Demo", "link": "https://www.tienda-demo.example",
                 "description": "Catálogo ficticio de demostración de Feed Studio"},
}

RULES = [
    {
        "name": "Añadir descripcion vacia",
        "priority": 80,
        "target": "description",
        "condition": {"operator": "and", "conditions": [{"field": "description", "operator": "is_empty"}]},
        "actions": [{"type": "set_value",
                     "template": "Descubre los mejores productos en nuestra tienda, envio en 24h y pago a plazos"}],
    },
    {
        "name": "Añadir premium",
        "priority": 100,
        "target": "title",
        "condition": {"operator": "and", "conditions": [{"field": "brand", "operator": "contains", "value": "ferro"}]},
        "actions": [{"type": "prepend", "template": "PREMIUM "}],
    },
]

SCHEDULE = {"mode": "interval", "every_hours": 2, "timezone": "Europe/Madrid"}


class Api:
    def __init__(self, base: str, token: str | None):
        self.base = base.rstrip("/")
        self.token = token

    def call(self, method: str, path: str, body: dict | None = None, raw: bytes | None = None,
             content_type: str = "application/json") -> dict:
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(f"{self.base}{path}", data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", content_type)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                text = res.read().decode()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            sys.exit(f"ERROR {exc.code} {method} {path}: {detail}")
        except urllib.error.URLError as exc:
            sys.exit(f"No se pudo conectar con {self.base}: {exc.reason}. ¿Está arrancado Feed Studio?")
        return json.loads(text) if text else {}

    def upload(self, path: Path, name: str) -> dict:
        boundary = uuid.uuid4().hex
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"name\"\r\n\r\n{name}\r\n".encode(),
            (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
             "Content-Type: application/xml\r\n\r\n").encode() + path.read_bytes() + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        return self.call("POST", "/api/sources/upload", raw=b"".join(parts),
                         content_type=f"multipart/form-data; boundary={boundary}")

    def wait(self, job_id: int, label: str) -> dict:
        for _ in range(300):
            job = self.call("GET", f"/api/jobs/{job_id}")
            if job["status"] in ("succeeded", "failed"):
                print(f"  {label}: {job['status']}" + (f" — {job['error']['message']}" if job.get("error") else ""))
                return job
            time.sleep(1)
        sys.exit(f"{label}: tiempo de espera agotado")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://localhost:8080", help="Feed Studio base URL")
    parser.add_argument("--token", default=None, help="FEEDSTUDIO_API_TOKEN, if the server requires it")
    parser.add_argument("--upload", action="store_true", help="upload demo/demo_feed.xml instead of using the HTTPS URL")
    parser.add_argument("--url", default=DEMO_URL, help="HTTPS URL of the demo feed")
    args = parser.parse_args()
    api = Api(args.api, args.token)

    if any(s["name"] == SOURCE_NAME for s in api.call("GET", "/api/sources")["items"]):
        sys.exit(f"Ya existe una fuente «{SOURCE_NAME}». Bórrala desde la interfaz si quieres volver a cargar la demo.")

    print("1. Fuente")
    if args.upload:
        created = api.upload(Path(__file__).with_name("demo_feed.xml"), SOURCE_NAME)
    else:
        created = api.call("POST", "/api/sources", {"name": SOURCE_NAME, "url": args.url})
    source_id = created["source"]["id"]
    if api.wait(created["job"]["id"], "importación")["status"] != "succeeded":
        sys.exit("La importación falló; revisa el mensaje anterior.")

    print("2. Canal")
    channel = api.call("POST", "/api/channels", {"source_id": source_id, **CHANNEL})
    print(f"  {channel['name']} (publicación automática)")

    print("3. Reglas")
    for rule in RULES:
        api.call("POST", "/api/rules", {"source_id": source_id, "channel_id": None, "definition": rule})
        print(f"  {rule['name']}")

    if not args.upload:
        print("4. Programación")
        source = api.call("PUT", f"/api/sources/{source_id}/schedule", SCHEDULE)
        print(f"  {source['schedule_label']}; próxima ejecución {source['next_run_at']}")

    print("5. Primera ejecución completa")
    run = api.call("POST", f"/api/sources/{source_id}/run")
    api.wait(run["job"]["id"], "actualización")
    channel = api.call("GET", f"/api/channels/{channel['id']}")
    print(f"\nDemo lista. Feed publicado: {channel['public_url']}")


if __name__ == "__main__":
    main()
