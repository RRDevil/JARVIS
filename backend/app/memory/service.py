"""Preference Resolution and Memory Service (Phase 7 Foundation).

Implements the strict 5-tier preference resolution hierarchy and manages
explicit, confirmed learned, and inferred preferences.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.memory.models import (
    MemorySettings,
    PreferenceCategory,
    PreferenceResolution,
    PreferenceSource,
    PreferenceType,
    UserPreference,
)
from app.memory.store import PreferenceMemoryStore, preference_memory_store

logger = logging.getLogger("jarvis.memory.service")


class PreferenceService:
    """Core domain service for resolving and learning user preferences."""

    def __init__(self, store: PreferenceMemoryStore = preference_memory_store):
        self.store = store
        self.settings = MemorySettings()

    def set_memory_enabled(self, enabled: bool) -> None:
        """Enable or disable persistent preference memory."""
        self.settings.memory_enabled = enabled

    def set_learning_enabled(self, enabled: bool) -> None:
        """Enable or disable heuristic learning of repeated preferences."""
        self.settings.learning_enabled = enabled

    def set_explicit_preference(
        self,
        category: PreferenceCategory,
        key: str,
        app_id: Optional[str] = None,
        target_entity: Optional[str] = None,
        browser_id: Optional[str] = None,
        profile_name: Optional[str] = None,
        workflow_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> UserPreference:
        """Directly record an explicit user preference."""
        now = datetime.now(timezone.utc).isoformat()
        pref_id = f"pref-{uuid.uuid4().hex[:10]}"

        # Check for existing preference with same category and key
        existing = self.store.get_by_key(preference_key=key.lower().strip(), category=category)
        if existing:
            pref_id = existing.id

        pref = UserPreference(
            id=pref_id,
            category=category,
            preference_key=key.lower().strip(),
            app_id=app_id,
            target_entity=target_entity,
            browser_id=browser_id,
            profile_name=profile_name,
            workflow_type=workflow_type,
            preference_type=PreferenceType.EXPLICIT,
            confidence=1.0,
            source=PreferenceSource.USER_EXPLICIT,
            is_enabled=True,
            user_confirmed=True,
            details=details or {},
            created_at=existing.created_at if existing else now,
            updated_at=now,
            last_confirmed_at=now,
        )
        return self.store.save_preference(pref)

    def confirm_learned_preference(
        self,
        category: PreferenceCategory,
        key: str,
        app_id: Optional[str] = None,
        target_entity: Optional[str] = None,
        browser_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> UserPreference:
        """Save a confirmed learned preference after operator consent."""
        now = datetime.now(timezone.utc).isoformat()
        pref_id = f"pref-{uuid.uuid4().hex[:10]}"

        existing = self.store.get_by_key(preference_key=key.lower().strip(), category=category)
        if existing:
            pref_id = existing.id

        pref = UserPreference(
            id=pref_id,
            category=category,
            preference_key=key.lower().strip(),
            app_id=app_id,
            target_entity=target_entity,
            browser_id=browser_id,
            preference_type=PreferenceType.CONFIRMED_LEARNED,
            confidence=1.0,
            source=PreferenceSource.CONVERSATION_CONFIRMATION,
            is_enabled=True,
            user_confirmed=True,
            details=details or {},
            created_at=existing.created_at if existing else now,
            updated_at=now,
            last_confirmed_at=now,
        )
        return self.store.save_preference(pref)

    def resolve_application(
        self,
        explicit_request: Optional[str] = None,
        person_name: Optional[str] = None,
        website_domain: Optional[str] = None,
        workflow_type: Optional[str] = None,
    ) -> PreferenceResolution:
        """Resolve target application and browser according to the mandatory 5-tier resolution hierarchy:

        Tier 1: Explicit instruction in current request
        Tier 2: Relevant confirmed per-person or per-website preference
        Tier 3: Relevant confirmed workflow preference
        Tier 4: Confirmed global default
        Tier 5: Reasonable supported default
        """
        # Tier 1: Explicit request in prompt overrides all stored memory
        if explicit_request:
            exp_clean = explicit_request.lower().strip()
            # Resolve common explicit app references
            if "opera" in exp_clean:
                return PreferenceResolution(
                    resolved_app_id="browser.opera_gx",
                    resolved_browser_id="browser.opera_gx",
                    resolution_source="explicit_request",
                    confidence=1.0,
                    explanation=f"User explicitly requested Opera GX: '{explicit_request}'",
                )
            if "chrome" in exp_clean:
                return PreferenceResolution(
                    resolved_app_id="browser.chrome",
                    resolved_browser_id="browser.chrome",
                    resolution_source="explicit_request",
                    confidence=1.0,
                    explanation=f"User explicitly requested Google Chrome: '{explicit_request}'",
                )
            if "whatsapp" in exp_clean:
                return PreferenceResolution(
                    resolved_app_id="messaging.whatsapp",
                    resolution_source="explicit_request",
                    confidence=1.0,
                    explanation=f"User explicitly requested WhatsApp: '{explicit_request}'",
                )
            if "discord" in exp_clean:
                return PreferenceResolution(
                    resolved_app_id="messaging.discord",
                    resolution_source="explicit_request",
                    confidence=1.0,
                    explanation=f"User explicitly requested Discord: '{explicit_request}'",
                )
            if "instagram" in exp_clean:
                return PreferenceResolution(
                    resolved_app_id="messaging.instagram",
                    resolution_source="explicit_request",
                    confidence=1.0,
                    explanation=f"User explicitly requested Instagram: '{explicit_request}'",
                )
            if any(w in exp_clean for w in ["word", "winword"]):
                return PreferenceResolution(
                    resolved_app_id="office.word",
                    resolution_source="explicit_request",
                    confidence=1.0,
                    explanation=f"User explicitly requested Microsoft Word: '{explicit_request}'",
                )
            if "excel" in exp_clean:
                return PreferenceResolution(
                    resolved_app_id="office.excel",
                    resolution_source="explicit_request",
                    confidence=1.0,
                    explanation=f"User explicitly requested Microsoft Excel: '{explicit_request}'",
                )
            if "notepad" in exp_clean:
                return PreferenceResolution(
                    resolved_app_id="notepad",
                    resolution_source="explicit_request",
                    confidence=1.0,
                    explanation=f"User explicitly requested Notepad: '{explicit_request}'",
                )

        # Check if memory is enabled
        if not self.settings.memory_enabled:
            return self._fallback_default(workflow_type, website_domain)

        # Tier 2: Per-person communication preference
        if person_name:
            person_key = f"person:{person_name.lower().strip()}"
            person_pref = self.store.get_by_key(person_key, category=PreferenceCategory.PERSON_COMMUNICATIONS)
            if person_pref and person_pref.user_confirmed and person_pref.is_enabled:
                return PreferenceResolution(
                    resolved_app_id=person_pref.app_id,
                    resolved_browser_id=person_pref.browser_id,
                    resolved_profile=person_pref.profile_name,
                    preference_match=person_pref,
                    resolution_source="person_preference",
                    confidence=person_pref.confidence,
                    explanation=f"Applied saved preference for {person_name}: {person_pref.app_id}" + (
                        f" in {person_pref.browser_id}" if person_pref.browser_id else ""
                    ),
                )

        # Tier 2 (cont): Per-website browser preference
        if website_domain:
            domain_key = f"domain:{website_domain.lower().strip()}"
            site_pref = self.store.get_by_key(domain_key, category=PreferenceCategory.WEBSITE_BROWSERS)
            if site_pref and site_pref.user_confirmed and site_pref.is_enabled:
                return PreferenceResolution(
                    resolved_app_id=site_pref.browser_id or site_pref.app_id,
                    resolved_browser_id=site_pref.browser_id,
                    resolved_profile=site_pref.profile_name,
                    preference_match=site_pref,
                    resolution_source="website_preference",
                    confidence=site_pref.confidence,
                    explanation=f"Applied saved website preference for {website_domain}: {site_pref.browser_id or site_pref.app_id}",
                )

        # Tier 3: Workflow-level preference
        if workflow_type:
            wf_key = f"workflow:{workflow_type.lower().strip()}"
            wf_pref = self.store.get_by_key(wf_key, category=PreferenceCategory.WORKFLOW_PREFERENCES)
            if wf_pref and wf_pref.user_confirmed and wf_pref.is_enabled:
                return PreferenceResolution(
                    resolved_app_id=wf_pref.app_id,
                    resolved_browser_id=wf_pref.browser_id,
                    preference_match=wf_pref,
                    resolution_source="workflow_preference",
                    confidence=wf_pref.confidence,
                    explanation=f"Applied workflow preference for {workflow_type}: {wf_pref.app_id}",
                )

        # Tier 4: Global application defaults
        global_cat = PreferenceCategory.GLOBAL_DEFAULTS
        if workflow_type in ("browse", "web", "research") or website_domain:
            default_browser = self.store.get_by_key("default:browser", category=global_cat)
            if default_browser and default_browser.user_confirmed and default_browser.is_enabled:
                return PreferenceResolution(
                    resolved_app_id=default_browser.app_id or default_browser.browser_id,
                    resolved_browser_id=default_browser.browser_id or default_browser.app_id,
                    preference_match=default_browser,
                    resolution_source="global_default",
                    confidence=default_browser.confidence,
                    explanation=f"Applied global default browser preference: {default_browser.app_id or default_browser.browser_id}",
                )

        if workflow_type == "messaging":
            default_messenger = self.store.get_by_key("default:messaging", category=global_cat)
            if default_messenger and default_messenger.user_confirmed and default_messenger.is_enabled:
                return PreferenceResolution(
                    resolved_app_id=default_messenger.app_id,
                    resolved_browser_id=default_messenger.browser_id,
                    preference_match=default_messenger,
                    resolution_source="global_default",
                    confidence=default_messenger.confidence,
                    explanation=f"Applied global default messaging preference: {default_messenger.app_id}",
                )

        # Tier 5: Reasonable supported default
        return self._fallback_default(workflow_type, website_domain)

    def _fallback_default(self, workflow_type: Optional[str], website_domain: Optional[str]) -> PreferenceResolution:
        """Provide a reasonable supported default when no preference exists."""
        if workflow_type in ("browse", "web", "search", "navigate") or website_domain:
            return PreferenceResolution(
                resolved_app_id="browser.opera_gx",
                resolved_browser_id="browser.opera_gx",
                resolution_source="system_fallback",
                confidence=0.7,
                explanation="Defaulting to primary installed browser Opera GX.",
            )
        if workflow_type == "messaging":
            return PreferenceResolution(
                resolved_app_id="messaging.discord",
                resolution_source="system_fallback",
                confidence=0.5,
                requires_confirmation=True,
                explanation="No messaging preference found. Asking user for preferred application.",
            )
        if workflow_type in ("document", "word_processing"):
            return PreferenceResolution(
                resolved_app_id="office.word",
                resolution_source="system_fallback",
                confidence=0.7,
                explanation="Defaulting to Microsoft Word for document processing.",
            )
        return PreferenceResolution(
            resolved_app_id="browser.opera_gx",
            resolution_source="system_fallback",
            confidence=0.5,
            explanation="Defaulting to Opera GX desktop environment.",
        )


# Global singleton instance
preference_service = PreferenceService()
