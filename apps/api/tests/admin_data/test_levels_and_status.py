import pytest

from app.admin_data.levels import (
    DEFAULT_LEVEL_GRAPH,
    DEFAULT_LEVELS,
    DEFAULT_PARENT_EDGES,
    ROOT_LEVEL_KEY,
    LevelDef,
    LevelGraph,
    LevelGraphError,
)
from app.admin_data.status import (
    ALLOWED_TRANSITIONS,
    EDITABLE_STATUSES,
    InvalidTransition,
    PublicationStatus,
    can_transition,
    require_transition,
)

S = PublicationStatus


# ---- level graph -------------------------------------------------------------------------


def test_default_graph_is_state_district_subdistrict_locality():
    g = DEFAULT_LEVEL_GRAPH
    assert [lvl.key for lvl in g.levels_by_rank()] == [
        "state_ut",
        "district",
        "subdistrict",
        "locality",
    ]
    assert g.is_root("state_ut") and not g.is_root("district")
    assert g.allowed_parents("district") == {"state_ut"}
    assert g.allowed_parents("locality") == {"subdistrict"}
    assert g.allowed_parents("state_ut") == frozenset()


def test_levels_cannot_skip_or_reverse():
    g = DEFAULT_LEVEL_GRAPH
    assert "state_ut" not in g.allowed_parents("subdistrict")  # no skipping
    assert "district" not in g.allowed_parents("state_ut")  # no reversing


def test_graph_can_be_extended_with_new_levels_without_code_changes():
    """Villages / towns / wards are added as data: new levels plus allowed-parent edges."""
    levels = [*DEFAULT_LEVELS, LevelDef("ward", 5, "Ward")]
    edges = [*DEFAULT_PARENT_EDGES, ("ward", "locality")]
    graph = LevelGraph(levels, edges)
    assert graph.allowed_parents("ward") == {"locality"}


def test_a_level_may_have_several_allowed_parent_levels():
    levels = [*DEFAULT_LEVELS, LevelDef("ward", 5, "Ward")]
    edges = [*DEFAULT_PARENT_EDGES, ("ward", "locality"), ("ward", "subdistrict")]
    assert LevelGraph(levels, edges).allowed_parents("ward") == {"locality", "subdistrict"}


@pytest.mark.parametrize(
    ("edges", "why"),
    [
        ([("district", "district")], "parent must rank above child"),
        ([("state_ut", "district")], "parent must rank above child"),
        ([("district", "nowhere")], "unknown level"),
    ],
)
def test_invalid_edges_rejected(edges, why):
    with pytest.raises(LevelGraphError):
        LevelGraph(DEFAULT_LEVELS, edges)


def test_every_non_root_level_needs_a_parent():
    with pytest.raises(LevelGraphError):
        LevelGraph(DEFAULT_LEVELS, [("district", "state_ut")])  # subdistrict/locality orphaned


def test_root_level_is_required_and_ranks_must_be_unique():
    with pytest.raises(LevelGraphError):
        LevelGraph([LevelDef("district", 2, "District")], [])
    with pytest.raises(LevelGraphError):
        LevelGraph([LevelDef(ROOT_LEVEL_KEY, 1, "A"), LevelDef("district", 1, "B")], [])


# ---- publication status ------------------------------------------------------------------


def test_every_status_has_a_transition_entry():
    assert set(ALLOWED_TRANSITIONS) == set(PublicationStatus)


def test_the_happy_path_is_allowed_step_by_step():
    path = [S.RECEIVED, S.VALIDATED, S.UNDER_REVIEW, S.APPROVED, S.PUBLISHED, S.SUPERSEDED]
    for current, target in zip(path, path[1:], strict=False):
        assert can_transition(current, target)


def test_nothing_can_skip_review():
    assert not can_transition(S.RECEIVED, S.PUBLISHED)
    assert not can_transition(S.VALIDATED, S.PUBLISHED)
    assert not can_transition(S.VALIDATED, S.APPROVED)
    assert not can_transition(S.UNDER_REVIEW, S.PUBLISHED)


def test_only_approved_versions_can_be_published():
    sources = [s for s in S if can_transition(s, S.PUBLISHED)]
    assert sources == [S.APPROVED]


def test_terminal_states_have_no_exits():
    assert ALLOWED_TRANSITIONS[S.REJECTED] == frozenset()
    assert ALLOWED_TRANSITIONS[S.SUPERSEDED] == frozenset()


def test_published_data_can_only_be_superseded_never_rejected_or_reverted():
    assert ALLOWED_TRANSITIONS[S.PUBLISHED] == {S.SUPERSEDED}


def test_no_going_backwards():
    order = [S.RECEIVED, S.VALIDATED, S.UNDER_REVIEW, S.APPROVED, S.PUBLISHED, S.SUPERSEDED]
    for i, later in enumerate(order):
        for earlier in order[:i]:
            assert not can_transition(later, earlier)


def test_content_is_editable_only_before_review():
    assert EDITABLE_STATUSES == {S.RECEIVED, S.VALIDATED}


def test_require_transition_raises_a_readable_error():
    with pytest.raises(InvalidTransition, match="'validated' to 'published'"):
        require_transition(S.VALIDATED, S.PUBLISHED)
    require_transition(S.APPROVED, S.PUBLISHED)  # does not raise
