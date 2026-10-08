from config_manager import env
import uvicorn


def main():
    settings = env
    uvicorn.run(
        "src.main:app",
        host=settings.SERVICE_HOST,
        port=settings.USER_SERVICE_PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
