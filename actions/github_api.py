"""SONIC AI — GitHub Integration

Full GitHub control via gh CLI (already authenticated).
Features:
- View/manage repositories
- View/create/update issues
- View/create/manage pull requests
- View commits, releases
- Search code, issues, repos
- View notifications
- Manage branches

Usage:
    "GitHub pe mere repos dikhao"
    "Is repo mein naya issue banao"
    "Pull requests check karo"
    "Commits dikhao last 5"
    "Code search karo Python mein"
"""
from __future__ import annotations

import json
import subprocess
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("GITHUB_API")

# ── gh CLI wrapper ──────────────────────────────────────────────────────

def _gh(args: list[str], timeout: int = 30) -> dict:
    """Run a gh CLI command and return parsed output."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )

        if result.returncode != 0:
            return {"error": result.stderr.strip() or "Command failed"}

        output = result.stdout.strip()
        if not output:
            return {"success": True, "message": "Command executed successfully"}

        # Try to parse as JSON
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"output": output}

    except subprocess.TimeoutExpired:
        return {"error": "Command timed out"}
    except FileNotFoundError:
        return {"error": "gh CLI not found. Install from: https://cli.github.com/"}
    except Exception as e:
        return {"error": str(e)}


def _gh_raw(args: list[str], timeout: int = 30) -> str:
    """Run gh CLI and return raw output (no JSON wrapping)."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


# ── Repository Operations ───────────────────────────────────────────────

def _repos_list(limit: int = 20) -> dict:
    """List user's repositories."""
    result = _gh(["repo", "list", "--limit", str(limit)])
    if "output" in result:
        # Parse tab-separated output
        lines = result["output"].strip().split("\n")
        repos = []
        for line in lines:
            parts = line.split("\t")
            if len(parts) >= 1:
                repos.append({
                    "name": parts[0],
                    "description": parts[1] if len(parts) > 1 else "",
                    "visibility": parts[2] if len(parts) > 2 else "",
                    "updated": parts[3] if len(parts) > 3 else "",
                })
        return repos
    return result


def _repo_view(repo: str = "") -> dict:
    """View repository details."""
    if repo:
        return _gh(["repo", "view", repo])
    return _gh(["repo", "view"])


def _repo_create(name: str, description: str = "", private: bool = False) -> dict:
    """Create a new repository."""
    args = ["repo", "create", name]
    if description:
        args.extend(["--description", description])
    if private:
        args.append("--private")
    else:
        args.append("--public")
    return _gh(args)


def _repo_clone(repo: str, destination: str = "") -> dict:
    """Clone a repository."""
    args = ["repo", "clone", repo]
    if destination:
        args.append(destination)
    return _gh(args)


# ── Issue Operations ────────────────────────────────────────────────────

def _issues_list(repo: str = "", state: str = "open", limit: int = 20) -> dict:
    """List issues."""
    args = ["issue", "list", "--state", state, "--limit", str(limit)]
    if repo:
        args.extend(["--repo", repo])
    return _gh(args)


def _issue_view(repo: str, issue_number: int) -> dict:
    """View an issue."""
    args = ["issue", "view", str(issue_number)]
    if repo:
        args.extend(["--repo", repo])
    return _gh(args)


def _issue_create(repo: str, title: str, body: str = "", labels: list = None) -> dict:
    """Create a new issue."""
    args = ["issue", "create", "--repo", repo, "--title", title]
    if body:
        args.extend(["--body", body])
    if labels:
        args.extend(["--label", ",".join(labels)])
    return _gh(args)


def _issue_close(repo: str, issue_number: int) -> dict:
    """Close an issue."""
    return _gh(["issue", "close", str(issue_number), "--repo", repo])


def _issue_comment(repo: str, issue_number: int, comment: str) -> dict:
    """Add a comment to an issue."""
    return _gh(["issue", "comment", str(issue_number), "--repo", repo, "--body", comment])


# ── Pull Request Operations ─────────────────────────────────────────────

def _prs_list(repo: str = "", state: str = "open", limit: int = 20) -> dict:
    """List pull requests."""
    args = ["pr", "list", "--state", state, "--limit", str(limit)]
    if repo:
        args.extend(["--repo", repo])
    return _gh(args)


def _pr_view(repo: str, pr_number: int) -> dict:
    """View a pull request."""
    args = ["pr", "view", str(pr_number)]
    if repo:
        args.extend(["--repo", repo])
    return _gh(args)


def _pr_merge(repo: str, pr_number: int) -> dict:
    """Merge a pull request."""
    return _gh(["pr", "merge", str(pr_number), "--merge", "--repo", repo])


def _pr_close(repo: str, pr_number: int) -> dict:
    """Close a pull request."""
    return _gh(["pr", "close", str(pr_number), "--repo", repo])


# ── Commit Operations ───────────────────────────────────────────────────

def _commits_list(repo: str = "", limit: int = 10) -> dict:
    """List recent commits."""
    args = ["api", "repos/{owner}/{repo}/commits"]
    if repo:
        # Parse owner/repo
        parts = repo.split("/")
        if len(parts) == 2:
            args = ["api", f"repos/{parts[0]}/{parts[1]}/commits"]
    else:
        # Get current repo's commits
        args = ["api", "repos/{owner}/{repo}/commits"]

    args.extend(["--paginate", "--jq", f".[0:{limit}]"])
    return _gh(args)


def _commits_list_current(limit: int = 10) -> dict:
    """List commits in current repo."""
    result = _gh_raw(["log", f"--oneline", f"-{limit}"])
    return {"output": result}


# ── Search Operations ───────────────────────────────────────────────────

def _search_repos(query: str, limit: int = 10) -> dict:
    """Search repositories."""
    return _gh(["search", "repos", query, "--limit", str(limit)])


def _search_issues(query: str, limit: int = 10) -> dict:
    """Search issues."""
    return _gh(["search", "issues", query, "--limit", str(limit)])


def _search_code(query: str, limit: int = 10) -> dict:
    """Search code."""
    return _gh(["search", "code", query, "--limit", str(limit)])


# ── Notification Operations ─────────────────────────────────────────────

def _notifications_list(limit: int = 20) -> dict:
    """List GitHub notifications."""
    return _gh(["api", "notifications", "--paginate", "--jq", f".[0:{limit}]"])


# ── Release Operations ──────────────────────────────────────────────────

def _releases_list(repo: str = "", limit: int = 5) -> dict:
    """List releases."""
    args = ["release", "list"]
    if repo:
        args.extend(["--repo", repo])
    args.extend(["--limit", str(limit)])
    return _gh(args)


# ── Tool Interface ──────────────────────────────────────────────────────

def github_api(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    GitHub integration tool.
    Full GitHub control via gh CLI.
    """
    action = parameters.get("action", "repos")
    repo = parameters.get("repo", "")
    limit = parameters.get("limit", 10)

    # ── Repository Actions ──
    if action == "repos":
        result = _repos_list(limit)
        if isinstance(result, list):
            lines = [f"Repositories ({len(result)}):"]
            for r in result:
                stars = r.get("stargazerCount", 0)
                lang = r.get("primaryLanguage", {}).get("name", "N/A") if r.get("primaryLanguage") else "N/A"
                lines.append(f"  {r['name']} [{lang}] Stars: {stars} - {r.get('description', '')[:50]}")
            return "\n".join(lines)
        return json.dumps(result, indent=2)

    elif action == "repo_view":
        result = _repo_view(repo)
        if isinstance(result, dict) and "name" in result:
            return (
                f"Repo: {result['name']}\n"
                f"Description: {result.get('description', 'N/A')}\n"
                f"Stars: {result.get('stargazerCount', 0)}\n"
                f"Forks: {result.get('forkCount', 0)}\n"
                f"Language: {result.get('primaryLanguage', {}).get('name', 'N/A') if result.get('primaryLanguage') else 'N/A'}\n"
                f"URL: {result.get('url', 'N/A')}"
            )
        return json.dumps(result, indent=2)

    elif action == "repo_create":
        name = parameters.get("name", "")
        if not name:
            return "Error: repo name is required"
        desc = parameters.get("description", "")
        private = parameters.get("private", False)
        result = _repo_create(name, desc, private)
        return json.dumps(result, indent=2)

    # ── Issue Actions ──
    elif action == "issues":
        result = _issues_list(repo, limit=limit)
        if isinstance(result, list):
            lines = [f"Issues ({len(result)}):"]
            for i in result:
                labels = ", ".join(l["name"] for l in i.get("labels", []))
                lines.append(f"  #{i['number']}: {i['title']} [{i['state']}] {labels}")
            return "\n".join(lines)
        return json.dumps(result, indent=2)

    elif action == "issue_view":
        issue_num = parameters.get("issue_number", 0)
        if not issue_num:
            return "Error: issue_number is required"
        result = _issue_view(repo, issue_num)
        if isinstance(result, dict) and "title" in result:
            return (
                f"Issue #{result['number']}: {result['title']}\n"
                f"State: {result['state']}\n"
                f"Author: {result.get('author', {}).get('login', 'N/A')}\n"
                f"Body:\n{result.get('body', 'N/A')[:500]}"
            )
        return json.dumps(result, indent=2)

    elif action == "issue_create":
        title = parameters.get("title", "")
        if not title or not repo:
            return "Error: repo and title are required"
        body = parameters.get("body", "")
        labels = parameters.get("labels", [])
        result = _issue_create(repo, title, body, labels)
        return json.dumps(result, indent=2)

    elif action == "issue_close":
        issue_num = parameters.get("issue_number", 0)
        if not issue_num or not repo:
            return "Error: repo and issue_number are required"
        result = _issue_close(repo, issue_num)
        return json.dumps(result, indent=2)

    elif action == "issue_comment":
        issue_num = parameters.get("issue_number", 0)
        comment = parameters.get("comment", "")
        if not issue_num or not repo or not comment:
            return "Error: repo, issue_number, and comment are required"
        result = _issue_comment(repo, issue_num, comment)
        return json.dumps(result, indent=2)

    # ── Pull Request Actions ──
    elif action == "prs":
        result = _prs_list(repo, limit=limit)
        if isinstance(result, list):
            lines = [f"Pull Requests ({len(result)}):"]
            for pr in result:
                lines.append(f"  #{pr['number']}: {pr['title']} [{pr['state']}] by {pr.get('author', {}).get('login', 'N/A')}")
            return "\n".join(lines)
        return json.dumps(result, indent=2)

    elif action == "pr_view":
        pr_num = parameters.get("pr_number", 0)
        if not pr_num:
            return "Error: pr_number is required"
        result = _pr_view(repo, pr_num)
        return json.dumps(result, indent=2)

    elif action == "pr_merge":
        pr_num = parameters.get("pr_number", 0)
        if not pr_num or not repo:
            return "Error: repo and pr_number are required"
        result = _pr_merge(repo, pr_num)
        return json.dumps(result, indent=2)

    # ── Commit Actions ──
    elif action == "commits":
        result = _commits_list_current(limit)
        return result.get("output", json.dumps(result, indent=2))

    # ── Search Actions ──
    elif action == "search_repos":
        query = parameters.get("query", "")
        if not query:
            return "Error: query is required"
        result = _search_repos(query, limit)
        if isinstance(result, list):
            lines = [f"Search Results ({len(result)}):"]
            for r in result:
                lines.append(f"  {r['fullName']} - {r.get('description', '')[:60]}")
            return "\n".join(lines)
        return json.dumps(result, indent=2)

    elif action == "search_issues":
        query = parameters.get("query", "")
        if not query:
            return "Error: query is required"
        result = _search_issues(query, limit)
        return json.dumps(result, indent=2)

    elif action == "search_code":
        query = parameters.get("query", "")
        if not query:
            return "Error: query is required"
        result = _search_code(query, limit)
        return json.dumps(result, indent=2)

    # ── Notification Actions ──
    elif action == "notifications":
        result = _notifications_list(limit)
        if isinstance(result, list):
            lines = [f"Notifications ({len(result)}):"]
            for n in result[:limit]:
                repo_name = n.get("repository", {}).get("fullName", "N/A")
                subject = n.get("subject", {}).get("title", "N/A")
                lines.append(f"  [{repo_name}] {subject}")
            return "\n".join(lines)
        return json.dumps(result, indent=2)

    # ── Release Actions ──
    elif action == "releases":
        result = _releases_list(repo, limit)
        if isinstance(result, list):
            lines = [f"Releases ({len(result)}):"]
            for r in result:
                lines.append(f"  {r['tagName']} - {r['name']} ({r['publishedAt'][:10]})")
            return "\n".join(lines)
        return json.dumps(result, indent=2)

    return f"Unknown action: {action}. Use: repos, repo_view, repo_create, issues, issue_view, issue_create, issue_close, issue_comment, prs, pr_view, pr_merge, commits, search_repos, search_issues, search_code, notifications, releases"
