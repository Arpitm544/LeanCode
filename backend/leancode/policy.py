import json
import math
import uuid
from urllib.parse import urlparse


class PolicyError(ValueError):
    """A trusted policy blocks further execution."""


def allowed_routes(routes, confidential):
    result = []
    for route in routes:
        if confidential and not route.get("local", False):
            continue
        if route.get("local"):
            endpoint = urlparse(route.get("url", ""))
            if endpoint.hostname not in {"127.0.0.1", "::1"} or endpoint.scheme != "http":
                raise PolicyError("Local inference must use a literal loopback HTTP endpoint")
            if "cloud" in route.get("model", "").lower():
                raise PolicyError("Cloud-backed model names cannot be used as local models")
        result.append(route)
    if not result:
        raise PolicyError("No allowed model configured; confidential repositories require local inference")
    return result[:3]


def charge(input_tokens, output_tokens, route):
    for key in ("input_rate", "output_rate"):
        if type(route.get(key)) is not int or route[key] < 0:
            raise PolicyError("Verified non-negative integer model prices are required")
    return math.ceil((input_tokens * route["input_rate"] + output_tokens * route["output_rate"]) / 1_000_000)


def request_bound(messages, route, max_output):
    # shortcut: conservative byte bound for text-only models, validate other tokenizers before adding them.
    upper_input = len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + 1024
    return charge(upper_input, max_output, route)


def reserve(store, user_id, session_id, amount):
    if type(amount) is not int or amount < 0:
        raise PolicyError("Invalid reservation")
    reservation_id = uuid.uuid4().hex
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        held = db.execute("SELECT COALESCE(SUM(amount_micro),0) FROM reservations "
                          "WHERE user_id=? AND status='held'", (user_id,)).fetchone()[0]
        if not user or user["spent_micro"] + held + amount > user["limit_micro"]:
            raise PolicyError("Budget exhausted: request blocked before dispatch; session saved")
        db.execute("INSERT INTO reservations(id,user_id,session_id,amount_micro) VALUES(?,?,?,?)",
                   (reservation_id, user_id, session_id, amount))
    return reservation_id


def settle(store, reservation_id, actual):
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM reservations WHERE id=? AND status='held'", (reservation_id,)).fetchone()
        if not row:
            raise PolicyError("Reservation already resolved")
        if type(actual) is not int or actual < 0:
            raise PolicyError("Invalid reported cost; reservation retained")
        db.execute("UPDATE users SET spent_micro=spent_micro+? WHERE id=?", (actual, row["user_id"]))
        db.execute("UPDATE reservations SET status='settled' WHERE id=?", (reservation_id,))
    if actual > row["amount_micro"]:
        raise PolicyError("Provider exceeded the configured cost bound; correct pricing before resuming")
