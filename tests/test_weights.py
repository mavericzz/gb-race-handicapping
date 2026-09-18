"""GB weight and beaten-lengths conversions for the handicapper."""

from src.handicap.weights import (
    lbs_per_length,
    parse_stone_pounds,
    performance_figure,
    weight_swing_lbs,
)


def test_lbs_per_length_is_steeper_at_sprints_than_staying_trips():
    assert lbs_per_length(5 * 201) == 3.0
    assert lbs_per_length(8 * 201) == 2.0
    assert lbs_per_length(12 * 201) == 1.5
    assert lbs_per_length(6 * 201) > lbs_per_length(10 * 201)


def test_parse_stone_pounds_to_lbs():
    assert parse_stone_pounds("9-7") == 133
    assert parse_stone_pounds("8-11") == 123
    assert parse_stone_pounds("10-0") == 140


def test_weight_swing_credits_a_horse_dropping_weight():
    # Last run 9-7, today 9-2 → 5 lb off
    assert weight_swing_lbs(last_carried_lbs=133, today_lbs=128) == 5.0


def test_performance_figure_adds_beaten_lengths_and_weight_swing():
    # Last-run official mark 90, beaten 2L over 6f (~2.5 lb/L), today 3 lb lighter
    fig = performance_figure(
        last_or=90,
        beaten_lengths=2.0,
        distance_m=1207,
        last_carried_lbs=133,
        today_lbs=130,
    )
    assert fig == 90 - (2.0 * 2.5) + 3.0
