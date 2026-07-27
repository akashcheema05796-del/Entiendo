"""refundly.ledger — the case ledger (state). The decide unit writes each case."""

_CASES = []


def record_case(case):
    _CASES.append(case)
    return {"caseId": len(_CASES), "recorded": True}
