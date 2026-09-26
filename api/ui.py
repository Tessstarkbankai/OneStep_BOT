from pathlib import Path

from fastapi import (
    APIRouter,
    HTTPException,
)

from fastapi.responses import (
    FileResponse,
)


router = APIRouter(
    tags=[
        "UI",
    ],
)


BASE_DIR = Path(
    __file__
).resolve().parent.parent


UI_DIR = (
    BASE_DIR
    / "ui"
).resolve()


def _index_file() -> Path:

    return (
        UI_DIR
        / "index.html"
    )


@router.api_route(
    "/dashboard",
    methods=[
        "GET",
        "HEAD",
    ],
    include_in_schema=False,
)
def dashboard():

    index_file = _index_file()

    if not index_file.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                "OutrightBot UI is "
                "not installed."
            ),
        )

    return FileResponse(
        index_file
    )


@router.api_route(
    "/dashboard/",
    methods=[
        "GET",
        "HEAD",
    ],
    include_in_schema=False,
)
def dashboard_slash():

    index_file = _index_file()

    if not index_file.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                "OutrightBot UI is "
                "not installed."
            ),
        )

    return FileResponse(
        index_file
    )


@router.api_route(
    "/dashboard/{asset_path:path}",
    methods=[
        "GET",
        "HEAD",
    ],
    include_in_schema=False,
)
def dashboard_asset(
    asset_path: str,
):

    target = (
        UI_DIR
        / asset_path
    ).resolve()

    #
    # Prevent paths such as:
    #
    # /dashboard/../../storage/database.py
    #
    try:

        target.relative_to(
            UI_DIR
        )

    except ValueError:

        raise HTTPException(
            status_code=404,
            detail=(
                "Asset not found."
            ),
        )

    if (
        not target.exists()
        or not target.is_file()
    ):

        raise HTTPException(
            status_code=404,
            detail=(
                "Asset not found."
            ),
        )

    return FileResponse(
        target
    )