"""Job and Workflow framework — Textual worker plumbing in one place.

See [docs/adr/0001-deck-job-and-workflow.md](../../docs/adr/0001-deck-job-and-workflow.md)
for the rationale. The pure outcome types live in :mod:`anki_git_ui.domain.jobs`;
this module wires them to Textual's worker layer.

Public surface for screens:

- :class:`Job` — a named work function returning a :class:`JobOutcome`.
- :func:`run_job` — launch a job on the screen's worker layer and route its
  result to a typed ``on_done`` callback.
- :func:`dispatch_job_event` — the one-liner the screen drops inside its
  ``on_worker_state_changed`` to forward worker events into the framework.
- :func:`run_with_anki_locked_retry` — wrap a job: if it returns
  :class:`AnkiLocked`, ask the screen to show a modal; on user retry, re-run.

Workflows are not their own type yet — per the ADR's open question, screens
compose jobs by chaining ``on_done`` callbacks. Promote to a class only when
two workflows need the same scaffolding.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import uuid4

from textual.screen import Screen
from textual.worker import Worker, WorkerState

from .domain.jobs import AnkiLocked, Failed, JobOutcome

T = TypeVar("T")

# Group used for every job worker, so launching a second job cancels the
# first via Textual's `exclusive=True` semantics.
JOB_WORKER_GROUP = "deck-actions"


@dataclass
class Job(Generic[T]):
    """A single async operation against a deck.

    - ``name``: short identifier (``"download"``, ``"build"``…) used in the
      Textual worker name and the activity log.
    - ``work``: the function invoked on the worker thread. Returns a
      :class:`JobOutcome`; never raises (exceptions caught by the framework
      surface as :class:`Failed`).
    """

    name: str
    work: Callable[[], JobOutcome[T]]


def run_job(
    screen: Screen,
    job: Job[T],
    *,
    on_done: Callable[[JobOutcome[T]], None],
    group: str = JOB_WORKER_GROUP,
) -> None:
    """Launch ``job`` on ``screen``'s worker layer; call ``on_done`` with the outcome.

    The Textual worker is started with ``exclusive=True`` in ``group``, so
    launching a new job in the same group cancels any in-flight one. Most
    screens want the default :data:`JOB_WORKER_GROUP`; an isolated flow
    (e.g. add-deck URL verification) can pass its own group name to avoid
    cross-screen interference. Exceptions from ``job.work`` are translated
    into :class:`Failed` before ``on_done`` is called — screens never see
    raw tracebacks.
    """
    callbacks = _callbacks(screen)
    worker_name = f"job:{job.name}:{uuid4().hex[:8]}"
    callbacks[worker_name] = on_done
    screen.run_worker(
        job.work,
        thread=True,
        exclusive=True,
        group=group,
        name=worker_name,
    )


def dispatch_job_event(screen: Screen, event: Worker.StateChanged) -> bool:
    """Forward a Textual worker event into the job framework.

    The screen's ``on_worker_state_changed`` should call this first and return
    early on ``True``. Returns ``False`` for any event the framework didn't
    register (e.g. screen-owned workers like the dashboard refresh).

    SUCCESS events deliver the worker's return value to the stored callback.
    ERROR events translate the raised exception into :class:`Failed` and call
    the same callback — jobs themselves are expected to return outcomes rather
    than raise, but an unexpected raise still routes cleanly.
    """
    callbacks = _callbacks(screen)
    name = event.worker.name
    if name is None or name not in callbacks:
        return False
    if event.state not in (WorkerState.SUCCESS, WorkerState.ERROR):
        return False
    callback = callbacks.pop(name)
    if event.state == WorkerState.SUCCESS:
        callback(event.worker.result)
    else:
        err = event.worker.error or RuntimeError("worker failed without an exception")
        callback(Failed(exc=err, message=str(err) or type(err).__name__))
    return True


def run_with_anki_locked_retry(
    screen: Screen,
    job: Job[T],
    *,
    on_done: Callable[[JobOutcome[T]], None],
    on_locked: Callable[[Callable[[], None]], None],
) -> None:
    """Run ``job``; on :class:`AnkiLocked`, invoke ``on_locked(retry)``.

    ``on_locked`` is given a zero-arg ``retry`` callable. The screen typically
    pushes an :class:`AnkiLockedModal` and calls ``retry()`` only if the user
    confirms. Any other outcome flows through to ``on_done`` directly.
    """

    def _on_outcome(outcome: JobOutcome[T]) -> None:
        if isinstance(outcome, AnkiLocked):

            def _retry() -> None:
                run_with_anki_locked_retry(
                    screen, job, on_done=on_done, on_locked=on_locked
                )

            on_locked(_retry)
            return
        on_done(outcome)

    run_job(screen, job, on_done=_on_outcome)


def _callbacks(screen: Screen) -> dict[str, Callable[[JobOutcome], None]]:
    callbacks = getattr(screen, "_job_callbacks", None)
    if callbacks is None:
        callbacks = {}
        screen._job_callbacks = callbacks
    return callbacks


__all__ = [
    "JOB_WORKER_GROUP",
    "Job",
    "dispatch_job_event",
    "run_job",
    "run_with_anki_locked_retry",
]
