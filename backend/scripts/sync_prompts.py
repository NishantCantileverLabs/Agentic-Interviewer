"""Mirror /prompts files into prompt_versions (invariant D7).

    python scripts/sync_prompts.py [prompts_dir]

File naming: prompts/<role>/<name>_v<N>.txt -> prompt_versions.name = "<role>/<name>_v<N>".
Idempotent against the LATEST row per name: any change — including a revert
to earlier content — inserts a fresh row, because runtime resolution picks the
newest row by created_at (a revert matched against ANY historical row was a
silent no-op: the rollback never took effect).

    python scripts/sync_prompts.py --check   # exit 1 on drift, change nothing
                                             # (CI/deploy gate: images do not
                                             # ship prompt files, so drift is
                                             # caught here, not at runtime)
"""

import pathlib
import sys

import sqlalchemy as sa

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.config import get_settings  # noqa: E402

ROLES = {"conduct", "evaluate", "brief"}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = (
        pathlib.Path(args[0])
        if args
        else pathlib.Path(__file__).parent.parent.parent / "prompts"
    )
    settings = get_settings()
    model_by_role = {
        "conduct": settings.conduct_model,
        "evaluate": settings.eval_model,
        "brief": settings.eval_model,
    }
    # try the configured URL first (works in-container); fall back to the
    # localhost rewrite for host-side dev runs against compose Postgres
    engine = sa.create_engine(settings.database_url)
    try:
        with engine.connect():
            pass
    except sa.exc.OperationalError:
        engine = sa.create_engine(
            settings.database_url.replace("@postgres:", "@localhost:")
        )

    check_only = "--check" in sys.argv
    drifted: list[str] = []
    synced = skipped = 0
    with engine.begin() as conn:
        for role_dir in sorted(root.iterdir()):
            if role_dir.name not in ROLES or not role_dir.is_dir():
                continue
            for f in sorted(role_dir.glob("*.txt")):
                name = f"{role_dir.name}/{f.stem}"
                content = f.read_text(encoding="utf-8")
                latest = conn.execute(
                    sa.text(
                        "SELECT content FROM prompt_versions WHERE name = :n "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"n": name},
                ).first()
                if latest is not None and latest[0] == content:
                    skipped += 1
                    continue
                if check_only:
                    drifted.append(name)
                    continue
                conn.execute(
                    sa.text(
                        "INSERT INTO prompt_versions (id, name, role, content, model_target, notes) "
                        "VALUES (gen_random_uuid(), :n, :r, :c, :m, :notes)"
                    ),
                    {
                        "n": name,
                        "r": role_dir.name,
                        "c": content,
                        "m": model_by_role[role_dir.name],
                        "notes": f"synced from {f.as_posix()}",
                    },
                )
                synced += 1
                print(f"synced {name}")
    if check_only:
        if drifted:
            print(f"DRIFT: {len(drifted)} prompt file(s) differ from the DB latest:")
            for name in drifted:
                print(f"  - {name}")
            sys.exit(1)
        print(f"no drift ({skipped} prompts match)")
        return
    print(f"\n{synced} inserted, {skipped} unchanged")


if __name__ == "__main__":
    main()
