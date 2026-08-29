"""
Tests for agent.py pipeline functions - fetch, analyze, alert.
"""

import json
import pytest
import requests
from unittest.mock import patch, MagicMock
import os
import sys


@pytest.fixture(autouse=True)
def mock_openai():
    """Mock the openai SDK before agent import so no real client is built."""
    mock_sdk = MagicMock()
    sys.modules["openai"] = mock_sdk
    yield mock_sdk
    sys.modules.pop("openai", None)


def _fake_llm_response(content):
    """Build a minimal OpenAI-shaped chat.completions response object."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.fixture
def agent_mod(mock_openai):
    """Import agent module with mocked dependencies."""
    with patch.dict(os.environ, {
        "MINIMAX_API_KEY": "fake",
        "TELEGRAM_BOT_TOKEN": "fake",
        "TELEGRAM_CHAT_ID": "99999",
        "QUANT_ENGINE_URL": "http://localhost:8000/signals",
    }):
        agent_dir = os.path.join(os.path.dirname(__file__), "..")
        if agent_dir not in sys.path:
            sys.path.insert(0, agent_dir)
        if "agent" in sys.modules:
            del sys.modules["agent"]
        import agent as mod
        return mod


class TestFetchSignals:
    def test_fetch_signals_returns_list(self, agent_mod):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "signals": [{"ticker": "RELIANCE"}],
            "market_regime": "BULL",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            result = agent_mod.fetch_signals()
            assert result == [{"ticker": "RELIANCE"}]


    def test_fetch_signals_handles_failure(self, agent_mod):
        import requests # Make sure requests is imported
        # FIX: Throw the exact error the code is looking to catch
        with patch("requests.get", side_effect=requests.exceptions.RequestException("Network error")):
            result = agent_mod.fetch_signals()
            assert result == [] or result is None

def _review(payload=None, *, unavailable_reason=None):
    """[ADVISORY 2026-08-05] Wrap a legacy analysis dict as a typed Review.

    The pipelines now consume Review objects rather than dict|None, so a test
    that patches analyze_with_minimax has to hand back the same shape the real
    function does.
    """
    from advisory import from_payload, unavailable
    if unavailable_reason is not None:
        return unavailable(unavailable_reason)
    return from_payload(payload or {})


class TestAnalyzeWithMiniMax:
    def test_returns_parsed_output(self, agent_mod):
        content = json.dumps({
            "conviction_score": 75,
            "pitch": "Good setup",
            "rationale": "Volume confirms",
            "risks": "Sector risk",
        })

        agent_mod.client = MagicMock()
        agent_mod.client.chat.completions.create.return_value = _fake_llm_response(content)

        result = agent_mod.analyze_with_minimax(
            {"ticker": "RELIANCE", "close": 1000, "target_1": 1075, "stop_loss": 950},
            "Some sentiment text",
            "BULL",
        )
        assert result.verdict.value == "approve"
        assert result.conviction == 75
        assert "pitch" in result.payload

    def test_api_failure_is_review_unavailable_with_a_named_reason(self, agent_mod):
        """[ADVISORY 2026-08-05] Not None. The caller has to be able to tell an
        outage from an opinion -- collapsing both into None is what let a
        timed-out review masquerade as an approval."""
        agent_mod.client = MagicMock()
        agent_mod.client.chat.completions.create.side_effect = Exception("API down")

        result = agent_mod.analyze_with_minimax(
            {"ticker": "RELIANCE", "close": 1000, "target_1": 1075, "stop_loss": 950},
            "",
            "BULL",
        )
        assert result.verdict.value == "review_unavailable"
        assert result.reason == "api_error"
        assert result.available is False

    def test_parses_content_wrapped_in_markdown_fence(self, agent_mod):
        # MiniMax is told to emit bare JSON but LLMs sometimes fence it anyway;
        # the extractor must still recover the object.
        content = "```json\n" + json.dumps({
            "conviction_score": 60,
            "pitch": "Fenced",
            "rationale": "Test",
            "risks": "None",
        }) + "\n```"

        agent_mod.client = MagicMock()
        agent_mod.client.chat.completions.create.return_value = _fake_llm_response(content)

        result = agent_mod.analyze_with_minimax(
            {"ticker": "INFY", "close": 500, "target_1": 530, "stop_loss": 480},
            "",
            "BULL",
        )
        assert result.conviction == 60

    def test_unparseable_output_is_review_unavailable(self, agent_mod):
        agent_mod.client = MagicMock()
        agent_mod.client.chat.completions.create.return_value = _fake_llm_response(
            "I cannot help with that request."
        )

        result = agent_mod.analyze_with_minimax(
            {"ticker": "INFY", "close": 500, "target_1": 530, "stop_loss": 480},
            "",
            "BULL",
        )
        assert result.verdict.value == "review_unavailable"
        assert result.reason == "unparseable_output"

    def test_parses_content_with_reasoning_think_block(self, agent_mod):
        # [MINIMAX-REASONING 2026-07-16] MiniMax-M3 emits a <think>...</think>
        # reasoning block inline in content before the JSON (the 2026-07-16
        # FIVESTAR failure shape). The extractor must strip it and recover the
        # object instead of failing open to a SYSTEM FALLBACK alert.
        content = (
            "<think>\nLet me analyze this trade carefully from a cynical, "
            "risk-first perspective. Volume looks like {accumulation}.\n</think>\n"
            + json.dumps({
                "conviction_score": 72,
                "pitch": "Momentum with volume",
                "rationale": "Breakout on 3x volume",
                "risks": "Regime unknown",
            })
        )

        agent_mod.client = MagicMock()
        agent_mod.client.chat.completions.create.return_value = _fake_llm_response(content)

        result = agent_mod.analyze_with_minimax(
            {"ticker": "FIVESTAR", "close": 500, "target_1": 530, "stop_loss": 480},
            "",
            "UNKNOWN",
        )
        assert result.conviction == 72
        assert result.payload["pitch"] == "Momentum with volume"

    def test_unclosed_think_block_is_review_unavailable(self, agent_mod):
        # Reasoning ran past max_tokens: content is an unclosed <think> with no
        # JSON ever emitted. Nothing to recover -> REVIEW_UNAVAILABLE -> the
        # caller takes the fail-open SYSTEM FALLBACK path, but now the banner
        # names the reason instead of saying "AI analysis failed".
        agent_mod.client = MagicMock()
        agent_mod.client.chat.completions.create.return_value = _fake_llm_response(
            "<think>\nLet me analyze this trade carefully. The setup shows"
        )

        result = agent_mod.analyze_with_minimax(
            {"ticker": "FIVESTAR", "close": 500, "target_1": 530, "stop_loss": 480},
            "",
            "UNKNOWN",
        )
        assert result.verdict.value == "review_unavailable"
        assert result.reason == "unparseable_output"


class TestDeduplication:
    def test_processed_signals_cleared_by_clear_memory(self, agent_mod):
        agent_mod.processed_signals_today.add("RELIANCE")
        assert "RELIANCE" in agent_mod.processed_signals_today
        agent_mod.clear_memory()
        assert len(agent_mod.processed_signals_today) == 0


class TestRunPipeline:
    def test_skips_low_conviction_signals(self, agent_mod):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "signals": [{"ticker": "RELIANCE", "close": 100, "target_1": 110, "stop_loss": 90}],
            "market_regime": "BULL",
        }
        mock_resp.raise_for_status = MagicMock()

        low_analysis = {
            "conviction_score": 40,
            "pitch": "Weak",
            "rationale": "No volume",
            "risks": "High",
        }

        with patch("requests.get", return_value=mock_resp), \
             patch.object(agent_mod, "scrape_sentiment", return_value=""), \
             patch.object(agent_mod, "analyze_with_minimax", return_value=_review(low_analysis)), \
             patch.object(agent_mod, "send_telegram_alert") as mock_send, \
             patch("time.sleep"):
            agent_mod.processed_signals_today.clear()
            agent_mod.run_pipeline()
            mock_send.assert_not_called()
            # But signal should be marked as processed
            assert "RELIANCE" in agent_mod.processed_signals_today

    def test_sends_alert_for_high_conviction(self, agent_mod):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "signals": [{"ticker": "INFY", "close": 500, "target_1": 530, "stop_loss": 480}],
            "market_regime": "BULL",
        }
        mock_resp.raise_for_status = MagicMock()

        high_analysis = {
            "conviction_score": 80,
            "pitch": "Strong",
            "rationale": "Good volume",
            "risks": "Low",
        }

        with patch("requests.get", return_value=mock_resp), \
             patch.object(agent_mod, "scrape_sentiment", return_value=""), \
             patch.object(agent_mod, "analyze_with_minimax", return_value=_review(high_analysis)), \
             patch.object(agent_mod, "send_telegram_alert") as mock_send, \
             patch("time.sleep"):
            agent_mod.processed_signals_today.clear()
            agent_mod.run_pipeline()
            mock_send.assert_called_once()


class TestRunMomentumPipeline:
    @pytest.fixture(autouse=True)
    def _during_market_hours(self, agent_mod):
        """[POLL-CADENCE 2026-08-04] run_momentum_pipeline now self-gates on
        market hours, because its schedule became a bare 3-minute interval that
        fires around the clock. These tests exercise the pipeline body, so put
        the clock inside the session; test_gate_blocks_outside_market_hours
        covers the gate itself."""
        with patch.object(agent_mod, "_is_market_hours", return_value=True):
            yield

    def test_gate_blocks_outside_market_hours(self, agent_mod):
        """Outside 09:15-15:30 Mon-Fri the poll must not even hit the engine."""
        with patch.object(agent_mod, "_is_market_hours", return_value=False), \
             patch("requests.get") as mock_get:
            agent_mod.run_momentum_pipeline()
            mock_get.assert_not_called()

    def test_stale_signal_is_dropped_without_an_alert(self, agent_mod):
        """The engine flags anything over 30 min old. A breakout that age has
        already worked or failed, so the button would invite an entry at a
        price the setup no longer describes."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "signals": [{
                "ticker": "STALEB", "close": 100, "target_1": 110,
                "stop_loss": 90, "stale_data": True,
            }],
            "market_regime": "BULL",
            "momentum_pool": 5000,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp), \
             patch.object(agent_mod, "send_momentum_telegram_alert") as mock_send:
            agent_mod.run_momentum_pipeline()
            mock_send.assert_not_called()
        # Marked processed, so the next poll (3 min later) does not re-evaluate it.
        assert "STALEB_MOM" in agent_mod.processed_signals_today

    def test_skips_already_processed_momentum(self, agent_mod):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "signals": [{"ticker": "RELIANCE", "close": 100, "target_1": 110, "stop_loss": 90}],
            "market_regime": "BULL",
            "momentum_pool": 5000,
        }
        mock_resp.raise_for_status = MagicMock()

        agent_mod.processed_signals_today.add("RELIANCE_MOM")

        with patch("requests.get", return_value=mock_resp), \
             patch.object(agent_mod, "send_momentum_telegram_alert") as mock_send:
            agent_mod.run_momentum_pipeline()
            mock_send.assert_not_called()

    def test_one_bad_signal_does_not_stall_the_rest(self, agent_mod):
        """[FIX 2026-07-11 STALL] On 2026-07-10 an exception while
        processing COCHINSHIP killed the loop and HUDCO (same snapshot)
        was never processed. Each signal must be isolated: the failing
        ticker is retried next poll (not marked processed), the rest of
        the batch still goes out."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "signals": [
                {"ticker": "COCHINSHIP", "close": 100, "target_1": 110, "stop_loss": 90},
                {"ticker": "HUDCO", "close": 200, "target_1": 220, "stop_loss": 180},
            ],
            "market_regime": "BULL",
            "momentum_pool": 5000,
        }
        mock_resp.raise_for_status = MagicMock()

        high_analysis = {"conviction_score": 70, "pitch": "OK", "rationale": "Vol", "risks": "Low"}

        def sentiment_side_effect(ticker):
            if ticker == "COCHINSHIP":
                raise RuntimeError("scrape blew up")
            return ""

        with patch("requests.get", return_value=mock_resp), \
             patch.object(agent_mod, "scrape_sentiment", side_effect=sentiment_side_effect), \
             patch.object(agent_mod, "analyze_with_minimax", return_value=_review(high_analysis)), \
             patch.object(agent_mod, "send_momentum_telegram_alert") as mock_send, \
             patch("time.sleep"):
            agent_mod.processed_signals_today.clear()
            agent_mod.run_momentum_pipeline()
            # HUDCO still processed despite COCHINSHIP failing
            mock_send.assert_called_once()
            assert mock_send.call_args[0][0]["ticker"] == "HUDCO"
            assert "HUDCO_MOM" in agent_mod.processed_signals_today
            # Failed ticker NOT marked processed -> retried next poll
            assert "COCHINSHIP_MOM" not in agent_mod.processed_signals_today

    def test_low_conviction_is_advisory_by_default(self, agent_mod):
        """The deterministic, risk-sized setup remains a human decision."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "signals": [{"ticker": "COCHINSHIP", "close": 100, "target_1": 110, "stop_loss": 90}],
            "market_regime": "BULL",
            "momentum_pool": 5000,
        }
        mock_resp.raise_for_status = MagicMock()

        low_analysis = {"conviction_score": 30, "pitch": "Weak", "rationale": "No catalyst", "risks": "High"}

        with patch("requests.get", return_value=mock_resp), \
             patch.object(agent_mod, "scrape_sentiment", return_value=""), \
             patch.object(agent_mod, "analyze_with_minimax", return_value=_review(low_analysis)), \
             patch.object(agent_mod, "send_momentum_telegram_alert") as mock_buttons, \
             patch.object(agent_mod, "send_conviction_veto_notice") as mock_veto, \
             patch.object(agent_mod, "MOMENTUM_MINIMAX_REJECT_POLICY", "advisory"), \
             patch("time.sleep"):
            agent_mod.processed_signals_today.clear()
            agent_mod.run_momentum_pipeline()
            mock_buttons.assert_called_once()
            mock_veto.assert_not_called()
            assert "COCHINSHIP_MOM" in agent_mod.processed_signals_today

    def test_low_conviction_can_be_configured_as_hard_veto(self, agent_mod):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "signals": [{
                "ticker": "COCHINSHIP", "close": 100,
                "target_1": 110, "stop_loss": 90,
            }],
            "market_regime": "BULL",
            "momentum_pool": 5000,
        }
        mock_resp.raise_for_status = MagicMock()
        low_analysis = {
            "conviction_score": 30, "pitch": "Weak",
            "rationale": "No catalyst", "risks": "High",
        }

        with patch("requests.get", return_value=mock_resp), \
             patch.object(agent_mod, "scrape_sentiment", return_value=""), \
             patch.object(agent_mod, "analyze_with_minimax", return_value=_review(low_analysis)), \
             patch.object(agent_mod, "send_momentum_telegram_alert") as mock_buttons, \
             patch.object(agent_mod, "send_conviction_veto_notice") as mock_veto, \
             patch.object(agent_mod, "MOMENTUM_MINIMAX_REJECT_POLICY", "block"), \
             patch("time.sleep"):
            agent_mod.processed_signals_today.clear()
            agent_mod.run_momentum_pipeline()
            mock_buttons.assert_not_called()
            mock_veto.assert_called_once()
            assert "COCHINSHIP_MOM" in agent_mod.processed_signals_today

    def test_veto_notice_payload_has_no_buttons(self, agent_mod):
        analysis = {"conviction_score": 30, "pitch": "Weak", "rationale": "No catalyst", "risks": "High"}
        signal = {"ticker": "COCHINSHIP", "close": 100, "target_1": 110, "stop_loss": 90}
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(raise_for_status=MagicMock())
            agent_mod.send_conviction_veto_notice(signal, _review(analysis))
            mock_post.assert_called_once()
            payload = mock_post.call_args[1]["json"]
            assert "COCHINSHIP" in payload["text"]
            assert "30" in payload["text"]
            assert "reply_markup" not in payload

    def test_veto_notice_failure_is_swallowed(self, agent_mod):
        analysis = {"conviction_score": 30, "pitch": "W", "rationale": "N", "risks": "H"}
        signal = {"ticker": "COCHINSHIP"}
        with patch("requests.post", side_effect=Exception("network down")):
            # Must not raise
            agent_mod.send_conviction_veto_notice(signal, _review(analysis))

    def test_processes_new_momentum_signal(self, agent_mod):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "signals": [{"ticker": "TCS", "close": 3000, "target_1": 3100, "stop_loss": 2950}],
            "market_regime": "BULL",
            "momentum_pool": 5000,
        }
        mock_resp.raise_for_status = MagicMock()

        high_analysis = {"conviction_score": 70, "pitch": "OK", "rationale": "Vol", "risks": "Low"}

        with patch("requests.get", return_value=mock_resp), \
             patch.object(agent_mod, "scrape_sentiment", return_value=""), \
             patch.object(agent_mod, "analyze_with_minimax", return_value=_review(high_analysis)), \
             patch.object(agent_mod, "send_momentum_telegram_alert") as mock_send, \
             patch("time.sleep"):
            agent_mod.processed_signals_today.clear()
            agent_mod.run_momentum_pipeline()
            mock_send.assert_called_once()
            assert "TCS_MOM" in agent_mod.processed_signals_today

    def test_telegram_http_400_is_retried_and_not_deduplicated(self, agent_mod):
        """A rejected Telegram payload must remain eligible for the next poll.

        This is the Aug-25 PWL failure mode: the engine approved the setup,
        Telegram returned 400, but the swallowed exception let the caller mark
        it processed forever.
        """
        engine_resp = MagicMock()
        engine_resp.json.return_value = {
            "signals": [{
                "ticker": "PWL", "close": 100, "target_1": 106,
                "stop_loss": 97, "vwap": 99, "cost_ratio": 0.1,
            }],
            "market_regime": "BULL",
            "momentum_pool": 5000,
        }
        engine_resp.raise_for_status = MagicMock()
        analysis = {
            "conviction_score": 70, "pitch": "Breakout",
            "rationale": "Volume", "risks": "Whipsaw",
        }

        register_resp = MagicMock()
        register_resp.raise_for_status = MagicMock()
        register_resp.json.return_value = {"registered": True}
        telegram_resp = MagicMock()
        telegram_resp.raise_for_status.side_effect = requests.HTTPError(
            "400 Client Error for url: "
            "https://api.telegram.org/botfake/sendMessage"
        )

        def post_by_url(url, **kwargs):
            if url.endswith("/api/internal/register-signal"):
                return register_resp
            return telegram_resp

        with patch("requests.get", return_value=engine_resp), \
             patch("requests.post", side_effect=post_by_url) as mock_post, \
             patch.object(agent_mod, "scrape_sentiment", return_value=""), \
             patch.object(agent_mod, "analyze_with_minimax", return_value=_review(analysis)), \
             patch("time.sleep"):
            agent_mod.processed_signals_today.clear()
            agent_mod.run_momentum_pipeline()
            agent_mod.run_momentum_pipeline()

        telegram_calls = [
            call for call in mock_post.call_args_list
            if "/sendMessage" in call.args[0]
        ]
        assert len(telegram_calls) == 2
        assert "PWL_MOM" not in agent_mod.processed_signals_today


class TestSendTelegramAlert:
    def test_sends_swing_alert_with_buttons(self, agent_mod):
        analysis = {
            "conviction_score": 80,
            "pitch": "Strong",
            "rationale": "Confirmed",
            "risks": "Low",
        }
        signal = {"ticker": "RELIANCE", "close": 1000, "target_1": 1075, "stop_loss": 950}

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(raise_for_status=MagicMock())
            agent_mod.send_telegram_alert(signal, _review(analysis))
            assert mock_post.call_count == 2
            register_call, telegram_call = mock_post.call_args_list
            assert register_call.args[0].endswith("/api/internal/register-signal")
            assert register_call.kwargs["json"]["ticker"] == "RELIANCE"
            assert "/sendMessage" in telegram_call.args[0]
            payload = telegram_call.kwargs["json"]
            assert "RELIANCE" in payload["text"]
            # Verify inline keyboard exists
            markup = json.loads(payload["reply_markup"])
            assert "inline_keyboard" in markup
            buttons = markup["inline_keyboard"][0]
            assert len(buttons) == 2  # EXECUTE and REJECT

    def test_sends_fallback_when_analysis_is_none(self, agent_mod):
        signal = {"ticker": "TCS", "close": 3000, "target_1": 3100, "stop_loss": 2900}

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(raise_for_status=MagicMock())
            agent_mod.send_telegram_alert(signal, _review(unavailable_reason='timeout_100s'))
            assert mock_post.call_count == 2
            register_call, telegram_call = mock_post.call_args_list
            assert register_call.args[0].endswith("/api/internal/register-signal")
            assert register_call.kwargs["json"]["ticker"] == "TCS"
            assert "/sendMessage" in telegram_call.args[0]
            payload = telegram_call.kwargs["json"]
            assert "FALLBACK" in payload["text"]

    @pytest.mark.parametrize(
        "dynamic_text",
        [
            "Price <= VWAP; wait for confirmation",
            "under_score catalyst",
            "Risk [unmatched bracket and * marker",
        ],
    )
    def test_momentum_dynamic_text_is_sent_as_plain_text(
        self, agent_mod, dynamic_text
    ):
        """Free-text analysis cannot opt the message into Telegram parsing."""
        analysis = {
            "conviction_score": 75,
            "pitch": dynamic_text,
            "rationale": "Valid",
            "risks": dynamic_text,
        }
        signal = {
            "ticker": "PWL", "close": 100, "target_1": 106,
            "stop_loss": 97, "vwap": 99, "cost_ratio": 0.1,
        }
        with patch.object(agent_mod, "register_approved_snapshot"), \
             patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(raise_for_status=MagicMock())
            agent_mod.send_momentum_telegram_alert(
                signal, _review(analysis), 5000
            )

        payload = mock_post.call_args.kwargs["json"]
        assert "parse_mode" not in payload
        assert dynamic_text in payload["text"]

    def test_momentum_failure_redacts_bot_token(self, agent_mod, capsys):
        secret = "123456:VERY_SECRET_BOT_TOKEN"
        signal = {
            "ticker": "PWL", "close": 100, "target_1": 106,
            "stop_loss": 97, "vwap": 99, "cost_ratio": 0.1,
        }
        analysis = {
            "conviction_score": 75, "pitch": "Valid",
            "rationale": "Valid", "risks": "Contained",
        }
        leaked_url = f"https://api.telegram.org/bot{secret}/sendMessage"
        response = MagicMock()
        response.raise_for_status.side_effect = requests.HTTPError(
            f"400 Client Error for url: {leaked_url}"
        )

        with patch.object(agent_mod, "TELEGRAM_BOT_TOKEN", secret), \
             patch.object(agent_mod, "register_approved_snapshot"), \
             patch("requests.post", return_value=response), \
             pytest.raises(RuntimeError) as caught:
            agent_mod.send_momentum_telegram_alert(
                signal, _review(analysis), 5000
            )

        rendered = str(caught.value) + capsys.readouterr().out
        assert secret not in rendered
        assert "/bot<redacted>/sendMessage" in str(caught.value)

    def test_low_conviction_button_carries_explicit_advisory(self, agent_mod):
        signal = {
            "ticker": "GRAVITA", "close": 1823.7, "target_1": 1864.2,
            "stop_loss": 1798.38, "vwap": 1817.9, "cost_ratio": 0.0042,
        }
        review = _review({
            "conviction_score": 38, "pitch": "Mixed",
            "rationale": "Engine setup is valid", "risks": "Weak catalyst",
        })
        with patch.object(agent_mod, "register_approved_snapshot"), \
             patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(raise_for_status=MagicMock())
            agent_mod.send_momentum_telegram_alert(signal, review, 5000)

        payload = mock_post.call_args.kwargs["json"]
        assert "AI conviction is low" in payload["text"]
        assert "manual review" in payload["text"]
        assert "reply_markup" in payload
