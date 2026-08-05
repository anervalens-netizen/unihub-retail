from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from routers.filters import clear_filter_options_cache
from routers.visits_report import get_visit_photo


def test_clear_filter_options_cache_is_safe() -> None:
    clear_filter_options_cache()
    clear_filter_options_cache()


def visit_service(images_dir: Path, photos: list[str]) -> MagicMock:
    service = MagicMock()
    service.get_visit_detail = AsyncMock(return_value=SimpleNamespace(photos=photos))
    service.images_dir_path.return_value = images_dir
    service.photo_path.side_effect = lambda visit_id, filename: images_dir / visit_id / filename
    return service


@pytest.mark.asyncio
async def test_visit_photo_is_bound_to_visit_and_regular_contained_file(tmp_path: Path) -> None:
    images = tmp_path / "images"
    visit_dir = images / "visit-1"
    visit_dir.mkdir(parents=True)
    photo = visit_dir / "photo.jpg"
    photo.write_bytes(b"image")
    service = visit_service(images, ["photo.jpg"])

    response = await get_visit_photo("visit-1", "photo.jpg", service)

    assert Path(response.path) == photo
    service.get_visit_detail.assert_awaited_once_with("visit-1")


@pytest.mark.asyncio
async def test_visit_photo_rejects_unbound_or_symlink_file(tmp_path: Path) -> None:
    images = tmp_path / "images"
    visit_dir = images / "visit-1"
    visit_dir.mkdir(parents=True)
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"image")
    (visit_dir / "linked.jpg").symlink_to(outside)

    unbound = visit_service(images, [])
    with pytest.raises(HTTPException) as unbound_error:
        await get_visit_photo("visit-1", "linked.jpg", unbound)
    assert unbound_error.value.status_code == 404

    linked = visit_service(images, ["linked.jpg"])
    with pytest.raises(HTTPException) as linked_error:
        await get_visit_photo("visit-1", "linked.jpg", linked)
    assert linked_error.value.status_code == 404
