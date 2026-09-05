from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: {label}: expected 1 match, found {count}")
    path.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# fitness_probe.py
# ---------------------------------------------------------------------------
probe = Path("custom_components/garmin_connect/fitness_probe.py")
replace_once(
    probe,
    "from ha_garmin.exceptions import GarminAuthError, GarminConnectError\n",
    "from ha_garmin.exceptions import GarminAuthError, GarminConnectError\n\n"
    "from .const import (\n"
    "    FITNESS_LOAD_FOCUS_ALGORITHM_VERSION,\n"
    "    FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD,\n"
    "    FITNESS_LOAD_FOCUS_SOURCE,\n"
    ")\n"
    "from .fitness_load_focus import build_load_focus_day\n",
    "load-focus imports",
)

load_focus_builder = '''\n\ndef _build_load_focus_series(\n    by_day: dict[date, list[dict[str, Any]]],\n    start_date: date,\n    end_date: date,\n) -> dict[str, Any]:\n    """Build a strict daily Training Effect mix without load weighting."""\n    points: list[dict[str, Any]] = []\n    covered_activities = 0\n    missing_activities = 0\n    complete_activity_days = 0\n    incomplete_activity_days: list[date] = []\n\n    current = start_date\n    while current <= end_date:\n        items = by_day.get(current, [])\n        day = build_load_focus_day(\n            (\n                (\n                    _number(item.get("aerobicTrainingEffect")),\n                    _number(item.get("anaerobicTrainingEffect")),\n                )\n                for item in items\n            ),\n            high_aerobic_threshold=FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD,\n        )\n        covered_activities += int(day["covered_activities"])\n        missing_activities += int(day["missing_activities"])\n        if items:\n            if day["complete"]:\n                complete_activity_days += 1\n            else:\n                incomplete_activity_days.append(current)\n\n        points.append(\n            {\n                "date": current.isoformat(),\n                "complete": day["complete"],\n                "activity_count": day["activity_count"],\n                "covered_activities": day["covered_activities"],\n                "missing_activities": day["missing_activities"],\n                "low_aerobic": day["low_aerobic"],\n                "high_aerobic": day["high_aerobic"],\n                "anaerobic": day["anaerobic"],\n                "known_low_aerobic": day["known_low_aerobic"],\n                "known_high_aerobic": day["known_high_aerobic"],\n                "known_anaerobic": day["known_anaerobic"],\n            }\n        )\n        current += timedelta(days=1)\n\n    total_activities = covered_activities + missing_activities\n    return {\n        "algorithm_version": FITNESS_LOAD_FOCUS_ALGORITHM_VERSION,\n        "source": FITNESS_LOAD_FOCUS_SOURCE,\n        "high_aerobic_threshold": FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD,\n        "complete": missing_activities == 0,\n        "total_activities": total_activities,\n        "covered_activities": covered_activities,\n        "missing_activities": missing_activities,\n        "activity_coverage_percent": (\n            round(covered_activities / total_activities * 100.0, 1)\n            if total_activities\n            else 100.0\n        ),\n        "complete_activity_days": complete_activity_days,\n        "incomplete_activity_days": len(incomplete_activity_days),\n        "first_incomplete_dates": [\n            day.isoformat() for day in sorted(incomplete_activity_days, reverse=True)[:10]\n        ],\n        "points": points,\n    }\n'''
replace_once(
    probe,
    "\n\nasync def build_fitness_probe(\n",
    load_focus_builder + "\n\nasync def build_fitness_probe(\n",
    "load-focus daily series helper",
)
replace_once(
    probe,
    "    activity_days = len(by_day)\n",
    "    load_focus = _build_load_focus_series(by_day, start_date, end_date)\n\n"
    "    activity_days = len(by_day)\n",
    "load-focus series build",
)
replace_once(probe, '        "probe_version": 4,\n', '        "probe_version": 5,\n', "probe version")
replace_once(
    probe,
    '        "comparison": comparison,\n',
    '        "comparison": comparison,\n        "load_focus": load_focus,\n',
    "probe load-focus output",
)

# ---------------------------------------------------------------------------
# fitness_coordinator.py
# ---------------------------------------------------------------------------
coord = Path("custom_components/garmin_connect/fitness_coordinator.py")
replace_once(
    coord,
    "    FITNESS_HISTORY_DAYS,\n    FITNESS_RAMP_PERIOD_DAYS,\n",
    "    FITNESS_HISTORY_DAYS,\n"
    "    FITNESS_LOAD_FOCUS_ALGORITHM_VERSION,\n"
    "    FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD,\n"
    "    FITNESS_LOAD_FOCUS_SOURCE,\n"
    "    FITNESS_RAMP_PERIOD_DAYS,\n",
    "coordinator load-focus constants",
)

merge_helper = '''\n\ndef _merge_load_focus_metrics(\n    points: list[dict[str, Any]],\n    load_focus: Any,\n) -> list[dict[str, Any]]:\n    """Merge date-aligned daily Training Effect mix into canonical history."""\n    raw_points = load_focus.get("points") if isinstance(load_focus, dict) else None\n    focus_by_date: dict[str, dict[str, Any]] = {}\n    if isinstance(raw_points, list):\n        for raw in raw_points:\n            if not isinstance(raw, dict):\n                continue\n            raw_date = raw.get("date")\n            if isinstance(raw_date, str):\n                focus_by_date[raw_date] = raw\n\n    merged: list[dict[str, Any]] = []\n    for point in points:\n        item = dict(point)\n        point_date = item.get("date")\n        focus = focus_by_date.get(point_date) if isinstance(point_date, str) else None\n        complete = bool(focus and focus.get("complete") is True)\n        item["load_focus_complete"] = complete\n        item["load_focus_activity_count"] = (\n            int(focus.get("activity_count") or 0) if focus else 0\n        )\n        item["load_focus_covered_activities"] = (\n            int(focus.get("covered_activities") or 0) if focus else 0\n        )\n        for target, source in (\n            ("load_focus_low_aerobic", "low_aerobic"),\n            ("load_focus_high_aerobic", "high_aerobic"),\n            ("load_focus_anaerobic", "anaerobic"),\n        ):\n            value = focus.get(source) if focus else None\n            item[target] = (\n                float(value)\n                if not isinstance(value, bool) and isinstance(value, int | float)\n                else None\n            )\n        merged.append(item)\n    return merged\n'''
replace_once(
    coord,
    "\n\nclass FitnessCoordinator(DataUpdateCoordinator[dict[str, Any]]):\n",
    merge_helper + "\n\nclass FitnessCoordinator(DataUpdateCoordinator[dict[str, Any]]):\n",
    "coordinator load-focus merge helper",
)
replace_once(
    coord,
    "            enriched_points = (\n"
    "                _augment_training_metrics(\n"
    "                    all_points,\n"
    "                    personal_trimp_max=personal_trimp_max,\n"
    "                )\n"
    "                if all_points\n"
    "                else []\n"
    "            )\n",
    "            enriched_points = (\n"
    "                _augment_training_metrics(\n"
    "                    all_points,\n"
    "                    personal_trimp_max=personal_trimp_max,\n"
    "                )\n"
    "                if all_points\n"
    "                else []\n"
    "            )\n"
    "            enriched_points = _merge_load_focus_metrics(\n"
    "                enriched_points,\n"
    "                effective_probe.get(\"load_focus\"),\n"
    "            )\n",
    "coordinator enrich load-focus",
)
replace_once(
    coord,
    "        latest = visible_points[-1] if visible_points else {}\n        ready = (\n",
    "        latest = visible_points[-1] if visible_points else {}\n"
    "        load_focus_total_activities = sum(\n"
    "            int(point.get(\"load_focus_activity_count\") or 0)\n"
    "            for point in visible_points\n"
    "            if isinstance(point, dict)\n"
    "        )\n"
    "        load_focus_covered_activities = sum(\n"
    "            int(point.get(\"load_focus_covered_activities\") or 0)\n"
    "            for point in visible_points\n"
    "            if isinstance(point, dict)\n"
    "        )\n"
    "        load_focus_history_complete = bool(visible_points) and all(\n"
    "            point.get(\"load_focus_complete\") is True\n"
    "            for point in visible_points\n"
    "            if isinstance(point, dict)\n"
    "        )\n"
    "        load_focus_incomplete_dates = [\n"
    "            str(point.get(\"date\"))\n"
    "            for point in visible_points\n"
    "            if isinstance(point, dict)\n"
    "            and point.get(\"load_focus_complete\") is not True\n"
    "            and isinstance(point.get(\"date\"), str)\n"
    "        ]\n"
    "        load_focus_coverage_percent = (\n"
    "            round(\n"
    "                load_focus_covered_activities\n"
    "                / load_focus_total_activities\n"
    "                * 100.0,\n"
    "                1,\n"
    "            )\n"
    "            if load_focus_total_activities\n"
    "            else 100.0\n"
    "        )\n"
    "        ready = (\n",
    "coordinator visible load-focus provenance",
)
replace_once(
    coord,
    '            "strain": latest.get("strain") if ready else None,\n',
    '            "strain": latest.get("strain") if ready else None,\n'
    '            "load_focus_low_aerobic": (\n'
    '                latest.get("load_focus_low_aerobic") if ready else None\n'
    '            ),\n'
    '            "load_focus_high_aerobic": (\n'
    '                latest.get("load_focus_high_aerobic") if ready else None\n'
    '            ),\n'
    '            "load_focus_anaerobic": (\n'
    '                latest.get("load_focus_anaerobic") if ready else None\n'
    '            ),\n',
    "coordinator current load-focus values",
)
replace_once(
    coord,
    '            "hard_day_threshold": FITNESS_STRAIN_HARD_DAY_THRESHOLD,\n',
    '            "hard_day_threshold": FITNESS_STRAIN_HARD_DAY_THRESHOLD,\n'
    '            "load_focus_algorithm_version": FITNESS_LOAD_FOCUS_ALGORITHM_VERSION,\n'
    '            "load_focus_source": FITNESS_LOAD_FOCUS_SOURCE,\n'
    '            "load_focus_high_aerobic_threshold": (\n'
    '                FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD\n'
    '            ),\n'
    '            "load_focus_history_complete": (\n'
    '                load_focus_history_complete if ready else False\n'
    '            ),\n'
    '            "load_focus_activity_coverage_percent": (\n'
    '                load_focus_coverage_percent if ready else None\n'
    '            ),\n'
    '            "load_focus_total_activities": (\n'
    '                load_focus_total_activities if ready else None\n'
    '            ),\n'
    '            "load_focus_covered_activities": (\n'
    '                load_focus_covered_activities if ready else None\n'
    '            ),\n'
    '            "load_focus_incomplete_dates": (\n'
    '                load_focus_incomplete_dates if ready else []\n'
    '            ),\n',
    "coordinator load-focus attrs",
)
replace_once(
    coord,
    '            "strain": None,\n            "history": [],\n',
    '            "strain": None,\n'
    '            "load_focus_low_aerobic": None,\n'
    '            "load_focus_high_aerobic": None,\n'
    '            "load_focus_anaerobic": None,\n'
    '            "history": [],\n',
    "empty load-focus values",
)
replace_once(
    coord,
    '            "hard_day_threshold": FITNESS_STRAIN_HARD_DAY_THRESHOLD,\n            **strain_calibration,\n',
    '            "hard_day_threshold": FITNESS_STRAIN_HARD_DAY_THRESHOLD,\n'
    '            "load_focus_algorithm_version": FITNESS_LOAD_FOCUS_ALGORITHM_VERSION,\n'
    '            "load_focus_source": FITNESS_LOAD_FOCUS_SOURCE,\n'
    '            "load_focus_high_aerobic_threshold": (\n'
    '                FITNESS_LOAD_FOCUS_HIGH_AEROBIC_THRESHOLD\n'
    '            ),\n'
    '            "load_focus_history_complete": False,\n'
    '            "load_focus_activity_coverage_percent": None,\n'
    '            "load_focus_total_activities": None,\n'
    '            "load_focus_covered_activities": None,\n'
    '            "load_focus_incomplete_dates": [],\n'
    '            **strain_calibration,\n',
    "empty load-focus attrs",
)

# ---------------------------------------------------------------------------
# fitness_sensor.py
# ---------------------------------------------------------------------------
sensor = Path("custom_components/garmin_connect/fitness_sensor.py")
replace_once(
    sensor,
    'FITNESS_UNIT = "TRIMP"\n',
    'FITNESS_UNIT = "TRIMP"\nFITNESS_TRAINING_EFFECT_UNIT = "TE"\n',
    "TE unit",
)
replace_once(
    sensor,
    '''    GarminFitnessSensorEntityDescription(\n        key="strain",\n        name="Strain",\n        state_class=SensorStateClass.MEASUREMENT,\n        suggested_display_precision=1,\n    ),\n)\n''',
    '''    GarminFitnessSensorEntityDescription(\n        key="strain",\n        name="Strain",\n        state_class=SensorStateClass.MEASUREMENT,\n        suggested_display_precision=1,\n    ),\n    GarminFitnessSensorEntityDescription(\n        key="load_focus_low_aerobic",\n        name="Load focus low aerobic",\n        state_class=SensorStateClass.MEASUREMENT,\n        native_unit_of_measurement=FITNESS_TRAINING_EFFECT_UNIT,\n        suggested_display_precision=1,\n    ),\n    GarminFitnessSensorEntityDescription(\n        key="load_focus_high_aerobic",\n        name="Load focus high aerobic",\n        state_class=SensorStateClass.MEASUREMENT,\n        native_unit_of_measurement=FITNESS_TRAINING_EFFECT_UNIT,\n        suggested_display_precision=1,\n    ),\n    GarminFitnessSensorEntityDescription(\n        key="load_focus_anaerobic",\n        name="Load focus anaerobic",\n        state_class=SensorStateClass.MEASUREMENT,\n        native_unit_of_measurement=FITNESS_TRAINING_EFFECT_UNIT,\n        suggested_display_precision=1,\n    ),\n)\n''',
    "load-focus sensor descriptions",
)
replace_once(
    sensor,
    '''            "hard_day_threshold": data.get("hard_day_threshold"),\n            "personal_trimp_max": data.get("personal_trimp_max"),\n''',
    '''            "hard_day_threshold": data.get("hard_day_threshold"),\n            "load_focus_algorithm_version": data.get(\n                "load_focus_algorithm_version"\n            ),\n            "load_focus_source": data.get("load_focus_source"),\n            "load_focus_high_aerobic_threshold": data.get(\n                "load_focus_high_aerobic_threshold"\n            ),\n            "load_focus_history_complete": data.get(\n                "load_focus_history_complete", False\n            ),\n            "load_focus_activity_coverage_percent": data.get(\n                "load_focus_activity_coverage_percent"\n            ),\n            "load_focus_total_activities": data.get(\n                "load_focus_total_activities"\n            ),\n            "load_focus_covered_activities": data.get(\n                "load_focus_covered_activities"\n            ),\n            "load_focus_incomplete_dates": data.get(\n                "load_focus_incomplete_dates"\n            )\n            or [],\n            "personal_trimp_max": data.get("personal_trimp_max"),\n''',
    "load-focus sensor attrs",
)

# ---------------------------------------------------------------------------
# tests/test_fitness_load_focus.py
# ---------------------------------------------------------------------------
Path("tests/test_fitness_load_focus.py").write_text('''"""Tests for Training Effect-derived Garmin Fitness load focus."""\n\nfrom custom_components.garmin_connect.fitness_load_focus import (\n    build_load_focus_day,\n    compute_load_focus_contribution,\n)\n\n\ndef test_load_focus_contribution_splits_aerobic_at_threshold() -> None:\n    low = compute_load_focus_contribution(2.5, 0.4)\n    high = compute_load_focus_contribution(3.2, 1.8)\n\n    assert low == {\n        "low_aerobic": 2.5,\n        "high_aerobic": 0.0,\n        "anaerobic": 0.4,\n    }\n    assert high == {\n        "low_aerobic": 0.0,\n        "high_aerobic": 3.2,\n        "anaerobic": 1.8,\n    }\n\n\ndef test_load_focus_day_preserves_missing_training_effect() -> None:\n    result = build_load_focus_day([(2.5, 0.2), (4.0, None)])\n\n    assert result["complete"] is False\n    assert result["activity_count"] == 2\n    assert result["covered_activities"] == 1\n    assert result["missing_activities"] == 1\n    assert result["low_aerobic"] is None\n    assert result["high_aerobic"] is None\n    assert result["anaerobic"] is None\n    assert result["known_low_aerobic"] == 2.5\n    assert result["known_high_aerobic"] == 0.0\n    assert result["known_anaerobic"] == 0.2\n\n\ndef test_load_focus_rest_day_is_complete_zero() -> None:\n    result = build_load_focus_day([])\n\n    assert result["complete"] is True\n    assert result["activity_count"] == 0\n    assert result["low_aerobic"] == 0.0\n    assert result["high_aerobic"] == 0.0\n    assert result["anaerobic"] == 0.0\n''')

# ---------------------------------------------------------------------------
# tests/test_fitness_probe.py
# ---------------------------------------------------------------------------
probe_test = Path("tests/test_fitness_probe.py")
replace_once(
    probe_test,
    '    assert result["probe_version"] == 4\n',
    '    assert result["probe_version"] == 5\n',
    "probe version test",
)
append_probe_test = '''\n\n@pytest.mark.asyncio\nasync def test_probe_builds_strict_training_effect_load_focus() -> None:\n    client = AsyncMock()\n    client.get_activities.return_value = [\n        {\n            **_activity(3, "2026-09-03"),\n            "aerobicTrainingEffect": 1.5,\n        },\n        {\n            **_activity(2, "2026-09-02"),\n            "aerobicTrainingEffect": 4.0,\n            "anaerobicTrainingEffect": 3.0,\n        },\n        {\n            **_activity(1, "2026-09-01"),\n            "aerobicTrainingEffect": 2.5,\n            "anaerobicTrainingEffect": 0.2,\n        },\n    ]\n    _configure_resting_hr(\n        client,\n        {"2026-09-01": 55, "2026-09-02": 55, "2026-09-03": 55},\n    )\n\n    result = await build_fitness_probe(\n        client,\n        days=4,\n        end_date=date(2026, 9, 4),\n    )\n\n    focus = result["load_focus"]\n    assert focus["algorithm_version"] == 1\n    assert focus["source"] == "garmin_training_effect"\n    assert focus["high_aerobic_threshold"] == 3.0\n    assert focus["total_activities"] == 3\n    assert focus["covered_activities"] == 2\n    assert focus["missing_activities"] == 1\n    assert focus["activity_coverage_percent"] == pytest.approx(66.7)\n    assert focus["first_incomplete_dates"] == ["2026-09-03"]\n\n    by_date = {point["date"]: point for point in focus["points"]}\n    assert by_date["2026-09-01"]["low_aerobic"] == 2.5\n    assert by_date["2026-09-01"]["anaerobic"] == 0.2\n    assert by_date["2026-09-02"]["high_aerobic"] == 4.0\n    assert by_date["2026-09-02"]["anaerobic"] == 3.0\n    assert by_date["2026-09-03"]["complete"] is False\n    assert by_date["2026-09-03"]["low_aerobic"] is None\n    assert by_date["2026-09-04"]["complete"] is True\n    assert by_date["2026-09-04"]["low_aerobic"] == 0.0\n'''
with probe_test.open("a") as handle:
    handle.write(append_probe_test)

# ---------------------------------------------------------------------------
# tests/test_fitness_runtime.py
# ---------------------------------------------------------------------------
runtime = Path("tests/test_fitness_runtime.py")
load_focus_fixture = '''\n\ndef _load_focus_points(days: int = 180) -> list[dict]:\n    start = date(2026, 9, 4) - timedelta(days=days - 1)\n    points = []\n    for offset in range(days):\n        point_date = start + timedelta(days=offset)\n        points.append(\n            {\n                "date": point_date.isoformat(),\n                "complete": True,\n                "activity_count": 0,\n                "covered_activities": 0,\n                "missing_activities": 0,\n                "low_aerobic": 0.0,\n                "high_aerobic": 0.0,\n                "anaerobic": 0.0,\n            }\n        )\n    points[-1].update(\n        {\n            "activity_count": 1,\n            "covered_activities": 1,\n            "low_aerobic": 2.2,\n            "high_aerobic": 0.0,\n            "anaerobic": 0.3,\n        }\n    )\n    return points\n'''
replace_once(
    runtime,
    "\n\n@pytest.fixture(autouse=True)\ndef mock_strain_calibration():\n",
    load_focus_fixture + "\n\n@pytest.fixture(autouse=True)\ndef mock_strain_calibration():\n",
    "runtime load-focus fixture",
)
replace_once(
    runtime,
    '''        "training_series": {\n            "trimp": {\n                "ready": True,\n                "blocker_dates": [],\n                "points": points,\n                "latest": points[-1],\n            }\n        },\n    }\n\n    with patch(\n''',
    '''        "training_series": {\n            "trimp": {\n                "ready": True,\n                "blocker_dates": [],\n                "points": points,\n                "latest": points[-1],\n            }\n        },\n        "load_focus": {"points": _load_focus_points()},\n    }\n\n    with patch(\n''',
    "runtime main load-focus probe",
)
replace_once(
    runtime,
    '    assert data["strain"] == 1.27\n    assert data["load_source"] == "trimp"\n',
    '    assert data["strain"] == 1.27\n'
    '    assert data["load_focus_low_aerobic"] == 2.2\n'
    '    assert data["load_focus_high_aerobic"] == 0.0\n'
    '    assert data["load_focus_anaerobic"] == 0.3\n'
    '    assert data["load_focus_history_complete"] is True\n'
    '    assert data["load_focus_activity_coverage_percent"] == 100.0\n'
    '    assert data["load_focus_total_activities"] == 1\n'
    '    assert data["load_focus_covered_activities"] == 1\n'
    '    assert data["load_focus_incomplete_dates"] == []\n'
    '    assert data["load_source"] == "trimp"\n',
    "runtime load-focus assertions",
)
replace_once(
    runtime,
    '        "strain": 1.08,\n        "history": [{"date": "2026-09-03", "daily_load": 6.708}],\n',
    '        "strain": 1.08,\n'
    '        "load_focus_low_aerobic": 2.4,\n'
    '        "load_focus_high_aerobic": 0.0,\n'
    '        "load_focus_anaerobic": 0.5,\n'
    '        "history": [{"date": "2026-09-03", "daily_load": 6.708}],\n',
    "sensor data load-focus values",
)
replace_once(
    runtime,
    '        "hard_day_threshold": 14.0,\n        "personal_trimp_max": 120.0,\n',
    '        "hard_day_threshold": 14.0,\n'
    '        "load_focus_algorithm_version": 1,\n'
    '        "load_focus_source": "garmin_training_effect",\n'
    '        "load_focus_high_aerobic_threshold": 3.0,\n'
    '        "load_focus_history_complete": True,\n'
    '        "load_focus_activity_coverage_percent": 100.0,\n'
    '        "load_focus_total_activities": 12,\n'
    '        "load_focus_covered_activities": 12,\n'
    '        "load_focus_incomplete_dates": [],\n'
    '        "personal_trimp_max": 120.0,\n',
    "sensor data load-focus attrs",
)
replace_once(
    runtime,
    '    assert sensor.extra_state_attributes["hard_day_threshold"] == 14.0\n',
    '    assert sensor.extra_state_attributes["hard_day_threshold"] == 14.0\n'
    '    assert sensor.extra_state_attributes["load_focus_algorithm_version"] == 1\n'
    '    assert sensor.extra_state_attributes["load_focus_source"] == "garmin_training_effect"\n'
    '    assert sensor.extra_state_attributes["load_focus_high_aerobic_threshold"] == 3.0\n'
    '    assert sensor.extra_state_attributes["load_focus_history_complete"] is True\n'
    '    assert sensor.extra_state_attributes["load_focus_activity_coverage_percent"] == 100.0\n',
    "sensor attr load-focus assertions",
)
replace_once(
    runtime,
    '''    strain_sensor = GarminFitnessSensor(\n        coordinator,\n        next(item for item in FITNESS_SENSOR_DESCRIPTIONS if item.key == "strain"),\n        "entry_1",\n    )\n    assert acwr_sensor.native_value == 0.82\n''',
    '''    strain_sensor = GarminFitnessSensor(\n        coordinator,\n        next(item for item in FITNESS_SENSOR_DESCRIPTIONS if item.key == "strain"),\n        "entry_1",\n    )\n    low_focus_sensor = GarminFitnessSensor(\n        coordinator,\n        next(\n            item\n            for item in FITNESS_SENSOR_DESCRIPTIONS\n            if item.key == "load_focus_low_aerobic"\n        ),\n        "entry_1",\n    )\n    assert acwr_sensor.native_value == 0.82\n''',
    "load-focus sensor instance",
)
replace_once(
    runtime,
    '    assert strain_sensor.native_value == 1.08\n    assert strain_sensor.native_unit_of_measurement is None\n',
    '    assert strain_sensor.native_value == 1.08\n'
    '    assert strain_sensor.native_unit_of_measurement is None\n'
    '    assert low_focus_sensor.native_value == 2.4\n'
    '    assert low_focus_sensor.native_unit_of_measurement == "TE"\n',
    "load-focus sensor unit assertions",
)
replace_once(runtime, "    assert len(entities) == 7\n", "    assert len(entities) == 10\n", "sensor count")
replace_once(
    runtime,
    '        "entry_1_fitness_strain",\n    }\n',
    '        "entry_1_fitness_strain",\n'
    '        "entry_1_fitness_load_focus_low_aerobic",\n'
    '        "entry_1_fitness_load_focus_high_aerobic",\n'
    '        "entry_1_fitness_load_focus_anaerobic",\n'
    '    }\n',
    "sensor unique ids",
)

# ---------------------------------------------------------------------------
# tests/test_fitness_statistics.py
# ---------------------------------------------------------------------------
stats = Path("tests/test_fitness_statistics.py")
for date_value, low, high, anaerobic in (
    ("2026-09-02", 3.0, 4.0, 1.0),
    ("2026-09-03", 2.0, 5.0, 2.0),
    ("2026-09-04", 0.0, 0.0, 0.0),
):
    marker = f'                "date": "{date_value}",\n'
    replacement = (
        marker
        + f'                "load_focus_low_aerobic": {low},\n'
        + f'                "load_focus_high_aerobic": {high},\n'
        + f'                "load_focus_anaerobic": {anaerobic},\n'
    )
    replace_once(stats, marker, replacement, f"stats load-focus {date_value}")
replace_once(stats, "    assert imported == 14\n", "    assert imported == 20\n", "stats row count")
replace_once(stats, "    assert import_statistics.call_count == 7\n", "    assert import_statistics.call_count == 10\n", "stats sensor count")
replace_once(
    stats,
    '        "sensor.garmin_fitness_strain",\n    }\n',
    '        "sensor.garmin_fitness_strain",\n'
    '        "sensor.garmin_fitness_load_focus_low_aerobic",\n'
    '        "sensor.garmin_fitness_load_focus_high_aerobic",\n'
    '        "sensor.garmin_fitness_load_focus_anaerobic",\n'
    '    }\n',
    "stats expected ids",
)
replace_once(
    stats,
    '''    strain_metadata, strain_statistics = by_statistic_id[\n        "sensor.garmin_fitness_strain"\n    ]\n    assert strain_metadata["unit_of_measurement"] is None\n    assert [row["mean"] for row in strain_statistics] == [2.1, 2.5]\n''',
    '''    strain_metadata, strain_statistics = by_statistic_id[\n        "sensor.garmin_fitness_strain"\n    ]\n    assert strain_metadata["unit_of_measurement"] is None\n    assert [row["mean"] for row in strain_statistics] == [2.1, 2.5]\n\n    focus_metadata, focus_statistics = by_statistic_id[\n        "sensor.garmin_fitness_load_focus_low_aerobic"\n    ]\n    assert focus_metadata["unit_of_measurement"] == "TE"\n    assert [row["mean"] for row in focus_statistics] == [3.0, 2.0]\n''',
    "stats focus metadata assertions",
)
replace_once(
    stats,
    "    # Five always-defined metrics contribute two rows each; ACWR and ramp one each.\n    assert imported == 12\n",
    "    # Eight always-defined metrics contribute two rows each; ACWR and ramp one each.\n    assert imported == 18\n",
    "stats missing rolling count",
)
