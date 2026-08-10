#!/usr/bin/env python3
"""Create a one-time development enrollment credential file."""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--token")
    parser.add_argument("--tenant-id", default="dev-tenant")
    parser.add_argument("--site-id", default="dev-site")
    parser.add_argument("--environment", default="development")
    parser.add_argument("--identity-domain", default="observability.local")
    parser.add_argument("--host-name")
    parser.add_argument("--agent-version")
    parser.add_argument("--capability", action="append", default=[])
    args = parser.parse_args()

    store = Path(args.store)
    token = args.token or secrets.token_urlsafe(32)
    data = json.loads(store.read_text()) if store.exists() else {"tokens": {}}
    data.setdefault("tokens", {})[token] = {
        "tenant_id": args.tenant_id,
        "site_id": args.site_id,
        "environment": args.environment,
        "identity_domain": args.identity_domain,
        "purpose": "enrollment",
        "host_name": args.host_name,
        "agent_version": args.agent_version,
        "capabilities": args.capability,
        "used": False,
    }
    store.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(token)


if __name__ == "__main__":
    main()
