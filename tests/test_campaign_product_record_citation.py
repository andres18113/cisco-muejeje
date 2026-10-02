"""Which product record a campaign seals beside a qualification record.

Production code: the qualification CLI's citation selector. A measurement
that assessed a product names its record in the `product_record_path` fact;
the campaign seals exactly that file, whatever the stage is called. Episode 8
of the SP-2 campaign lost its seal because the selector matched two stage
names only, so these cases pin the contract by citation, not by name.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from packet_tracer_mcp.adapters.cli.service_qualification import (
    _native_product_record_path,
)


def _record(*measurements: tuple[str, dict]) -> SimpleNamespace:
    return SimpleNamespace(
        measurements=[
            SimpleNamespace(experiment_id=experiment, facts=facts)
            for experiment, facts in measurements
        ]
    )


@pytest.mark.parametrize(
    "experiment",
    [
        "M-NATIVE-PRODUCT",
        "M-SP1-ROUTED-PRODUCT",
        "M-SP2-MIXED-PRODUCT",
        "M-SP2-CAPACITY-PRODUCT",
    ],
)
def test_every_product_measurement_citing_a_record_names_it(experiment):
    """The citation, not the stage name, selects the sealed product."""
    record = _record(
        (experiment, {"product_record_path": "data/services/p/run-product.json"}),
        (experiment.replace("PRODUCT", "FINAL"), {"scans": {}}),
    )
    assert _native_product_record_path(record) == "data/services/p/run-product.json"


def test_no_record_or_no_citation_names_nothing():
    """A stage that assessed no product has no product to seal."""
    assert _native_product_record_path(None) == ""
    assert _native_product_record_path(_record(("M-Q0", {"build": "x"}))) == ""


def test_an_empty_citation_names_nothing():
    """A product that persisted nothing cites nothing; its own summary says why."""
    record = _record(("M-SP2-MIXED-PRODUCT", {"product_record_path": ""}))
    assert _native_product_record_path(record) == ""


def test_the_same_record_cited_twice_is_one_citation():
    """Two measurements naming one file are one unambiguous citation."""
    path = "data/services/p/run-product.json"
    record = _record(
        ("M-SP2-MIXED-PRODUCT", {"product_record_path": path}),
        ("M-SP2-MIXED-FINAL", {"product_record_path": path}),
    )
    assert _native_product_record_path(record) == path


def test_two_different_cited_records_cannot_be_sealed():
    """Choosing one of two cited products would hide the other."""
    record = _record(
        ("M-SP2-MIXED-PRODUCT", {"product_record_path": "data/services/a.json"}),
        ("M-SP2-MIXED-FINAL", {"product_record_path": "data/services/b.json"}),
    )
    with pytest.raises(ValueError, match="ambiguous"):
        _native_product_record_path(record)


@pytest.mark.parametrize("value", [None, 7, ["data/services/a.json"], {"p": 1}])
def test_a_citation_that_is_not_text_cannot_be_sealed(value):
    """A malformed citation is a finding, never an empty path."""
    record = _record(("M-SP2-MIXED-PRODUCT", {"product_record_path": value}))
    with pytest.raises(ValueError, match="malformed"):
        _native_product_record_path(record)
