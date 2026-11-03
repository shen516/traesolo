"""One-off: sync Docker football_analytics -> local football (13306)."""
import subprocess
import sys
from pathlib import Path

DUMP = Path(__file__).resolve().parent / "data" / "football_analytics_dump.sql"
MYSQL = Path(r"D:\ProgramData\MySQL\bin\mysql.exe")

SRC = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "database": "football_analytics",
}
DST = {
    "host": "127.0.0.1",
    "port": 13306,
    "user": "root",
    "password": "123456",
    "database": "football",
}


def dump_from_docker() -> None:
    DUMP.parent.mkdir(parents=True, exist_ok=True)
    print(f"Dumping {SRC['database']} from Docker ...")
    with open(DUMP, "wb") as out:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "football-mysql",
                "mysqldump",
                f"-u{SRC['user']}",
                f"-p{SRC['password']}",
                "--single-transaction",
                "--routines",
                "--triggers",
                "--set-gtid-purged=OFF",
                "--add-drop-table",
                SRC["database"],
            ],
            stdout=out,
            stderr=subprocess.PIPE,
        )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")
        print("mysqldump failed:", err)
        sys.exit(1)
    size = DUMP.stat().st_size
    print(f"Dump written: {DUMP} ({size:,} bytes)")


def import_to_local() -> None:
    if not MYSQL.is_file():
        print(f"mysql client not found: {MYSQL}")
        sys.exit(1)
    print(f"Importing into {DST['database']} @ {DST['host']}:{DST['port']} ...")
    with open(DUMP, "rb") as dump:
        proc = subprocess.run(
            [
                str(MYSQL),
                f"--host={DST['host']}",
                f"-P{DST['port']}",
                f"-u{DST['user']}",
                f"-p{DST['password']}",
                "--default-character-set=utf8mb4",
                DST["database"],
            ],
            stdin=dump,
            stderr=subprocess.PIPE,
        )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")
        print("mysql import failed:", err)
        sys.exit(1)
    print("Import completed.")


def verify() -> None:
    from sqlalchemy import create_engine, text

    dst_url = (
        f"mysql+pymysql://{DST['user']}:{DST['password']}"
        f"@{DST['host']}:{DST['port']}/{DST['database']}"
    )
    engine = create_engine(dst_url, connect_args={"charset": "utf8mb4"})
    checks = ("matches", "leagues", "crawl_logs", "match_player_stats", "players", "teams")
    with engine.connect() as conn:
        for table in checks:
            n = conn.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar()
            print(f"  {table}: {n}")


if __name__ == "__main__":
    dump_from_docker()
    import_to_local()
    print("Verification:")
    verify()
