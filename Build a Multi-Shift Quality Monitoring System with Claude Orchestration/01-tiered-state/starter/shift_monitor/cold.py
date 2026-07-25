"""Cold tier: monthly Markdown summaries derived deterministically from the warm tier."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .warm import WarmStore


@dataclass
class ColdStore:
    store: WarmStore
    cold_dir: Path

    def write_monthly_summary(self, year: int, month: int) -> Path:
        # TODO: Produce a Markdown file at `self.cold_dir / "YYYY-MM.md"` with:
        #   - A heading `# YYYY-MM`
        #   - A `Total defects: N` line (from WarmStore.count_for_month)
        #   - A "## Top components" section listing the top-3 components by
        #     count (from WarmStore.top_components_for_month), one per bullet
        # An empty month should still produce a valid file with `Total defects: 0`.
        # Return the path to the written file.
        self.cold_dir.mkdir(parents=True, exist_ok=True)
        path = self.cold_dir / f"{year:04d}-{month:02d}.md"
        with open(path, "w") as f:
            f.write(f"# {year:04d}-{month:02d}\n")
            f.write(f"Total defects: {self.store.count_for_month(year, month)}\n")
            f.write("## Top components\n")
            for component, count in self.store.top_components_for_month(year, month):
                f.write(f"- {component}: {count} defects\n")
            return path
