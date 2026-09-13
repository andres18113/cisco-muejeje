"""What each outcome of the LIVE run establishes, and what it may not be read as.

Split out of `test_live_runbook` when that module reached its line budget, and
the concerns really are different: there, whether the run is *capable* of
establishing anything — its identity, its privilege selection, the fixture it is
taken over; here, the rules its results are read under once it has them
(MJ-018, MJ-020).

A declaration that says what each outcome would mean is what makes a verdict a
reading rather than an argument after the fact (`MJ-011`). Two of these rules
were already load-bearing, and two arrive with the full-trust change:

* a root that answered is not a member that answered, and a descendant that
  failed does not retract its root;
* a denial is never answered by widening the selection;
* the run has an **investigative target** — `platform.module_descriptors`, the
  one operation the previous run left unexplained — and the page has to name it,
  or a person repeats a run nobody is reading;
* `PLATFORM_ANSWER_UNUSABLE` is not a privilege result. Under
  `FULL_TRUSTED_MODULE` the temptation reverses: with nothing left to select, an
  unattributable answer starts looking like something the selection caused.

None of these gates runs Packet Tracer. What a person is told to conclude is all
this repository can check (MJ-011, MJ-015).
"""

from __future__ import annotations

from tests.muejeje.test_live_runbook import runbook_prose


def test_the_runbook_keeps_root_and_descendant_qualification_apart():
    """A working root behind a broken descendant is its own state."""
    prose = runbook_prose()

    assert "It does **not** invalidate the root result" in prose
    assert "record the exact `Interface.member` that was reached" in prose


def test_the_runbook_forbids_widening_privilege_on_a_denial():
    """A denial is investigated, never answered by selecting more."""
    prose = runbook_prose()

    assert "**Do not add privileges.**" in prose
    assert "**No privilege is changed mid-artifact.**" in prose
    assert "contradiction" in prose


def test_the_runbook_names_the_result_the_run_exists_to_locate():
    """The run has an investigative target, and the page has to say which.

    `platform.module_descriptors` is the one operation the previous run left
    unexplained. A declaration that only changed the privilege line would send a
    person to repeat a run whose interesting result nobody was looking for.
    """
    prose = runbook_prose()

    assert "Its investigative target is `platform.module_descriptors`" in prose
    assert "with no privilege diagnostic printed beside it" in prose
    assert "read `unavailable_member` and `unavailable_argument`" in prose
    assert "That pair is the result this run exists for." in prose


def test_the_runbook_refuses_to_read_an_unusable_answer_as_a_privilege_result():
    """The one inference the wider selection makes tempting, refused in advance.

    With every token selected there is nothing left to add, so the risk reverses:
    instead of reaching for another privilege, a reader starts treating an
    unattributable answer as though the selection had caused it.
    """
    prose = runbook_prose()

    assert (
        "**`PLATFORM_ANSWER_UNUSABLE` is not a privilege result, and this run "
        "may not turn it into one.**" in prose
    )
    assert "reaches the runtime as `PLATFORM_CALL_FAILED`" in prose
    assert "There are none left to add" in prose
