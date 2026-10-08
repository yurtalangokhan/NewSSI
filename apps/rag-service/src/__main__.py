"""Launch RAG from its source package using central service configuration."""

from config_manager import env
import uvicorn

if __name__ == "__main__":
    # 0.0.0.0 is required inside the container; APISIX is the only ingress.
    uvicorn.run("src.server:APP", host="0.0.0.0", port=env.RAG_SERVICE_PORT)  # noqa: S104
