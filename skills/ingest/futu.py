"""Futu OpenAPI ingestion helpers.

This module is deliberately fetch-only.  Futu's OpenAPI provides the market
data connection, while :class:`skills.store.data_manager.DataManager` remains
the owner of local Parquet persistence.

The Futu skill under ``.agents/skills/futuapi`` contains CLI workflows for
interactive use.  The reusable project boundary uses the same ``futu-api``
SDK directly instead of importing those scripts: the skill's ``common.py``
performs an OpenD health check at import time, which would make a normal
library import unexpectedly depend on a live OpenD process.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pandas as pd

FUTU_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]

_QS_TO_FUTU = {
    "SHSE": "SH",
    "SZSE": "SZ",
    "HKEX": "HK",
    "NASDAQ": "US",
    "SG": "SG",
    "MY": "MY",
    "JP": "JP",
    "CC": "CC",
}
_FUTU_TO_QS = {value: key for key, value in _QS_TO_FUTU.items()}

_KTYPE_NAMES = {
    "1m": "K_1M",
    "3m": "K_3M",
    "5m": "K_5M",
    "15m": "K_15M",
    "30m": "K_30M",
    "60m": "K_60M",
    "1d": "K_DAY",
    "1w": "K_WEEK",
    "1M": "K_MON",
    "1Q": "K_QUARTER",
    "1Y": "K_YEAR",
}
_REHAB_NAMES = {
    "none": "NONE",
    "forward": "QFQ",
    "backward": "HFQ",
}
_SESSION_NAMES = {
    "NONE": "NONE",
    "RTH": "RTH",
    "ETH": "ETH",
    "ALL": "ALL",
}


class FutuAPIError(RuntimeError):
    """Raised when OpenD returns a non-OK response for a data request."""

    def __init__(self, ret: Any, message: Any):
        self.ret = ret
        self.message = str(message)
        super().__init__(f"Futu API request failed (ret={ret}): {self.message}")


def to_futu_symbol(symbol: str) -> str:
    """Convert a QuantSpace symbol to Futu's ``MARKET.CODE`` format.

    Examples
    --------
    ``SHSE.600519`` -> ``SH.600519``
    ``NASDAQ.AAPL`` -> ``US.AAPL``

    Futu's quote API does not use the QuantSpace futures namespace, so
    unsupported prefixes fail explicitly instead of silently producing a
    request for the wrong instrument.
    """
    if not isinstance(symbol, str) or "." not in symbol:
        raise ValueError(f"Not a market symbol (missing '.'): {symbol!r}")
    prefix, code = symbol.strip().split(".", 1)
    prefix = prefix.upper()
    code = code.strip()
    if not code:
        raise ValueError(f"Symbol code cannot be empty: {symbol!r}")
    futu_prefix = _QS_TO_FUTU.get(prefix)
    if futu_prefix is None:
        if prefix in _FUTU_TO_QS:
            futu_prefix = prefix
        else:
            raise ValueError(
                f"Unsupported Futu quote market prefix {prefix!r}; "
                f"supported prefixes: {sorted(_QS_TO_FUTU)}"
            )
    return f"{futu_prefix}.{code}"


def to_quantspace_futu_symbol(symbol: str) -> str:
    """Convert a Futu ``MARKET.CODE`` symbol to QuantSpace format."""
    if not isinstance(symbol, str) or "." not in symbol:
        raise ValueError(f"Not a Futu symbol (missing '.'): {symbol!r}")
    prefix, code = symbol.strip().split(".", 1)
    prefix = prefix.upper()
    code = code.strip()
    if not code:
        raise ValueError(f"Symbol code cannot be empty: {symbol!r}")
    qs_prefix = _FUTU_TO_QS.get(prefix)
    if qs_prefix is None:
        if prefix in _QS_TO_FUTU:
            qs_prefix = prefix
        else:
            raise ValueError(
                f"Unsupported Futu quote market prefix {prefix!r}; "
                f"supported prefixes: {sorted(_FUTU_TO_QS)}"
            )
    return f"{qs_prefix}.{code}"


def _empty_bars() -> pd.DataFrame:
    frame = pd.DataFrame(columns=FUTU_OHLCV_COLUMNS)
    frame.index = pd.DatetimeIndex([], name="eob")
    return frame


def normalize_futu_kline(raw: pd.DataFrame | list[dict[str, Any]] | None) -> pd.DataFrame:
    """Normalize a Futu history-K-line response to QuantSpace OHLCV.

    Futu returns ``time_key``; the installed skill's JSON workflow calls the
    same field ``time``.  Both names are accepted so this helper can also
    normalize records produced by the skill CLI.
    """
    if raw is None:
        return _empty_bars()
    frame = raw.copy() if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
    if frame.empty:
        return _empty_bars()

    time_column = "time_key" if "time_key" in frame.columns else "time"
    if time_column not in frame.columns:
        raise ValueError("Futu K-line response is missing time_key")
    missing = [column for column in FUTU_OHLCV_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Futu K-line response is missing OHLCV columns: {missing}")

    timestamps = pd.to_datetime(frame[time_column], errors="coerce")
    if timestamps.isna().any():
        raise ValueError(f"Futu K-line response contains invalid {time_column} values")
    if getattr(timestamps.dt, "tz", None) is not None:
        timestamps = timestamps.dt.tz_localize(None)

    normalized = frame.assign(eob=timestamps)
    normalized = normalized.drop_duplicates(subset=["eob"], keep="last").sort_values("eob")
    for column in FUTU_OHLCV_COLUMNS:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if normalized[FUTU_OHLCV_COLUMNS].isna().any().any():
        raise ValueError("Futu K-line response contains non-numeric or missing OHLCV values")

    result = normalized.set_index("eob")[FUTU_OHLCV_COLUMNS].astype(float)
    result.index.name = "eob"
    return result


class FutuClient:
    """Fetch historical OHLCV bars from Futu OpenAPI.

    The ``futu`` SDK is imported lazily, so importing ``skills.ingest`` does
    not require an installed SDK or a running OpenD process.  Use the client
    as a context manager when fetching multiple symbols to reuse one quote
    connection.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        *,
        ai_type: int | None = 1,
        sdk_module: ModuleType | Any | None = None,
        context_factory: Callable[..., Any] | None = None,
    ):
        self.host = host or os.environ.get("FUTU_OPEND_HOST", "127.0.0.1")
        self.port = int(port or os.environ.get("FUTU_OPEND_PORT", "11111"))
        self.ai_type = ai_type
        self._sdk_module = sdk_module
        self._context_factory = context_factory
        self._context: Any | None = None

    def _sdk(self) -> ModuleType | Any:
        if self._sdk_module is None:
            try:
                import futu  # noqa: PLC0415
            except ImportError as exc:
                raise RuntimeError(
                    "futu-api is not installed. Run `uv sync --extra futu` "
                    "and ensure OpenD is running."
                ) from exc
            self._sdk_module = futu
        return self._sdk_module

    def _create_context(self) -> Any:
        if self._context_factory is not None:
            kwargs: dict[str, Any] = {"host": self.host, "port": self.port}
            if self.ai_type is not None:
                kwargs["ai_type"] = self.ai_type
            return self._context_factory(**kwargs)

        sdk = self._sdk()
        kwargs = {"host": self.host, "port": self.port}
        if self.ai_type is not None:
            kwargs["ai_type"] = self.ai_type
        try:
            return sdk.OpenQuoteContext(**kwargs)
        except TypeError as exc:
            if "ai_type" not in str(exc) or self.ai_type is None:
                raise
            raise RuntimeError(
                "Installed futu-api does not support ai_type; upgrade to "
                "futu-api>=10.4.6408."
            ) from exc

    def __enter__(self) -> FutuClient:
        if self._context is None:
            self._context = self._create_context()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the shared quote context, if one is open."""
        context, self._context = self._context, None
        if context is not None:
            context.close()

    def _borrow_context(self) -> tuple[Any, bool]:
        if self._context is not None:
            return self._context, False
        return self._create_context(), True

    @staticmethod
    def _enum_value(sdk: ModuleType | Any, enum_name: str, value: str, choices: dict[str, str]) -> Any:
        if value not in choices:
            raise ValueError(f"Unsupported {enum_name} value {value!r}; choose from {sorted(choices)}")
        return getattr(getattr(sdk, enum_name), choices[value])

    def fetch_history_kline(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        *,
        ktype: str = "1d",
        rehab: str = "none",
        session: str = "NONE",
        extended_time: bool = False,
        max_count: int = 1000,
        max_pages: int | None = None,
    ) -> pd.DataFrame:
        """Fetch and normalize one symbol's historical K-line series.

        ``max_count`` is the page size and is capped by Futu at 1000.  Futu's
        history quota is per symbol rather than per page; callers importing a
        universe should check :meth:`get_history_kline_quota` first.
        """
        if not isinstance(max_count, int) or not 1 <= max_count <= 1000:
            raise ValueError("max_count must be an integer between 1 and 1000")
        if max_pages is not None and (not isinstance(max_pages, int) or max_pages < 1):
            raise ValueError("max_pages must be None or a positive integer")

        sdk = self._sdk()
        futu_code = to_futu_symbol(symbol)
        kline_type = self._enum_value(sdk, "KLType", ktype, _KTYPE_NAMES)
        rehab_type = self._enum_value(sdk, "AuType", rehab.lower(), _REHAB_NAMES)
        session_type = self._enum_value(sdk, "Session", session.upper(), _SESSION_NAMES)
        context, owns_context = self._borrow_context()

        frames: list[pd.DataFrame] = []
        page_key = None
        page_count = 0
        try:
            while True:
                kwargs: dict[str, Any] = {
                    "code": futu_code,
                    "start": start,
                    "end": end,
                    "ktype": kline_type,
                    "autype": rehab_type,
                    "max_count": max_count,
                    "extended_time": extended_time,
                    "session": session_type,
                }
                if page_key is not None:
                    kwargs["page_req_key"] = page_key
                ret, data, next_page_key = context.request_history_kline(**kwargs)
                if ret != getattr(sdk, "RET_OK", 0):
                    raise FutuAPIError(ret, data)
                if data is not None and len(data):
                    frames.append(data if isinstance(data, pd.DataFrame) else pd.DataFrame(data))
                page_count += 1
                if next_page_key is None or (max_pages is not None and page_count >= max_pages):
                    break
                page_key = next_page_key
        finally:
            if owns_context:
                context.close()

        if not frames:
            return _empty_bars()
        return normalize_futu_kline(pd.concat(frames, ignore_index=True))

    def get_history_kline_quota(self, *, get_detail: bool = False) -> Any:
        """Return Futu's history-K-line quota using the shared context."""
        sdk = self._sdk()
        context, owns_context = self._borrow_context()
        try:
            ret, data = context.get_history_kl_quota(get_detail=get_detail)
            if ret != getattr(sdk, "RET_OK", 0):
                raise FutuAPIError(ret, data)
            return data
        finally:
            if owns_context:
                context.close()


__all__ = [
    "FUTU_OHLCV_COLUMNS",
    "FutuAPIError",
    "FutuClient",
    "normalize_futu_kline",
    "to_futu_symbol",
    "to_quantspace_futu_symbol",
]
