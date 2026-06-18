from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import EpisodeLog


@dataclass
class JsonlLogger:
    output_dir: Path

    def __post_init__(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_episode(self, episode: EpisodeLog) -> Path:
        path = self.output_dir / f"{episode.method_name}_{episode.task_id}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for round_log in episode.rounds:
                f.write(json.dumps(round_log.to_dict(), ensure_ascii=False) + "\n")
        return path

    def write_summary(self, episodes: list[EpisodeLog], filename: str = "summary.json") -> Path:
        summary = []
        for ep in episodes:
            summary.append(
                {
                    "task_id": ep.task_id,
                    "method_name": ep.method_name,
                    "success": ep.success,
                    "steps": ep.steps,
                    "total_tokens": ep.total_tokens,
                    "terminated_by": ep.terminated_by,
                }
            )

        path = self.output_dir / filename
        with path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return path
