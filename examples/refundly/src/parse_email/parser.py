"""refundly.parse_email — pull the order id + reason out of a support email."""

import ent

import re


@ent.node("refundly.parse_email")
def parse(req):
    body = req.get("email", "")
    m = re.search(r"order\s+(\w+)", body, re.I)
    return {"orderId": m.group(1) if m else None, "reason": req.get("reason", "unspecified")}
