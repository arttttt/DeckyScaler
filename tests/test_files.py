import json
import os

from deckyscaler.infrastructure import files


def test_read_json_returns_empty_dict_for_missing_malformed_or_non_object(tmp_path):
    (tmp_path / "list.json").write_text("[1, 2]")
    (tmp_path / "broken.json").write_text("{not json")
    (tmp_path / "ok.json").write_text('{"a": 1}')

    assert files.read_json(tmp_path / "missing.json") == {}
    assert files.read_json(tmp_path / "list.json") == {}
    assert files.read_json(tmp_path / "broken.json") == {}
    assert files.read_json(tmp_path / "ok.json") == {"a": 1}


def test_rewrite_text_writes_only_when_the_content_changes(tmp_path):
    path = tmp_path / "OptiScaler.ini"
    path.write_text("A=1\n")
    os.utime(path, (1_000_000, 1_000_000))

    assert files.rewrite_text(path, lambda text: text) is False
    assert path.stat().st_mtime == 1_000_000

    assert files.rewrite_text(path, lambda text: text.replace("1", "2")) is True
    assert path.read_text() == "A=2\n"


def test_files_match_compares_content_and_requires_both_files(tmp_path):
    a = tmp_path / "a.dll"
    b = tmp_path / "b.dll"
    a.write_bytes(b"same")
    b.write_bytes(b"same")

    assert files.files_match(a, b) is True
    b.write_bytes(b"different")
    assert files.files_match(a, b) is False
    assert files.files_match(a, tmp_path / "missing.dll") is False


def test_rewriting_a_text_file_keeps_its_line_endings(tmp_path):
    from deckyscaler.infrastructure import files

    path = tmp_path / "OptiScaler.ini"
    path.write_bytes(b"[Menu]\r\nUseHQFont=auto\r\n")

    files.rewrite_text(path, lambda text: text.replace("auto", "false"))

    assert path.read_bytes() == b"[Menu]\r\nUseHQFont=false\r\n"


def test_a_kept_json_file_is_replaced_whole_and_its_directory_made(tmp_path):
    path = tmp_path / "settings" / "proton.json"

    files.replace_json(path, {"a": 1})
    files.replace_json(path, {"b": 2})

    assert json.loads(path.read_text()) == {"b": 2}
    assert sorted(p.name for p in path.parent.iterdir()) == ["proton.json"]  # nothing staged is left


def test_read_text_or_empty_reads_a_file_and_gives_nothing_for_one_that_cant_be_read(tmp_path):
    (tmp_path / "vendor").write_text("0x1002\n")
    (tmp_path / "a-directory").mkdir()

    assert files.read_text_or_empty(tmp_path / "vendor") == "0x1002\n"
    assert files.read_text_or_empty(tmp_path / "gone") == ""
    assert files.read_text_or_empty(tmp_path / "a-directory") == ""

