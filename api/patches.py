from fastapi import (
    APIRouter,
    HTTPException,
)

from llm.provider import (
    LLMError,
)

from patching.lifecycle import (
    cleanup_patch,
    list_workspace_patches,
    reconcile_patch,
    reconcile_workspace_patches,
)

from patching.models import (
    PatchDecisionResponse,
    PatchHistoryItem,
    PatchHistoryResponse,
    PatchReconcileResponse,
    PatchRequest,
    PatchResponse,
    PatchStatus,
)

from patching.service import (
    approve_patch,
    create_patch,
    get_patch,
    reject_patch,
)

from patching.worktree import (
    WorktreeError,
)

from workspace.manager import (
    WorkspaceError,
)


router = APIRouter(
    tags=[
        "Safe Patching",
    ],
)


# ============================================================
# PATCH HISTORY
# ============================================================


@router.get(
    "/api/workspaces/"
    "{workspace_id}/patches",
    response_model=(
        PatchHistoryResponse
    ),
)
def api_list_patches(
    workspace_id: str,
    limit: int = 50,
):

    patches = (
        list_workspace_patches(
            workspace_id,
            limit=limit,
        )
    )

    return PatchHistoryResponse(
        workspace_id=workspace_id,
        patches=patches,
    )


# ============================================================
# WORKSPACE PATCH RECONCILIATION
# ============================================================


@router.post(
    "/api/workspaces/"
    "{workspace_id}/patches/"
    "reconcile",
    response_model=(
        PatchReconcileResponse
    ),
)
def api_reconcile_patches(
    workspace_id: str,
):

    try:

        patches = (
            reconcile_workspace_patches(
                workspace_id
            )
        )

        return PatchReconcileResponse(
            workspace_id=(
                workspace_id
            ),
            checked=len(
                patches
            ),
            patches=patches,
        )

    except RuntimeError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# ============================================================
# SINGLE PATCH RECONCILIATION
# ============================================================


@router.post(
    "/api/patches/"
    "{patch_id}/reconcile",
    response_model=(
        PatchHistoryItem
    ),
)
def api_reconcile_patch(
    patch_id: str,
):

    try:

        return reconcile_patch(
            patch_id
        )

    except RuntimeError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# ============================================================
# PATCH CLEANUP
# ============================================================


@router.post(
    "/api/patches/"
    "{patch_id}/cleanup",
    response_model=(
        PatchHistoryItem
    ),
)
def api_cleanup_patch(
    patch_id: str,
):

    try:

        return cleanup_patch(
            patch_id
        )

    except RuntimeError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# ============================================================
# APPROVE PATCH
# ============================================================


@router.post(
    "/api/patches/"
    "{patch_id}/approve",
    response_model=(
        PatchDecisionResponse
    ),
)
def api_approve_patch(
    patch_id: str,
):

    try:

        return approve_patch(
            patch_id
        )

    except WorkspaceError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except WorktreeError as error:

        raise HTTPException(
            status_code=409,
            detail=str(error),
        )

    except RuntimeError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# ============================================================
# REJECT PATCH
# ============================================================


@router.post(
    "/api/patches/"
    "{patch_id}/reject",
    response_model=(
        PatchDecisionResponse
    ),
)
def api_reject_patch(
    patch_id: str,
):

    try:

        return reject_patch(
            patch_id
        )

    except WorkspaceError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except WorktreeError as error:

        raise HTTPException(
            status_code=409,
            detail=str(error),
        )

    except RuntimeError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# ============================================================
# CREATE PATCH
# ============================================================


@router.post(
    "/api/workspaces/"
    "{workspace_id}/patches",
    response_model=(
        PatchResponse
    ),
)
def api_create_patch(
    workspace_id: str,
    request: PatchRequest,
):

    try:

        return create_patch(
            workspace_id=(
                workspace_id
            ),
            task=request.task,
            max_files=(
                request.max_files
            ),
            use_semantic=(
                request.use_semantic
            ),
        )

    except WorkspaceError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except WorktreeError as error:

        raise HTTPException(
            status_code=409,
            detail=str(error),
        )

    except LLMError as error:

        raise HTTPException(
            status_code=502,
            detail=str(error),
        )

    except (RuntimeError, ValueError) as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


# ============================================================
# GET PATCH
# ============================================================


@router.get(
    "/api/patches/{patch_id}",
    response_model=(
        PatchStatus
    ),
)
def api_get_patch(
    patch_id: str,
):

    result = get_patch(
        patch_id
    )

    if result is None:

        raise HTTPException(
            status_code=404,
            detail=(
                "Patch not found."
            ),
        )

    return result