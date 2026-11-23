import logging
import time
from pathlib import Path

from src.runs import compute_next


def main():
    logging.basicConfig(level=logging.INFO)
    pulse = Path('/runtime/sorting-pulse')
    pulse.unlink(missing_ok=True)
    while True:
        try:
            compute_next()
            pulse.touch()
        except Exception:
            logging.exception('Cannot complete a fieldwork queue tick')
            time.sleep(2)
        time.sleep(1)


if __name__ == '__main__':
    main()
