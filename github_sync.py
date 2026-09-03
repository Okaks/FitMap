"""GitHub persistence for the dataset.

Falls back to download-only when no token is configured, so the app runs
locally and for demo visitors without any setup.
"""

import base64
import json
import urllib.error
import urllib.request

API = "https://api.github.com"


def _cfg(secrets):
    try:
        gh = secrets.get("github", {})
    except Exception:
        return None
    needed = ("token", "repo", "path")
    if not all(gh.get(k) for k in needed):
        return None
    return {
        "token": gh["token"],
        "repo": gh["repo"],
        "path": gh["path"],
        "branch": gh.get("branch", "main"),
    }


def configured(secrets):
    return _cfg(secrets) is not None


def _request(url, token, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def current_sha(secrets):
    cfg = _cfg(secrets)
    if not cfg:
        return None
    url = f"{API}/repos/{cfg['repo']}/contents/{cfg['path']}?ref={cfg['branch']}"
    try:
        return _request(url, cfg["token"])["sha"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def push(secrets, companies, message):
    """Commit the dataset. Returns (ok, detail)."""
    cfg = _cfg(secrets)
    if not cfg:
        return False, "No GitHub credentials configured."

    payload_doc = {
        "project": "Yellow Card Customer Opportunity Scoring Engine",
        "framework_version": "1.4",
        "counts": {"total_rows": len(companies)},
        "companies": companies,
    }
    body = json.dumps(payload_doc, indent=2, ensure_ascii=False)

    try:
        sha = current_sha(secrets)
    except Exception as e:
        return False, f"Could not read the current file: {e}"

    url = f"{API}/repos/{cfg['repo']}/contents/{cfg['path']}"
    payload = {
        "message": message,
        "content": base64.b64encode(body.encode()).decode(),
        "branch": cfg["branch"],
    }
    if sha:
        payload["sha"] = sha

    try:
        res = _request(url, cfg["token"], method="PUT", payload=payload)
        return True, res.get("commit", {}).get("html_url", "committed")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        if e.code == 409:
            return False, "Someone else changed the file since this session loaded. Reload the app and redo the edit."
        if e.code in (401, 403):
            return False, "GitHub rejected the token. Check it has Contents write access to this repo."
        return False, f"GitHub returned {e.code}: {detail}"
    except Exception as e:
        return False, str(e)
