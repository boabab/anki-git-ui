"""Unit tests for the Job/Workflow framework (ADR-0001).

These tests live below the Textual layer: they stub out the screen's
``run_worker`` call so the framework can be exercised without a running
app. The point of the framework is that ``on_done`` callbacks fire with
typed outcomes — that's what we assert on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from anki_git_ui.domain.jobs import (
    AnkiLocked,
    Completed,
    Failed,
    JobOutcome,
    NetworkFailed,
)
from anki_git_ui.jobs import (
    JOB_WORKER_GROUP,
    Job,
    dispatch_job_event,
    run_job,
    run_with_anki_locked_retry,
)


# ---------- Stubs ---------- #


@dataclass
class _StubWorker:
    name: str
    result: Any = None
    error: BaseException | None = None


class _StubEvent:
    """Mimics ``textual.worker.Worker.StateChanged`` enough for the dispatcher."""

    def __init__(self, *, worker: _StubWorker, state):
        self.worker = worker
        self.state = state


class _StubState:
    """Stand-in for ``textual.worker.WorkerState``."""

    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"


@dataclass
class _StubScreen:
    """Records the ``run_worker`` calls the framework would have made.

    Exposes the same attribute (``_job_callbacks``) the real framework reads
    so dispatch can be exercised end-to-end.
    """

    started: list[dict] = field(default_factory=list)
    _job_callbacks: dict[str, Any] | None = None

    def run_worker(self, work, *, thread, exclusive, group, name) -> None:
        self.started.append(
            {
                "work": work,
                "thread": thread,
                "exclusive": exclusive,
                "group": group,
                "name": name,
            }
        )


@pytest.fixture(autouse=True)
def _patch_worker_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``WorkerState`` so the dispatcher accepts the stub event's strings."""
    monkeypatch.setattr("anki_git_ui.jobs.WorkerState", _StubState)


# ---------- run_job ---------- #


def test_run_job_registers_callback_and_launches_worker() -> None:
    screen = _StubScreen()
    received: list[JobOutcome] = []
    job = Job(name="dl", work=lambda: Completed(value="ok"))

    run_job(screen, job, on_done=received.append)

    assert len(screen.started) == 1
    started = screen.started[0]
    assert started["thread"] is True
    assert started["exclusive"] is True
    assert started["group"] == JOB_WORKER_GROUP
    assert started["name"].startswith("job:dl:")
    assert started["work"] is job.work
    # Callback registered for the worker name actually used.
    assert started["name"] in screen._job_callbacks
    assert received == []  # callback hasn't fired yet


def test_run_job_uses_supplied_group() -> None:
    screen = _StubScreen()
    job = Job(name="verify", work=lambda: Completed(value=None))
    run_job(screen, job, on_done=lambda _: None, group="my-group")
    assert screen.started[0]["group"] == "my-group"


def test_run_job_names_are_unique_per_call() -> None:
    screen = _StubScreen()
    run_job(screen, Job("x", lambda: Completed(value=1)), on_done=lambda _: None)
    run_job(screen, Job("x", lambda: Completed(value=2)), on_done=lambda _: None)
    names = [s["name"] for s in screen.started]
    assert names[0] != names[1]


# ---------- dispatch_job_event ---------- #


def test_dispatch_routes_success_to_registered_callback() -> None:
    screen = _StubScreen()
    received: list[JobOutcome] = []
    job = Job("dl", lambda: Completed(value="ok"))
    run_job(screen, job, on_done=received.append)
    worker_name = screen.started[0]["name"]

    event = _StubEvent(
        worker=_StubWorker(name=worker_name, result=Completed(value="ok")),
        state=_StubState.SUCCESS,
    )
    handled = dispatch_job_event(screen, event)

    assert handled is True
    assert received == [Completed(value="ok")]
    # Callback is consumed after dispatch.
    assert worker_name not in screen._job_callbacks


def test_dispatch_translates_worker_error_into_failed() -> None:
    screen = _StubScreen()
    received: list[JobOutcome] = []
    job = Job("dl", lambda: Completed(value="ok"))
    run_job(screen, job, on_done=received.append)
    worker_name = screen.started[0]["name"]

    err = ValueError("boom")
    event = _StubEvent(
        worker=_StubWorker(name=worker_name, error=err),
        state=_StubState.ERROR,
    )
    handled = dispatch_job_event(screen, event)

    assert handled is True
    assert len(received) == 1
    outcome = received[0]
    assert isinstance(outcome, Failed)
    assert outcome.exc is err
    assert outcome.message == "boom"


def test_dispatch_ignores_unknown_worker_names() -> None:
    screen = _StubScreen()
    event = _StubEvent(
        worker=_StubWorker(name="not-a-job", result=None),
        state=_StubState.SUCCESS,
    )
    assert dispatch_job_event(screen, event) is False


def test_dispatch_ignores_intermediate_states() -> None:
    screen = _StubScreen()
    received: list[JobOutcome] = []
    run_job(screen, Job("x", lambda: Completed(value=1)), on_done=received.append)
    worker_name = screen.started[0]["name"]

    event = _StubEvent(
        worker=_StubWorker(name=worker_name),
        state=_StubState.PENDING,
    )
    handled = dispatch_job_event(screen, event)
    assert handled is False
    assert received == []
    # Callback is preserved for the eventual SUCCESS/ERROR.
    assert worker_name in screen._job_callbacks


# ---------- run_with_anki_locked_retry ---------- #


def test_lock_retry_passes_completed_straight_through() -> None:
    screen = _StubScreen()
    received: list[JobOutcome] = []
    locked_calls: list = []

    job = Job("filtered", lambda: Completed(value="report"))
    run_with_anki_locked_retry(
        screen,
        job,
        on_done=received.append,
        on_locked=lambda retry: locked_calls.append(retry),
    )

    # Simulate the worker resolving with Completed.
    worker_name = screen.started[0]["name"]
    dispatch_job_event(
        screen,
        _StubEvent(
            worker=_StubWorker(name=worker_name, result=Completed(value="report")),
            state=_StubState.SUCCESS,
        ),
    )

    assert received == [Completed(value="report")]
    assert locked_calls == []


def test_lock_retry_invokes_on_locked_then_re_runs_on_retry() -> None:
    screen = _StubScreen()
    received: list[JobOutcome] = []
    locked_retries: list = []

    # First worker resolves AnkiLocked; the next resolves Completed.
    job = Job("filtered", lambda: AnkiLocked())
    run_with_anki_locked_retry(
        screen,
        job,
        on_done=received.append,
        on_locked=lambda retry: locked_retries.append(retry),
    )

    first_name = screen.started[0]["name"]
    dispatch_job_event(
        screen,
        _StubEvent(
            worker=_StubWorker(name=first_name, result=AnkiLocked()),
            state=_StubState.SUCCESS,
        ),
    )

    # on_locked should have fired with a retry callable; on_done not yet.
    assert received == []
    assert len(locked_retries) == 1
    assert callable(locked_retries[0])

    # Now the user "clicks retry" — re-runs the job.
    locked_retries[0]()
    assert len(screen.started) == 2
    second_name = screen.started[1]["name"]
    assert second_name != first_name

    # Second attempt resolves Completed.
    dispatch_job_event(
        screen,
        _StubEvent(
            worker=_StubWorker(name=second_name, result=Completed(value="ok")),
            state=_StubState.SUCCESS,
        ),
    )

    assert received == [Completed(value="ok")]


def test_lock_retry_passes_failed_outcomes_through_without_modal() -> None:
    screen = _StubScreen()
    received: list[JobOutcome] = []
    locked_retries: list = []

    job = Job("filtered", lambda: Failed(exc=RuntimeError("no"), message="no"))
    run_with_anki_locked_retry(
        screen,
        job,
        on_done=received.append,
        on_locked=lambda retry: locked_retries.append(retry),
    )

    name = screen.started[0]["name"]
    fail = Failed(exc=RuntimeError("no"), message="no")
    dispatch_job_event(
        screen,
        _StubEvent(
            worker=_StubWorker(name=name, result=fail),
            state=_StubState.SUCCESS,
        ),
    )

    assert received == [fail]
    assert locked_retries == []


# ---------- Worker-level outcome translation ---------- #


def test_make_apkg_job_translates_card_override_to_failed_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Build job translates CardOverrideRequired to Failed(kind="card_override")."""
    from anki_git_ui.domain import anki_interop
    from anki_git_ui.domain.anki_interop import CardOverrideRequired
    from anki_git_ui.domain.models import DeckEntry, DeckStatus
    from anki_git_ui.workers.make_apkg_worker import make_apkg_job

    monkeypatch.setattr(
        anki_interop, "import_deck", lambda *a, **k: CardOverrideRequired()
    )

    deck = DeckEntry(
        nickname="x",
        url="https://example.com/x",
        local_path=tmp_path / "deck",
        status=DeckStatus.UP_TO_DATE,
        last_pulled_commit="a" * 40,
    )
    job = make_apkg_job(deck, tmp_path / "save")
    outcome = job.work()

    assert isinstance(outcome, Failed)
    assert outcome.kind == "card_override"


def test_filtered_decks_job_translates_locked_to_anki_locked(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """apply_filtered_decks_job maps anki_interop's Locked → AnkiLocked."""
    from anki_git_ui.domain import anki_interop
    from anki_git_ui.domain.anki_interop import Locked
    from anki_git_ui.domain.models import AnkiProfileChoice, DeckEntry, DeckStatus
    from anki_git_ui.workers.filtered_decks_worker import apply_filtered_decks_job

    deck_dir = tmp_path / "deck"
    deck_dir.mkdir()
    (deck_dir / "filtered_decks.yml").write_text("entries: []\n", encoding="utf-8")

    monkeypatch.setattr(anki_interop, "apply_filtered", lambda *a, **k: Locked())

    deck = DeckEntry(
        nickname="x",
        url="https://example.com/x",
        local_path=deck_dir,
        status=DeckStatus.UP_TO_DATE,
    )
    job = apply_filtered_decks_job(deck, AnkiProfileChoice())
    outcome = job.work()

    assert isinstance(outcome, AnkiLocked)


def test_filtered_decks_job_translates_collection_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """CollectionMissing surfaces as Failed(kind="collection_missing")."""
    from anki_git_ui.domain import anki_interop
    from anki_git_ui.domain.anki_interop import CollectionMissing
    from anki_git_ui.domain.models import AnkiProfileChoice, DeckEntry, DeckStatus
    from anki_git_ui.workers.filtered_decks_worker import apply_filtered_decks_job

    deck_dir = tmp_path / "deck"
    deck_dir.mkdir()
    (deck_dir / "filtered_decks.yml").write_text("entries: []\n", encoding="utf-8")

    monkeypatch.setattr(
        anki_interop,
        "apply_filtered",
        lambda *a, **k: CollectionMissing(message="no anki"),
    )

    deck = DeckEntry(
        nickname="x",
        url="https://example.com/x",
        local_path=deck_dir,
        status=DeckStatus.UP_TO_DATE,
    )
    job = apply_filtered_decks_job(deck, AnkiProfileChoice())
    outcome = job.work()

    assert isinstance(outcome, Failed)
    assert outcome.kind == "collection_missing"
    assert outcome.message == "no anki"


def test_download_deck_job_translates_network_to_network_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A CloneFailed(NETWORK) surfaces as NetworkFailed, not generic Failed."""
    from anki_git_ui.domain.git_ops import CloneFailed, GitFailureKind
    from anki_git_ui.domain.models import DeckEntry, DeckStatus
    from anki_git_ui.workers import download_deck_worker
    from anki_git_ui.workers.download_deck_worker import download_deck_job

    monkeypatch.setattr(
        download_deck_worker,
        "clone_deck",
        lambda *a, **k: CloneFailed(kind=GitFailureKind.NETWORK, message="DNS down"),
    )

    deck = DeckEntry(
        nickname="x",
        url="https://example.com/x",
        local_path=tmp_path / "x",
        status=DeckStatus.NOT_DOWNLOADED,
    )
    job = download_deck_job(deck)
    outcome = job.work()

    assert isinstance(outcome, NetworkFailed)
    assert outcome.message == "DNS down"


def test_download_deck_job_translates_non_network_to_failed_with_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Non-network git failures surface as Failed carrying GitFailureKind.value."""
    from anki_git_ui.domain.git_ops import CloneFailed, GitFailureKind
    from anki_git_ui.domain.models import DeckEntry, DeckStatus
    from anki_git_ui.workers import download_deck_worker
    from anki_git_ui.workers.download_deck_worker import download_deck_job

    monkeypatch.setattr(
        download_deck_worker,
        "clone_deck",
        lambda *a, **k: CloneFailed(kind=GitFailureKind.AUTH, message="403"),
    )

    deck = DeckEntry(
        nickname="x",
        url="https://example.com/x",
        local_path=tmp_path / "x",
        status=DeckStatus.NOT_DOWNLOADED,
    )
    outcome = download_deck_job(deck).work()

    assert isinstance(outcome, Failed)
    assert outcome.kind == GitFailureKind.AUTH.value
    assert outcome.message == "403"
