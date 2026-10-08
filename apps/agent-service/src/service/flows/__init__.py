"""Flow services: the parts of the flow canvas that do I/O.

Option resolution against live datasources, audit emission, publish gating,
playground execution and ``FlowService`` itself. The spec model these build on
— templates, registry, validator, migrations, data operations — is next door in
``service.flow_model``, which stays free of I/O so the agent runtime can
compile a flow without depending on this context.
"""

from service.flows.service import FlowService

__all__ = [
    "FlowService",
]
