"""Case-facts extraction into a persistent block at the top of context.

Extraction is LLM-driven: one Claude call against the full transcript that returns
strict JSON for the 12 required fields. This is commonly called a *scratchpad* — same
concept, different word: a dense structured block that survives compression and is
placed at the top boundary of context so the model can recover transactional facts
without scanning thousands of tokens of narrative.

Missing-field behavior raises `CaseFactExtractionError` listing the gaps — silent
null-fill is forbidden.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from retail_context.client import complete_with_system, get_model
from retail_context.transcript import Transcript

# TODO (Exercise 2): Replace with the 12-field contract for the case-facts block.
# Order matters — the to_markdown() rendering uses this order so the block is
# reviewer-readable and the model can re-find a value by name. Each name appears
# verbatim in the extraction system prompt as the JSON key the LLM must return.
#
# Required fields (12 total): customer_id; refund_order_id, refund_amount_usd,
# refund_status; subscription_id, subscription_plan, subscription_cancel_reason,
# subscription_status; active_payment_method_last4, new_payment_method_last4,
# payment_update_failure_code, payment_update_status.
REQUIRED_FIELDS: tuple[str, ...] = (
    "customer_id",
    "refund_order_id",
    "refund_amount_usd",
    "refund_status",
    "subscription_id",
    "subscription_plan",
    "subscription_cancel_reason",
    "subscription_status",
    "active_payment_method_last4",
    "new_payment_method_last4",
    "payment_update_failure_code",
    "payment_update_status",
)


# TODO (Exercise 2): Replace with a dataclass that carries the 12 fields above
# with explicit Python types (str for IDs / status tokens / last4 strings,
# float for refund_amount_usd). Then implement to_markdown(self) -> str so the
# block renders with a level-1 `# Case Facts` header and the three subgroups
# (Customer / Refund (resolved) / Subscription (resolved) / Payment update
# (active)) as bold inline labels. The rendering is part of the contract:
# fixed key order, Markdown headers, reviewer-readable.
@dataclass
class CaseFacts:
    customer_id: str
    refund_order_id: str
    refund_amount_usd: float
    refund_status: str
    subscription_id: str
    subscription_plan: str
    subscription_cancel_reason: str
    subscription_status: str
    active_payment_method_last4: str
    new_payment_method_last4: str
    payment_update_failure_code: str
    payment_update_status: str

    def to_markdown(self) -> str:
        missing_fields = [field for field in REQUIRED_FIELDS if getattr(self, field) is None]
        if missing_fields:
            raise CaseFactExtractionError(missing=missing_fields, raw=asdict(self))
        markdown = f"# Case Facts\n\n"
        markdown += f"## Customer\n\n"
        markdown += f"Customer ID: {self.customer_id}\n\n"
        markdown += f"## Refund (resolved)\n\n"
        markdown += f"Refund Order ID: {self.refund_order_id}\n\n"
        markdown += f"Refund Amount: {self.refund_amount_usd}\n\n"
        markdown += f"Refund Status: {self.refund_status}\n\n"
        markdown += f"## Subscription (resolved)\n\n"
        markdown += f"Subscription ID: {self.subscription_id}\n\n"
        markdown += f"Subscription Plan: {self.subscription_plan}\n\n"
        markdown += f"Subscription Cancel Reason: {self.subscription_cancel_reason}\n\n"
        markdown += f"Subscription Status: {self.subscription_status}\n\n"
        markdown += f"## Payment update (active)\n\n"
        markdown += f"Active Payment Method Last4: {self.active_payment_method_last4}\n\n"
        markdown += f"New Payment Method Last4: {self.new_payment_method_last4}\n\n"
        markdown += f"Payment Update Failure Code: {self.payment_update_failure_code}\n\n"
        markdown += f"Payment Update Status: {self.payment_update_status}\n\n"
        return markdown 


class CaseFactExtractionError(ValueError):
    def __init__(self, missing: list[str], raw: dict[str, Any]):
        super().__init__(f"case-facts extraction missing required fields: {missing}")
        self.missing = missing
        self.raw = raw


# TODO (Exercise 2): Replace with the system prompt that drives the extraction.
# The prompt must require Claude to return EXACTLY one JSON object with the
# 12 REQUIRED_FIELDS as keys, with the right types (refund_amount_usd is a
# number, last4 are zero-padded strings, status tokens preserved verbatim).
# Missing fields are null — DO NOT invent. Output is JSON only — no prose,
# no markdown, no code fences. The prompt is reviewed for its strict-schema
# intent; the reviewer reads it to decide whether following it would reliably
# produce a parseable JSON with every required field.
_SYSTEM_PROMPT = """\
You are a precise information-extraction system. You are given the full transcript of a retail \
customer-support conversation. Extract the transactional case facts and return them as a single \
JSON object.

Return EXACTLY ONE JSON object and NOTHING ELSE. No prose, no explanation, no markdown, no code \
fences (no ```). Your entire response must be parseable by a strict JSON parser.

The object must contain all 12 of these keys, in this exact order:

  "customer_id"                 (string)  the customer identifier
  "refund_order_id"             (string)  the order the refund applies to
  "refund_amount_usd"           (number)  refund amount in USD as a JSON number, e.g. 49.99 —
                                          not a string, no "$", no thousands separators
  "refund_status"               (string)  the refund status token, verbatim (e.g. "refunded")
  "subscription_id"             (string)  the subscription identifier
  "subscription_plan"           (string)  the plan name, verbatim (e.g. "Pro")
  "subscription_cancel_reason"  (string)  the stated reason for cancellation
  "subscription_status"         (string)  the subscription status token, verbatim (e.g. "cancelled")
  "active_payment_method_last4" (string)  last 4 digits of the currently active card, as a
                                          zero-padded 4-character string, e.g. "0042"
  "new_payment_method_last4"    (string)  last 4 digits of the new card, zero-padded 4-char string
  "payment_update_failure_code" (string)  the failure/error code from the payment-update attempt, verbatim
  "payment_update_status"       (string)  the payment-update status token, verbatim

Rules:
- Extract only what the transcript actually states. DO NOT invent, guess, or infer values.
- If a value is genuinely absent from the transcript, set that key to null. Never fabricate a
  plausible-looking value to fill a gap.
- Preserve status tokens and codes EXACTLY as written — do not normalize casing, spelling, or wording.
- The last4 fields are STRINGS, zero-padded to 4 characters ("0042", not 42 and not "42").
- refund_amount_usd is a JSON number (49.99), never a string ("49.99") and never with a currency symbol.
- Include every one of the 12 keys, even when the value is null. Output the JSON object only.
"""


def _parse_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.rstrip().endswith("```"):
            raw = raw.rsplit("```", 1)[0]
    return json.loads(raw)


def extract(
    transcript: Transcript,
    *,
    model: str | None = None,
    log_path: Path | None = None,
) -> CaseFacts:
    # TODO (Exercise 2): Run the extraction call and validate the result.
    #
    # 1. Build the user message: f"Transcript:\n\n{transcript.full_text}".
    #
    # 2. Call complete_with_system(_SYSTEM_PROMPT, user, model=model,
    #    max_tokens=2048). It returns (text, input_tokens, output_tokens).
    #
    # 3. Parse the response text with _parse_json (handles a stray ``` fence).
    #
    # 4. If a `log_path` was given, write a JSON log containing the model
    #    name, the input/output token counts, and the raw parsed dict. This
    #    is the `case_facts_call.json` artifact the reviewer audits.
    #
    # 5. Validate that every name in REQUIRED_FIELDS is present in the parsed
    #    dict and is not None and not the empty string. If anything is
    #    missing, raise CaseFactExtractionError(missing=..., raw=...) — DO
    #    NOT silently fill with null.
    #
    # 6. Construct and return a CaseFacts. Cast types explicitly:
    #    str(...) for ID/status fields, float(...) for refund_amount_usd.
    user_message = f"Transcript:\n\n{transcript.full_text}"
    
    text, input_tokens, output_tokens = complete_with_system(
        _SYSTEM_PROMPT, 
        user_message, 
        model=model, 
        max_tokens=2048)
    
    parsed_dict = _parse_json(text)
    
    if log_path:
        with open(log_path, "w") as f:
            json.dump({"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens, "raw": parsed_dict}, f)
    
    missing_fields = [field for field in parsed_dict.keys() if parsed_dict[field] is None or parsed_dict[field] == "" or field not in REQUIRED_FIELDS]
    if missing_fields:
        raise CaseFactExtractionError(missing=missing_fields, raw=parsed_dict)

    case_facts = CaseFacts(
        customer_id=str(parsed_dict["customer_id"]),
        refund_order_id=str(parsed_dict["refund_order_id"]),
        refund_amount_usd=float(parsed_dict["refund_amount_usd"]),
        refund_status=str(parsed_dict["refund_status"]),
        subscription_id=str(parsed_dict["subscription_id"]),
        subscription_plan=str(parsed_dict["subscription_plan"]),
        subscription_cancel_reason=str(parsed_dict["subscription_cancel_reason"]),
        subscription_status=str(parsed_dict["subscription_status"]),
        active_payment_method_last4=str(parsed_dict["active_payment_method_last4"]),
        new_payment_method_last4=str(parsed_dict["new_payment_method_last4"]),
        payment_update_failure_code=str(parsed_dict["payment_update_failure_code"]),
        payment_update_status=str(parsed_dict["payment_update_status"]),
    )
    return case_facts


def to_dict(facts: CaseFacts) -> dict[str, Any]:
    return asdict(facts)
