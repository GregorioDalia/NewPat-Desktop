"""GitHub identity of the official NewPat repository."""

import os

REPOSITORY_ID = "1307623649"
REPOSITORY = "GregorioDalia/NewPat-Desktop"
REPOSITORY_INFO_URL = f"https://api.github.com/repositories/{REPOSITORY_ID}"
OFFICIAL_REPOSITORIES = (REPOSITORY,)


def official_actions_context() -> bool:
    return (os.environ.get("GITHUB_REPOSITORY_ID") == REPOSITORY_ID
            and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY)


def build_repository() -> str:
    return REPOSITORY


def release_urls(path: str) -> tuple[str, ...]:
    if not path.startswith("/releases/"):
        raise ValueError("Expected a release path.")
    return (f"https://github.com/{REPOSITORY}{path}",)
