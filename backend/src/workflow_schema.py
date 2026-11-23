from pathlib import Path

from src.storage import register


def initialize():
    """Install additive tables for fresh and existing field registers."""
    directory = Path(__file__).resolve().parents[1] / 'migrations'
    with register(write=True) as ledger:
        for migration in sorted(directory.glob('*.sql')):
            for statement in migration.read_text(encoding='utf-8').split(';'):
                if statement.strip():
                    ledger.execute(statement)
