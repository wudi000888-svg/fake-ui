import agent_pairing
from api_common import ok
from http_utils import api_error


def handle_agent_post(clean, data):
    if clean != "/api/agents/bootstrap":
        return None
    try:
        result = agent_pairing.bootstrap_agent(data or {})
    except (RuntimeError, ValueError, TypeError) as exc:
        return api_error(str(exc), 400)
    return ok(**result)
