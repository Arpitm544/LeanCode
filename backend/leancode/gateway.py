import json
import os

import httpx

from .policy import PolicyError, allowed_routes, charge, request_bound, reserve, settle


class Gateway:
    def __init__(self, settings, store, transport=None):
        self.settings, self.store, self.transport = settings, store, transport
        self.public_doc_cache = {}

    def complete(self, session, messages):
        repository = self.settings.repositories[session["repository"]]
        routes = allowed_routes(self.settings.routes, repository.get("confidential", True))
        if session["state"].get("mode") != "optimized":
            routes = [r for r in routes if r.get("primary", True)] or routes
        else:
            preferred = "strong" if session["state"].get("test_failures", 0) else "small"
            routes = sorted(routes, key=lambda route: route.get("tier", "small") != preferred)
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
            except httpx.RequestError:
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

    def documentation(self, session, topic):
        if self.settings.repositories[session["repository"]].get("confidential", True):
            raise PolicyError("External documentation search is disabled for confidential repositories")
        query = self.settings.documentation_topics.get(topic)
        if not query:
            raise PolicyError("Select a trusted public documentation topic; arbitrary queries are forbidden")
        if topic in self.public_doc_cache:
            return self.public_doc_cache[topic]
        key = os.getenv("TAVILY_API_KEY")
        try:
            cost = int(os.getenv("TAVILY_SEARCH_COST_MICRO", "0"))
        except ValueError:
            raise PolicyError("Configure the Tavily search cost bound") from None
        if not key or cost <= 0:
            raise PolicyError("Tavily key and conservative positive per-search cost are required")
        reservation = reserve(self.store, session["user_id"], session["id"], cost)
        try:
            with httpx.Client(timeout=20, trust_env=False, follow_redirects=False, transport=self.transport) as client:
                response = client.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {key}"}, json={
                    "query": query, "search_depth": "basic", "max_results": 2,
                    "include_domains": os.getenv("LEANCODE_DOC_DOMAINS", "docs.python.org").split(","),
                    "include_answer": False, "include_raw_content": False, "auto_parameters": False,
                })
                response.raise_for_status()
            results = [{"url": item["url"], "content": item.get("content", "")[:3000]}
                       for item in response.json()["results"][:2]]
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            raise PolicyError("Documentation search failed; possible charge retained as a reservation") from None
        # Tavily is charged at the configured conservative per-search price; no false exact billing claim.
        settle(self.store, reservation, cost)
        current = self.store.session(session["id"])["state"]
        self.store.update(session["id"], cost_micro=current.get("cost_micro", 0) + cost)
        self.public_doc_cache[topic] = results
        self.store.event(session["id"], "usage", {"message": "Public documentation retrieved; configured search cost recorded"})
        return results
