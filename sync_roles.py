#!/usr/bin/env python3
"""
Daily Jamf roles sync for roleAutomatorRoles repo.

- Fetches:
  - Classic API minimum required privileges
  - Jamf Pro API "Privileges and Deprecations"
- Writes:
  - roles/jamf-roles.json
  - roles/classic-api-roles.json
  - roles/jamf-pro-api-roles.json
  - roles/privilege-categories.json
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import requests
from bs4 import BeautifulSoup

CLASSIC_URL = "https://developer.jamf.com/jamf-pro/docs/classic-api-minimum-required-privileges-and-endpoint-mapping"
PROD_URL = "https://developer.jamf.com/jamf-pro/docs/privileges-and-deprecations"

ROOT = Path(__file__).resolve().parent
ROLES_DIR = ROOT / "roles"
DOCS_DIR = ROOT / "docs"


def clean(s: str) -> str:
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def fetch_html(url: str, timeout: int = 30) -> str:
    r = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": "roleAutomatorRoles-sync/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    r.raise_for_status()
    return r.text


def find_best_table(soup: BeautifulSoup, required_headers: List[str]) -> Optional[Tuple[List[str], BeautifulSoup]]:
    required = [h.lower() for h in required_headers]

    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if not header_row:
            continue
        ths = header_row.find_all("th")
        if not ths:
            continue
        headers = [clean(th.get_text()).lower() for th in ths]

        ok = True
        for req in required:
            if not any(req in h for h in headers):
                ok = False
                break
        if ok:
            return headers, table

    return None


@dataclass(frozen=True)
class ClassicRow:
    endpoint: str
    operation: str
    required_privileges: str


@dataclass(frozen=True)
class ProdRow:
    endpoint: str
    operation: str
    privilege_requirements: str
    deprecation_date: str  # may be "N/A"


def parse_classic(html: str) -> List[ClassicRow]:
    soup = BeautifulSoup(html, "html.parser")

    found = find_best_table(
        soup,
        required_headers=["Endpoint", "Operation", "Required Privilege"],
    )
    if not found:
        raise RuntimeError("Classic API table not found (page layout changed).")

    headers, table = found

    def idx_contains(key: str) -> int:
        key = key.lower()
        for i, h in enumerate(headers):
            if key in h:
                return i
        return -1

    i_endpoint = idx_contains("endpoint")
    i_operation = idx_contains("operation")
    i_priv = idx_contains("required")

    if min(i_endpoint, i_operation, i_priv) < 0:
        raise RuntimeError(f"Classic API table headers unexpected: {headers}")

    rows: List[ClassicRow] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        cells = [clean(td.get_text(" ", strip=True)) for td in tds]
        if max(i_endpoint, i_operation, i_priv) >= len(cells):
            continue

        endpoint = cells[i_endpoint]
        operation = cells[i_operation].upper()
        privs = cells[i_priv]

        if not endpoint or not operation:
            continue

        rows.append(
            ClassicRow(
                endpoint=endpoint,
                operation=operation,
                required_privileges=privs,
            )
        )

    seen = set()
    out: List[ClassicRow] = []
    for r in rows:
        k = (r.endpoint, r.operation, r.required_privileges)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def parse_prod(html: str) -> List[ProdRow]:
    soup = BeautifulSoup(html, "html.parser")

    found = find_best_table(
        soup,
        required_headers=["Endpoint", "Operation", "Privilege Requirements", "Deprecation Date"],
    )
    if not found:
        raise RuntimeError("Privileges and Deprecations table not found (page layout changed).")

    headers, table = found

    def idx_contains(name: str) -> int:
        name = name.lower()
        for i, h in enumerate(headers):
            if name in h:
                return i
        return -1

    i_endpoint = idx_contains("endpoint")
    i_operation = idx_contains("operation")
    i_priv = idx_contains("privilege")
    i_depr = idx_contains("deprecation")

    if min(i_endpoint, i_operation, i_priv, i_depr) < 0:
        raise RuntimeError(f"Prod API table headers unexpected: {headers}")

    rows: List[ProdRow] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        cells = [clean(td.get_text(" ", strip=True)) for td in tds]
        if max(i_endpoint, i_operation, i_priv, i_depr) >= len(cells):
            continue

        endpoint = cells[i_endpoint]
        operation = cells[i_operation].upper()
        privs = cells[i_priv]
        depr = cells[i_depr] if cells[i_depr] else "N/A"

        if not endpoint or not operation:
            continue

        rows.append(
            ProdRow(
                endpoint=endpoint,
                operation=operation,
                privilege_requirements=privs,
                deprecation_date=depr,
            )
        )

    seen = set()
    out: List[ProdRow] = []
    for r in rows:
        k = (r.endpoint, r.operation, r.privilege_requirements, r.deprecation_date)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def build_schema(classic_rows: List[ClassicRow], prod_rows: List[ProdRow]) -> Dict[str, Any]:
    all_privs = set()

    classic_endpoints = []
    for r in classic_rows:
        privs = [p.strip() for p in r.required_privileges.split(",") if p.strip()]
        classic_endpoints.append(
            {
                "endpoint": r.endpoint,
                "operation": r.operation,
                "privileges": privs,
                "deprecation_date": None,
            }
        )
        all_privs.update(privs)

    prod_endpoints = []
    for r in prod_rows:
        privs = [p.strip() for p in r.privilege_requirements.split(",") if p.strip()]
        deprecation = r.deprecation_date.strip() if r.deprecation_date else "N/A"
        if deprecation.upper() == "N/A":
            deprecation = None
        prod_endpoints.append(
            {
                "endpoint": r.endpoint,
                "operation": r.operation,
                "privileges": privs,
                "deprecation_date": deprecation,
            }
        )
        all_privs.update(privs)

    categories: Dict[str, List[str]] = {}
    for privilege in sorted(all_privs):
        if " - " in privilege:
            action, resource = privilege.split(" - ", 1)
            action = action.strip()
        else:
            action = "Other"
            resource = privilege
        categories.setdefault(action, [])
        if resource not in categories[action]:
            categories[action].append(resource)

    schema: Dict[str, Any] = {
        "version": "1.0.0",
        "last_updated": datetime.now().isoformat(),
        "metadata": {
            "description": "Jamf Pro API Role and Privilege Mappings",
            "source": "Jamf Developer Documentation",
            "documentation_urls": [PROD_URL, CLASSIC_URL],
        },
        "privilege_categories": categories,
        "all_privileges": sorted(list(all_privs)),
        "classic_api": {
            "description": "Classic API (XML-based) endpoints and required privileges",
            "endpoints": classic_endpoints,
        },
        "jamf_pro_api": {
            "description": "Jamf Pro API (REST-based) endpoints and required privileges",
            "endpoints": prod_endpoints,
        },
    }
    return schema


def main() -> int:
    ROLES_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    print("🔗 Fetching Jamf docs...")
    classic_html = fetch_html(CLASSIC_URL)
    prod_html = fetch_html(PROD_URL)

    print("📊 Parsing tables...")
    classic_rows = parse_classic(classic_html)
    prod_rows = parse_prod(prod_html)

    print(f"✅ Classic rows: {len(classic_rows)}")
    print(f"✅ Prod rows: {len(prod_rows)}")

    schema = build_schema(classic_rows, prod_rows)

    (ROLES_DIR / "jamf-roles.json").write_text(
        json.dumps(schema, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    classic_only = {
        "version": schema["version"],
        "last_updated": schema["last_updated"],
        "endpoints": schema["classic_api"]["endpoints"],
    }
    (ROLES_DIR / "classic-api-roles.json").write_text(
        json.dumps(classic_only, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    prod_only = {
        "version": schema["version"],
        "last_updated": schema["last_updated"],
        "endpoints": schema["jamf_pro_api"]["endpoints"],
    }
    (ROLES_DIR / "jamf-pro-api-roles.json").write_text(
        json.dumps(prod_only, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    priv_cats = {
        "version": schema["version"],
        "categories": schema["privilege_categories"],
        "all_privileges": schema["all_privileges"],
    }
    (ROLES_DIR / "privilege-categories.json").write_text(
        json.dumps(priv_cats, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("🎉 Completed writing roles/*.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
