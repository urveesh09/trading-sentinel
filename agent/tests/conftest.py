"""Shared fixtures for Agent (Container C) tests."""

import pytest
from unittest.mock import patch, MagicMock
import os

# Set env vars before any import of agent.py
os.environ.setdefault("GEMINI_API_KEY", "fake-gemini-key-for-testing")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ")
os.environ.setdefault("TELEGRAM_CHAT_ID", "99999999999")
os.environ.setdefault("QUANT_ENGINE_URL", "http://localhost:8000/signals")


@pytest.fixture
def sample_swing_signal():
    return {
        "ticker": "RELIANCE",
        "close": 2500.0,
        "target_1": 2625.0,
        "stop_loss": 2375.0,
        "strategy_type": "SWING",
        "net_ev": 150.0,
        "score": 78,
        "volume_ratio": 2.5,
        "rsi_14": 58.0,
        "rs_score": 1.2,
    }


@pytest.fixture
def sample_momentum_signal():
    return {
        "ticker": "INFY",
        "close": 1500.0,
        "target_1": 1545.0,
        "stop_loss": 1470.0,
        "strategy_type": "MOMENTUM",
        "vwap": 1490.0,
        "product_type": "MIS",
        "cost_ratio": 0.15,
        "net_ev": 30.0,
        "score": 70,
        "volume_ratio": 3.1,
        "rsi_14": 62.0,
        "rs_score": None,
    }


@pytest.fixture
def sample_gemini_output():
    return {
        "conviction_score": 75,
        "pitch": "Strong breakout with volume confirmation.",
        "rationale": "Price above VWAP with institutional buying.",
        "risks": "Sector rotation risk; broad market weakness.",
    }
