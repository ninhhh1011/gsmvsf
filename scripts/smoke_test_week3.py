"""Live Week 3 smoke verification. GraphHopper failure always fails this command."""
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_graphhopper import verify_graphhopper


async def run_smoke_test():
    return await verify_graphhopper()


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
