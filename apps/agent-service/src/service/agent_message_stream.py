"""Backward-compatible alias for the SSE streaming pipeline.

Two refactors extracted the ``/stream`` generator out of
``api/routes/AgentsRoute.py`` at the same time — this module and
``service/AgentStreamService.py``. ``AgentStreamService`` is the one that kept
being developed (flow stage brackets, per-stage timelines, resumed-flow
answers), so it is the implementation and this module only re-exports it, for
callers still importing the older path.
"""

from service.AgentStreamService import message_generator

__all__ = ["message_generator"]
