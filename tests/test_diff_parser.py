from app.core.diff_parser import DiffParser


def test_parse_counts_files_hunks_and_line_types():
    diff_text = """diff --git a/example.py b/example.py
index 1111111..2222222 100644
--- a/example.py
+++ b/example.py
@@ -1,2 +1,3 @@
 line1
-old_value = 1
+new_value = 2
+print(new_value)
"""

    files = DiffParser().parse(diff_text)

    assert len(files) == 1
    file_change = files[0]
    assert file_change.file_name == "example.py"
    assert file_change.total_added == 2
    assert file_change.total_removed == 1
    assert len(file_change.hunks) == 1
    assert file_change.hunks[0].added_lines == ["new_value = 2", "print(new_value)"]
    assert file_change.hunks[0].removed_lines == ["old_value = 1"]
    assert file_change.hunks[0].context_lines == ["line1"]


def test_parse_marks_new_and_deleted_files():
    diff_text = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1 @@
+print("hi")
diff --git a/old.py b/old.py
deleted file mode 100644
--- a/old.py
+++ /dev/null
@@ -1 +0,0 @@
-print("bye")
"""

    files = DiffParser().parse(diff_text)

    assert files[0].is_new is True
    assert files[1].is_deleted is True
