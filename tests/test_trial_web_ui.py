from mahjong_agent import TRIAL_WEB_HTML


def test_trial_web_html_contains_console_shell() -> None:
    assert TRIAL_WEB_HTML.startswith("<!doctype html>")
    assert "麻将馆组局试用台" in TRIAL_WEB_HTML
    assert 'id="messageText"' in TRIAL_WEB_HTML
    assert 'id="candidateBox"' in TRIAL_WEB_HTML
    assert "async function analyze()" in TRIAL_WEB_HTML
    assert "async function candidateReply" in TRIAL_WEB_HTML
