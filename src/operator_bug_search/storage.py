from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .models import Finding


class Storage:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.raw_dir = self.output_dir / "raw"
        self.normalized_dir = self.output_dir / "normalized"
        self.findings_jsonl_path = self.normalized_dir / "github_findings.jsonl"
        self.findings_csv_path = self.normalized_dir / "github_findings.csv"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.normalized_dir.mkdir(parents=True, exist_ok=True)

    def append_raw(self, name: str, payload: dict) -> None:
        path = self.raw_dir / f"{name}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def append_error(self, payload: dict) -> None:
        path = self.raw_dir / "errors.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def load_findings(self) -> list[Finding]:
        if not self.findings_jsonl_path.exists():
            return []
        findings: list[Finding] = []
        with self.findings_jsonl_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                findings.append(Finding(**json.loads(line)))
        return findings

    def overwrite_findings_jsonl(self, findings: Iterable[Finding]) -> None:
        with self.findings_jsonl_path.open("w", encoding="utf-8") as handle:
            for finding in findings:
                handle.write(json.dumps(finding.to_dict(), ensure_ascii=False) + "\n")

    def append_finding(self, finding: Finding) -> None:
        with self.findings_jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(finding.to_dict(), ensure_ascii=False) + "\n")

    def load_checkpoint(self, checkpoint_path: str | Path) -> dict:
        path = Path(checkpoint_path)
        if not path.exists():
            return {"completed_pages": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def save_checkpoint(self, checkpoint_path: str | Path, payload: dict) -> None:
        Path(checkpoint_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def remove_checkpoint(self, checkpoint_path: str | Path) -> None:
        path = Path(checkpoint_path)
        if path.exists():
            path.unlink()

    def write_findings(self, findings: Iterable[Finding]) -> tuple[Path, Path]:
        rows = [finding.to_dict() for finding in findings]
        self.overwrite_findings_jsonl(findings)

        if rows:
            fieldnames = list(rows[0].keys())
            with self.findings_csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    serialized = {
                        key: json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (dict, list))
                        else value
                        for key, value in row.items()
                    }
                    writer.writerow(serialized)
        else:
            self.findings_csv_path.write_text("", encoding="utf-8")
        return self.findings_jsonl_path, self.findings_csv_path
