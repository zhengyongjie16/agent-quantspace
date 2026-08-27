"""Import Futu historical K-lines into QuantSpace market Parquet files."""

from __future__ import annotations

import argparse
from pathlib import Path

from skills.ingest import FutuClient, to_quantspace_futu_symbol
from skills.store.data_manager import DataManager


def _storage_frequency(ktype: str, rehab: str) -> str:
    """Map Futu's bar and adjustment choices to a DataManager directory key."""
    return f"{ktype}_adj" if rehab != "none" else ktype


def import_futu_data(
    symbols: list[str],
    start_date: str,
    end_date: str,
    *,
    ktype: str = "1d",
    rehab: str = "none",
    session: str = "NONE",
    data_root: str | Path | None = None,
    max_count: int = 1000,
    max_pages: int | None = None,
    check_quota: bool = True,
) -> list[str]:
    """Fetch explicit symbols from Futu and save normalized OHLCV Parquet."""
    if not symbols:
        raise ValueError("symbols cannot be empty")

    data_manager = DataManager(data_root=str(data_root) if data_root is not None else None)
    frequency = _storage_frequency(ktype, rehab)
    imported: list[str] = []

    with FutuClient() as client:
        if check_quota:
            # Futu charges history quota per symbol, not per pagination request.
            print(f"Futu history K-line quota: {client.get_history_kline_quota()}")

        for symbol in symbols:
            qs_symbol = to_quantspace_futu_symbol(symbol)
            bars = client.fetch_history_kline(
                symbol,
                start=start_date,
                end=end_date,
                ktype=ktype,
                rehab=rehab,
                session=session,
                max_count=max_count,
                max_pages=max_pages,
            )
            if bars.empty:
                print(f"{qs_symbol}: no data")
                continue
            data_manager.save_symbol(
                qs_symbol,
                bars,
                frequency=frequency,
                source=f"futu_{rehab}",
            )
            imported.append(qs_symbol)
            print(
                f"{qs_symbol}: {len(bars)} rows "
                f"{bars.index.min()} -> {bars.index.max()}"
            )

    print(f"Imported {len(imported)} symbols from Futu into {frequency}")
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Futu historical K-lines")
    parser.add_argument(
        "--symbols",
        nargs="+",
        required=True,
        help="Explicit QuantSpace or Futu symbols, e.g. SHSE.600519 US.AAPL",
    )
    parser.add_argument("--start-date", required=True, help="Start date, YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date, YYYY-MM-DD")
    parser.add_argument(
        "--ktype",
        choices=["1m", "3m", "5m", "15m", "30m", "60m", "1d", "1w", "1M", "1Q", "1Y"],
        default="1d",
    )
    parser.add_argument("--rehab", choices=["none", "forward", "backward"], default="none")
    parser.add_argument("--session", choices=["NONE", "RTH", "ETH", "ALL"], default="NONE")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--max-count", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument(
        "--skip-quota-check",
        action="store_true",
        help="Skip the preflight get_history_kl_quota call",
    )
    args = parser.parse_args()
    import_futu_data(
        symbols=args.symbols,
        start_date=args.start_date,
        end_date=args.end_date,
        ktype=args.ktype,
        rehab=args.rehab,
        session=args.session,
        data_root=args.data_root,
        max_count=args.max_count,
        max_pages=args.max_pages,
        check_quota=not args.skip_quota_check,
    )


if __name__ == "__main__":
    main()
