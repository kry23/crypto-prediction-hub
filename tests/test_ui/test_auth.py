import os
from unittest.mock import patch


@patch("crypto_predictor.ui.auth.st")
def test_current_user_email_returns_header_value(mock_st):
    mock_st.context.headers.get.return_value = "koray@example.com"
    from crypto_predictor.ui.auth import current_user_email
    assert current_user_email() == "koray@example.com"


@patch("crypto_predictor.ui.auth.st")
def test_current_user_email_returns_none_when_header_missing(mock_st):
    mock_st.context.headers.get.return_value = None
    from crypto_predictor.ui.auth import current_user_email
    assert current_user_email() is None


@patch("crypto_predictor.ui.auth.st")
def test_current_user_email_returns_none_on_exception(mock_st):
    mock_st.context.headers.get.side_effect = AttributeError()
    from crypto_predictor.ui.auth import current_user_email
    assert current_user_email() is None


@patch.dict(os.environ, {"ENV": "dev"}, clear=False)
@patch("crypto_predictor.ui.auth.st")
def test_require_auth_dev_fallback(mock_st):
    mock_st.context.headers.get.return_value = None
    from crypto_predictor.ui.auth import require_auth
    assert require_auth() == "dev@local"


@patch.dict(os.environ, {"ENV": "prod"}, clear=False)
@patch("crypto_predictor.ui.auth.st")
def test_require_auth_prod_stops_without_header(mock_st):
    mock_st.context.headers.get.return_value = None
    from crypto_predictor.ui.auth import require_auth
    require_auth()
    mock_st.error.assert_called_once()
    mock_st.stop.assert_called_once()
