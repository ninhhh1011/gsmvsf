"""Replay real FastAPI matching; policy lives only in production realtime code."""
from replay_realtime import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
