from __future__ import annotations

import pandas as pd

from scripts import import_futu_data
from skills.store.data_manager import DataManager


def test_import_futu_data_saves_standard_parquet(monkeypatch, tmp_path) -> None:
    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def get_history_kline_quota(self):
            return {"remain_quota": 10}

        def fetch_history_kline(self, symbol, **kwargs):
            assert symbol == "SHSE.600519"
            assert kwargs["rehab"] == "forward"
            return pd.DataFrame(
                {
                    "open": [1.0],
                    "high": [2.0],
                    "low": [0.5],
                    "close": [1.5],
                    "volume": [100.0],
                },
                index=pd.DatetimeIndex(["2024-01-01"], name="eob"),
            )

    monkeypatch.setattr(import_futu_data, "FutuClient", FakeClient)

    imported = import_futu_data.import_futu_data(
        ["SHSE.600519"],
        "2024-01-01",
        "2024-01-02",
        rehab="forward",
        data_root=tmp_path,
    )

    assert imported == ["SHSE.600519"]
    bars = DataManager(data_root=str(tmp_path)).read_symbol("SHSE.600519", frequency="1d_adj")
    assert bars.index.name == "eob"
    assert bars["close"].tolist() == [1.5]
