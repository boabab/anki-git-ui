"""Subprocess wrappers around system ``git``.

This is the only file in the project that imports :mod:`subprocess`. Each
function returns a structured result and never prints. Streaming variants
(``clone``, ``fetch``, ``pull``) accept ``on_line`` / ``on_progress``
callbacks for the log panel.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


# ---------- Detection ---------- #


@dataclass
class GitDetection:
    found: bool
    version: str | None = None
    error: str | None = None


def detect_git() -> GitDetection:
    """Best-effort detection of system ``git`` on PATH."""
    path = shutil.which("git")
    if path is None:
        return GitDetection(found=False, error="git not found on PATH")
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return GitDetection(found=False, error=f"could not run git: {exc}")
    if proc.returncode != 0:
        return GitDetection(
            found=False,
            error=(proc.stderr or proc.stdout or "git --version exited non-zero").strip(),
        )
    version = (proc.stdout or "").strip() or None
    return GitDetection(found=True, version=version)


# ---------- Errors ---------- #


class GitError(RuntimeError):
    """Base class for git operation failures the UI should surface as a friendly modal."""


class GitNotFoundError(GitError):
    """``git`` binary not on PATH."""


class GitAuthError(GitError):
    """Authentication failure — almost always a private repo without creds."""


class GitNetworkError(GitError):
    """DNS/connection failure."""


class GitUnsupportedUrlError(GitError):
    """URL scheme isn't supported (ssh://, git@…, file://, etc.)."""


class GitRepoNotFoundError(GitError):
    """Remote returned a 404 or similar — the URL doesn't point at a git repo."""


# ---------- Streaming clone ---------- #


@dataclass
class CloneProgress:
    """One progress tick parsed from ``git clone --progress`` output."""

    phase: str          # "Counting", "Compressing", "Receiving", "Resolving"
    percent: int | None  # 0–100, or None if git didn't include one
    message: str        # raw line, stripped


_PROGRESS_RE = re.compile(
    r"^\s*(?P<phase>[A-Za-z][A-Za-z ]+?):\s+(?:\d+%\s+\()?(?P<percent>\d+)%"
)


def _parse_progress(line: str) -> CloneProgress | None:
    m = _PROGRESS_RE.match(line)
    if not m:
        return None
    try:
        pct = int(m.group("percent"))
    except (TypeError, ValueError):
        pct = None
    return CloneProgress(phase=m.group("phase").strip(), percent=pct, message=line.strip())


def _classify_clone_error(stderr: str, returncode: int) -> GitError:
    text = stderr.lower()
    if "authentication failed" in text or "could not read username" in text or "permission denied (publickey)" in text:
        return GitAuthError(
            "We couldn't download this deck. It looks like the repository is private — "
            "Anki Deck Sync only supports public deck links right now."
        )
    if "could not resolve host" in text or "could not connect" in text or "operation timed out" in text:
        return GitNetworkError(
            "We couldn't reach the internet. Check your connection and try again."
        )
    if "remote repository not found" in text or "repository not found" in text or "404" in text:
        return GitRepoNotFoundError(
            "We couldn't find anything at that link. Double-check the address — it should "
            "look like https://github.com/<someone>/<deck-name>."
        )
    if "unsupported" in text and "url" in text:
        return GitUnsupportedUrlError(
            "This link uses an address format we don't support. Please use an https:// link "
            "from a deck's GitHub page."
        )
    return GitError(
        f"git clone failed (exit {returncode}). Technical details:\n{stderr.strip() or '(no output)'}"
    )


def clone(
    url: str,
    dest: Path,
    *,
    on_line: Callable[[str], None] | None = None,
    on_progress: Callable[[CloneProgress], None] | None = None,
    timeout: float = 600.0,
) -> None:
    """Clone ``url`` into ``dest`` (which must not already exist).

    Streams stderr line by line through ``on_line``; parses progress lines
    and additionally fires ``on_progress``. Raises a :class:`GitError`
    subclass on failure with a user-friendly message; the caller surfaces
    it as a modal.
    """
    git = shutil.which("git")
    if git is None:
        raise GitNotFoundError(
            "We need git to download decks, but it's not installed. Please install git "
            "and try again."
        )

    if dest.exists():
        raise GitError(
            f"The folder {dest} already exists. Choose a different folder or remove it first."
        )

    dest.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [git, "clone", "--progress", "--", url, str(dest)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    captured: list[str] = []
    try:
        assert proc.stderr is not None
        # git emits both `\n` and `\r` for progress; iterate by line where possible.
        for raw in proc.stderr:
            for piece in raw.replace("\r", "\n").split("\n"):
                line = piece.strip()
                if not line:
                    continue
                captured.append(line)
                if on_line is not None:
                    on_line(line)
                if on_progress is not None:
                    pg = _parse_progress(line)
                    if pg is not None:
                        on_progress(pg)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise GitError("Download timed out. Please check your connection and try again.")

    if proc.returncode != 0:
        # Best-effort cleanup of the partial clone.
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        raise _classify_clone_error("\n".join(captured), proc.returncode)


# ---------- Update flow: fetch + pull --------- #


def fetch(
    repo: Path,
    *,
    on_line: Callable[[str], None] | None = None,
    timeout: float = 600.0,
) -> None:
    """``git fetch --prune --progress`` for an existing clone."""
    git = shutil.which("git")
    if git is None:
        raise GitNotFoundError(
            "git isn't available — please install it and try again."
        )
    proc = subprocess.Popen(
        [git, "-C", str(repo), "fetch", "--prune", "--progress"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    captured: list[str] = []
    try:
        assert proc.stderr is not None
        for raw in proc.stderr:
            for piece in raw.replace("\r", "\n").split("\n"):
                line = piece.strip()
                if not line:
                    continue
                captured.append(line)
                if on_line is not None:
                    on_line(line)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise GitError("git fetch timed out. Please check your connection and try again.")
    if proc.returncode != 0:
        raise _classify_clone_error("\n".join(captured), proc.returncode)


def pull_ff_only(
    repo: Path,
    *,
    on_line: Callable[[str], None] | None = None,
    timeout: float = 600.0,
) -> None:
    """``git pull --ff-only --progress`` — refuses non-fast-forward.

    A non-fast-forward error means the local copy diverged from upstream,
    which shouldn't happen for a deck the user only consumes; surface it as
    a friendly "please re-download" message.
    """
    git = shutil.which("git")
    if git is None:
        raise GitNotFoundError("git isn't available — please install it and try again.")
    proc = subprocess.Popen(
        [git, "-C", str(repo), "pull", "--ff-only", "--progress"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    captured: list[str] = []
    try:
        # pull writes to both stdout and stderr; stream stderr for progress.
        assert proc.stderr is not None
        for raw in proc.stderr:
            for piece in raw.replace("\r", "\n").split("\n"):
                line = piece.strip()
                if not line:
                    continue
                captured.append(line)
                if on_line is not None:
                    on_line(line)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise GitError("git pull timed out. Please check your connection and try again.")
    if proc.returncode != 0:
        text = "\n".join(captured).lower()
        if (
            "non-fast-forward" in text
            or "diverged" in text
            or "diverging" in text
            or "not possible to fast-forward" in text
        ):
            raise GitError(
                "Local changes were detected in this deck folder, so we can't apply the "
                "updates safely. To fix this, remove this deck (without keeping the files) "
                "and add it again."
            )
        raise _classify_clone_error("\n".join(captured), proc.returncode)


@dataclass
class UpdateStatus:
    """Result of comparing local HEAD to upstream."""

    upstream_known: bool
    ahead: int = 0
    behind: int = 0
    dirty: bool = False
    error: str | None = None


def update_status(repo: Path) -> UpdateStatus:
    """Compare local HEAD to upstream — does not fetch.

    Run :func:`fetch` first if you want a fresh comparison. Returns
    ``upstream_known=False`` for repos that don't have an upstream branch yet
    (rare for a freshly-cloned consumer deck, but possible if the remote was
    odd).
    """
    git = shutil.which("git")
    if git is None or not (repo / ".git").exists():
        return UpdateStatus(upstream_known=False, error="not a git repo")

    # Check upstream
    p = subprocess.run(
        [git, "-C", str(repo), "rev-parse", "--abbrev-ref", "@{u}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        return UpdateStatus(upstream_known=False, error="no upstream branch")

    # ahead/behind counts
    p = subprocess.run(
        [git, "-C", str(repo), "rev-list", "--left-right", "--count", "HEAD...@{u}"],
        capture_output=True,
        text=True,
        check=False,
    )
    ahead = behind = 0
    if p.returncode == 0:
        parts = p.stdout.strip().split()
        if len(parts) == 2:
            try:
                ahead = int(parts[0])
                behind = int(parts[1])
            except ValueError:
                pass

    # Dirty?
    p = subprocess.run(
        [git, "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    dirty = bool(p.stdout.strip())

    return UpdateStatus(upstream_known=True, ahead=ahead, behind=behind, dirty=dirty)


# ---------- One-shot helpers ---------- #


def head_commit(repo: Path) -> str | None:
    """Return the full HEAD sha of ``repo``, or ``None`` if not a repo."""
    git = shutil.which("git")
    if git is None or not (repo / ".git").exists():
        return None
    proc = subprocess.run(
        [git, "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def head_branch(repo: Path) -> str | None:
    """Return the current branch name (e.g. ``main``), or ``None`` if detached."""
    git = shutil.which("git")
    if git is None or not (repo / ".git").exists():
        return None
    proc = subprocess.run(
        [git, "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        return None
    name = proc.stdout.strip()
    return name if name and name != "HEAD" else None
