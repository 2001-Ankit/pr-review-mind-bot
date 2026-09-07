from reviewmindbot.core.diff_parser import DiffParser


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
    assert file_change.total_changes == 3
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


def test_hunk_records_new_file_start_line():
    diff_text = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -10,3 +42,4 @@ def f():
+x = 1
"""

    hunk = DiffParser().parse(diff_text)[0].hunks[0]

    assert hunk.new_start == 42


def test_added_line_starting_with_plus_signs_is_not_dropped():
    """`++i;` renders as `+++i;` in a diff and must count as an added line."""
    diff_text = """diff --git a/main.c b/main.c
--- a/main.c
+++ b/main.c
@@ -1 +1,2 @@
 int i = 0;
+++i;
"""

    file_change = DiffParser().parse(diff_text)[0]

    assert file_change.total_added == 1
    assert file_change.hunks[0].added_lines == ["++i;"]


def test_binary_files_are_flagged():
    diff_text = """diff --git a/logo.png b/logo.png
index 1111111..2222222 100644
Binary files a/logo.png and b/logo.png differ
"""

    assert DiffParser().parse(diff_text)[0].is_binary is True


def test_no_newline_marker_is_ignored():
    diff_text = """diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-old
+new
\\ No newline at end of file
"""

    hunk = DiffParser().parse(diff_text)[0].hunks[0]

    assert hunk.added_lines == ["new"]
    assert "\\ No newline at end of file" not in hunk.raw_lines


def test_empty_diff_returns_no_files():
    assert DiffParser().parse("") == []
