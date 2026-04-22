"""
Tests for agent.py pipeline functions - fetch, analyze, alert.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
import os
import sys


@pytest.fixture(autouse=True)
def mock_google_genai():
    """Mock google.genai before agent import."""
    mock_genai = MagicMock()
    mock_types = MagicMock()
    sys.modules["google"] = MagicMock()
    sys.modules["google.genai"] = mock_genai
    sys.modules["google.genai.types"] = mock_types
    yield mock_genai
    for m in ["google", "google.genai", "google.genai.types"]:
        sys.modules.pop(m, None)


@pytest.fixture
def agent_mod(mock_google_genai):
    """Import agent module with mocked dependencies."""
    with patch.dict(os.environ, {
        "GEMINI_API_KEY": "fake",
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

class TestAnalyzeWithGemini:
    def test_returns_parsed_output(self, agent_mod):
        mock_parsed = MagicMock()
        mock_parsed.model_dump.return_value = {
            "conviction_score": 75,
            "pitch": "Good setup",
            "rationale": "Volume confirms",
            "risks": "Sector risk",
        }
        mock_response = MagicMock()
        mock_response.parsed = mock_parsed

        agent_mod.client = MagicMock()
        agent_mod.client.models.generate_content.return_value = mock_response

        result = agent_mod.analyze_with_gemini(
            {"ticker": "RELIANCE", "close": 1000, "target_1": 1075, "stop_loss": 950},
            "Some sentiment text",
            "BULL",
        )
        assert result["conviction_score"] == 75
        assert "pitch" in result

    def test_returns_none_on_failure(self, agent_mod):
        agent_mod.client = MagicMock()
        agent_mod.client.models.generate_content.side_effect = Exception("API down")

        result = agent_mod.analyze_with_gemini(
            {"ticker": "RELIANCE", "close": 1000, "target_1": 1075, "stop_loss": 950},
            "",
            "BULL",
        )
        assert result is None

    def test_falls_back_to_json_parse_when_parsed_is_none(self, agent_mod):
        mock_response = MagicMock()
        mock_response.parsed = None
        mock_response.text = json.dumps({
            "conviction_score": 60,
            "pitch": "Fallback",
            "rationale": "Test",
            "risks": "None",
        })

        agent_mod.client = MagicMock()
        agent_mod.client.models.generate_content.return_value = mock_response

        result = agent_mod.analyze_with_gemini(
            {"ticker": "INFY", "close": 500, "target_1": 530, "stop_loss": 480},
            "",
            "BULL",
        )
        assert result["conviction_score"] == 60


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
             patch.object(agent_mod, "analyze_with_gemini", return_value=low_analysis), \
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
             patch.object(agent_mod, "analyze_with_gemini", return_value=high_analysis), \
             patch.object(agent_mod, "send_telegram_alert") as mock_send, \
             patch("time.sleep"):
            agent_mod.processed_signals_today.clear()
            agent_mod.run_pipeline()
            mock_send.assert_called_once()


class TestRunMomentumPipeline:
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
             patch.object(agent_mod, "analyze_with_gemini", return_value=high_analysis), \
             patch.object(agent_mod, "send_momentum_telegram_alert") as mock_send, \
             patch("time.sleep"):
            agent_mod.processed_signals_today.clear()
            agent_mod.run_momentum_pipeline()
            mock_send.assert_called_once()
            assert "TCS_MOM" in agent_mod.processed_signals_today


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
            agent_mod.send_telegram_alert(signal, analysis)
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            payload = call_kwargs[1].get("json") or call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs[1]["json"]
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
            agent_mod.send_telegram_alert(signal, None)
            mock_post.assert_called_once()
            payload = mock_post.call_args[1]["json"]
            assert "FALLBACK" in payload["text"]
