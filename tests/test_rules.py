from app.rules_engine import evaluate_rules
from app.schemas import OpenCVFeatures


def test_strong_light_is_false_alarm():
    feat = OpenCVFeatures(
        mean_brightness=200,
        bright_ratio=0.15,
        edge_sharpness=120,
        fire_area_ratio=0.0001,
        smoke_area_ratio=0.001,
    )
    result = evaluate_rules(feat)
    assert result.top_type == "强光误报"
    assert result.preliminary_decision == "疑似误报"


def test_large_fire_is_real():
    feat = OpenCVFeatures(
        mean_brightness=140,
        bright_ratio=0.02,
        edge_sharpness=40,
        fire_area_ratio=0.05,
        smoke_area_ratio=0.08,
    )
    result = evaluate_rules(feat)
    assert result.preliminary_decision == "疑似真实火情"


def test_large_smoke_not_auto_false():
    """云雾与真实烟雾易混淆：大烟雾不得直接判疑似误报。"""
    feat = OpenCVFeatures(
        mean_brightness=120,
        bright_ratio=0.02,
        edge_sharpness=30,
        fire_area_ratio=0.0001,
        smoke_area_ratio=0.25,
    )
    result = evaluate_rules(feat)
    assert result.preliminary_decision in ("建议人工复核", "疑似真实火情")
    assert result.preliminary_decision != "疑似误报"
