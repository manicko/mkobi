from datetime import datetime
from pydantic import BaseModel, ConfigDict
from uuid import UUID

from mkobi.models.enums import AggregationFunctionEnum
from mkobi.models.types import ProcessingSettingsModel


class ProcessingConfigBase(BaseModel):
    """Base model for processing settings."""

    settings: ProcessingSettingsModel
    metric_agg: AggregationFunctionEnum | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "settings": {
                    "loader": "sales_loader",
                    "date_column": "event_date",
                    "timezone": "UTC",
                },
                "metric_agg": "sum",
            }
        },
    )


class ProcessingConfigCreate(ProcessingConfigBase):
    """Model for creating processing settings."""

    pass


class ProcessingConfigUpdate(BaseModel):
    """Model for updating processing settings."""

    settings: ProcessingSettingsModel | None = None
    metric_agg: AggregationFunctionEnum | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "settings": {
                    "loader": "updated_loader",
                    "date_column": "updated_date",
                    "timezone": "Europe/Moscow",
                },
                "metric_agg": "mean",
            }
        },
    )


class ProcessingConfigRead(ProcessingConfigBase):
    """Model for reading processing settings data."""

    dashboard_id: UUID
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
                "settings": {
                    "loader": "sales_loader",
                    "date_column": "event_date",
                    "timezone": "UTC",
                },
                "metric_agg": "sum",
                "updated_at": "2026-04-24T16:02:46+03:00",
            }
        },
    )