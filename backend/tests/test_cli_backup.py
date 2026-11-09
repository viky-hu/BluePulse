import sqlite3

from bluepulse_backend import cli


def test_explicit_backup_includes_committed_wal_at_current_schema(tmp_path, monkeypatch):
    database = tmp_path / "pulse.db"
    monkeypatch.setenv("BLUEPULSE_DATABASE_URL", f"sqlite:///{database.as_posix()}")
    cli.initialize()
    with sqlite3.connect(database) as source:
        source.execute("PRAGMA journal_mode=WAL")
        source.execute("CREATE TABLE backup_probe (value TEXT)")
        source.execute("INSERT INTO backup_probe VALUES ('committed')")
        source.commit()
        backup = cli.backup()
        assert backup.parent == tmp_path / "backups"
        with sqlite3.connect(backup) as copy:
            assert copy.execute("PRAGMA quick_check").fetchone() == ("ok",)
            assert copy.execute("SELECT value FROM backup_probe").fetchone() == ("committed",)
            assert copy.execute("SELECT version_num FROM alembic_version").fetchone() == source.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
