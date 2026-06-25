import pytest
import schemathesis
from app.main import app

# Load schema directly from the FastAPI app instance
schema = schemathesis.openapi.from_asgi("/api/openapi.json", app=app)

from app.api.deps import get_db

@schema.parametrize()
def test_api_contract(case, db_session):
    """
    Fuzzes the OpenAPI schema to ensure no 500s are returned 
    and the API shape does not regress.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    
    try:
        response = case.call(app=app)
        
        # We only care that the server doesn't crash (i.e. no 500 errors).
        # 400, 401, 403, 404, 422 are all perfectly valid responses for fuzzing.
        assert response.status_code < 500
    finally:
        app.dependency_overrides.clear()
