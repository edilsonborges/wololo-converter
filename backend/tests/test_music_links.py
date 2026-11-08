"""Tests for music link resolution"""
from app import music_links
from app.music_links import base_title, is_music_link, parse_duration, pick_best_match, search_query

# Real YouTube results for "djnoone Dale Candela" (Nov 2026)
RESULTS = [
    {"id": "p63v0n73aMg", "title": "Dale Candela", "channel": "djnoone", "duration": 196},
    {"id": "BSubfESgZmE", "title": "DJNoone - Dale Candela | Get Up and Move", "channel": "Vibes 5606", "duration": 196},
    {"id": "YOqbB130CK8", "title": "Dale Candela Boom", "channel": "Release - Topic", "duration": 93},
    {"id": "TUHya_Bfc6c", "title": "Dale Candela", "channel": "Ragamuzi - Topic", "duration": 168},
    {"id": "f8LZWEkltFU", "title": "Candy (Instrumental Version)", "channel": "djnoone", "duration": 182},
    {"id": "0FImB64Q3yM", "title": "Dale Candela (Instrumental Mix)", "channel": "PolyRhythm", "duration": 463},
    {"id": "1ju-davw9Pw", "title": "LUNAY - YA NO ME MUERDO (Karaoke/Instrumental)", "channel": "[FKM]", "duration": 149},
]


def test_is_music_link():
    assert is_music_link("https://artlist.io/royalty-free-music/song/earthquake/6002056")
    assert is_music_link("https://artlist.io/royalty-free-music/album/dale-candela/1000047?x=1")
    assert not is_music_link("https://artlist.io/royalty-free-music/artist/djnoone/2901")
    assert not is_music_link("https://evil.com/artlist.io/royalty-free-music/song/a/1")


def test_parse_duration():
    assert parse_duration("03:15") == 195
    assert parse_duration("1:02:03") == 3723
    assert parse_duration("PT3M15S") == 195
    assert parse_duration(None) is None
    assert parse_duration("abc") is None


def test_base_title_and_query():
    assert base_title("Dale Candela - Instrumental version") == "Dale Candela"
    assert base_title("Dale Candela (Instrumental Version)") == "Dale Candela"
    assert search_query({"title": "Dale Candela - Instrumental version", "artist": "djnoone"}) == (
        "djnoone Dale Candela instrumental"
    )


def test_picks_artist_upload_for_original():
    match = pick_best_match({"title": "Dale Candela", "artist": "djnoone", "duration": 195}, RESULTS)
    assert match["id"] == "p63v0n73aMg"


def test_never_substitutes_vocal_or_other_mix_for_instrumental():
    track = {"title": "Dale Candela - Instrumental version", "artist": "djnoone", "duration": 194}
    assert pick_best_match(track, RESULTS) is None


def test_rejects_same_name_with_different_duration():
    assert pick_best_match({"title": "Dale Candela", "artist": "x", "duration": 120}, RESULTS) is None


def test_accepts_existing_instrumental():
    track = {"title": "Candy - Instrumental version", "artist": "djnoone", "duration": 181}
    assert pick_best_match(track, RESULTS)["id"] == "f8LZWEkltFU"


def test_resolve_combines_tracks_and_matches(monkeypatch):
    monkeypatch.setattr(music_links, "fetch_tracks", lambda url: {
        "album": "Dale Candela",
        "tracks": [
            {"title": "Dale Candela", "artist": "djnoone", "duration": 195},
            {"title": "Dale Candela - Instrumental version", "artist": "djnoone", "duration": 194},
        ],
    })
    monkeypatch.setattr(music_links, "search_youtube", lambda query: RESULTS)

    result = music_links.resolve("https://artlist.io/royalty-free-music/album/dale-candela/1000047")

    assert result["album"] == "Dale Candela"
    assert result["tracks"][0]["video_url"] == "https://www.youtube.com/watch?v=p63v0n73aMg"
    assert result["tracks"][1]["video_url"] is None


class TestResolveEndpoint:
    async def test_rejects_unsupported_link(self, client):
        response = await client.post("/api/resolve", json={"url": "https://www.youtube.com/watch?v=abc"})
        assert response.status_code == 400

    async def test_returns_resolved_tracks(self, client, monkeypatch):
        monkeypatch.setattr(music_links, "resolve", lambda url: {
            "album": "Earthquake",
            "tracks": [{
                "title": "Earthquake", "artist": "Romeo", "duration": 122,
                "video_url": "https://www.youtube.com/watch?v=TRHJ_U0CcIg", "video_title": "Earthquake",
            }],
        })
        response = await client.post(
            "/api/resolve", json={"url": "https://artlist.io/royalty-free-music/song/earthquake/6002056"}
        )
        assert response.status_code == 200
        assert response.json()["tracks"][0]["video_url"].endswith("TRHJ_U0CcIg")

    async def test_page_errors_become_502(self, client, monkeypatch):
        def blocked(url):
            raise ValueError("The music page is temporarily blocking access, try again in a minute")

        monkeypatch.setattr(music_links, "resolve", blocked)
        response = await client.post(
            "/api/resolve", json={"url": "https://artlist.io/royalty-free-music/song/earthquake/6002056"}
        )
        assert response.status_code == 502
        assert "blocking" in response.json()["detail"]


def test_resolve_searches_again_when_results_miss_the_track(monkeypatch):
    monkeypatch.setattr(music_links, "fetch_tracks", lambda url: {
        "album": "Dale Candela",
        "tracks": [{"title": "Dale Candela", "artist": "djnoone", "duration": 195}],
    })
    responses = iter([RESULTS[2:4], RESULTS])
    calls = []

    def search(query):
        calls.append(query)
        return next(responses)

    monkeypatch.setattr(music_links, "search_youtube", search)

    result = music_links.resolve("https://artlist.io/royalty-free-music/song/dale-candela/6000143")

    assert len(calls) == 2
    assert result["tracks"][0]["video_url"].endswith("p63v0n73aMg")


def test_open_retries_and_reports_blocking(monkeypatch):
    import pytest

    class FakePage:
        def route(self, *args):
            pass

        def goto(self, *args, **kwargs):
            pass

        def wait_for_function(self, *args, **kwargs):
            raise TimeoutError("still on the check page")

    class FakeContext:
        closed = 0

        def new_page(self):
            return FakePage()

        def close(self):
            FakeContext.closed += 1

    class FakeBrowser:
        def new_context(self, **kwargs):
            return FakeContext()

    with pytest.raises(ValueError, match="temporarily blocking"):
        music_links._open(FakeBrowser(), "https://artlist.io/royalty-free-music/song/a/1")
    assert FakeContext.closed == music_links.PAGE_ATTEMPTS
