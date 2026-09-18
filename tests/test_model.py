from src.handicap.model import PastRun, RunnerInput, fractional_kelly, handicap_race


def test_horse_dropping_weight_outranks_same_rating_rival():
    a = RunnerInput(
        name="Dropper",
        today_weight_kg=57.0,
        handicap_rating=100,
        market_odds=6.0,
        last_run=PastRun(finish=1, beaten_lengths=0, distance_m=1207, weight_kg=60.0, going="soft"),
        going="soft",
        distance_m=1207,
        field_size=12,
        barrier=5,
    )
    b = RunnerInput(
        name="Riser",
        today_weight_kg=62.0,
        handicap_rating=100,
        market_odds=6.0,
        last_run=PastRun(finish=1, beaten_lengths=0, distance_m=1207, weight_kg=57.0, going="good"),
        going="soft",
        distance_m=1207,
        field_size=12,
        barrier=5,
    )
    rows = handicap_race([a, b], venue="ayr")
    assert rows[0]["name"] == "Dropper"
    assert rows[0]["p_model"] > rows[1]["p_model"]


def test_overlay_flags_play_when_model_price_beats_the_market():
    strong = RunnerInput(
        name="Well In",
        today_weight_kg=56.0,
        handicap_rating=110,
        market_odds=8.0,
        last_run=PastRun(
            finish=1,
            beaten_lengths=0,
            distance_m=1207,
            weight_kg=60.0,
            going="soft",
            fsp=104.0,
            par_fsp=100.0,
        ),
        going="soft",
        distance_m=1207,
        field_size=10,
        barrier=3,
    )
    weak = RunnerInput(
        name="Exposed",
        today_weight_kg=63.0,
        handicap_rating=90,
        market_odds=2.2,
        last_run=PastRun(
            finish=7,
            beaten_lengths=8.0,
            distance_m=1207,
            weight_kg=58.0,
            going="good",
            fsp=96.0,
            par_fsp=100.0,
        ),
        going="soft",
        distance_m=1207,
        field_size=10,
        barrier=12,
    )
    rows = {r["name"]: r for r in handicap_race([strong, weak], venue="ayr")}
    assert rows["Well In"]["edge"] is not None
    assert rows["Well In"]["edge"] > 0
    assert rows["Well In"]["action"] in {"PLAY", "WATCH"}


def test_unrated_longshot_is_not_a_play():
    unrated = RunnerInput(name="Guess", today_weight_kg=58.0, market_odds=51.0, field_size=10)
    fav = RunnerInput(
        name="Mark",
        today_weight_kg=58.0,
        handicap_rating=90,
        market_odds=2.5,
        field_size=10,
    )
    rows = {r["name"]: r for r in handicap_race([unrated, fav], venue="ayr")}
    assert rows["Guess"]["action"] != "PLAY"


def test_quarter_kelly_is_capped_and_zero_without_edge():
    assert fractional_kelly(0.4, 5.0) > 0
    assert fractional_kelly(0.4, 5.0) <= 0.05
    assert fractional_kelly(-0.1, 5.0) == 0.0
