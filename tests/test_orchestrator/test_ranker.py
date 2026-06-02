from crypto_predictor.orchestrator.ranker import rank_predictions, RankedSlate


def test_rank_predictions_separates_long_short_wild():
    rows = [
        {"id": "a", "symbol": "SOL", "prediction": "up", "p_direction": 0.82,
         "target_value": 0.06, "composite_score": 0.049, "confidence_flag": "HIGH_CONV"},
        {"id": "b", "symbol": "AVAX", "prediction": "up", "p_direction": 0.76,
         "target_value": 0.05, "composite_score": 0.038, "confidence_flag": "NORMAL"},
        {"id": "c", "symbol": "ENS", "prediction": "down", "p_direction": 0.72,
         "target_value": -0.04, "composite_score": 0.029, "confidence_flag": "NORMAL"},
        {"id": "d", "symbol": "AGIX", "prediction": "up", "p_direction": 0.81,
         "target_value": 0.07, "composite_score": 0.040, "confidence_flag": "WILD_CARD"},
    ]
    slate = rank_predictions(rows, k_long=10, k_short=10)
    assert isinstance(slate, RankedSlate)
    assert "SOL" in [p["symbol"] for p in slate.top_long]
    assert "ENS" in [p["symbol"] for p in slate.top_short]
    assert "AGIX" in [p["symbol"] for p in slate.wild_cards]
    assert "AGIX" not in [p["symbol"] for p in slate.top_long]


def test_rank_predictions_orders_by_composite_descending():
    rows = [
        {"id": "a", "symbol": "A", "prediction": "up", "p_direction": 0.7,
         "target_value": 0.04, "composite_score": 0.028, "confidence_flag": "NORMAL"},
        {"id": "b", "symbol": "B", "prediction": "up", "p_direction": 0.6,
         "target_value": 0.08, "composite_score": 0.048, "confidence_flag": "NORMAL"},
        {"id": "c", "symbol": "C", "prediction": "up", "p_direction": 0.8,
         "target_value": 0.02, "composite_score": 0.016, "confidence_flag": "NORMAL"},
    ]
    slate = rank_predictions(rows, k_long=10, k_short=10)
    symbols = [p["symbol"] for p in slate.top_long]
    assert symbols == ["B", "A", "C"]
