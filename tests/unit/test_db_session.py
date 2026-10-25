from heatmap_core.db.session import MAX_BIND_PARAMS, insert_batches


def test_insert_batches_stay_under_the_bind_parameter_limit() -> None:
    rows = [{f"c{i}": n for i in range(19)} for n in range(10_000)]
    batches = list(insert_batches(rows))
    assert sum(len(b) for b in batches) == 10_000
    assert all(len(b) * 19 <= MAX_BIND_PARAMS for b in batches)
    assert list(insert_batches([])) == []
