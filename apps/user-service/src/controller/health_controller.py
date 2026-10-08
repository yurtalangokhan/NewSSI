from src.service.health_service import HealthService


class HealthController:
    def __init__(self) -> None:
        self.service = HealthService()

    async def health(self) -> dict:
        return self.service.health()

    async def readiness(self) -> dict:
        return await self.service.readiness()


def get_health_controller() -> HealthController:
    return HealthController()
