"""pymysql stubs: only the storage layer imports this at module load time."""


class OperationalError(Exception):
    pass


class DictCursor:
    pass


def connect(**_kwargs):
    raise RuntimeError('offline tests must replace src.storage.register with FakeLedger')
