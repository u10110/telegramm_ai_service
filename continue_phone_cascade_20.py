from __future__ import annotations
import argparse, asyncio, os
from pathlib import Path
from phone_checker_rotation import run_rotation

DEFAULT_PATH = Path(os.getenv('PHONE_CHECKER_CSV', '/root/.hermes/profiles/aibomber/cache/documents/telegram_numbers_1000_no_800_with_status_checked_corrected.csv'))
DEFAULT_STATE = Path(os.getenv('PHONE_CHECKER_STATE', str(DEFAULT_PATH.with_suffix('.rotation_state.json'))))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Telegram phone checker with rotating accounts')
    parser.add_argument('--csv', type=Path, default=DEFAULT_PATH)
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--limit', type=int, default=None)
    args = parser.parse_args()
    print(asyncio.run(run_rotation(args.csv, args.state, args.limit)))
