from dataclasses import dataclass
from typing import List


@dataclass
class Hunk:
    header: str
    added_lines: List[str]
    removed_lines: List[str]
    context_lines: List[str]


@dataclass
class FileChange:
    file_name: str
    hunks: List[Hunk]
    total_added: int
    total_removed: int


class DiffParser:
    def parse(self, diff: str) -> List[FileChange]:
        lines = diff.splitlines()
        files: List[FileChange] = []

        current_file = None
        current_hunk = None

        for line in lines:
            
            # New file section
            if line.startswith("diff --git"):
                if current_file:
                    files.append(current_file)

                parts = line.split(" ")
                file_path = parts[-1]  # usually b/path/to/file.py
                file_name = file_path.replace("b/", "")

                current_file = FileChange(
                    file_name=file_name,
                    hunks=[],
                    total_added=0,
                    total_removed=0,
                )
                current_hunk = None

            # New hunk
            elif line.startswith("@@") and current_file:
                current_hunk = Hunk(
                    header=line,
                    added_lines=[],
                    removed_lines=[],
                    context_lines=[],
                )
                current_file.hunks.append(current_hunk)

            # Inside a hunk
            elif current_hunk:

                if line.startswith("+") and not line.startswith("+++"):
                    current_hunk.added_lines.append(line[1:])
                    current_file.total_added += 1

                elif line.startswith("-") and not line.startswith("---"):
                    current_hunk.removed_lines.append(line[1:])
                    current_file.total_removed += 1

                elif line.startswith(" "):
                    current_hunk.context_lines.append(line[1:])

        # Append last file
        if current_file:
            files.append(current_file)

        return files


if __name__ == "__main__":
    parser = DiffParser()

    diff_text = """
diff --git a/example.py b/example.py
@@ -1,3 +1,4 @@
 def hello():
-    print("Hello")
+    print("Hello world")
+    print("New line")
"""

    files = parser.parse(diff_text)

    for file in files:
        print("File:", file.file_name)
        print("Added:", file.total_added)
        print("Removed:", file.total_removed)
        print("Hunks:", len(file.hunks))