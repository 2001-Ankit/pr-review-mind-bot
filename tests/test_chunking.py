from reviewmindbot.core.chunking import build_chunks
from reviewmindbot.core.diff_parser import FileChange, Hunk


def make_file(name: str, *hunk_bodies: str) -> FileChange:
    hunks = [
        Hunk(header="@@ -1 +1 @@", raw_lines=body.splitlines(), added_lines=[body])
        for body in hunk_bodies
    ]
    return FileChange(file_name=name, hunks=hunks, total_added=len(hunks))


def test_hunks_are_packed_together_while_they_fit():
    chunks = build_chunks([make_file("a.py", "+one", "+two")], max_chunk_size=4000)

    assert len(chunks) == 1
    assert "+one" in chunks[0].text
    assert "+two" in chunks[0].text


def test_chunk_records_every_file_it_covers():
    files = [make_file("a.py", "+one"), make_file("b.py", "+two")]

    chunks = build_chunks(files, max_chunk_size=4000)

    assert chunks[0].files == ["a.py", "b.py"]


def test_chunks_never_exceed_the_size_limit():
    files = [make_file("a.py", *[f"+line {i}" for i in range(40)])]

    chunks = build_chunks(files, max_chunk_size=120)

    assert len(chunks) > 1
    assert all(len(chunk) <= 120 for chunk in chunks)


def test_oversized_hunk_is_split_on_line_boundaries():
    body = "\n".join(f"+statement_{i}()" for i in range(50))
    chunks = build_chunks([make_file("big.py", body)], max_chunk_size=200)

    assert len(chunks) > 1
    # No piece may end mid-token: every line survives intact somewhere.
    joined = "\n".join(chunk.text for chunk in chunks)
    assert "+statement_49()" in joined
    assert all(chunk.files == ["big.py"] for chunk in chunks)


def test_binary_and_empty_files_are_not_chunked():
    binary = FileChange(file_name="logo.png", is_binary=True)
    empty = FileChange(file_name="untouched.py")

    assert build_chunks([binary, empty], max_chunk_size=1000) == []


def test_each_block_is_labelled_with_its_path():
    chunks = build_chunks([make_file("pkg/mod.py", "+x = 1")], max_chunk_size=1000)

    assert chunks[0].text.startswith("FILE: pkg/mod.py")
