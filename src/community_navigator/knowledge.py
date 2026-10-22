"""Loading and indexing for the local community knowledge base."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .models import CommunityData, LocationRecord, ServiceRecord


class KnowledgeBase:
    """Validated, indexed community service facts."""

    def __init__(self, data: CommunityData) -> None:
        self.data = data
        self._locations = {location.id: location for location in data.locations}
        self._services = {service.id: service for service in data.services}
        self._validate_integrity()

    @classmethod
    def load(cls, path: Path) -> "KnowledgeBase":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            data = CommunityData.model_validate(raw)
            return cls(data)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"知识库格式无效: {exc}") from exc

    def get_service(self, service_id: str) -> ServiceRecord | None:
        return self._services.get(service_id)

    def get_location(self, location_id: str) -> LocationRecord | None:
        return self._locations.get(location_id)

    def _validate_integrity(self) -> None:
        location_ids = [location.id for location in self.data.locations]
        service_ids = [service.id for service in self.data.services]
        led_indices = [location.led_index for location in self.data.locations]

        if len(location_ids) != len(set(location_ids)):
            raise ValueError("地点 ID 不能重复")
        if len(service_ids) != len(set(service_ids)):
            raise ValueError("服务 ID 不能重复")
        if len(led_indices) != len(set(led_indices)):
            raise ValueError("地图 LED 编号不能重复")

        missing_locations = {
            service.location_id
            for service in self.data.services
            if service.location_id not in self._locations
        }
        if missing_locations:
            missing = ", ".join(sorted(missing_locations))
            raise ValueError(f"服务引用了不存在的地点: {missing}")

