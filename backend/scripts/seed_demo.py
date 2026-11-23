from src.security import password_hash
from src.storage import register

STAFF = (
    ('field', '林晓 · 巡查员', 'analyst'),
    ('ops', '梁蔚 · 社区运营', 'admin'),
    ('desk', '方雪 · 社区联络', 'viewer'),
)

# Entries represent independent aggregate observation windows at each address.
DEMO = (
    ('QW-01', '银杏西门', '银杏里', '银杏里西门内侧 10 米', ((22, 12, 1), (38, 22, 3))),
    ('QW-02', '银杏南廊', '银杏里', '银杏里南廊快递架前', ((22, 14, 1), (36, 22, 2))),
    ('QW-03', '云岫车棚', '云岫苑', '云岫苑北侧车棚', ((35, 31, 4), (14, 13, 2))),
    ('QW-04', '云岫东口', '云岫苑', '云岫苑东门保安亭旁', ((32, 28, 3), (16, 15, 2))),
    ('QW-05', '溪径花厅', '溪径坊', '溪径坊花厅步道口', ((30, 29, 0), (22, 21, 0))),
    ('QW-06', '溪径北门', '溪径坊', '溪径坊北门便民亭后', ((29, 28, 0), (19, 18, 0))),
)


def seed():
    with register(write=True) as ledger:
        for username, display_name, role in STAFF:
            if not ledger.one('SELECT username FROM staff WHERE username=%s', (username,)):
                ledger.execute('INSERT INTO staff (username,display_name,role,password_hash) VALUES (%s,%s,%s,%s)',
                               (username, display_name, role, password_hash('qiwu-demo')))
        for code, name, sector, address, counts in DEMO:
            point = ledger.one('SELECT id,revision,pending_location FROM disposal_points WHERE code=%s', (code,))
            if not point:
                point_id = ledger.execute('INSERT INTO disposal_points (code,name,sector,location) VALUES (%s,%s,%s,%s)',
                                          (code, name, sector, address))
            elif point['revision'] == 1 and not point['pending_location']:
                point_id = point['id']
            else:
                continue
            for day, slot, (total, correct, overflow) in zip(('2026-11-10', '2026-11-11'),
                                                            ('morning', 'evening'), counts):
                key = (point_id, day, slot)
                if not ledger.one('''SELECT id FROM sampling_windows WHERE point_id=%s AND point_revision=1
                                   AND sample_day=%s AND slot=%s''', key):
                    ledger.execute('''INSERT INTO sampling_windows (point_id,point_revision,sample_day,slot,
                        total,correct,overflow,entered_by) VALUES (%s,1,%s,%s,%s,%s,%s,'field')''',
                        (*key, total, correct, overflow))
        return {table: ledger.one(f'SELECT COUNT(*) AS n FROM {table}')['n']
                for table in ('staff', 'disposal_points', 'sampling_windows', 'behavior_runs', 'outreach_tasks')}


if __name__ == '__main__':
    print(seed())
