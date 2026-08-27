from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from skills.ingest import (
    FutuClient,
    normalize_futu_kline,
    to_futu_symbol,
    to_quantspace_futu_symbol,
)


def test_futu_symbol_conversion() -> None:
    assert to_futu_symbol("SHSE.600519") == "SH.600519"
    assert to_futu_symbol("NASDAQ.AAPL") == "US.AAPL"
    assert to_futu_symbol("HK.00700") == "HK.00700"
    assert to_quantspace_futu_symbol("SH.600519") == "SHSE.600519"
    assert to_quantspace_futu_symbol("US.AAPL") == "NASDAQ.AAPL"
    assert to_quantspace_futu_symbol("HK.00700") == "HKEX.00700"


def test_futu_symbol_conversion_rejects_unsupported_exchange() -> None:
    with pytest.raises(ValueError, match="Unsupported Futu quote market prefix"):
        to_futu_symbol("SHFE.RB99")


def test_normalize_futu_kline_returns_sorted_deduplicated_ohlcv() -> None:
    raw = pd.DataFrame(
        {
            "time_key": ["2024-01-02 09:31:00", "2024-01-01 09:31:00", "2024-01-01 09:31:00"],
            "open": [2, "1", 10],
            "high": [3, "2", 11],
            "low": [1, "0.5", 9],
            "close": [2.5, "1.5", 10.5],
            "volume": [20, "10", 99],
            "code": ["SH.600519"] * 3,
        }
    )

    result = normalize_futu_kline(raw)

    assert result.index.name == "eob"
    assert result.index.tolist() == [pd.Timestamp("2024-01-01 09:31"), pd.Timestamp("2024-01-02 09:31")]
    assert result.loc[pd.Timestamp("2024-01-01 09:31"), "close"] == 10.5
    assert result.columns.tolist() == ["open", "high", "low", "close", "volume"]
    assert result.dtypes.eq(float).all()


def test_normalize_futu_kline_accepts_skill_json_field_name() -> None:
    result = normalize_futu_kline(
        [
            {
                "time": "2024-01-02 09:31:00",
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.5,
                "volume": 100,
            }
        ]
    )

    assert result.shape == (1, 5)


def test_futu_client_fetches_all_pages_and_reuses_context() -> None:
    pages = [
        (
            pd.DataFrame(
                {
                    "time_key": ["2024-01-01"],
                    "open": [1],
                    "high": [2],
                    "low": [0.5],
                    "close": [1.5],
                    "volume": [100],
                }
            ),
            "page-2",
        ),
        (
            pd.DataFrame(
                {
                    "time_key": ["2024-01-02"],
                    "open": [2],
                    "high": [3],
                    "low": [1.5],
                    "close": [2.5],
                    "volume": [200],
                }
            ),
            None,
        ),
    ]
    calls: list[dict] = []

    class FakeContext:
        closed = False

        def request_history_kline(self, **kwargs):
            calls.append(kwargs)
            data, page_key = pages.pop(0)
            return 0, data, page_key

        def close(self):
            self.closed = True

    context = FakeContext()
    sdk = SimpleNamespace(
        RET_OK=0,
        KLType=SimpleNamespace(K_DAY="day"),
        AuType=SimpleNamespace(NONE="none"),
        Session=SimpleNamespace(NONE="session-none"),
    )
    client = FutuClient(
        host="opend",
        port=123,
        sdk_module=sdk,
        context_factory=lambda **kwargs: context,
    )

    with client:
        result = client.fetch_history_kline(
            "SHSE.600519",
            start="2024-01-01",
            end="2024-01-02",
            max_count=100,
        )

    assert result.index.tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")]
    assert calls[0]["code"] == "SH.600519"
    assert calls[0]["ktype"] == "day"
    assert calls[0]["autype"] == "none"
    assert "page_req_key" not in calls[0]
    assert calls[1]["page_req_key"] == "page-2"
    assert context.closed


def test_futu_client_raises_on_api_error_and_closes_owned_context() -> None:
    class FakeContext:
        closed = False

        def request_history_kline(self, **kwargs):
            return -1, "quota exceeded", None

        def close(self):
            self.closed = True

    context = FakeContext()
    sdk = SimpleNamespace(
        RET_OK=0,
        KLType=SimpleNamespace(K_DAY="day"),
        AuType=SimpleNamespace(NONE="none"),
        Session=SimpleNamespace(NONE="session-none"),
    )
    client = FutuClient(sdk_module=sdk, context_factory=lambda **kwargs: context)

    with pytest.raises(RuntimeError, match="quota exceeded"):
        client.fetch_history_kline("SHSE.600519")

    assert context.closed
