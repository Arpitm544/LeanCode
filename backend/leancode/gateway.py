import json
import os

import httpx

from .policy import PolicyError, allowed_routes, charge, request_bound, reserve, settle


class Gateway:
    def __init__(self, settings, store, transport=None):
        self.settings, self.store, self.transport = settings, store, transport

    def complete(self, session, messages):
        repository = self.settings.repositories[session["repository"]]
        routes = allowed_routes(self.settings.routes, repository.get("confidential", True))
        if session["state"].get("mode") != "optimized":
            routes = [r for r in routes if r.get("primary", True)] or routes
        max_output = 2048
        for index, route in enumerate(routes):
            if route.get("local") and os.getenv("LEANCODE_LOCAL_OFFLINE") != "true":
                raise PolicyError("Local model egress isolation is not confirmed; see local-model setup")
            if not route.get("local"):
                if os.getenv("LEANCODE_GATEWAY_SINGLE_ATTEMPT") != "true" or not route.get("bounded_output"):
                    raise PolicyError("Cloud routes require single-attempt gateway and bounded-output confirmation")
            amount = request_bound(messages, route, max_output)
            reservation = reserve(self.store, session["user_id"], session["id"], amount)
            name = route.get("name", route["model"])
            if index:
                self.store.event(session["id"], "model", {"message": f"Taking over with {name}; saved context retained"})
            self.store.update(session["id"], model=name)
            self.store.event(session["id"], "model", {"message": f"Using {name}", "model": name})
            endpoint = route["url"] if route.get("local") else os.getenv("BIFROST_URL", "http://127.0.0.1:8080/openai/v1")
            headers = {"Content-Type": "application/json"}
            if not route.get("local") and os.getenv("BIFROST_KEY"):
                headers["Authorization"] = f"Bearer {os.environ['BIFROST_KEY']}"
            payload = {"model": route["model"], "messages": messages, "max_tokens": max_output,
                       "temperature": 0, "stream": False, "response_format": {"type": "json_object"}}
            try:
                with httpx.Client(timeout=60, transport=self.transport, trust_env=False, follow_redirects=False) as client:
                    response = client.post(endpoint.rstrip("/") + "/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
            except (httpx.TimeoutException, httpx.NetworkError):
                # Billing may already have happened: retain this attempt's reservation.
                self.store.event(session["id"], "error", {"message": f"{name} unavailable; unknown charge stays reserved"})
                continue
            except httpx.HTTPStatusError as exc:
                self.store.event(session["id"], "error", {"message": f"{name} returned HTTP {exc.response.status_code}; charge stays reserved"})
                if exc.response.status_code not in {408, 429, 500, 502, 503, 504}:
                    raise PolicyError("Model rejected the request; correct its configuration before resuming") from None
                continue
            try:
                body = response.json()
                usage = body["usage"]
                input_tokens, output_tokens = usage["prompt_tokens"], usage["completion_tokens"]
                if type(input_tokens) is not int or type(output_tokens) is not int or min(input_tokens, output_tokens) < 0:
                    raise ValueError("Invalid usage")
                actual = charge(input_tokens, output_tokens, route)
                settle(self.store, reservation, actual)
                current = self.store.session(session["id"])["state"]
                self.store.update(session["id"], input_tokens=current.get("input_tokens", 0) + input_tokens,
                                  output_tokens=current.get("output_tokens", 0) + output_tokens,
                                  cost_micro=current.get("cost_micro", 0) + actual)
                self.store.event(session["id"], "usage", {"message": f"{input_tokens} input + {output_tokens} output tokens; cost recorded",
                                                         "input_tokens": input_tokens, "output_tokens": output_tokens})
                return json.loads(body["choices"][0]["message"]["content"])
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                raise PolicyError("Malformed model response or missing usage; inspect reservations before retrying") from exc
        raise PolicyError("All allowed providers unavailable; progress saved for resume")
