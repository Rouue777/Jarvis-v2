
import re
import unicodedata


def normalize_text(text):
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(
        char for char in text
        if unicodedata.category(char) != "Mn"
    )
    return set(re.findall(r"[a-z0-9]+", text))


def search_tracks(spotify, query, limit=10):
    results = spotify.search(
        q=query,
        type="track",
        limit=limit
    )

    tracks = results.get("tracks", {}).get("items", [])
    query_words = normalize_text(query)

    ranked = []

    for track in tracks:
        title_words = normalize_text(track.get("name", ""))

        artist_names = [
            artist.get("name", "")
            for artist in track.get("artists", [])
        ]
        artist_words = set()

        for artist in artist_names:
            artist_words.update(normalize_text(artist))

        matched_title = query_words & title_words
        matched_artist = query_words & artist_words
        matched_words = matched_title | matched_artist

        coverage = (
            len(matched_words) / len(query_words)
            if query_words else 0
        )

        score = (
            coverage * 100
            + len(matched_title) * 2
            + len(matched_artist) * 4
        )

        ranked.append({
            "track": track,
            "score": score,
            "coverage": coverage,
        })

    ranked.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return ranked
