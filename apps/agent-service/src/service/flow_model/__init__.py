"""The flow canvas model: what a flow spec means, with no I/O.

Component templates, the registry that serves them, spec migration, structural
validation, handle compatibility and the data operations the processing nodes
perform. Everything here is a pure function of a spec — no repository, no HTTP
client, no framework.

That purity is the point. Both sides of the product need this vocabulary: the
service layer validates and stores specs, and ``agents.graphs.flow`` compiles
them into LangGraph graphs. Keeping it in its own I/O-free context means the
agent runtime can depend on the model without reaching into a bounded context
that talks to the database.
"""
