import base64

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.schemas import LunaRefineRequest


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl3nwAAAABJRU5ErkJggg=="
)


def data_url(content: bytes, image_type: str = "png") -> str:
    return f"data:image/{image_type};base64,{base64.b64encode(content).decode('ascii')}"


def request(**changes) -> LunaRefineRequest:
    return LunaRefineRequest(instruction="Rends le bouton plus visible", **changes)


def test_capture_and_attachments_are_bounded_valid_images():
    capture = data_url(PNG_BYTES)
    parsed = request(
        screenshot_data_url=capture,
        images=[capture],
        region="hero",
        selection_rect={"x": 10, "y": 15, "width": 30, "height": 20},
    )
    assert parsed.screenshot_data_url == capture
    assert parsed.images == [capture]
    assert parsed.selection_rect.x == 10


@pytest.mark.parametrize("value", [
    "data:image/svg+xml;base64,PHN2Zz4=",
    "data:image/png;base64,aGVsbG8=",
    "data:image/png;base64,@@@@",
    "data:image/png;base64,iVBORw0KGgo=",
    "https://example.fr/image.png",
])
def test_capture_rejects_wrong_format_or_content(value):
    with pytest.raises(ValidationError):
        request(screenshot_data_url=value)


def test_attachment_has_its_own_byte_limit():
    oversized = data_url(PNG_BYTES + b"x" * 2_000_000)
    with pytest.raises(ValidationError, match="volumineuse"):
        request(images=[oversized])


def test_total_payload_is_bounded(monkeypatch):
    from app import schemas

    monkeypatch.setattr(schemas, "MAX_TOTAL_IMAGE_BYTES", len(PNG_BYTES) * 2 - 1)
    with pytest.raises(ValidationError, match="ensemble"):
        request(screenshot_data_url=data_url(PNG_BYTES), images=[data_url(PNG_BYTES)])


def test_selection_rectangle_stays_inside_page():
    with pytest.raises(ValidationError, match="rectangle"):
        request(selection_rect={"x": 90, "y": 10, "width": 20, "height": 20})


def test_version_keeps_capture_and_attachments_after_reload():
    from app.models import Base, FormVersion

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    capture = data_url(PNG_BYTES)
    with Session(engine) as db:
        db.add(FormVersion(form_id="form1", snapshot={"html": "<html></html>"}, screenshot_data_url=capture, images=[capture]))
        db.commit()
    with Session(engine) as db:
        version = db.scalar(select(FormVersion))
        assert version.screenshot_data_url == capture
        assert version.images == [capture]
    engine.dispose()
