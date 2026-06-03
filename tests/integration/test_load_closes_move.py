def test_load_closes_is_shared_from_core():
    from saalr_api.forecast.repo import load_closes as reexported
    from saalr_core.marketdata.bars import load_closes as core_fn
    assert core_fn is reexported
