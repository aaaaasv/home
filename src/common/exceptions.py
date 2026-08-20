from datetime import datetime

from src.common.constants import CareTaskType, ErrorCode


class DomainError(Exception):
    default_code: ErrorCode = ErrorCode.VALIDATION_ERROR

    def __init__(self, detail: str, code: ErrorCode | None = None):
        self.detail = detail
        self.code = code or self.default_code
        super().__init__(detail)


class DoesNotExistError(DomainError):
    default_code = ErrorCode.NOT_FOUND


class AlreadyExistsError(DomainError):
    default_code = ErrorCode.ALREADY_EXISTS


class ConflictError(DomainError):
    default_code = ErrorCode.CONFLICT


class ValidationError(DomainError):
    default_code = ErrorCode.VALIDATION_ERROR


class RecentCareExistsError(ConflictError):
    default_code = ErrorCode.RECENT_CARE_EXISTS

    def __init__(
        self,
        detail: str,
        plant_name: str,
        task_type: CareTaskType,
        performed_at: datetime,
        performed_by_display_name: str,
    ):
        super().__init__(detail)
        self.plant_name = plant_name
        self.task_type = task_type
        self.performed_at = performed_at
        self.performed_by_display_name = performed_by_display_name
