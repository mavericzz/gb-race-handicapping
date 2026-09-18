from src.scrapers.merge import merge_and_score


def test_merge_scores_a_weight_dropper_as_the_play():
    punters = {
        "date": "2026-09-19",
        "meetings": [{
            "venue": "Ayr",
            "races": [{
                "race_number": 5,
                "name": "Ayr Gold Cup",
                "going": "Soft",
                "distance_m": 1207,
                "runners": [{
                    "name": "Well In",
                    "number": 1,
                    "barrier": 3,
                    "weight_kg": 56.0,
                    "handicap_rating": 110,
                    "odds": 9.0,
                    "last_run": {
                        "finish": 1,
                        "beaten_lengths": 0,
                        "distance_m": 1207,
                        "weight_kg": 61.0,
                        "going": "soft",
                    },
                }, {
                    "name": "Exposed",
                    "number": 2,
                    "barrier": 14,
                    "weight_kg": 63.0,
                    "handicap_rating": 92,
                    "odds": 2.5,
                    "last_run": {
                        "finish": 8,
                        "beaten_lengths": 9,
                        "distance_m": 1207,
                        "weight_kg": 56.0,
                        "going": "good",
                    },
                }],
            }],
        }],
    }
    rs = {
        "date": "2026-09-19",
        "meetings": [{
            "venue": "Ayr",
            "races": [{
                "race_number": 5,
                "runners": [{
                    "name": "Well In",
                    "weight_kg": 56.0,
                    "past_runs": [{"track": "York", "finish": 1, "weight_kg": 61.0}],
                }],
            }],
        }],
    }
    card = merge_and_score(punters, rs)
    race = card["meetings"][0]["races"][0]
    assert race["runners"][0]["name"] == "Well In"
    assert any(p["name"] == "Well In" for p in card["plays"]) or race["runners"][0]["action"] in {"PLAY", "WATCH"}
