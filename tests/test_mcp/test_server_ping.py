from crypto_predictor.mcp.server import ping


def test_ping_returns_status_ok():
    result = ping()
    assert result["status"] == "ok"
    assert "version" in result
    assert "timestamp" in result
