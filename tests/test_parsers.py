from src.scrapers.parsers import (
    horse_key,
    parse_decimal_odds,
    parse_last_start_block,
    parse_st_lb,
    race_number_from_url,
    venue_key,
)


def test_parse_last_start_block_extracts_weight_beaten_and_trip():
    blob = (
        "Last Start Statistics Place 7th of 9 (9L) Date 06/09/26 Track York "
        "Distance 1207m Class CL1 Track/Con Good Weight 59kg Runner Time 01:11.690"
    )
    parsed = parse_last_start_block(blob)
    assert parsed["finish"] == 7
    assert parsed["beaten_lengths"] == 9.0
    assert parsed["weight_kg"] == 59.0
    assert parsed["distance_m"] == 1207
    assert parsed["track"] == "York"
    assert parsed["going"] == "Good"
    assert parsed["time_s"] == 71.69


def test_horse_key_and_race_number_and_odds():
    assert horse_key("Two Tribes (GBR)") == "twotribes"
    assert race_number_from_url(
        "https://www.punters.com.au/form-guide/horses/ayr-uk-20260919/foo-race-5/#Overview"
    ) == 5
    assert race_number_from_url(
        "https://www.racingandsports.co.uk/form-guide/thoroughbred/united-kingdom/ayr/2026-09-19/R5"
    ) == 5
    assert parse_decimal_odds("$4.00") == 4.0
    assert parse_decimal_odds("SCR") is None
    assert parse_st_lb("Wgt: 9st 13lbs") == 139
    assert parse_st_lb("9st") == 126
    assert venue_key("Newmarket Rowley") == venue_key("Newmarket")
