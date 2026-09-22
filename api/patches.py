from fastapi import (
    APIRouter,
    HTTPException,
)

from patching.models import (
    PatchRequest,
    PatchResponse,
    PatchStatus,
)

from patching.service import (
    create_patch,
    get_patch,
)

from llm.provider import (
    LLMError,
)

from patching.worktree import (
    WorktreeError,
)

from workspace.manager import (
    WorkspaceError,
)


router = APIRouter(
    tags=["Safe Patching"],
)


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

    except RuntimeError as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


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
            detail="Patch not found.",
        )

    return result
