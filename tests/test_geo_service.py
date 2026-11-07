from unittest.mock import AsyncMock
import pytest
from app.core.exceptions import EntityNotFoundException, VeciRedException
from app.modules.geo.models import Department
from app.modules.geo.schemas import DepartmentCreate, DepartmentUpdate
from app.modules.geo.service import GeoService


@pytest.fixture
def mock_dept_repo():
    return AsyncMock()


@pytest.fixture
def mock_comm_repo():
    return AsyncMock()


@pytest.fixture
def geo_service(mock_dept_repo, mock_comm_repo):
    return GeoService(dept_repo=mock_dept_repo, comm_repo=mock_comm_repo)


@pytest.mark.asyncio
async def test_list_departments_empty(geo_service, mock_dept_repo):
    mock_dept_repo.count.return_value = 0
    mock_dept_repo.get_multi.return_value = []

    res = await geo_service.list_departments(page=1, limit=10)
    assert res.items == []
    assert res.meta.total == 0
    assert res.meta.total_pages == 1


@pytest.mark.asyncio
async def test_get_department_not_found(geo_service, mock_dept_repo):
    mock_dept_repo.get_by_id.return_value = None

    with pytest.raises(EntityNotFoundException) as exc_info:
        await geo_service.get_department(999)
    assert "999" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_create_department_duplicate_ubigeo(geo_service, mock_dept_repo):
    mock_dept_repo.get_by_ubigeo.return_value = Department(id=1, name="Lima", ubigeo="15")

    data = DepartmentCreate(name="Lima Nueva", ubigeo="15")
    with pytest.raises(VeciRedException) as exc_info:
        await geo_service.create_department(data)
    assert exc_info.value.code == "UBIGEO_ALREADY_EXISTS"
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_create_department_duplicate_name(geo_service, mock_dept_repo):
    mock_dept_repo.get_by_ubigeo.return_value = None
    mock_dept_repo.get_by_name.return_value = Department(id=2, name="Arequipa", ubigeo="04")

    data = DepartmentCreate(name="Arequipa", ubigeo="99")
    with pytest.raises(VeciRedException) as exc_info:
        await geo_service.create_department(data)
    assert exc_info.value.code == "DEPARTMENT_NAME_EXISTS"
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_create_department_success(geo_service, mock_dept_repo):
    mock_dept_repo.get_by_ubigeo.return_value = None
    mock_dept_repo.get_by_name.return_value = None
    mock_dept_repo.create.return_value = Department(id=3, name="Cusco", ubigeo="08")

    data = DepartmentCreate(name="Cusco", ubigeo="08")
    result = await geo_service.create_department(data)
    assert result.id == 3
    assert result.name == "Cusco"
    mock_dept_repo.create.assert_awaited_once_with(data)
