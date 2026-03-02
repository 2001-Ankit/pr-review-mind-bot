from dataclasses import dataclass
from typing import List


@dataclass
class Hunk:
    header: str
    raw_lines: List[str]
    added_lines: List[str]
    removed_lines: List[str]
    context_lines: List[str]


@dataclass
class FileChange:
    file_name: str
    hunks: List[Hunk]
    total_added: int
    total_removed: int
    is_deleted:bool = False
    is_new:bool = False


class DiffParser:
    def parse(self, diff: str) -> List[FileChange]:
        lines = diff.splitlines()
        files = []

        current_file = None
        current_hunk = None

        for line in lines:

            if line.startswith("diff --git"):
                if current_file:
                    files.append(current_file)

                parts = line.split()
                b_path = parts[3] if len(parts) >= 4 else ""
                file_name = b_path[2:] if b_path.startswith("b/") else b_path

                current_file = FileChange(
                    file_name=file_name,
                    hunks=[],
                    total_added=0,
                    total_removed=0,
                )
                current_hunk = None

            elif current_file and line.startswith("new file mode"):
                current_file.is_new = True

            elif current_file and line.startswith("deleted file mode"):
                current_file.is_deleted = True

            elif line.startswith("@@") and current_file:
                current_hunk = Hunk(
                    header=line,
                    added_lines=[],
                    removed_lines=[],
                    context_lines=[],
                    raw_lines=[],
                )
                current_file.hunks.append(current_hunk)

            elif current_hunk:
                current_hunk.raw_lines.append(line)

                if line.startswith("+") and not line.startswith("+++"):
                    current_hunk.added_lines.append(line[1:])
                    current_file.total_added += 1

                elif line.startswith("-") and not line.startswith("---"):
                    current_hunk.removed_lines.append(line[1:])
                    current_file.total_removed += 1

                elif line.startswith(" "):
                    current_hunk.context_lines.append(line[1:])

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