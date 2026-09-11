# Visual Flow Canvas Architecture & Developer Guide

## 1. Overview

The Visual Flow Canvas is a visual node-and-edge graph editor integrated into the Onyx platform, allowing developers and administrators to build, configure, test, and publish custom AI agent workflows compiled directly to LangGraph execution graphs.

---

## 2. Core Architecture



---

## 3. Component Templates & Port Types

Component templates define the visual and functional contract for nodes on the canvas.

### 3.1 Port Types
- : Message flow between ChatInput, Agents, Stages, and ChatOutput.
- : Language model instance injected from  / .
- : Tool bundle injected from , , or category toolkits.
- : Persistent memory resource ().
- : Document or Knowledge Graph retrieval handle (, ).
- : Scheduling and data sync trigger handles ().

### 3.2 Categories
1. **Agents**: , , , , , .
2. **Models**: , .
3. **Tools**: , , , , , etc.
4. **Memory**: .
5. **Knowledge & RAG**: , .
6. **Web Search**: , , .
7. **Data Sources**: , .
8. **Input / Output**: , .

---

## 4. Graph Compilation & Execution

1. **Validation ()**:
   - Single Entry () and Single Exit ().
   - Port Type Compatibility (cannot connect  to ).
   - Cycle detection and required input presence.
2. **Compilation ()**:
   - Partitions resource nodes vs execution nodes.
   - Binds models and tools to corresponding execution nodes.
   - Compiles topological edges into a LangGraph .
3. **Execution**:
   - Invoked via standard  SSE streaming pipeline.

---

## 5. Versioning & Lifecycle

- **Draft**: Working copy saved in .
- **Publish**: Creates an immutable snapshot in .
- **Rollback**: Restores a previously published version snapshot into the active draft.
