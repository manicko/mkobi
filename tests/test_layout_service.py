"""Unit tests for LayoutService business logic.

Tests the LayoutService class methods with mocked repository.
Following the pattern from test_graph_service.py.
"""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from sqlalchemy.exc import IntegrityError

from mkobi.models.layout import LayoutCreate, LayoutRead, LayoutUpdate
from mkobi.services.layout_service import LayoutService


@pytest.mark.asyncio
class TestLayoutService:
    """Unit tests for LayoutService business logic."""

    @pytest.fixture
    def mock_layout_repo(self):
        """Create a mock layout repository."""
        return AsyncMock()

    @pytest.fixture
    def layout_service(self, mock_layout_repo):
        """Create LayoutService with mocked repository."""
        return LayoutService(mock_layout_repo)

    # --- Helper ---

    def _make_layout_obj(self, layout_id=None, name="Test Layout", definition=None):
        """Create a mock layout DB object."""
        obj = MagicMock()
        obj.id = layout_id or uuid4()
        obj.name = name
        obj.definition = definition or {"grid": []}
        return obj

    # --- create tests ---

    async def test_create_layout_success(self, layout_service, mock_layout_repo, mock_db):
        """Test successful layout creation."""
        layout_id = uuid4()
        mock_layout_repo.create.return_value = self._make_layout_obj(
            layout_id=layout_id, name="Sales Layout"
        )

        data = LayoutCreate(
            name="Sales Layout",
            definition={"grid": [{"columns": [{"graph_id": "g1", "width": 12}]}]},
        )
        result = await layout_service.create_layout(
            name=data.name,
            definition=data.definition,
            db=mock_db,
        )

        assert isinstance(result, LayoutRead)
        assert result.name == "Sales Layout"
        mock_layout_repo.create.assert_called_once()
        call_args = mock_layout_repo.create.call_args
        assert call_args.kwargs["name"] == "Sales Layout"
        assert call_args.kwargs["definition"] == {"grid": [{"columns": [{"graph_id": "g1", "width": 12}]}]}

    async def test_create_layout_duplicate_name_raises(self, layout_service, mock_layout_repo, mock_db):
        """Test layout creation propagates the database's duplicate-name error.

        The service no longer pre-checks the name; it surfaces the repository's
        ``IntegrityError`` unchanged so the HTTP layer can classify it, and it
        rolls the session back so the aborted transaction cannot leak into the
        next statement on the same session.
        """
        mock_layout_repo.create.side_effect = IntegrityError(
            "INSERT INTO layouts", {}, Exception("duplicate key value violates unique constraint")
        )

        data = LayoutCreate(name="existing_layout", definition={"grid": []})

        with pytest.raises(IntegrityError, match="duplicate key value violates unique constraint"):
            await layout_service.create_layout(
                name=data.name,
                definition=data.definition,
                db=mock_db,
            )
        mock_layout_repo.create.assert_called_once()
        mock_db.rollback.assert_awaited_once()

    async def test_create_layout_repo_returns_none_raises(self, layout_service, mock_layout_repo, mock_db):
        """Test layout creation fails when repo returns None."""
        mock_layout_repo.create.return_value = None

        data = LayoutCreate(name="Test Layout", definition={"grid": []})

        with pytest.raises(ValueError, match="Failed to create layout"):
            await layout_service.create_layout(
                name=data.name,
                definition=data.definition,
                db=mock_db,
            )

    # --- get tests ---

    async def test_get_layout_found(self, layout_service, mock_layout_repo, mock_db):
        """Test getting layout by ID when it exists."""
        layout_id = uuid4()
        mock_layout_repo.get.return_value = self._make_layout_obj(layout_id=layout_id)

        result = await layout_service.get_layout(layout_id, db=mock_db)

        assert isinstance(result, LayoutRead)
        assert result.id == layout_id

    async def test_get_layout_not_found(self, layout_service, mock_layout_repo, mock_db):
        """Test getting layout by ID when it doesn't exist."""
        mock_layout_repo.get.return_value = None

        result = await layout_service.get_layout(uuid4(), db=mock_db)

        assert result is None

    # --- update tests ---

    async def test_update_layout_success(self, layout_service, mock_layout_repo, mock_db):
        """Test successful layout update."""
        layout_id = uuid4()
        mock_layout_repo.get.return_value = self._make_layout_obj(layout_id=layout_id, name="Old Name")
        mock_layout_repo.update.return_value = self._make_layout_obj(layout_id=layout_id, name="Updated Name")

        data = LayoutUpdate(name="Updated Name")
        result = await layout_service.update_layout(layout_id, data, db=mock_db)

        assert isinstance(result, LayoutRead)
        assert result.name == "Updated Name"

    async def test_update_layout_not_found(self, layout_service, mock_layout_repo, mock_db):
        """Test update returns None when layout not found."""
        mock_layout_repo.get.return_value = None

        data = LayoutUpdate(name="Nonexistent")
        result = await layout_service.update_layout(uuid4(), data, db=mock_db)

        assert result is None

    async def test_update_layout_duplicate_name_raises(self, layout_service, mock_layout_repo, mock_db):
        """Test update propagates the database's duplicate-name error.

        As with creation, the service surfaces the repository's
        ``IntegrityError`` rather than producing a domain error itself, and it
        rolls the session back so the aborted transaction cannot leak into the
        next statement on the same session.
        """
        layout_id = uuid4()
        mock_layout_repo.get.return_value = self._make_layout_obj(layout_id=layout_id, name="Old Name")
        mock_layout_repo.update.side_effect = IntegrityError(
            "UPDATE layouts", {}, Exception("duplicate key value violates unique constraint")
        )

        data = LayoutUpdate(name="Duplicate Name")

        with pytest.raises(IntegrityError, match="duplicate key value violates unique constraint"):
            await layout_service.update_layout(layout_id, data, db=mock_db)
        mock_db.rollback.assert_awaited_once()

    async def test_update_layout_partial(self, layout_service, mock_layout_repo, mock_db):
        """Test partial update only changes provided fields."""
        layout_id = uuid4()
        mock_layout_repo.get.return_value = self._make_layout_obj(
            layout_id=layout_id, name="Old Name", definition={"grid": []}
        )
        mock_layout_repo.update.return_value = self._make_layout_obj(layout_id=layout_id, name="Updated Name")

        data = LayoutUpdate(name="Updated Name")
        result = await layout_service.update_layout(layout_id, data, db=mock_db)

        assert result.name == "Updated Name"

    async def test_update_layout_no_fields(self, layout_service, mock_layout_repo, mock_db):
        """Test update with no fields returns existing layout."""
        layout_id = uuid4()
        existing_layout = self._make_layout_obj(layout_id=layout_id, name="Existing")
        mock_layout_repo.get.return_value = existing_layout

        data = LayoutUpdate()
        result = await layout_service.update_layout(layout_id, data, db=mock_db)

        assert result.name == "Existing"
        mock_layout_repo.update.assert_not_called()

    # --- delete tests ---

    async def test_delete_layout_success(self, layout_service, mock_layout_repo, mock_db):
        """Test successful layout deletion."""
        mock_layout_repo.delete.return_value = True

        result = await layout_service.delete_layout(uuid4(), db=mock_db)

        assert result is True

    async def test_delete_layout_not_found(self, layout_service, mock_layout_repo, mock_db):
        """Test deletion returns False when layout not found."""
        mock_layout_repo.delete.return_value = False

        result = await layout_service.delete_layout(uuid4(), db=mock_db)

        assert result is False

    # --- list tests ---

    async def test_get_all_layouts(self, layout_service, mock_layout_repo, mock_db):
        """Test getting all layouts."""
        mock_layout_repo.get_all.return_value = [
            self._make_layout_obj(name="Layout 1"),
            self._make_layout_obj(name="Layout 2"),
        ]

        result = await layout_service.get_all_layouts(db=mock_db)

        assert len(result) == 2
        assert all(isinstance(layout, LayoutRead) for layout in result)

    async def test_get_all_layouts_empty(self, layout_service, mock_layout_repo, mock_db):
        """Test getting layouts when none exist."""
        mock_layout_repo.get_all.return_value = []

        result = await layout_service.get_all_layouts(db=mock_db)

        assert result == []

    async def test_get_layouts_by_dashboard_ids(self, layout_service, mock_layout_repo, mock_db):
        """Test getting layouts by dashboard IDs."""
        dashboard_ids = [uuid4(), uuid4()]
        mock_layout_repo.get_layouts_by_dashboard_ids.return_value = [
            self._make_layout_obj(name="Layout 1"),
        ]

        result = await layout_service.get_layouts_by_dashboard_ids(dashboard_ids, db=mock_db)

        assert len(result) == 1
        assert isinstance(result[0], LayoutRead)

    # --- get_dashboard_id_for_layout tests ---

    async def test_get_dashboard_id_for_layout_found(self, layout_service, mock_layout_repo, mock_db):
        """Test getting dashboard ID for a layout when association exists."""
        layout_id = uuid4()
        dashboard_id = uuid4()
        mock_layout_repo.get_dashboard_id_for_layout.return_value = dashboard_id

        result = await layout_service.get_dashboard_id_for_layout(layout_id, db=mock_db)

        assert result == dashboard_id

    async def test_get_dashboard_id_for_layout_not_found(self, layout_service, mock_layout_repo, mock_db):
        """Test getting dashboard ID for layout when no association exists."""
        mock_layout_repo.get_dashboard_id_for_layout.return_value = None

        result = await layout_service.get_dashboard_id_for_layout(uuid4(), db=mock_db)

        assert result is None