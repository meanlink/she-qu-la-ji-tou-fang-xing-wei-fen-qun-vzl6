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


def prepare(points, requested):
    """Profile, standardise and build the immutable pairwise distance table."""
    # String keys survive a JSON checkpoint round-trip (MySQL JSON object keys are strings).
    members = {str(p['id']): profile(p) for p in points}
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
    # JSON-safe: keys become sorted lists, values kept as plain floats.
    return {'members': members,
            'pairs': [[sorted(key), value] for key, value in pairs.items()]}


def merge_tree(prepared, requested, checkpoint=None, on_step=None):
    """Average-linkage agglomeration; resumes from the persisted active clusters."""
    members = prepared['members']
    pairs = {frozenset(key): value for key, value in prepared['pairs']}
    if checkpoint:
        active = [tuple(str(key) for key in cluster) for cluster in checkpoint['active']]
        merges = list(checkpoint['merges'])
        cut = [tuple(str(key) for key in cluster) for cluster in checkpoint['cut']] \
            if checkpoint.get('cut') else None
        start_step = checkpoint['steps']
    else:
        active = sorted((key,) for key in members)
        merges, cut, start_step = [], None, 0
    step = start_step
    while len(active) > 1:
        if len(active) == requested:
            cut = [cluster for cluster in active]
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
        step += 1
        if on_step:
            # Persistable state after each merge so an interrupted run continues in place.
            state = {'phase': 'merge', 'steps': step, 'total_steps': len(members) - 1,
                     'active': [list(cluster) for cluster in active],
                     'cut': [list(cluster) for cluster in cut] if cut else None,
                     'merges': merges, 'prepared': prepared}
            on_step(state)
    if cut is None:
        raise ArithmeticError('层次聚类无法切出所选群数')
    groups = []
    for number, keys in enumerate(cut, 1):
        rows = [members[key] for key in keys]
        centroid = {feature: mean(row[feature] for row in rows) for feature in FEATURES}
        groups.append({'number': number, 'label': group_label(centroid), 'summary': centroid,
                       'samples': sum(row['sample_count'] for row in rows),
                       'members': [dict(row, action=intervention(row)) for row in rows]})
    return {'method': 'average_linkage_zscore_euclidean', 'groups': groups, 'merges': merges}


def fit(points, requested, checkpoint=None, on_step=None):
    """Full average-linkage tree and a reproducible cut; keys break distance ties."""
    if checkpoint and checkpoint.get('phase') == 'merge' and 'prepared' in checkpoint:
        prepared = checkpoint['prepared']
    else:
        prepared = prepare(points, requested)
        if prepared is None:
            return None
    return merge_tree(prepared, requested, checkpoint, on_step)
