"""
GitHub client wrapper dùng PyGithub.

Hỗ trợ 2 auth mode:
- Personal Access Token (PAT): dùng khi dev/test
- GitHub App (App ID + private key): dùng khi production
"""

from github import Github, GithubIntegration, Auth
from github.PullRequest import PullRequest
from github.Repository import Repository

from app.config import settings


def _get_github_client() -> Github:
    """Trả về Github client dùng PAT hoặc GitHub App token."""
    if settings.github_token:
        return Github(auth=Auth.Token(settings.github_token))

    # GitHub App auth
    with open(settings.github_private_key_path) as f:
        private_key = f.read()

    integration = GithubIntegration(
        auth=Auth.AppAuth(settings.github_app_id, private_key)
    )
    # Lấy installation token đầu tiên (single-repo bot)
    installation = integration.get_installations()[0]
    return installation.get_github_for_installation()


def get_repo(repo_full_name: str) -> Repository:
    """Lấy Repository object theo 'owner/repo'."""
    client = _get_github_client()
    return client.get_repo(repo_full_name)


def get_pull_request(repo_full_name: str, pr_number: int) -> PullRequest:
    """Lấy PullRequest object."""
    repo = get_repo(repo_full_name)
    return repo.get_pull(pr_number)


def get_pr_diff(repo_full_name: str, pr_number: int) -> str:
    """
    Trả về toàn bộ diff của PR dưới dạng string.
    Mỗi file thay đổi được nối nhau bằng separator.
    """
    pr = get_pull_request(repo_full_name, pr_number)
    files = pr.get_files()

    diff_parts: list[str] = []
    for f in files:
        header = f"--- a/{f.filename}\n+++ b/{f.filename}"
        patch = f.patch or "(binary or no diff)"
        diff_parts.append(f"{header}\n{patch}")

    return "\n\n".join(diff_parts)


def post_pr_comment(repo_full_name: str, pr_number: int, body: str) -> None:
    """Đăng comment lên PR."""
    pr = get_pull_request(repo_full_name, pr_number)
    pr.create_issue_comment(body)


def list_open_prs(repo_full_name: str) -> list[dict]:
    """Liệt kê các PR đang mở (số, title, author)."""
    repo = get_repo(repo_full_name)
    return [
        {
            "number": pr.number,
            "title": pr.title,
            "author": pr.user.login,
            "url": pr.html_url,
        }
        for pr in repo.get_pulls(state="open")
    ]
