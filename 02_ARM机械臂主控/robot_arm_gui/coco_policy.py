"""Six requested classes; global IDs remain unchanged."""
RETAINED_NAMES=('banana', 'apple', 'orange', 'red_cube', 'yellow_cube', 'green_cube')
RETAINED_IDS=(46, 47, 49, 80, 81, 82)
RETAINED_SET=frozenset(RETAINED_IDS)
assert len(RETAINED_NAMES)==len(RETAINED_IDS)==len(RETAINED_SET)==6
def selection_spec():
    return {'schema': 1, 'vocabulary': 'COCO80 contiguous IDs plus red/yellow/green cube IDs 80/81/82', 'class_count': 6, 'class_ids': [46, 47, 49, 80, 81, 82], 'names': ['banana', 'apple', 'orange', 'red_cube', 'yellow_cube', 'green_cube']}
