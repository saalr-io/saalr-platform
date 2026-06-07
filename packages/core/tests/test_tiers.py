from saalr_core.tiers import Entitlements, entitlements_for


def test_price_forecast_is_premium_only():
    assert entitlements_for("premium")["price_forecast"] is True
    assert entitlements_for("pro")["price_forecast"] is False
    assert entitlements_for("free")["price_forecast"] is False


def test_news_sentiment_is_pro_plus():
    assert entitlements_for("pro")["news_sentiment"] is True
    assert entitlements_for("premium")["news_sentiment"] is True
    assert entitlements_for("free")["news_sentiment"] is False


def test_ml_forecast_mapping_unchanged():
    assert entitlements_for("pro")["ml_forecast"] is True
    assert entitlements_for("free")["ml_forecast"] is False


def test_unknown_tier_falls_back_to_free():
    assert entitlements_for("bogus") == entitlements_for("free")


def test_positional_construction_still_works():
    e = Entitlements(False, False, False, False, 0)
    assert e.price_forecast is False and e.news_sentiment is False
