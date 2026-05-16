"""Subprocess wrappers around system ``git``.

This is the only file in the project that imports :mod:`subprocess`. It
exposes a small set of outcome-returning functions; none of them raise. See
[docs/adr/0002-collapsed-git-interface.md](../../../docs/adr/0002-collapsed-git-interface.md)
for the rationale behind this shape.

Public surface:

- :func:`detect_git` — best-effort PATH probe for the welcome screen.
- :func:`clone_deck` — clone + capture HEAD; returns :class:`CloneOutcome`.
- :func:`update_deck` — fetch + fast-forward pull; returns :class:`UpdateOutcome`.
- :func:`list_recent_commits` — list commits, with an optional pre-fetch step;
  returns :class:`CommitsOutcome`.
- :func:`verify_anki_gitify_remote` — pre-clone probe; returns :class:`RemoteOutcome`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
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
            error=(
                proc.stderr or proc.stdout or "git --version exited non-zero"
            ).strip(),
        )
    version = (proc.stdout or "").strip() or None
    return GitDetection(found=True, version=version)


# ---------- Progress ---------- #


@dataclass(frozen=True)
class CloneProgress:
    """One progress tick parsed from ``git clone --progress`` output."""

    phase: str  # "Counting", "Compressing", "Receiving", "Resolving"
    percent: int | None  # 0–100, or None if git didn't include one
    message: str  # raw line, stripped


# ---------- Outcome types ---------- #


class GitFailureKind(str, Enum):
    """Why a git operation failed.

    Flat enum carried on every ``*Failed`` outcome, replacing the previous
    seven-class ``GitError`` hierarchy. The string value lets callers compare
    to literals if they want, but most code should use the enum members.
    """

    AUTH = "auth"
    NETWORK = "network"
    REPO_NOT_FOUND = "repo_not_found"
    NOT_ANKI_GITIFY = "not_anki_gitify"
    UNSUPPORTED_URL = "unsupported_url"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CloneSucceeded:
    commit: str
    branch: str | None
    pulled_at: datetime


@dataclass(frozen=True)
class CloneFailed:
    kind: GitFailureKind
    message: str


CloneOutcome = CloneSucceeded | CloneFailed


@dataclass(frozen=True)
class UpdateSucceeded:
    commit: str
    branch: str | None
    pulled_at: datetime
    advanced: bool  # True iff HEAD moved


@dataclass(frozen=True)
class UpdateFailed:
    kind: GitFailureKind
    message: str


UpdateOutcome = UpdateSucceeded | UpdateFailed


@dataclass(frozen=True)
class Commit:
    """One row in a commit listing."""

    sha: str  # full 40-char sha
    short: str  # 7-char short sha
    date: str
    subject: str

    @property
    def display(self) -> str:
        return f"{self.short}  {self.date}  {self.subject}"


@dataclass(frozen=True)
class CommitsListed:
    commits: list[Commit] = field(default_factory=list)
    branch: str | None = None  # local HEAD branch at listing time


@dataclass(frozen=True)
class CommitsFailed:
    kind: GitFailureKind
    message: str


CommitsOutcome = CommitsListed | CommitsFailed


@dataclass(frozen=True)
class RemoteOk:
    pass


@dataclass(frozen=True)
class RemoteFailed:
    kind: GitFailureKind
    message: str


RemoteOutcome = RemoteOk | RemoteFailed


# ---------- Public functions ---------- #


def clone_deck(
    url: str,
    dest: Path,
    *,
    on_log: Callable[[str], None] | None = None,
    on_progress: Callable[[CloneProgress], None] | None = None,
    timeout: float = 600.0,
) -> CloneOutcome:
    """Clone ``url`` into ``dest`` (which must not already exist) and capture HEAD."""
    git = shutil.which("git")
    if git is None:
        return CloneFailed(
            kind=GitFailureKind.UNKNOWN,
            message=(
                "We need git to download decks, but it's not installed. "
                "Please install git and try again."
            ),
        )
    if dest.exists():
        return CloneFailed(
            kind=GitFailureKind.UNKNOWN,
            message=(
                f"The folder {dest} already exists. Choose a different folder "
                "or remove it first."
            ),
        )

    dest.parent.mkdir(parents=True, exist_ok=True)

    if on_log is not None:
        on_log(f"git clone --progress {url} {dest}")

    captured, returncode = _stream_git(
        [git, "clone", "--progress", "--", url, str(dest)],
        on_log=on_log,
        on_progress=on_progress,
        timeout=timeout,
    )
    if returncode is None:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        return CloneFailed(
            kind=GitFailureKind.NETWORK,
            message="Download timed out. Please check your connection and try again.",
        )
    if returncode != 0:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        kind, message = _classify_clone_error("\n".join(captured), returncode)
        if on_log is not None:
            on_log(f"Clone failed: {message}")
        return CloneFailed(kind=kind, message=message)

    sha = _head_commit(dest)
    branch = _head_branch(dest)
    pulled_at = datetime.now(timezone.utc)
    if sha is None:
        return CloneFailed(
            kind=GitFailureKind.UNKNOWN,
            message="Cloned the repo but couldn't read its HEAD commit.",
        )
    if on_log is not None:
        on_log(f"Done — at branch {branch or '?'}, commit {sha[:7]}.")
    return CloneSucceeded(commit=sha, branch=branch, pulled_at=pulled_at)


def update_deck(
    repo: Path,
    *,
    on_log: Callable[[str], None] | None = None,
    timeout: float = 600.0,
) -> UpdateOutcome:
    """Fetch from origin and fast-forward-pull ``repo``.

    ``UpdateSucceeded.advanced`` is ``True`` iff HEAD moved. A non-fast-forward
    error (local divergence) surfaces as ``UpdateFailed`` with a friendly
    "remove and re-add" message.
    """
    git = shutil.which("git")
    if git is None:
        return UpdateFailed(
            kind=GitFailureKind.UNKNOWN,
            message="git isn't available — please install it and try again.",
        )

    previous = _head_commit(repo)

    if on_log is not None:
        on_log(f"git -C {repo} fetch --prune")
    failure = _run_op(
        [git, "-C", str(repo), "fetch", "--prune", "--progress"],
        on_log=on_log,
        timeout=timeout,
        op_name="fetch",
    )
    if failure is not None:
        kind, message = failure
        if on_log is not None:
            on_log(f"Update failed: {message}")
        return UpdateFailed(kind=kind, message=message)

    if on_log is not None:
        on_log(f"git -C {repo} pull --ff-only")
    failure = _run_op(
        [git, "-C", str(repo), "pull", "--ff-only", "--progress"],
        on_log=on_log,
        timeout=timeout,
        op_name="pull",
        # pull writes "Already up to date." / "Fast-forward" to stdout — keep
        # the pipe so the buffer doesn't fill, but don't read it.
        keep_stdout=True,
    )
    if failure is not None:
        kind, message = failure
        if on_log is not None:
            on_log(f"Update failed: {message}")
        return UpdateFailed(kind=kind, message=message)

    sha = _head_commit(repo)
    branch = _head_branch(repo)
    pulled_at = datetime.now(timezone.utc)
    if sha is None:
        return UpdateFailed(
            kind=GitFailureKind.UNKNOWN,
            message="Pulled the repo but couldn't read its HEAD commit.",
        )
    advanced = sha != previous
    if on_log is not None:
        on_log(f"Updated to {sha[:7]}." if advanced else "Already up to date.")
    return UpdateSucceeded(
        commit=sha, branch=branch, pulled_at=pulled_at, advanced=advanced
    )


def list_recent_commits(
    repo: Path,
    *,
    ref: str | None = None,
    limit: int = 20,
    fetch_first: bool = False,
    on_log: Callable[[str], None] | None = None,
    timeout: float = 600.0,
) -> CommitsOutcome:
    """List recent commits on ``repo``.

    Modes:
    - ``ref`` given: list commits reachable from that ref.
    - ``ref=None, fetch_first=False``: list commits from local ``HEAD``.
    - ``ref=None, fetch_first=True``: fetch origin first, then list commits
      from ``origin/<local-branch>`` — the "check for updates" path.

    The branch in :class:`CommitsListed` is always the local HEAD branch at
    listing time, suitable for UI display regardless of mode.
    """
    git = shutil.which("git")
    if git is None or not (repo / ".git").exists():
        return CommitsFailed(
            kind=GitFailureKind.UNKNOWN,
            message="git is not available or this folder isn't a git repo.",
        )

    if fetch_first:
        if on_log is not None:
            on_log(f"git -C {repo} fetch --prune")
        failure = _run_op(
            [git, "-C", str(repo), "fetch", "--prune", "--progress"],
            on_log=on_log,
            timeout=timeout,
            op_name="fetch",
        )
        if failure is not None:
            kind, message = failure
            return CommitsFailed(kind=kind, message=message)

    branch = _head_branch(repo)
    if ref is not None:
        effective_ref = ref
    elif fetch_first and branch is not None:
        effective_ref = f"origin/{branch}"
    else:
        effective_ref = "HEAD"

    commits = _git_log(repo, ref=effective_ref, limit=limit)
    return CommitsListed(commits=commits, branch=branch)


def verify_anki_gitify_remote(url: str, *, timeout: float = 30.0) -> RemoteOutcome:
    """Verify ``url`` is reachable and contains a top-level ``gitify.yml``.

    Runs a connectivity probe (``git ls-remote``), then a blobless shallow
    clone into a temp dir to check the root tree for ``gitify.yml``. Only
    commit and tree objects are fetched.
    """
    git = shutil.which("git")
    if git is None:
        return RemoteFailed(
            kind=GitFailureKind.UNKNOWN,
            message=(
                "We need git to download decks, but it's not installed. "
                "Please install git and try again."
            ),
        )

    try:
        proc = subprocess.run(
            [git, "ls-remote", "--exit-code", "--quiet", "--", url],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return RemoteFailed(
            kind=GitFailureKind.NETWORK,
            message="Checking the link timed out. Please check your connection and try again.",
        )
    except OSError as exc:
        return RemoteFailed(
            kind=GitFailureKind.UNKNOWN, message=f"Could not run git: {exc}"
        )
    if proc.returncode != 0:
        kind, message = _classify_clone_error(
            proc.stderr or proc.stdout, proc.returncode
        )
        return RemoteFailed(kind=kind, message=message)

    with tempfile.TemporaryDirectory(
        prefix="anki-git-ui-verify-", ignore_cleanup_errors=True
    ) as tmpdir:
        try:
            proc = subprocess.run(
                [
                    git,
                    "clone",
                    "--depth",
                    "1",
                    "--filter=blob:none",
                    "--no-checkout",
                    "--quiet",
                    "--",
                    url,
                    tmpdir,
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return RemoteFailed(
                kind=GitFailureKind.NETWORK,
                message="Checking the link timed out. Please check your connection and try again.",
            )
        except OSError as exc:
            return RemoteFailed(
                kind=GitFailureKind.UNKNOWN, message=f"Could not run git: {exc}"
            )
        if proc.returncode != 0:
            kind, message = _classify_clone_error(
                proc.stderr or proc.stdout, proc.returncode
            )
            return RemoteFailed(kind=kind, message=message)

        try:
            ls = subprocess.run(
                [
                    git,
                    "-C",
                    tmpdir,
                    "ls-tree",
                    "HEAD",
                    "--name-only",
                    "--",
                    "gitify.yml",
                ],
                capture_output=True,
                text=True,
                timeout=10.0,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return RemoteFailed(
                kind=GitFailureKind.NETWORK,
                message="Checking the link timed out. Please check your connection and try again.",
            )
        except OSError as exc:
            return RemoteFailed(
                kind=GitFailureKind.UNKNOWN, message=f"Could not run git: {exc}"
            )
        if ls.returncode != 0 or not ls.stdout.strip():
            return RemoteFailed(
                kind=GitFailureKind.NOT_ANKI_GITIFY,
                message=(
                    "This repository doesn't contain a 'gitify.yml' file at "
                    "its root, so it doesn't look like an anki-gitify deck. "
                    "Only decks prepared with anki-gitify can be used here."
                ),
            )
    return RemoteOk()


# ---------- Private helpers ---------- #


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
    return CloneProgress(
        phase=m.group("phase").strip(), percent=pct, message=line.strip()
    )


def _classify_clone_error(
    stderr: str, returncode: int
) -> tuple[GitFailureKind, str]:
    text = stderr.lower()
    if (
        "authentication failed" in text
        or "could not read username" in text
        or "permission denied (publickey)" in text
    ):
        return GitFailureKind.AUTH, (
            "We couldn't download this deck. It looks like the repository is "
            "private — Anki Community Deck Sync only supports public deck "
            "links right now."
        )
    if (
        "could not resolve host" in text
        or "could not connect" in text
        or "operation timed out" in text
    ):
        return GitFailureKind.NETWORK, (
            "We couldn't reach the internet. Check your connection and try again."
        )
    if (
        "remote repository not found" in text
        or "repository not found" in text
        or "404" in text
    ):
        return GitFailureKind.REPO_NOT_FOUND, (
            "We couldn't find anything at that link. Double-check the "
            "address — it should look like https://github.com/<someone>/"
            "<deck-name>."
        )
    if "unsupported" in text and "url" in text:
        return GitFailureKind.UNSUPPORTED_URL, (
            "This link uses an address format we don't support. Please use "
            "an https:// link from a deck's GitHub page."
        )
    return GitFailureKind.UNKNOWN, (
        f"git exited with code {returncode}. Technical details:\n"
        f"{stderr.strip() or '(no output)'}"
    )


def _classify_pull_error(
    captured: str, returncode: int
) -> tuple[GitFailureKind, str]:
    text = captured.lower()
    if (
        "non-fast-forward" in text
        or "diverged" in text
        or "diverging" in text
        or "not possible to fast-forward" in text
    ):
        # Map "local divergence" to UNKNOWN — the user-facing message tells
        # them how to recover, so we don't need a dedicated kind.
        return GitFailureKind.UNKNOWN, (
            "Local changes were detected in this deck folder, so we can't "
            "apply the updates safely. To fix this, remove this deck (without "
            "keeping the files) and add it again."
        )
    return _classify_clone_error(captured, returncode)


def _stream_git(
    args: list[str],
    *,
    on_log: Callable[[str], None] | None,
    on_progress: Callable[[CloneProgress], None] | None = None,
    timeout: float,
    keep_stdout: bool = False,
) -> tuple[list[str], int | None]:
    """Run git, stream stderr line-by-line, return ``(captured_lines, returncode)``.

    ``returncode`` is ``None`` if the process was killed by timeout. ``OSError``
    from a missing binary surfaces as ``returncode=-1`` with the message in
    ``captured_lines[0]``.
    """
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE if keep_stdout else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        return [f"Could not run git: {exc}"], -1

    captured: list[str] = []
    try:
        assert proc.stderr is not None
        for raw in proc.stderr:
            for piece in raw.replace("\r", "\n").split("\n"):
                line = piece.strip()
                if not line:
                    continue
                captured.append(line)
                if on_log is not None:
                    on_log(line)
                if on_progress is not None:
                    pg = _parse_progress(line)
                    if pg is not None:
                        on_progress(pg)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return captured, None
    return captured, proc.returncode


def _run_op(
    args: list[str],
    *,
    on_log: Callable[[str], None] | None,
    timeout: float,
    op_name: str,
    keep_stdout: bool = False,
) -> tuple[GitFailureKind, str] | None:
    """Run a fetch/pull-style streaming op. Returns ``None`` on success or
    a ``(kind, message)`` tuple on failure."""
    captured, returncode = _stream_git(
        args, on_log=on_log, timeout=timeout, keep_stdout=keep_stdout
    )
    if returncode is None:
        return GitFailureKind.NETWORK, (
            f"git {op_name} timed out. Please check your connection and try again."
        )
    if returncode != 0:
        text = "\n".join(captured)
        if op_name == "pull":
            return _classify_pull_error(text, returncode)
        return _classify_clone_error(text, returncode)
    return None


def _head_commit(repo: Path) -> str | None:
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


def _head_branch(repo: Path) -> str | None:
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


# Unit Separator — safe field delimiter for commit subjects.
_COMMIT_SEP = "\x1f"


def _git_log(repo: Path, *, ref: str, limit: int) -> list[Commit]:
    git = shutil.which("git")
    if git is None or not (repo / ".git").exists():
        return []
    fmt = _COMMIT_SEP.join(["%H", "%h", "%ad", "%s"])
    proc = subprocess.run(
        [
            git,
            "-C",
            str(repo),
            "log",
            f"-{limit}",
            f"--pretty=format:{fmt}",
            "--date=short",
            ref,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode != 0:
        return []
    out: list[Commit] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(_COMMIT_SEP, 3)
        if len(parts) != 4:
            continue
        sha, short, date, subject = parts
        out.append(Commit(sha=sha, short=short, date=date, subject=subject))
    return out
