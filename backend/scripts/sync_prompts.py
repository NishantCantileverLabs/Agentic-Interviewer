"""Mirror /prompts files into prompt_versions (invariant D7).

    python scripts/sync_prompts.py [prompts_dir]

File naming: prompts/<role>/<name>_v<N>.txt -> prompt_versions.name = "<role>/<name>_v<N>".
Idempotent: a row is inserted only when (name, content) isn't already recorded;
edited content under the same filename gets a fresh row (audit trail preserved).
"""

import pathlib
import sys

import sqlalchemy as sa

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.config import get_settings  # noqa: E402

ROLES = {"conduct", "evaluate", "brief"}


def main() -> None:
    root = (
        pathlib.Path(sys.argv[1])
        if len(sys.argv) > 1
        else pathlib.Path(__file__).parent.parent.parent / "prompts"
    )
    settings = get_settings()
    model_by_role = {
        "conduct": settings.conduct_model,
        "evaluate": settings.eval_model,
        "brief": settings.eval_model,
    }
    engine = sa.create_engine(settings.database_url.replace("@postgres:", "@localhost:"))

    synced = skipped = 0
    with engine.begin() as conn:
        for role_dir in sorted(root.iterdir()):
            if role_dir.name not in ROLES or not role_dir.is_dir():
                continue
            for f in sorted(role_dir.glob("*.txt")):
                name = f"{role_dir.name}/{f.stem}"
                content = f.read_text(encoding="utf-8")
                exists = conn.execute(
                    sa.text(
                        "SELECT 1 FROM prompt_versions WHERE name = :n AND content = :c"
                    ),
                    {"n": name, "c": content},
                ).first()
                if exists:
                    skipped += 1
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
    print(f"\n{synced} inserted, {skipped} unchanged")


if __name__ == "__main__":
    main()
