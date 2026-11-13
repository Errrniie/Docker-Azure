from fastapi import Header, HTTPException

API_KEY: str | None = None


def verify_api_key(x_api_key: str = Header(..., alias="x-api-key")):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
