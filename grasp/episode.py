"""Read and write `GraspEpisode` records — the unit of experience Morrow learns from.

One episode is one immutable JSON file per grasp attempt. Immutable is load-bearing:
the whole value of the track is a growing, trustworthy log of "we predicted X, Y
happened". So `save_episode` refuses to overwrite — a repeated id is a bug (a lost or
double-counted attempt), not something to paper over.
"""

from __future__ import annotations

from pathlib import Path

from .schemas import GraspEpisode


def save_episode(episode: GraspEpisode, directory: str | Path) -> Path:
    """Write `episode` to `<directory>/<episode_id>.json` and return the path.

    Creates the directory if needed. Raises `FileExistsError` if that episode id is
    already on disk — episodes are immutable, so overwriting would silently rewrite
    history.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{episode.episode_id}.json"
    if path.exists():
        raise FileExistsError(
            f"episode {episode.episode_id!r} already recorded at {path}; episodes are immutable"
        )
    path.write_text(episode.model_dump_json(indent=2))
    return path


def load_episode(path: str | Path) -> GraspEpisode:
    """Load and validate one `GraspEpisode` from a JSON file."""
    return GraspEpisode.model_validate_json(Path(path).read_text())


def load_episodes(directory: str | Path) -> list[GraspEpisode]:
    """Load every episode in `directory`, sorted by id for a deterministic order."""
    directory = Path(directory)
    return [load_episode(p) for p in sorted(directory.glob("*.json"))]
