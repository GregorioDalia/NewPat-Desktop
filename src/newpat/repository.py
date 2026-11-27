"""GitHub repository identity during the NewPat repository rename."""

import os

REPOSITORY_ID = "1307623649"
REPOSITORY_INFO_URL = f"https://api.github.com/repositories/{REPOSITORY_ID}"
LEGACY_REPOSITORY = "GregorioDalia/nipat-desktop"
RENAMED_REPOSITORY = "GregorioDalia/NewPat-Desktop"
OFFICIAL_REPOSITORIES = (RENAMED_REPOSITORY, LEGACY_REPOSITORY)


def official_actions_context() -> bool:
    return (os.environ.get("GITHUB_REPOSITORY_ID") == REPOSITORY_ID
            and os.environ.get("GITHUB_REPOSITORY") in OFFICIAL_REPOSITORIES)


def build_repository() -> str:
    """Choose the current CI name for official runs and the canonical name locally."""
    return os.environ["GITHUB_REPOSITORY"] if official_actions_context() else RENAMED_REPOSITORY


def release_urls(path: str) -> tuple[str, ...]:
    """Exact old/new URL candidates for one caller-validated release path."""
    if not path.startswith("/releases/"):
        raise ValueError("Expected a release path.")
    return tuple(f"https://github.com/{repository}{path}" for repository in OFFICIAL_REPOSITORIES)
