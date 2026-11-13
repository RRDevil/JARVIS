"""Tests for Phase 5 UI Element Grounding Engine."""

import pytest
from app.automation.factory import get_platform_adapter, set_platform_adapter
from app.automation.mock_adapter import MockPlatformAdapter
from app.perception.grounding import (
    AmbiguousTargetError,
    TargetNotFoundError,
    UIElementGroundingEngine,
    grounding_engine,
)
from app.perception.models import (
    BoundingBox,
    ElementBoundingBox,
    ElementSource,
    ElementType,
    GroundedUIElement,
    LocateElementsRequest,
    OCRLine,
    OCRWord,
    PointCoordinate,
)


@pytest.fixture(autouse=True)
def setup_mock_adapter():
    """Ensure mock platform adapter is active for all grounding tests."""
    mock = MockPlatformAdapter()
    set_platform_adapter(mock)
    yield mock
    set_platform_adapter(None)


def test_infer_element_type():
    engine = UIElementGroundingEngine()
    assert engine._infer_element_type("Button", "Submit") == ElementType.BUTTON
    assert engine._infer_element_type("Button", "Remember Me Checkbox") == ElementType.CHECKBOX
    assert engine._infer_element_type("Edit", "Search query") == ElementType.SEARCH_BAR
    assert engine._infer_element_type("Edit", "Username") == ElementType.TEXT_FIELD
    assert engine._infer_element_type("SysTabControl32", "General") == ElementType.TAB
    assert engine._infer_element_type("Static", "Save") == ElementType.BUTTON


def test_discover_uia_elements(setup_mock_adapter):
    engine = UIElementGroundingEngine()
    # Discover controls in mock window 1003 (Notepad)
    elements = engine.discover_uia_elements(window_handle=1003)
    assert len(elements) >= 3

    types = [e.element_type for e in elements]
    assert ElementType.BUTTON in types
    assert ElementType.TEXT_FIELD in types

    save_btn = next((e for e in elements if "Save" in e.text), None)
    assert save_btn is not None
    assert save_btn.source == ElementSource.UIA
    assert save_btn.bounding_box.width > 0
    assert save_btn.center.x == save_btn.bounding_box.left + save_btn.bounding_box.width // 2


def test_discover_ocr_elements():
    engine = UIElementGroundingEngine()
    ocr_lines = [
        OCRLine(
            text="Confirm Order",
            words=[
                OCRWord(text="Confirm", bounding_box=BoundingBox(x=120, y=200, width=50, height=20)),
                OCRWord(text="Order", bounding_box=BoundingBox(x=175, y=200, width=45, height=20)),
            ],
        ),
        OCRLine(
            text="Cancel",
            words=[
                OCRWord(text="Cancel", bounding_box=BoundingBox(x=240, y=200, width=45, height=20)),
            ],
        ),
    ]

    elements = engine.discover_ocr_elements(
        ocr_lines=ocr_lines,
        screen_left=0,
        screen_top=0,
        window_title="Checkout Window",
    )

    assert len(elements) == 2
    confirm_el = next(e for e in elements if "Confirm Order" in e.text)
    assert confirm_el.source == ElementSource.OCR
    assert confirm_el.center.x == 170
    assert confirm_el.center.y == 200 + 20 // 2


def test_fuse_elements():
    engine = UIElementGroundingEngine()
    now_iso = "2026-11-05T00:00:00Z"

    uia_elem = GroundedUIElement(
        element_id="elem-uia-1",
        description="Window Control (pane)",
        text="",  # Unlabeled Win32 pane
        element_type=ElementType.BUTTON,
        bounding_box=ElementBoundingBox(left=100, top=100, width=150, height=40),
        center=PointCoordinate(x=175, y=120),
        confidence=0.9,
        is_interactable=True,
        source=ElementSource.UIA,
        timestamp=now_iso,
    )

    ocr_elem = GroundedUIElement(
        element_id="elem-ocr-1",
        description="'Submit' (generic_clickable)",
        text="Submit",
        element_type=ElementType.GENERIC_CLICKABLE,
        bounding_box=ElementBoundingBox(left=110, top=105, width=60, height=25),
        center=PointCoordinate(x=140, y=117),  # Inside uia_elem bounds!
        confidence=0.85,
        is_interactable=True,
        source=ElementSource.OCR,
        timestamp=now_iso,
    )

    unrelated_ocr = GroundedUIElement(
        element_id="elem-ocr-2",
        description="'Help' (generic_clickable)",
        text="Help",
        element_type=ElementType.GENERIC_CLICKABLE,
        bounding_box=ElementBoundingBox(left=500, top=500, width=40, height=20),
        center=PointCoordinate(x=520, y=510),
        confidence=0.85,
        is_interactable=True,
        source=ElementSource.OCR,
        timestamp=now_iso,
    )

    fused = engine.fuse_elements([uia_elem], [ocr_elem, unrelated_ocr])
    # Should fuse uia_elem and ocr_elem into a HYBRID element, plus unrelated_ocr
    assert len(fused) == 2
    hybrid_elem = next(e for e in fused if e.element_id == "elem-uia-1")
    assert hybrid_elem.source == ElementSource.HYBRID
    assert hybrid_elem.text == "Submit"


def test_match_element_success():
    engine = UIElementGroundingEngine()
    now_iso = "2026-11-05T00:00:00Z"

    elements = [
        GroundedUIElement(
            element_id="elem-1",
            description="Save Document (button)",
            text="Save",
            element_type=ElementType.BUTTON,
            bounding_box=ElementBoundingBox(left=100, top=100, width=80, height=30),
            center=PointCoordinate(x=140, y=115),
            confidence=0.95,
            is_interactable=True,
            source=ElementSource.UIA,
            timestamp=now_iso,
        ),
        GroundedUIElement(
            element_id="elem-2",
            description="Cancel (button)",
            text="Cancel",
            element_type=ElementType.BUTTON,
            bounding_box=ElementBoundingBox(left=200, top=100, width=80, height=30),
            center=PointCoordinate(x=240, y=115),
            confidence=0.95,
            is_interactable=True,
            source=ElementSource.UIA,
            timestamp=now_iso,
        ),
    ]

    matched, score = engine.match_element("click the Save button", elements)
    assert matched.element_id == "elem-1"
    assert score >= 0.85


def test_match_element_not_found():
    engine = UIElementGroundingEngine()
    now_iso = "2026-11-05T00:00:00Z"
    elements = [
        GroundedUIElement(
            element_id="elem-1",
            description="Exit (button)",
            text="Exit",
            element_type=ElementType.BUTTON,
            bounding_box=ElementBoundingBox(left=10, top=10, width=50, height=20),
            center=PointCoordinate(x=35, y=20),
            confidence=0.9,
            is_interactable=True,
            source=ElementSource.UIA,
            timestamp=now_iso,
        )
    ]

    with pytest.raises(TargetNotFoundError):
        engine.match_element("Download Invoice", elements)


def test_match_element_ambiguity_rejection():
    engine = UIElementGroundingEngine()
    now_iso = "2026-11-05T00:00:00Z"

    # Two identical unlabeled generic buttons with same score
    elements = [
        GroundedUIElement(
            element_id="elem-1",
            description="Open (button)",
            text="Open",
            element_type=ElementType.BUTTON,
            bounding_box=ElementBoundingBox(left=50, top=50, width=60, height=25),
            center=PointCoordinate(x=80, y=62),
            confidence=0.8,
            is_interactable=True,
            source=ElementSource.OCR,
            timestamp=now_iso,
        ),
        GroundedUIElement(
            element_id="elem-2",
            description="Open (button)",
            text="Open",
            element_type=ElementType.BUTTON,
            bounding_box=ElementBoundingBox(left=50, top=200, width=60, height=25),
            center=PointCoordinate(x=80, y=212),
            confidence=0.8,
            is_interactable=True,
            source=ElementSource.OCR,
            timestamp=now_iso,
        ),
    ]

    with pytest.raises(AmbiguousTargetError) as exc_info:
        engine.match_element("Open", elements)

    assert len(exc_info.value.candidates) == 2
