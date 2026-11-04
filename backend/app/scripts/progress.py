"""Small standard-library progress bar for command-line scripts."""

from __future__ import annotations

import sys
from types import TracebackType
from typing import TextIO


class ProgressBar:
    def __init__(self, label: str, total: int, enabled: bool = True) -> None:
        self.label = label
        self.total = max(total, 0)
        self.enabled = enabled
        self.stream: TextIO = sys.stderr
        self.current = 0
        self.is_tty = enabled and self.stream.isatty()
        self.update_interval = max(1, self.total // 100)

    def __enter__(self) -> ProgressBar:
        if self.enabled and not self.is_tty:
            print(f"{self.label}...", file=self.stream)
        elif self.is_tty:
            self._render()
        return self

    def advance(self, amount: int = 1) -> None:
        if not self.enabled:
            return
        self.current = min(self.total, self.current + amount)
        if self.is_tty and (
            self.current == self.total or self.current % self.update_interval == 0
        ):
            self._render()

    def _render(self) -> None:
        percentage = 100 if self.total == 0 else int(self.current * 100 / self.total)
        filled = percentage // 5
        bar = "=" * filled + " " * (20 - filled)
        self.stream.write(f"\r{self.label}: [{bar}] {percentage:3d}%")
        self.stream.flush()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if not self.enabled:
            return False
        if self.is_tty:
            if exc_type is None:
                self.current = self.total
                self._render()
            self.stream.write("\n")
            self.stream.flush()
        else:
            status = "complete" if exc_type is None else "failed"
            print(f"{self.label}: {status}", file=self.stream)
        return False
