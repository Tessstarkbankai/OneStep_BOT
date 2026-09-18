from fastapi import APIRouter, HTTPException, Query

from workspace.scanner import (
    list_repository_files,
    scan_workspace,
)

from workspace.manager import (
    WorkspaceError,
    create_workspace,
    delete_workspace,
    get_workspace,
    list_workspaces,
)
from workspace.models import Workspace, WorkspaceCreate


router = APIRouter(
    prefix="/api/workspaces",
    tags=["Workspaces"],
)


@router.get("", response_model=list[Workspace])
def api_list_workspaces():
    return list_workspaces()


@router.post("", response_model=Workspace)
def api_create_workspace(data: WorkspaceCreate):
    try:
        return create_workspace(data)

    except WorkspaceError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get("/{workspace_id}", response_model=Workspace)
def api_get_workspace(workspace_id: str):
    workspace = get_workspace(workspace_id)

    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found",
        )

    return workspace
@router.post("/{workspace_id}/scan")
def api_scan_workspace(workspace_id: str):
    try:
        return scan_workspace(workspace_id)

    except WorkspaceError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.get("/{workspace_id}/files")
def api_list_repository_files(
    workspace_id: str,
    source_only: bool = False,
    limit: int = Query(
        default=500,
        ge=1,
        le=5000,
    ),
):
    try:
        return list_repository_files(
            workspace_id=workspace_id,
            source_only=source_only,
            limit=limit,
        )

    except WorkspaceError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

@router.delete("/{workspace_id}")
def api_delete_workspace(workspace_id: str):
    deleted = delete_workspace(workspace_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found",
        )

    return {
        "status": "deleted",
        "workspace_id": workspace_id,
    }
