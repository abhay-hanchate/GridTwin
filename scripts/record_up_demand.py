"""Record the UP state demand feed (yesterday and today, every 3 minutes) into data/live/up_demand.parquet.

Usage:  python -m scripts.record_up_demand        (run at least once a day; each fetch holds all of yesterday)
"""
import json

from ml import up_demand


def main() -> None:
    up_demand.download_history()
    record = up_demand.record(up_demand.fetch_load_graph())
    energy = up_demand.daily_energy(record)
    print(json.dumps({"readings": int(len(record)), "complete_days": len(energy),
                      "last_day": str(energy.index[-1].date()) if len(energy) else None,
                      "last_day_mu": round(float(energy.iloc[-1]), 1) if len(energy) else None}, indent=2))


if __name__ == "__main__":
    main()
