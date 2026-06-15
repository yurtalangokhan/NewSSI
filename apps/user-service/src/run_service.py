import uvicorn

from src.config import get_settings


def main():
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.SERVICE_HOST,
        port=settings.SERVICE_PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
