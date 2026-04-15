from core.user_classifier import UserLevel, classify, get_study_plan


def test_classify_beginner() -> None:
    level = classify({"correct": 2, "total": 10, "avg_response_time_ms": 15000})
    assert level == UserLevel.BEGINNER


def test_classify_intermediate() -> None:
    level = classify({"correct": 5, "total": 10, "avg_response_time_ms": 8000})
    assert level == UserLevel.INTERMEDIATE


def test_classify_advanced() -> None:
    level = classify({"correct": 9, "total": 10, "avg_response_time_ms": 7000})
    assert level == UserLevel.ADVANCED


def test_classify_speed_promotes_borderline_intermediate() -> None:
    level = classify({"correct": 7, "total": 10, "avg_response_time_ms": 5500})
    assert level == UserLevel.ADVANCED


def test_get_study_plan_by_level() -> None:
    beginner = get_study_plan(UserLevel.BEGINNER)
    intermediate = get_study_plan(UserLevel.INTERMEDIATE)
    advanced = get_study_plan(UserLevel.ADVANCED)

    assert beginner["daily_minutes"] < intermediate["daily_minutes"] < advanced["daily_minutes"]
    assert beginner["starting_hypothesis"] == "H01_Trig"
    assert advanced["starting_hypothesis"] == "H03_Chain"
