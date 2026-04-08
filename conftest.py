import pytest
from httpx import ASGITransport, AsyncClient

from gateway.config import GatewayConfig
from gateway.services.auth_service import InMemoryAuthStore
from gateway.services.jwt_service import JwtService
from matching.config import MatchingConfig
from matching.services.scorer import CandidateScorer
from profile.config import ProfileConfig
from profile.services.file_validator import FileValidator
from profile.services.text_extractor import TextExtractor

@pytest.fixture
def gateway_config():
    return GatewayConfig()


@pytest.fixture
def jwt_service(gateway_config):
    return JwtService(
        gateway_config.JWT_SECRET,
        gateway_config.JWT_ACCESS_TTL,
        gateway_config.JWT_REFRESH_TTL,
    )


@pytest.fixture
def auth_store():
    return InMemoryAuthStore()


@pytest.fixture
def admin_credentials(gateway_config):
    return gateway_config.ADMIN_USERNAME, gateway_config.ADMIN_PASSWORD


@pytest.fixture
def hr_credentials(gateway_config):
    return gateway_config.HR_USERNAME, gateway_config.HR_PASSWORD


@pytest.fixture
async def client():
    from gateway.app import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def profile_config():
    return ProfileConfig()


@pytest.fixture
def file_validator(profile_config):
    return FileValidator(
        max_size=profile_config.MAX_FILE_SIZE,
        allowed_extensions=profile_config.ALLOWED_EXTENSIONS,
    )


@pytest.fixture
def text_extractor():
    return TextExtractor()


@pytest.fixture
def matching_config():
    return MatchingConfig()


@pytest.fixture
def scorer():
    return CandidateScorer(embedding_model_name="test-model")


@pytest.fixture
def default_weights():
    return {
        "skills": 0.40,
        "experience": 0.25,
        "grade": 0.15,
        "location": 0.10,
        "salary": 0.10,
    }


@pytest.fixture
def sample_vacancy():
    return {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "Python Developer",
        "grade": ["middle", "senior"],
        "location": "Москва",
        "salary_min": 150000,
        "salary_max": 250000,
        "requirements": [
            {"skill": "Python", "priority": "required"},
            {"skill": "FastAPI", "priority": "required"},
            {"skill": "PostgreSQL", "priority": "preferred"},
            {"skill": "Docker", "priority": "nice_to_have"},
        ],
    }


@pytest.fixture
def sample_candidate():
    return {
        "id": "660e8400-e29b-41d4-a716-446655440001",
        "profile": {
            "skills": ["Python", "FastAPI", "PostgreSQL", "Redis"],
            "experience_years": 4,
            "grade": "middle",
            "location": "Москва",
            "salary_expectation": 200000,
        },
    }
