"""Comprehensive Unit and Integration Tests for Phase 5.2 Application Integration Framework."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.integrations.models import (
    AppCategory,
    ProviderType,
    PermissionLevel,
    IntegrationHealth,
    ApplicationManifest,
    CapabilitySpec,
    ProcessRule,
    ActionApprovalBinding,
)
from app.integrations.registry import application_registry
from app.integrations.permissions import integration_permissions
from app.integrations.manager import application_manager
from app.integrations.discovery import application_discovery_engine
from app.tools.base import RiskTier, PolicyDecision


@pytest.fixture
def client():
    return TestClient(app)


class TestApplicationRegistryAndManifests:
    """Verify built-in default manifests and registration."""

    def test_default_manifests_registered(self):
        apps = application_registry.list_all()
        app_ids = {a.app_id for a in apps}

        # Browsers
        assert "browser.opera_gx" in app_ids
        assert "browser.chrome" in app_ids

        # Office
        assert "office.word" in app_ids
        assert "office.excel" in app_ids
        assert "office.powerpoint" in app_ids
        assert "office.outlook" in app_ids

        # Messaging
        assert "messaging.discord" in app_ids
        assert "messaging.whatsapp" in app_ids

    def test_opera_gx_manifest_structure(self):
        opera = application_registry.get("browser.opera_gx")
        assert opera is not None
        assert opera.category == AppCategory.BROWSER
        assert "opera.exe" in opera.process_rule.executable_names
        assert ProviderType.BROWSER_AUTOMATION in opera.supported_providers
        assert ProviderType.DESKTOP_UI in opera.supported_providers

        # Verify key capabilities
        cap_ids = {c.id for c in opera.capabilities}
        assert "browser.navigate" in cap_ids
        assert "browser.read_page" in cap_ids
        assert "browser.manage_tabs" in cap_ids

    def test_office_word_manifest_structure(self):
        word = application_registry.get("office.word")
        assert word is not None
        assert word.category == AppCategory.OFFICE
        assert ProviderType.OFFICE_COM in word.supported_providers
        assert ProviderType.DESKTOP_UI in word.supported_providers

        cap_ids = {c.id for c in word.capabilities}
        assert "word.read_document" in cap_ids
        assert "word.create_document" in cap_ids
        assert "word.edit_text" in cap_ids

    def test_discord_manifest_structure(self):
        discord = application_registry.get("messaging.discord")
        assert discord is not None
        assert discord.category == AppCategory.MESSAGING
        cap_ids = {c.id for c in discord.capabilities}
        assert "discord.read_messages" in cap_ids
        assert "discord.send_message" in cap_ids


class TestPermissionsAndApprovalBinding:
    """Verify Level 1-4 permission enforcement and cryptographic approval binding."""

    def test_permission_level_defaults(self):
        # Read-only capability (Level 1)
        manifest = application_manager.get_application("browser.opera_gx")
        read_cap = next(c for c in manifest.capabilities if c.id == "browser.read_page")
        assert read_cap.permission_level == PermissionLevel.READ_ONLY
        decision, reason, binding = integration_permissions.evaluate_capability(
            manifest=manifest,
            capability=read_cap,
            provider=ProviderType.BROWSER_AUTOMATION,
            parameters={},
        )
        assert decision == PolicyDecision.ALLOW_AUTO
        assert binding is None

        # Consequential capability (Level 3 - e.g. send message)
        disc_manifest = application_manager.get_application("messaging.discord")
        send_cap = next(c for c in disc_manifest.capabilities if c.id == "discord.send_message")
        assert send_cap.permission_level == PermissionLevel.CONSEQUENTIAL
        decision, reason, binding = integration_permissions.evaluate_capability(
            manifest=disc_manifest,
            capability=send_cap,
            provider=ProviderType.DESKTOP_UI,
            parameters={"recipient": "#general", "message": "Hi"},
        )
        assert decision == PolicyDecision.REQUIRE_APPROVAL
        assert binding is not None

    def test_app_and_capability_disable_override(self):
        manifest = application_manager.get_application("browser.opera_gx")
        cap = next(c for c in manifest.capabilities if c.id == "browser.navigate")

        # Initially permitted
        decision, _, _ = integration_permissions.evaluate_capability(
            manifest, cap, ProviderType.BROWSER_AUTOMATION, {"url": "https://example.com"}
        )
        assert decision == PolicyDecision.ALLOW_AUTO

        # Disable capability
        integration_permissions.set_capability_enabled(manifest.app_id, cap.id, False)
        decision, reason, _ = integration_permissions.evaluate_capability(
            manifest, cap, ProviderType.BROWSER_AUTOMATION, {"url": "https://example.com"}
        )
        assert decision == PolicyDecision.BLOCK
        assert "disabled" in reason

        # Re-enable capability
        integration_permissions.set_capability_enabled(manifest.app_id, cap.id, True)
        decision, _, _ = integration_permissions.evaluate_capability(
            manifest, cap, ProviderType.BROWSER_AUTOMATION, {"url": "https://example.com"}
        )
        assert decision == PolicyDecision.ALLOW_AUTO

        # Disable whole application
        integration_permissions.set_app_enabled(manifest.app_id, False)
        decision, reason, _ = integration_permissions.evaluate_capability(
            manifest, cap, ProviderType.BROWSER_AUTOMATION, {"url": "https://example.com"}
        )
        assert decision == PolicyDecision.BLOCK

        # Reset
        integration_permissions.set_app_enabled(manifest.app_id, True)

    def test_cryptographic_approval_binding(self):
        disc_manifest = application_manager.get_application("messaging.discord")
        send_cap = next(c for c in disc_manifest.capabilities if c.id == "discord.send_message")

        # Create approval binding for sending a message
        binding = integration_permissions.create_approval_binding(
            app_id="messaging.discord",
            capability=send_cap,
            parameters={"recipient": "#general", "message": "Hello Team"},
        )
        assert binding.binding_id is not None
        assert len(binding.content_hash) == 64  # SHA-256

        # Valid verification with exact matching parameters
        is_valid, reason = integration_permissions.verify_approval_binding(
            binding.binding_id,
            current_parameters={"recipient": "#general", "message": "Hello Team"},
        )
        assert is_valid is True
        assert "verified" in reason.lower()

        # Replay protection: attempting to reuse already consumed binding fails
        is_valid_reused, err_reused = integration_permissions.verify_approval_binding(
            binding.binding_id,
            current_parameters={"recipient": "#general", "message": "Hello Team"},
        )
        assert is_valid_reused is False
        assert "consumed" in err_reused.lower()

        # Tampered parameter verification failure on fresh binding
        fresh_binding = integration_permissions.create_approval_binding(
            app_id="messaging.discord",
            capability=send_cap,
            parameters={"recipient": "#general", "message": "Hello Team"},
        )
        is_valid, err = integration_permissions.verify_approval_binding(
            fresh_binding.binding_id,
            current_parameters={"recipient": "#general", "message": "Malicious Tampered Content!"},
        )
        assert is_valid is False
        assert "changed" in err.lower() or "invalidated" in err.lower()


class TestIntegrationExecutionManager:
    """Verify execution engine routing and fallback."""

    @pytest.mark.asyncio
    async def test_execute_read_only_capability(self):
        manifest = application_manager.get_application("browser.opera_gx")
        manifest.is_installed = True
        browser_provider = application_manager._providers[ProviderType.BROWSER_AUTOMATION]
        with patch.object(
            browser_provider,
            "execute_capability",
            new_callable=AsyncMock,
        ) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "url": "https://example.com",
                "title": "Example Domain",
            }

            resp = await application_manager.execute_capability(
                app_id="browser.opera_gx",
                capability_id="browser.read_page",
                parameters={},
                preferred_provider=ProviderType.BROWSER_AUTOMATION,
            )
            assert resp.success is True
            assert resp.provider_used == ProviderType.BROWSER_AUTOMATION
            assert resp.result["title"] == "Example Domain"

    @pytest.mark.asyncio
    async def test_execute_consequential_requires_approval(self):
        resp = await application_manager.execute_capability(
            app_id="messaging.discord",
            capability_id="discord.send_message",
            parameters={"recipient": "dev-chat", "message": "Testing Phase 5.2"},
        )
        assert resp.success is False
        assert resp.approval_required is True
        assert resp.approval_id is not None
        assert "Discord" in (resp.action_summary or "")

    @pytest.mark.asyncio
    async def test_fallback_provider_execution(self):
        # If Office COM fails, fall back to Desktop UI
        word_manifest = application_manager.get_application("office.word")
        word_manifest.is_installed = True
        with patch.object(
            application_manager._providers[ProviderType.OFFICE_COM],
            "execute_capability",
            side_effect=RuntimeError("COM Server Busy"),
            new_callable=AsyncMock,
        ), patch.object(
            application_manager._providers[ProviderType.DESKTOP_UI],
            "execute_capability",
            return_value={"success": True, "result": "Extracted via Desktop UI OCR"},
            new_callable=AsyncMock,
        ):
            resp = await application_manager.execute_capability(
                app_id="office.word",
                capability_id="word.read_document",
                parameters={},
            )
            assert resp.success is True
            assert resp.provider_used == ProviderType.DESKTOP_UI


class TestIntegrationsRestApi:
    """Verify REST API endpoints under /api/v1/integrations/."""

    def test_list_applications_endpoint(self, client):
        res = client.get("/api/v1/integrations/applications")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 8

    def test_get_application_endpoint(self, client):
        res = client.get("/api/v1/integrations/applications/browser.opera_gx")
        assert res.status_code == 200
        data = res.json()
        assert data["app_id"] == "browser.opera_gx"
        assert data["display_name"] == "Opera GX"

    def test_get_nonexistent_application_404(self, client):
        res = client.get("/api/v1/integrations/applications/nonexistent.app")
        assert res.status_code == 404

    def test_trigger_discovery_endpoint(self, client):
        res = client.post("/api/v1/integrations/discover?refresh_installed=false")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)

    def test_permissions_endpoint_and_update(self, client):
        res = client.get("/api/v1/integrations/permissions/browser.opera_gx")
        assert res.status_code == 200
        data = res.json()
        assert data["app_id"] == "browser.opera_gx"

        # Update permissions
        update_res = client.post(
            "/api/v1/integrations/permissions",
            json={
                "app_id": "browser.opera_gx",
                "disabled_capabilities": ["browser.manage_tabs"],
            },
        )
        assert update_res.status_code == 200
        updated = update_res.json()
        assert "browser.manage_tabs" in updated["disabled_capabilities"]

        # Reset
        client.post(
            "/api/v1/integrations/permissions",
            json={"app_id": "browser.opera_gx", "disabled_capabilities": []},
        )

    def test_recent_activity_endpoint(self, client):
        res = client.get("/api/v1/integrations/activity?limit=10")
        assert res.status_code == 200
        data = res.json()
        assert "activity" in data
        assert "total" in data
