"""Clarification Policy Engine.

Enforces guidelines on when J.A.R.V.I.S. must ask user questions versus when it
must proceed autonomously using safe observations and saved preferences.
"""

import logging
import uuid
from typing import List, Optional

from app.memory.service import preference_service
from app.planning.models import ClarificationQuestion

logger = logging.getLogger("jarvis.planning.clarification")


class ClarificationPolicyEngine:
    """Evaluates whether user clarification is genuinely necessary for a task."""

    def should_ask_messaging_application(
        self,
        recipient_name: str,
        available_apps: List[str],
        explicit_app: Optional[str] = None,
    ) -> Optional[ClarificationQuestion]:
        """Check if clarification is required before messaging a recipient.

        Does NOT ask if:
        - User explicitly stated the app in prompt.
        - User has a saved confirmed preference for this person.
        - Only one messaging application is installed/supported.
        """
        # Rule 1: Explicit instruction overrides
        if explicit_app:
            return None

        # Rule 2: Check persistent preference
        resolution = preference_service.resolve_application(
            person_name=recipient_name,
            workflow_type="messaging",
        )
        if resolution.resolution_source == "person_preference" and not resolution.requires_confirmation:
            logger.info(f"Using saved preference for {recipient_name}: {resolution.resolved_app_id}")
            return None

        # Rule 3: If only one app exists, do not ask
        clean_apps = [a for a in available_apps if a]
        if len(clean_apps) <= 1:
            return None

        # Otherwise, ask concise question with memory confirmation offer
        q_id = f"clarif-{uuid.uuid4().hex[:8]}"
        options = ["WhatsApp in Opera GX", "Discord", "Instagram Direct"]
        return ClarificationQuestion(
            question_id=q_id,
            question_text=f"Which application would you like me to use to message {recipient_name}?",
            target_entity=recipient_name,
            options=options,
            default_option=options[0],
            reason_for_asking=f"No saved communication preference found for '{recipient_name}'.",
            can_be_remembered=True,
        )

    def should_ask_browser_preference(
        self,
        website_domain: str,
        available_browsers: List[str],
        explicit_browser: Optional[str] = None,
    ) -> Optional[ClarificationQuestion]:
        """Check if browser clarification is necessary."""
        if explicit_browser:
            return None

        resolution = preference_service.resolve_application(
            website_domain=website_domain,
            workflow_type="browse",
        )
        if resolution.resolution_source in ("website_preference", "global_default") and not resolution.requires_confirmation:
            return None

        if len(available_browsers) <= 1:
            return None

        q_id = f"clarif-{uuid.uuid4().hex[:8]}"
        return ClarificationQuestion(
            question_id=q_id,
            question_text=f"Which browser would you like me to use for {website_domain}?",
            target_entity=website_domain,
            options=["Opera GX", "Google Chrome"],
            default_option="Opera GX",
            reason_for_asking=f"No website browser preference saved for '{website_domain}'.",
            can_be_remembered=True,
        )


# Global singleton instance
clarification_policy = ClarificationPolicyEngine()
