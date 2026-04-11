from dataclasses import dataclass, field
from pathlib import Path
import json

from .ir import WorkflowCase


@dataclass
class Repository:
    cases: list[WorkflowCase] = field(default_factory=list)

    def add_case(self, case: WorkflowCase):
        if self.get_case_by_name(case.name) is not None:
            return
        self.cases.append(case)

    def get_case_by_name(self, name: str) -> WorkflowCase | None:
        for case in self.cases:
            if case.name == name:
                return case
        return None

    def add_from_json(self, data: dict):
        self.add_case(WorkflowCase.from_json(data))

    def save_to_folder(self, folder_path: Path):
        folder_path.mkdir(parents=True, exist_ok=True)
        for case in self.cases:
            case_file = Path(folder_path, case.name).with_suffix(".json")
            with open(case_file, "w", encoding="utf-8") as f:
                json.dump(case.to_json(), f, indent=4)

    def load_from_folder(self, folder_path: Path):
        if not folder_path.exists():
            return
        for case_file in folder_path.glob("*.json"):
            with open(case_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.add_from_json(data)
