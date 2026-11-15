import lzma
import sqlite3

import config


def test_ensure_db_unpacks_archive(tmp_path, monkeypatch):
    src = tmp_path / "src.db"
    c = sqlite3.connect(src); c.execute("CREATE TABLE t(x)"); c.execute("INSERT INTO t VALUES (7)"); c.commit(); c.close()
    archive = tmp_path / "a.db.xz"
    archive.write_bytes(lzma.compress(src.read_bytes()))
    target = tmp_path / "data" / "x.db"
    monkeypatch.setattr(config, "DB_PATH", target)
    monkeypatch.setattr(config, "DEMO_DB_ARCHIVE", archive)
    assert config.ensure_db() == target
    assert sqlite3.connect(target).execute("SELECT x FROM t").fetchone() == (7,)
    assert not target.with_suffix(".tmp").exists()


def test_ensure_db_clear_error_when_nothing_available(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "none.db")
    monkeypatch.setattr(config, "DEMO_DB_ARCHIVE", tmp_path / "none.xz")
    with pytest.raises(FileNotFoundError, match="load_data"):
        config.ensure_db()
