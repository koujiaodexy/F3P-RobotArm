"""Requested pick-item keys, independent of the three physical drop boxes."""

PICK_ITEMS = ('red', 'yellow', 'green', 'apple', 'orange', 'banana')
PICK_LABELS = {'red': '红色积木', 'yellow': '黄色积木', 'green': '绿色积木',
               'apple': '苹果', 'orange': '橘子', 'banana': '香蕉'}
PICK_CLASS_IDS = {'red': 80, 'yellow': 81, 'green': 82,
                  'apple': 47, 'orange': 49, 'banana': 46}
CLASS_ID_TO_ITEM = {class_id: item for item, class_id in PICK_CLASS_IDS.items()}
MODEL_CLASS_IDS = (46, 47, 49, 80, 81, 82)
MODEL_NAMES = ('banana', 'apple', 'orange', 'red_cube', 'yellow_cube', 'green_cube')
BOX_KEYS = ('red', 'yellow', 'green')
DROP_BOX_FOR_ITEM = {'red': 'red', 'yellow': 'yellow', 'green': 'green',
                     'apple': 'red', 'orange': 'green', 'banana': 'yellow'}

assert set(PICK_ITEMS) == set(PICK_LABELS) == set(PICK_CLASS_IDS)
assert set(MODEL_CLASS_IDS) == set(CLASS_ID_TO_ITEM) and len(CLASS_ID_TO_ITEM) == 6
assert set(DROP_BOX_FOR_ITEM) == set(PICK_ITEMS) and set(DROP_BOX_FOR_ITEM.values()) == set(BOX_KEYS)
