"""Make temporary Load Focus patch-script anchors deterministic."""

from pathlib import Path

path = Path(".github/scripts/apply_fitness_load_focus.py")
text = path.read_text()

helper_anchor = '''def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: {label}: expected 1 match, found {count}")
    path.write_text(text.replace(old, new, 1))
'''
helper_replacement = helper_anchor + '''

def replace_first(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count < 1:
        raise SystemExit(f"{path}: {label}: expected at least 1 match, found {count}")
    path.write_text(text.replace(old, new, 1))
'''
if text.count(helper_anchor) != 1:
    raise SystemExit("Could not locate replace_once helper")
text = text.replace(helper_anchor, helper_replacement, 1)

coordinator_anchor = '''replace_once(
    coord,
    '            "hard_day_threshold": FITNESS_STRAIN_HARD_DAY_THRESHOLD,\\n',
'''
coordinator_replacement = '''replace_first(
    coord,
    '            "hard_day_threshold": FITNESS_STRAIN_HARD_DAY_THRESHOLD,\\n',
'''
if text.count(coordinator_anchor) != 1:
    raise SystemExit(
        "Could not uniquely locate coordinator attrs call: "
        f"{text.count(coordinator_anchor)}"
    )
text = text.replace(coordinator_anchor, coordinator_replacement, 1)

runtime_anchor = (
    "replace_once(\n"
    "    runtime,\n"
    "    '''        \"training_series\": {\\n"
    "            \"trimp\": {\\n"
)
runtime_replacement = runtime_anchor.replace("replace_once(", "replace_first(", 1)
if text.count(runtime_anchor) != 1:
    raise SystemExit(
        "Could not uniquely locate runtime training-series patch call: "
        f"{text.count(runtime_anchor)}"
    )
text = text.replace(runtime_anchor, runtime_replacement, 1)

path.write_text(text)
