from itertools import combinations
from math import dist
from statistics import mean, pstdev

FEATURES = ('accuracy', 'evening_share', 'overflow_rate')


def aggregate(windows):
    return {key: sum(window[key] for window in windows) for key in ('total', 'correct', 'overflow')}


def profile(point):
    windows = point['windows']
    totals = aggregate(windows)
    by_slot = {slot: aggregate([w for w in windows if w['slot'] == slot])
               for slot in sorted({w['slot'] for w in windows})}
    return {
        'point_id': point['id'], 'code': point['code'], 'name': point['name'],
        'location': point['location'], 'revision': point['revision'], 'sample_count': totals['total'],
        'accuracy': totals['correct'] / totals['total'],
        'evening_share': by_slot.get('evening', {}).get('total', 0) / totals['total'],
        'overflow_rate': totals['overflow'] / totals['total'], 'by_slot': by_slot,
    }


def intervention(member):
    if member['accuracy'] < .80:
        goal, count = 'accuracy', lambda cell: cell['total'] - cell['correct']
    elif member['overflow_rate'] >= .08:
        goal, count = 'overflow', lambda cell: cell['overflow']
    else:
        return None
    slot, counts = max(member['by_slot'].items(), key=lambda item: (count(item[1]), item[1]['total'], item[0]))
    return {'goal': goal, 'focus_slot': slot, **counts}


def group_label(totals):
    if totals['accuracy'] < .80:
        return '易混投点位'
    if totals['overflow_rate'] >= .08:
        return '满溢较多点位'
    if totals['evening_share'] >= .60:
        return '晚间集中点位'
    return '稳定投放点位'


def fit(points, requested):
    """Full average-linkage tree and a reproducible cut; keys break distance ties."""
    members = {p['id']: profile(p) for p in points}
    columns = [[member[feature] for member in members.values()] for feature in FEATURES]
    scales = [(mean(column), pstdev(column)) for column in columns]
    vectors = {
        key: tuple((row[feature] - center) / scale if scale else 0.0
                   for feature, (center, scale) in zip(FEATURES, scales))
        for key, row in members.items()
    }
    if len(set(vectors.values())) < requested:
        return None
    pairs = {frozenset((a, b)): dist(vectors[a], vectors[b]) for a, b in combinations(vectors, 2)}
    active = sorted((key,) for key in members)
    cut = None
    merges = []
    while len(active) > 1:
        if len(active) == requested:
            cut = active.copy()
        distance, left, right = min(
            (mean(pairs[frozenset((a, b))] for a in x for b in y), x, y)
            for x, y in combinations(active, 2)
        )
        merged = tuple(sorted((*left, *right)))
        merges.append({'left': [members[x]['code'] for x in left],
                       'right': [members[x]['code'] for x in right], 'distance': round(distance, 6)})
        active.remove(left)
        active.remove(right)
        active = sorted([*active, merged])
    groups = []
    for number, keys in enumerate(cut, 1):
        rows = [members[key] for key in keys]
        centroid = {feature: mean(row[feature] for row in rows) for feature in FEATURES}
        groups.append({'number': number, 'label': group_label(centroid), 'summary': centroid,
                       'samples': sum(row['sample_count'] for row in rows),
                       'members': [dict(row, action=intervention(row)) for row in rows]})
    return {'method': 'average_linkage_zscore_euclidean', 'groups': groups, 'merges': merges}
