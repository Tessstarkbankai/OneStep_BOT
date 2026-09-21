import re

from agent.models import (
    RoutingDecision,
)


INVESTIGATION_PATTERNS = [
    (
        r"\btrace\b",
        3,
        "explicit execution tracing",
    ),

    (
        r"\bcall\s+path\b",
        3,
        "call-path investigation",
    ),

    (
        r"\bwho\s+calls\b",
        3,
        "caller investigation",
    ),

    (
        r"\bwhat\s+calls\b",
        3,
        "caller investigation",
    ),

    (
        r"\bfind\s+callers?\b",
        3,
        "caller investigation",
    ),

    (
        r"\bfind\s+callees?\b",
        3,
        "callee investigation",
    ),

    (
        r"\broot\s+cause\b",
        4,
        "root-cause investigation",
    ),

    (
        r"\bdebug\b",
        3,
        "debugging request",
    ),

    (
        r"\binvestigat",
        3,
        "explicit investigation",
    ),

    (
        r"\bwhy\s+(?:does|is|did)\b",
        2,
        "causal investigation",
    ),

    (
        r"\bexecution\s+flow\b",
        2,
        "execution-flow analysis",
    ),

    (
        r"\bdependency\s+(?:chain|flow|graph)\b",
        3,
        "dependency analysis",
    ),

    (
        r"\bimpact\b",
        2,
        "impact analysis",
    ),

    (
        r"\bacross\s+(?:the\s+)?(?:repo|repository|codebase)\b",
        2,
        "cross-repository investigation",
    ),

    (
        r"\brelated\s+files\b",
        2,
        "multi-file investigation",
    ),
]


CHANGE_PATTERNS = [
    r"\bfix\b",
    r"\bmodify\b",
    r"\bchange\b",
    r"\bimplement\b",
    r"\badd\b",
    r"\bremove\b",
    r"\brefactor\b",
    r"\bpatch\b",
    r"\brewrite\b",
    r"\bupdate\b",
]


SIMPLE_PATTERNS = [
    r"\bwhere\s+is\b",
    r"\bwhat\s+does\b",
    r"\bexplain\b",
    r"\bshow\s+me\b",
    r"\bwhat\s+is\b",
]


def _matches_any(
    text: str,
    patterns: list[str],
) -> bool:

    return any(
        re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        for pattern in patterns
    )


def classify_task(
    question: str,
) -> RoutingDecision:

    text = question.strip()

    lowered = text.lower()

    reasons = []

    score = 0

    #
    # --------------------------------
    # Detect modification intent.
    # --------------------------------
    #
    change_request = (
        _matches_any(
            lowered,
            CHANGE_PATTERNS,
        )
    )

    if change_request:

        score += 3

        reasons.append(
            "request appears to involve "
            "a code change"
        )

        request_kind = "change"

    else:

        request_kind = "question"

    #
    # --------------------------------
    # Investigation indicators.
    # --------------------------------
    #
    for (
        pattern,
        weight,
        reason,
    ) in INVESTIGATION_PATTERNS:

        if re.search(
            pattern,
            lowered,
            re.IGNORECASE,
        ):

            score += weight

            if reason not in reasons:

                reasons.append(
                    reason
                )

    #
    # Multiple explicit tasks often
    # require iterative exploration.
    #
    conjunction_count = len(
        re.findall(
            r"\b(?:and|then|also)\b",
            lowered,
        )
    )

    if conjunction_count >= 2:

        score += 1

        reasons.append(
            "multiple requested operations"
        )

    #
    # Very long questions usually carry
    # several constraints.
    #
    word_count = len(
        re.findall(
            r"\b\w+\b",
            text,
        )
    )

    if word_count >= 45:

        score += 2

        reasons.append(
            "long multi-constraint request"
        )

    elif word_count >= 25:

        score += 1

        reasons.append(
            "moderately complex request"
        )

    #
    # Error/exception content is usually
    # better handled by the agent.
    #
    if any(
        token in lowered

        for token in [
            "traceback",
            "exception",
            "stack trace",
            "error:",
            "failed with",
        ]
    ):

        score += 3

        reasons.append(
            "error diagnosis requested"
        )

    #
    # --------------------------------
    # Simple lookup/explanation signals.
    # --------------------------------
    #
    simple_signal = (
        _matches_any(
            lowered,
            SIMPLE_PATTERNS,
        )
    )

    if (
        simple_signal
        and score == 0
    ):

        reasons.append(
            "simple lookup or explanation"
        )

    #
    # --------------------------------
    # Final routing.
    # --------------------------------
    #
    if score >= 3:

        route = "agent"

        if request_kind == "question":

            request_kind = (
                "investigation"
            )

    else:

        route = "fast"

    if not reasons:

        reasons.append(
            "no strong investigation "
            "signals detected"
        )

    return RoutingDecision(
        route=route,

        request_kind=(
            request_kind
        ),

        score=score,

        reasons=reasons,
    )
