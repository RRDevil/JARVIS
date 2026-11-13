"""Automated Test Suite for Persistent Preference and Workflow Memory (Phase 7)."""

import pytest
from app.memory.models import (
    PreferenceCategory,
    PreferenceSource,
    PreferenceType,
    UserPreference,
)
from app.memory.service import PreferenceService
from app.memory.store import (
    MemoryPrivacyViolation,
    PreferenceMemoryStore,
)
from app.memory.tools import (
    PreferenceQueryParams,
    PreferenceQueryTool,
    PreferenceStoreParams,
    PreferenceStoreTool,
)
from app.tools.base import ExecutionContext


@pytest.fixture
def temp_store(tmp_path):
    """Provide isolated SQLite store in temporary directory."""
    db_file = tmp_path / "test_memory.db"
    store = PreferenceMemoryStore(db_path=db_file)
    return store


@pytest.fixture
def pref_service(temp_store):
    """Provide PreferenceService bound to isolated temporary store."""
    return PreferenceService(store=temp_store)


def test_preference_crud_and_persistence(temp_store):
    """Verify structured preference records can be inserted, retrieved, and deleted."""
    pref = UserPreference(
        id="pref-test-1",
        category=PreferenceCategory.PERSON_COMMUNICATIONS,
        preference_key="person:sarah",
        app_id="messaging.whatsapp",
        browser_id="browser.opera_gx",
        target_entity="sarah",
        confidence=1.0,
        user_confirmed=True,
    )
    temp_store.save_preference(pref)

    # Fetch by ID
    retrieved = temp_store.get_preference("pref-test-1")
    assert retrieved is not None
    assert retrieved.preference_key == "person:sarah"
    assert retrieved.app_id == "messaging.whatsapp"
    assert retrieved.browser_id == "browser.opera_gx"

    # Fetch by key
    by_key = temp_store.get_by_key("person:sarah", category=PreferenceCategory.PERSON_COMMUNICATIONS)
    assert by_key is not None
    assert by_key.id == "pref-test-1"

    # Delete
    deleted = temp_store.delete_preference("pref-test-1")
    assert deleted is True
    assert temp_store.get_preference("pref-test-1") is None


def test_privacy_enforcement_blocks_credentials(temp_store):
    """Verify that credentials, passwords, and tokens are strictly rejected from memory."""
    with pytest.raises(MemoryPrivacyViolation):
        pref = UserPreference(
            id="pref-secret",
            category=PreferenceCategory.GLOBAL_DEFAULTS,
            preference_key="account:test",
            details={"password": "MySuperSecretPassword123"},
        )
        temp_store.save_preference(pref)

    with pytest.raises(MemoryPrivacyViolation):
        pref = UserPreference(
            id="pref-token",
            category=PreferenceCategory.GLOBAL_DEFAULTS,
            preference_key="account:test",
            details={"auth_token": "bearer eyJhbGciOiJIUzI1NiIs..."},
        )
        temp_store.save_preference(pref)


def test_5_tier_resolution_hierarchy(pref_service):
    """Verify the strict 5-tier resolution priority:
    1. Explicit Request > 2. Person/Website > 3. Workflow > 4. Global Default > 5. System Fallback
    """
    # Set up memory store
    pref_service.set_explicit_preference(
        category=PreferenceCategory.GLOBAL_DEFAULTS,
        key="default:browser",
        app_id="browser.chrome",
        browser_id="browser.chrome",
    )
    pref_service.set_explicit_preference(
        category=PreferenceCategory.WEBSITE_BROWSERS,
        key="domain:instagram.com",
        app_id="browser.opera_gx",
        browser_id="browser.opera_gx",
        target_entity="instagram.com",
    )
    pref_service.set_explicit_preference(
        category=PreferenceCategory.PERSON_COMMUNICATIONS,
        key="person:alex",
        app_id="messaging.whatsapp",
        browser_id="browser.opera_gx",
        target_entity="alex",
    )

    # Test Tier 1: Explicit prompt instruction overrides saved memory
    res_tier1 = pref_service.resolve_application(
        explicit_request="Open in Chrome",
        website_domain="instagram.com",
    )
    assert res_tier1.resolved_browser_id == "browser.chrome"
    assert res_tier1.resolution_source == "explicit_request"

    # Test Tier 2: Per-website preference overrides global default
    res_tier2_site = pref_service.resolve_application(
        website_domain="instagram.com",
        workflow_type="browse",
    )
    assert res_tier2_site.resolved_browser_id == "browser.opera_gx"
    assert res_tier2_site.resolution_source == "website_preference"

    # Test Tier 2 (cont): Per-person preference
    res_tier2_person = pref_service.resolve_application(
        person_name="alex",
        workflow_type="messaging",
    )
    assert res_tier2_person.resolved_app_id == "messaging.whatsapp"
    assert res_tier2_person.resolved_browser_id == "browser.opera_gx"
    assert res_tier2_person.resolution_source == "person_preference"

    # Test Tier 4: Global default applies when no person or site preference matches
    res_tier4 = pref_service.resolve_application(
        website_domain="wikipedia.org",
        workflow_type="browse",
    )
    assert res_tier4.resolved_browser_id == "browser.chrome"
    assert res_tier4.resolution_source == "global_default"

    # Test Tier 5: System fallback applies when no preferences exist
    res_tier5 = pref_service.resolve_application(
        workflow_type="messaging",
        person_name="unknown_person",
    )
    assert res_tier5.resolution_source == "system_fallback"
    assert res_tier5.requires_confirmation is True


def test_disabled_memory_bypasses_persistence(pref_service):
    """Verify that disabling memory ignores saved preferences and uses safe defaults."""
    pref_service.set_explicit_preference(
        category=PreferenceCategory.PERSON_COMMUNICATIONS,
        key="person:bob",
        app_id="messaging.discord",
        target_entity="bob",
    )
    pref_service.set_memory_enabled(False)

    res = pref_service.resolve_application(person_name="bob", workflow_type="messaging")
    assert res.resolution_source == "system_fallback"
    assert res.preference_match is None


@pytest.mark.asyncio
async def test_preference_tools_execution(pref_service):
    """Verify BaseTool execution for preference_query and preference_store."""
    from app.memory.service import preference_service as global_pref_service

    store_tool = PreferenceStoreTool()
    query_tool = PreferenceQueryTool()
    ctx = ExecutionContext(execution_id="test-pref-exec")

    # Store preference via tool
    res_store = await store_tool.execute(
        PreferenceStoreParams(
            category="person_communications",
            key="person:charlie",
            app_id="messaging.whatsapp",
            target_entity="charlie",
            browser_id="browser.opera_gx",
        ),
        ctx,
    )
    assert res_store.success is True
    assert res_store.data["app_id"] == "messaging.whatsapp"

    # Query preference via tool
    res_query = await query_tool.execute(
        PreferenceQueryParams(person_name="charlie", workflow_type="messaging"),
        ctx,
    )
    assert res_query.success is True
    assert res_query.data["resolved_app_id"] == "messaging.whatsapp"
    assert res_query.data["resolution_source"] == "person_preference"
