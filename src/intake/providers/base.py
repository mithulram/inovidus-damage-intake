"""One interface for every way of "reading" an email: offline rules, Groq, recorded."""

from __future__ import annotations

from typing import Protocol

from ..models import InboundEmail, Understanding
from ..rules import Rules


class LLMProvider(Protocol):
    name: str
    model: str | None

    def understand(self, email: InboundEmail, rules: Rules) -> Understanding:
        """Classify the message, extract raw facts and give an urgency hint.

        Must return a validated :class:`Understanding`. It never decides the ERP
        contract, the final urgency or the status – those are deterministic steps.
        """
        ...
