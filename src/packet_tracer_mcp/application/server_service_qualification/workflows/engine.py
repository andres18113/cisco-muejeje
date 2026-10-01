"""Q0: run-bag persistence, atomicity and observer release on the engine."""

from __future__ import annotations

from collections.abc import Sequence

from ....domain.enterprise.models.service_qualification import (
    MeasurementConclusion,
    ReleaseRecord,
)
from ....domain.enterprise.services.service_qualification_evidence import (
    Assessment,
    ProbeReading,
    assess_atomicity,
    assess_bag_persistence,
    assess_observer_release,
)
from ..execution import Execution
from ..fixtures import setup_fixtures


def run_q0(execution: Execution) -> None:
    """Run the bag, atomicity and observer-release procedures of Q0."""
    probes = execution.probes
    channel = execution.channel
    ids = ("M-ENG-1",)
    if execution.begin(ids, "ENG"):
        with execution.procedure(ids):
            # The claim may have executed whatever the channel reported back,
            # so the finalizer has to look. Only a reported collision proves
            # that nothing was written, and then there is nothing to look for.
            execution.bag_touched = True
            write = probes.write_bag_sentinel()
            read: ProbeReading | None = None
            if write.observed and write.payload["run_bag_preexisting"]:
                execution.bag_collision = True
            else:
                execution.bag_unreleased.add("sentinel")
                read = probes.read_and_release_bag_sentinel()
                if read.observed and read.payload["released"]:
                    execution.bag_unreleased.discard("sentinel")
            execution.conclude(
                "M-ENG-1", assess_bag_persistence(write, read, channel=channel)
            )
        execution.finish("ENG")

    ids = ("ATOM-1",)
    if execution.begin(ids, "ATOM"):
        with execution.procedure(ids):
            execution.bag_unreleased.add("atom")
            # The second contender is queued only once the first receipt has
            # been interpreted. A dispatch whose acceptance is unknown is not
            # permission to add another contender to the same claim.
            receipts = [probes.queue_atomicity_contender("A")]
            if receipts[0].accepted:
                receipts.append(probes.queue_atomicity_contender("B"))
            execution.settle()
            collect = probes.collect_atomicity()
            if collect.observed and collect.payload["released"]:
                execution.bag_unreleased.discard("atom")
            execution.conclude(
                "ATOM-1", assess_atomicity(receipts, collect, channel=channel)
            )
        execution.finish("ATOM")

    ids = ("M-UNREG-1", "M-UNREG-2")
    # The fixture exists only for this procedure, so it is created only once
    # the procedure itself is admissible, fixture cost included.
    if execution.admissible(
        ids, "UNREG", extra_operations=execution.definition.fixture_operations
    ):
        if not setup_fixtures(execution):
            execution.not_run(ids, "fixture_setup_failed")
            return
        if execution.announce(ids, "UNREG"):
            _run_unregister(execution, ids)
            execution.finish("UNREG")


def _run_unregister(execution: Execution, ids: Sequence[str]) -> None:
    probes = execution.probes
    device = execution.definition.fixtures[0].name
    with execution.procedure(ids):
        execution.bag_unreleased.add("unreg")
        register = probes.register_observer_and_trigger(device)
        evidence = release = after = None
        if not register.observed:
            execution.observers_unresolved.add("cb1:registration_unknown")
        elif register.payload["registered1"]:
            execution.observers_unresolved.add("cb1")
            execution.settle()
            evidence = probes.read_observer_and_register_zero_event(device)
            if not evidence.observed:
                execution.observers_unresolved.add("cb2:registration_unknown")
            else:
                if evidence.payload["registered2"]:
                    execution.observers_unresolved.add("cb2")
                release = probes.release_observers_and_trigger(device)
                if not release.observed:
                    execution.observers_unresolved.add("cb3:registration_unknown")
                else:
                    if release.payload["registered3"]:
                        execution.observers_unresolved.add("cb3")
                    execution.settle()
                    after = probes.read_post_release_and_drop()
                    if after.observed and after.payload["dropped"]:
                        execution.bag_unreleased.discard("unreg")
        first, second = assess_observer_release(register, evidence, release, after)
        _observer_releases(execution, first, release, after)
        execution.conclude("M-UNREG-1", first)
        execution.conclude("M-UNREG-2", second)


def _observer_releases(
    execution: Execution,
    first: Assessment,
    release: ProbeReading | None,
    after: ProbeReading | None,
) -> None:
    """Record observer outcomes; only a supported release resolves one."""
    releases = execution.record.releases
    if (
        first.facts.get("release_conclusion")
        == MeasurementConclusion.SUPPORTED_IN_SAMPLE
    ):
        execution.observers_unresolved.discard("cb1")
        releases.append(
            ReleaseRecord(
                resource="observer:cb1",
                kind="observer",
                outcome="released_in_sample",
                detail="no invocation after a control event",
            )
        )
    elif release is not None and release.observed:
        attempt = release.payload["release1"]
        releases.append(
            ReleaseRecord(
                resource="observer:cb1",
                kind="observer",
                outcome=(
                    "release_threw"
                    if attempt.get("threw")
                    else "release_attempted_unverified"
                    if attempt.get("attempted")
                    else "release_not_attempted"
                ),
            )
        )
    if after is not None and after.observed:
        for name, key in (("cb2", "release2"), ("cb3", "release3")):
            attempt = after.payload[key]
            releases.append(
                ReleaseRecord(
                    resource=f"observer:{name}",
                    kind="observer",
                    outcome=(
                        "release_threw"
                        if attempt.get("threw")
                        else "release_attempted_unverified"
                        if attempt.get("attempted")
                        else "inert_attached"
                    ),
                    detail="marked inert; detachment is not observed",
                )
            )
