import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from storage.database import get_database
from workspace.models import Workspace, WorkspaceCreate


class WorkspaceError(Exception):
    pass


def _generate_workspace_id(name: str) -> str:
    slug = name.lower().strip()

    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")

    if not slug:
        slug = "workspace"

    suffix = uuid.uuid4().hex[:8]

    return f"{slug}-{suffix}"


def create_workspace(data: WorkspaceCreate) -> Workspace:
    repo_path = Path(data.path).expanduser().resolve()

    if not repo_path.exists():
        raise WorkspaceError(
            f"Repository path does not exist: {repo_path}"
        )

    if not repo_path.is_dir():
        raise WorkspaceError(
            f"Repository path is not a directory: {repo_path}"
        )

    git_directory = repo_path / ".git"
    is_git_repo = git_directory.exists()

    workspace_id = _generate_workspace_id(data.name)

    created_at = datetime.now(timezone.utc).isoformat()

    with get_database() as database:
        existing = database.execute(
            "SELECT id FROM workspaces WHERE path = ?",
            (str(repo_path),),
        ).fetchone()

        if existing:
            raise WorkspaceError(
                f"This repository is already registered as workspace: "
                f"{existing['id']}"
            )

        database.execute(
            """
            INSERT INTO workspaces (
                id,
                name,
                path,
                is_git_repo,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                data.name.strip(),
                str(repo_path),
                int(is_git_repo),
                created_at,
            ),
        )

    return Workspace(
        id=workspace_id,
        name=data.name.strip(),
        path=str(repo_path),
        is_git_repo=is_git_repo,
        created_at=created_at,
    )


def list_workspaces() -> list[Workspace]:
    with get_database() as database:
        rows = database.execute(
            """
            SELECT
                id,
                name,
                path,
                is_git_repo,
                created_at
            FROM workspaces
            ORDER BY created_at ASC
            """
        ).fetchall()

    return [
        Workspace(
            id=row["id"],
            name=row["name"],
            path=row["path"],
            is_git_repo=bool(row["is_git_repo"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_workspace(workspace_id: str) -> Workspace | None:
    with get_database() as database:
        row = database.execute(
            """
            SELECT
                id,
                name,
                path,
                is_git_repo,
                created_at
            FROM workspaces
            WHERE id = ?
            """,
            (workspace_id,),
        ).fetchone()

    if row is None:
        return None

    return Workspace(
        id=row["id"],
        name=row["name"],
        path=row["path"],
        is_git_repo=bool(row["is_git_repo"]),
        created_at=row["created_at"],
    )


def delete_workspace(workspace_id: str) -> bool:
    with get_database() as database:
        cursor = database.execute(
            "DELETE FROM workspaces WHERE id = ?",
            (workspace_id,),
        )

        deleted = cursor.rowcount > 0

    return deleted
