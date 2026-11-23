import logging
import time
from pathlib import Path

from src.runs import compute_next, worker_identity


def main():
    logging.basicConfig(level=logging.INFO)
    worker_id = worker_identity()
    pulse = Path('/runtime/sorting-pulse')
    pulse.unlink(missing_ok=True)
    while True:
        try:
            compute_next(worker_id)
            pulse.touch()
        except Exception:
            logging.exception('Cannot complete a fieldwork queue tick')
            time.sleep(2)
        time.sleep(1)


if __name__ == '__main__':
    main()
