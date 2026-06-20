from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "sports-lit-digest/0.1 (https://github.com/example/sports-lit-digest)"


def load_env(root: Path = ROOT) -> None:
    """Load a local .env without requiring python-dotenv."""
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
        return
    except ModuleNotFoundError:
        pass

    env_path = root / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_yaml_config(path: Path) -> dict[str, Any]:
    """Load YAML, falling back to JSON-compatible YAML if PyYAML is absent."""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml

        data = yaml.safe_load(text)
        return data or {}
    except ModuleNotFoundError:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"{path} requires PyYAML because it is not JSON-compatible YAML."
            ) from exc


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff%+-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_doi(value: Any) -> str:
    doi = str(value or "").strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:\s*", "", doi)
    return doi.strip()


def bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def http_get_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    text = http_get_text(url, params=params, headers=headers, timeout=timeout)
    return json.loads(text)


def http_post_json(
    url: str,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    text = http_post_text(url, data=data, headers=headers, timeout=timeout)
    return json.loads(text)


def http_get_text(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> str:
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)

    try:
        import requests

        response = requests.get(url, params=params, headers=request_headers, timeout=timeout)
        response.raise_for_status()
        return response.text
    except ModuleNotFoundError:
        pass
    except Exception as exc:
        raise RuntimeError(f"GET {url} failed: {exc}") from exc

    full_url = _url_with_params(url, params)
    request = urllib.request.Request(full_url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed with HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GET {url} failed: {exc.reason}") from exc


def http_post_text(
    url: str,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> str:
    request_headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if headers:
        request_headers.update(headers)
    cleaned = {key: value for key, value in (data or {}).items() if value not in (None, "")}

    try:
        import requests

        response = requests.post(url, data=cleaned, headers=request_headers, timeout=timeout)
        response.raise_for_status()
        return response.text
    except ModuleNotFoundError:
        pass
    except Exception as exc:
        raise RuntimeError(f"POST {url} failed: {exc}") from exc

    encoded = urllib.parse.urlencode(cleaned, doseq=True).encode("utf-8")
    request = urllib.request.Request(url, data=encoded, headers=request_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} failed with HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"POST {url} failed: {exc.reason}") from exc


def _url_with_params(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    cleaned = {key: value for key, value in params.items() if value not in (None, "")}
    query = urllib.parse.urlencode(cleaned, doseq=True)
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query}"


def read_seen(path: Path) -> dict[str, set[str]]:
    if not path.exists():
        return {"dois": set(), "pmids": set()}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "dois": {normalize_doi(doi) for doi in data.get("dois", []) if doi},
        "pmids": {str(pmid) for pmid in data.get("pmids", []) if pmid},
    }


def write_seen(path: Path, seen: dict[str, set[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "dois": sorted(seen.get("dois", set())),
        "pmids": sorted(seen.get("pmids", set())),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add_seen_paper(seen: dict[str, set[str]], paper: dict[str, Any]) -> None:
    doi = normalize_doi(paper.get("doi"))
    pmid = str(paper.get("pmid") or "").strip()
    if doi:
        seen.setdefault("dois", set()).add(doi)
    if pmid:
        seen.setdefault("pmids", set()).add(pmid)


def is_seen_paper(seen: dict[str, set[str]], paper: dict[str, Any]) -> bool:
    doi = normalize_doi(paper.get("doi"))
    pmid = str(paper.get("pmid") or "").strip()
    return bool((doi and doi in seen.get("dois", set())) or (pmid and pmid in seen.get("pmids", set())))
