from fastapi import HTTPException


class BaseController:
    def _raise_not_found(self, detail: str):
        raise HTTPException(status_code=404, detail=detail)

    def _raise_bad_request(self, detail: str):
        raise HTTPException(status_code=400, detail=detail)

    def _raise_unauthorized(self, detail: str = "Unauthorized"):
        raise HTTPException(status_code=401, detail=detail)

    def _raise_forbidden(self, detail: str = "Forbidden"):
        raise HTTPException(status_code=403, detail=detail)

    def _raise_conflict(self, detail: str):
        raise HTTPException(status_code=409, detail=detail)

    def _raise_internal_error(self, detail: str = "Internal server error"):
        raise HTTPException(status_code=500, detail=detail)
