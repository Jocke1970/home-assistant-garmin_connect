"""Make the temporary Load Focus patch script's coordinator anchor deterministic."""

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

call_anchor = '''replace_once(
    coord,
    '            "hard_day_threshold": FITNESS_STRAIN_HARD_DAY_THRESHOLD,\\n',
'''
call_replacement = '''replace_first(
    coord,
    '            "hard_day_threshold": FITNESS_STRAIN_HARD_DAY_THRESHOLD,\\n',
'''
if text.count(call_anchor) != 1:
    raise SystemExit(
        f"Could not uniquely locate coordinator attrs call: {text.count(call_anchor)}"
    )
text = text.replace(call_anchor, call_replacement, 1)
path.write_text(text)
