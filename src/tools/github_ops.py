"""GitHub access for the *website* repo. The app never pushes to the base branch: it opens Pull Requests."""
from __future__ import annotations

import base64
import time
from pathlib import PurePosixPath

from ..constants import TEXT_EXT


class GitHubError(Exception):
    pass


def safe_path(path: str) -> bool:
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        return False
    if p.parts[0] in (".github", ".git"):  # never let generated content alter CI/workflows
        return False
    return p.suffix.lower() in TEXT_EXT


class GitHubOps:
    def __init__(self, token: str, repo_name: str, base_branch: str = "main"):
        if not token or not repo_name:
            raise GitHubError("GITHUB_TOKEN and SITE_REPO (owner/repo) are required.")
        try:
            from github import Github
        except ImportError as exc:  # pragma: no cover
            raise GitHubError("PyGithub is not installed (pip install PyGithub).") from exc
        self.gh = Github(token)
        self.repo = self.gh.get_repo(repo_name)
        self.base = base_branch

    def check(self) -> str:
        b = self.repo.get_branch(self.base)
        return f"Connected to {self.repo.full_name}, branch '{self.base}' at {b.commit.sha[:7]}."

    def fetch_text_files(self, max_files: int = 500, max_bytes: int = 1_000_000) -> dict[str, str]:
        tree = self.repo.get_git_tree(self.base, recursive=True)
        files: dict[str, str] = {}
        for el in tree.tree:
            if el.type != "blob" or not safe_path(el.path) or (el.size or 0) > max_bytes:
                continue
            blob = self.repo.get_git_blob(el.sha)
            try:
                files[el.path] = base64.b64decode(blob.content).decode("utf-8")
            except UnicodeDecodeError:
                continue
            if len(files) >= max_files:
                break
        return files

    def open_pr(self, files: dict[str, str], branch_prefix: str, title: str, body: str, draft: bool = True) -> str:
        bad = [p for p in files if not safe_path(p)]
        if bad:
            raise GitHubError(f"Refusing to write unsafe paths: {bad[:5]}")
        if not files:
            raise GitHubError("Nothing to commit.")
        branch = f"{branch_prefix}-{time.strftime('%H%M%S')}"
        if branch == self.base:
            raise GitHubError("Refusing to write to the base branch.")
        sha = self.repo.get_branch(self.base).commit.sha
        self.repo.create_git_ref(ref=f"refs/heads/{branch}", sha=sha)
        for path, content in files.items():
            msg = f"SEO autopilot: update {path}"
            try:
                existing = self.repo.get_contents(path, ref=branch)
                self.repo.update_file(path, msg, content, existing.sha, branch=branch)
            except Exception as exc:
                if getattr(exc, "status", None) == 404:
                    self.repo.create_file(path, msg, content, branch=branch)
                else:
                    raise
        pr = self.repo.create_pull(title=title, body=body, head=branch, base=self.base, draft=draft)
        return pr.html_url

    def merge_pr_number(self, number: int) -> str:  # only used when ALLOW_AUTOMERGE_LOW_RISK=true
        pr = self.repo.get_pull(number)
        if pr.draft:
            raise GitHubError("Draft PRs cannot be merged; mark it ready for review first.")
        res = pr.merge(merge_method="squash")
        return res.message
