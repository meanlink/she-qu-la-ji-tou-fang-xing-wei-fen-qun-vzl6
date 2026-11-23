import json
import os
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

JSON_COLUMNS = {'reasons', 'input_snapshot', 'result', 'baseline', 'facts', 'checkpoint'}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class Register:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, args=()):
        self.cursor.execute(sql, args)
        return self.cursor.lastrowid

    def rows(self, sql, args=()):
        self.execute(sql, args)
        rows = self.cursor.fetchall()
        for row in rows:
            for column in JSON_COLUMNS.intersection(row):
                if row[column] is not None:
                    row[column] = json.loads(row[column])
        return rows

    def one(self, sql, args=()):
        return next(iter(self.rows(sql, args)), None)

    def audit(self, actor, event, object_id, facts):
        self.execute('INSERT INTO field_audit (actor,event,object_id,facts) VALUES (%s,%s,%s,%s)',
                     (actor, event, object_id, encode(facts)))


@contextmanager
def register(write=False):
    connection = pymysql.connect(
        host=os.getenv('MYSQL_HOST', '127.0.0.1'), port=int(os.getenv('MYSQL_PORT', '3306')),
        user=os.getenv('MYSQL_USER', 'sorting_ops'), password=os.environ['MYSQL_PASSWORD'],
        database=os.getenv('MYSQL_DATABASE', 'sorting_field'), charset='utf8mb4', cursorclass=DictCursor,
        connect_timeout=3, read_timeout=5, write_timeout=5,
    )
    try:
        with connection.cursor() as cursor:
            ledger = Register(cursor)
            if write:
                # Serialize low-volume business writes so migration, publication and sampling agree.
                ledger.one('SELECT id FROM field_register WHERE id=1 FOR UPDATE')
            yield ledger
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
