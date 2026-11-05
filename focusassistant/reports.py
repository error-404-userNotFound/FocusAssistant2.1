"""Three-stream merge, iterative Quicksort and prefix time-range queries."""
from bisect import bisect_right
from dataclasses import dataclass
import math
import time

from .models import Control, LABELS


@dataclass
class Span:
    start: float
    end: float
    label: str
    host: str
    title: str

    @property
    def duration(self):
        return max(0, self.end - self.start)


def merge_chronological(pages, applications, controls):
    """O(p+a+c). A page supersedes its app placeholder at the same instant."""
    streams = [controls, applications, pages]
    positions = [0, 0, 0]
    while any(i < len(s) for i, s in zip(positions, streams)):
        winner = min(range(3), key=lambda k: (
            streams[k][positions[k]].occurred_at if positions[k] < len(streams[k]) else math.inf, k))
        yield streams[winner][positions[winner]]
        positions[winner] += 1


def quicksort_ranking(values):
    """Descending seconds, host name as tie-breaker; explicit partition stack."""
    values = list(values)
    stack = [(0, len(values) - 1)]
    def key(item):
        return (-item[1], item[0].casefold(), item[0])
    while stack:
        low, high = stack.pop()
        if low >= high:
            continue
        pivot = key(values[(low + high) // 2])
        left, right = low, high
        while left <= right:
            while key(values[left]) < pivot:
                left += 1
            while key(values[right]) > pivot:
                right -= 1
            if left <= right:
                values[left], values[right] = values[right], values[left]
                left, right = left + 1, right - 1
        if low < right:
            stack.append((low, right))
        if left < high:
            stack.append((left, high))
    return values


class PrefixSums:
    def __init__(self, spans):
        self.spans = spans
        self.starts = [s.start for s in spans]
        self.cumulative = [{label: 0.0 for label in LABELS}]
        for span in spans:
            total = self.cumulative[-1].copy()
            total[span.label] += span.duration
            self.cumulative.append(total)

    def until(self, date):
        index = bisect_right(self.starts, date) - 1
        if index < 0:
            return self.cumulative[0].copy()
        total = self.cumulative[index].copy()
        span = self.spans[index]
        total[span.label] += min(max(0, date - span.start), span.duration)
        return total

    def totals(self, start, end):
        if end <= start:
            return {label: 0.0 for label in LABELS}
        a, b = self.until(start), self.until(end)
        return {label: max(0, b[label] - a[label]) for label in LABELS}


@dataclass
class Report:
    spans: list
    total: dict
    ranking: list
    distraction_ranking: list
    warnings: list
    prefix: PrefixSums


def build_report(session, state, now=None):
    end = session.ended_at if session.ended_at is not None else (time.time() if now is None else now)
    warnings = list(state.storage_warnings)
    def activity(rows):
        seen = set()
        valid = []
        for event in rows:
            if event.session_id != session.id:
                continue
            if (event.id in seen or not math.isfinite(event.occurred_at)
                    or not session.started_at <= event.occurred_at <= end or not event.url):
                warnings.append("Skipped invalid or duplicate activity records.")
                continue
            seen.add(event.id)
            valid.append(event)
        if any(a.occurred_at > b.occurred_at for a, b in zip(valid, valid[1:])):
            valid.sort(key=lambda e: e.occurred_at)
            warnings.append("Reordered an unsorted activity log.")
        return valid
    pages, applications = activity(state.pages), activity(state.applications)
    controls = [c for c in state.controls if c.session_id == session.id and session.started_at <= c.occurred_at <= end]
    if not any(c.kind == "started" for c in controls):
        controls.insert(0, Control(session.id, session.started_at, "started"))
        warnings.append("Recovered a missing session start record.")
    controls.sort(key=lambda c: c.occurred_at)
    spans = []
    active, paused = False, False
    start, label, host, title = None, "uncertain", "Unclassified activity", "Waiting for activity"
    def close(at):
        nonlocal start
        if start is not None and at > start:
            spans.append(Span(start, at, label, host, title))
        start = None
    for event in merge_chronological(pages, applications, controls):
        if isinstance(event, Control):
            if event.kind == "started":
                active, paused, start = True, False, event.occurred_at
                label, host, title = "uncertain", "Unclassified activity", "Waiting for activity"
            elif event.kind == "paused":
                close(event.occurred_at)
                paused = True
            elif event.kind == "resumed":
                paused = False
                label, host, title = "uncertain", "Unclassified activity", "Waiting for activity after resume"
                start = event.occurred_at if active else None
            elif event.kind == "ended":
                close(event.occurred_at)
                active, paused = False, False
        else:
            close(event.occurred_at)
            label, host, title = event.label, event.host or event.url, event.title
            start = event.occurred_at if active and not paused else None
    if active and not paused:
        close(end)
    total, hosts, distractions = {k: 0.0 for k in LABELS}, {}, {}
    for span in spans:
        total[span.label] += span.duration
        hosts[span.host] = hosts.get(span.host, 0) + span.duration
        if span.label == "distracting":
            distractions[span.host] = distractions.get(span.host, 0) + span.duration
    return Report(spans, total, quicksort_ranking(hosts.items()), quicksort_ranking(distractions.items()),
                  sorted(set(warnings)), PrefixSums(spans))
