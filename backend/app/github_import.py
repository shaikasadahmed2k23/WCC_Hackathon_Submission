"""Import a public GitHub repository's README and issues/PRs as sources."""
import base64
import json
import os
import re
import urllib.error
import urllib.request


class GitHubError(ValueError):
    pass


def parse_repo(ref: str):
    m = re.match(r"^(?:https?://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$", ref.strip())
    if not m:
        raise GitHubError("Enter a repository as owner/name or a github.com URL.")
    return m.group(1), m.group(2)


def _get(path):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ContinuityOS"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.github.com" + path, headers=headers), timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise GitHubError("Repository not found, or it is private. Only public repositories can be imported in this build.")
        if exc.code in (403, 429):
            raise GitHubError("GitHub rate limit reached. Try again later or set GITHUB_TOKEN on the server.")
        raise GitHubError(f"GitHub returned an error ({exc.code}).")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise GitHubError("Could not reach GitHub from the server.")


def fetch_repo(owner: str, repo: str, max_issues: int = 40):
    """Return [(source_name, text, doc_date)] built from README and issues."""
    out = []
    try:
        readme = _get(f"/repos/{owner}/{repo}/readme")
        text = base64.b64decode(readme["content"]).decode("utf-8", "replace")
        out.append((f"{owner}/{repo}/README.md", text, None))
    except GitHubError as exc:
        if "not found" in str(exc).lower():
            raise
    issues = _get(f"/repos/{owner}/{repo}/issues?state=all&per_page={min(max_issues, 100)}")
    blocks = []
    for it in issues:
        body = (it.get("body") or "").strip().replace("\r\n", "\n")
        kind = "Pull request" if it.get("pull_request") else "Issue"
        head = f"{kind} #{it['number']} ({it['state']}), opened {str(it['created_at'])[:10]} by {it['user']['login']}: {it['title']}."
        blocks.append((head + ("\n" + body[:900] if body else "")).strip())
    if blocks:
        out.append((f"{owner}/{repo} issues and pull requests", "\n\n".join(blocks), None))
    if not out:
        raise GitHubError("The repository has no README or issues to import.")
    return out
