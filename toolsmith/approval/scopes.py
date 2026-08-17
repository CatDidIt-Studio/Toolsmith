"""Translating scope names into what they actually let someone do.

A card that says `repo` has told the user nothing. Almost nobody knows that
GitHub's `repo` scope reaches every private repository on the account, which
is precisely why over-broad scopes get approved: the string looks modest and
the consequence is not written anywhere the person clicking can see it.

So the card never shows a bare scope name. It shows the consequence, and the
scope name second.

Unknown scopes are deliberately not silent. An unrecognised scope is rendered
as unknown and treated as high risk, because the failure we can least afford
is a permission slipping past because this table was incomplete.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Risk = Literal["low", "medium", "high", "critical"]

_RISK_ORDER: dict[Risk, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class ScopeMeaning:
    scope: str
    consequence: str
    risk: Risk
    # Set when the scope reaches beyond the resource the task named.
    account_wide: bool = False


_GITHUB: dict[str, ScopeMeaning] = {
    # Classic OAuth scopes.
    "repo": ScopeMeaning(
        "repo",
        "Read and write every repository on your account, including private ones",
        "critical",
        account_wide=True,
    ),
    "public_repo": ScopeMeaning(
        "public_repo", "Read and write all of your public repositories", "high", True
    ),
    "delete_repo": ScopeMeaning(
        "delete_repo", "Permanently delete repositories", "critical", True
    ),
    "admin:org": ScopeMeaning(
        "admin:org",
        "Administer your organisations, including membership and settings",
        "critical",
        True,
    ),
    "read:org": ScopeMeaning(
        "read:org", "Read your organisation membership and team structure", "medium", True
    ),
    "read:user": ScopeMeaning(
        "read:user", "Read your profile and account details", "medium", True
    ),
    "user:email": ScopeMeaning("user:email", "Read your email addresses", "medium", True),
    "workflow": ScopeMeaning(
        "workflow",
        "Create and modify GitHub Actions workflows, which run code on your behalf",
        "critical",
        True,
    ),
    "gist": ScopeMeaning("gist", "Create and edit gists on your account", "medium", True),
    "notifications": ScopeMeaning(
        "notifications", "Read and act on your notifications", "medium", True
    ),
    "write:packages": ScopeMeaning(
        "write:packages", "Publish packages under your account", "high", True
    ),
    # Fine-grained permissions, scoped to the repositories you select.
    "issues:write": ScopeMeaning(
        "issues:write", "Create, edit and label issues on the selected repository", "low"
    ),
    "issues:read": ScopeMeaning(
        "issues:read", "Read issues on the selected repository", "low"
    ),
    "contents:read": ScopeMeaning(
        "contents:read", "Read files in the selected repository", "low"
    ),
    "contents:write": ScopeMeaning(
        "contents:write", "Add, change and delete files in the selected repository", "high"
    ),
    "pull_requests:write": ScopeMeaning(
        "pull_requests:write",
        "Open and modify pull requests on the selected repository",
        "medium",
    ),
    "administration:write": ScopeMeaning(
        "administration:write",
        "Change settings and collaborators on the selected repository",
        "high",
    ),
    "metadata:read": ScopeMeaning(
        "metadata:read", "Read basic information about the selected repository", "low"
    ),
}


def explain(scope: str) -> ScopeMeaning:
    known = _GITHUB.get(scope.strip())
    if known is not None:
        return known
    return ScopeMeaning(
        scope,
        "Unrecognised permission — Toolsmith cannot tell you what this grants",
        "high",
        account_wide=True,
    )


def explain_all(scopes: list[str]) -> list[ScopeMeaning]:
    """Highest risk first, so the worst thing is never below the fold."""
    return sorted(
        (explain(s) for s in scopes),
        key=lambda m: (-_RISK_ORDER[m.risk], m.scope),
    )


def overall_risk(scopes: list[str]) -> Risk:
    if not scopes:
        return "low"
    return max((explain(s).risk for s in scopes), key=lambda r: _RISK_ORDER[r])


def risk_rank(risk: Risk) -> int:
    return _RISK_ORDER[risk]
