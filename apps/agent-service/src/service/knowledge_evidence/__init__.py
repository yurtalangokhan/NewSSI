"""Knowledge evidence: the chunks and subgraph each retrieval call used.

Records ``KnowledgeEvidence`` out of band (never in the checkpoint), references
it from the ToolMessage artifact or the flow timeline, and turns it back into
timeline packets for the live stream and for reloaded history.
"""
