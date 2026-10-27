
import json
import sys
from pathlib import Path

import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyPKCE


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
TOKEN_PATH = BASE_DIR / "config" / "token_spotify.json"

REDIRECT_URI = "http://127.0.0.1:8888/callback"

SPOTIFY_SCOPES = " ".join([
    "user-read-private",
    "user-read-email",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "user-read-recently-played",
    "user-top-read",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-library-read",
    "user-library-modify",
    "user-follow-read",
    "user-follow-modify",
])


def get_spotify_client():
    if not CONFIG_PATH.exists():
        raise RuntimeError(
            f"Arquivo de configuração não encontrado: {CONFIG_PATH}"
        )

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    client_id = config.get("spotify_client_id")

    if not client_id:
        raise RuntimeError(
            "Configure spotify_client_id em config/api_keys.json."
        )

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    cache_handler = CacheFileHandler(
        cache_path=str(TOKEN_PATH)
    )

    auth_manager = SpotifyPKCE(
        client_id=client_id,
        redirect_uri=REDIRECT_URI,
        scope=SPOTIFY_SCOPES,
        cache_handler=cache_handler,
        requests_timeout=10,
    )

    return spotipy.Spotify(
        auth_manager=auth_manager,
        requests_timeout=10,
    )
