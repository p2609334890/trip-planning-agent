"""
全局异常处理器
统一处理所有异常并返回标准格式的错误响应（ApiResponse 风格）
"""

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.exceptions.custom_exceptions import BaseAppException
from app.exceptions.error_codes import ErrorCode, get_error_message
from app.models import ApiResponse
from app.observability.logger import default_logger as logger, get_request_id


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    全局异常处理器

    所有错误统一包装为 ApiResponse[None]：
    - code: 业务错误码（0 以外）
    - message: 错误信息
    - data: 错误详情（包含 request_id 等上下文）
    """
    request_id = get_request_id()

    # 处理自定义业务异常
    if isinstance(exc, BaseAppException):
        logger.error(
            f"业务异常: {exc.message}",
            exc_info=True,
            extra={
                "request_id": request_id,
                "error_code": exc.error_code.value,
                "error_message": exc.message,
                "details": exc.details,
                "path": request.url.path,
                "method": request.method,
            },
        )

        resp = ApiResponse[dict](
            code=exc.error_code.value,
            message=exc.message,
            data={
                "details": exc.details,
                "request_id": request_id,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=resp.model_dump(),
        )

    # 处理 FastAPI 参数验证异常
    if isinstance(exc, RequestValidationError):
        errors = exc.errors()
        logger.warning(
            f"请求验证失败: {errors}",
            extra={
                "request_id": request_id,
                "errors": errors,
                "path": request.url.path,
                "method": request.method,
            },
        )

        resp = ApiResponse[dict](
            code=ErrorCode.INVALID_PARAMETER.value,
            message="请求参数验证失败",
            data={
                "validation_errors": errors,
                "request_id": request_id,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=resp.model_dump(),
        )

    # 处理 HTTP 异常
    if isinstance(exc, (StarletteHTTPException, HTTPException)):
        status_code = exc.status_code if hasattr(exc, "status_code") else 500
        detail = exc.detail if hasattr(exc, "detail") else str(exc)

        # 429 Too Many Requests 特殊处理
        if status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            error_code = ErrorCode.RATE_LIMIT_EXCEEDED.value
        else:
            error_code = ErrorCode.UNKNOWN_ERROR.value

        logger.warning(
            f"HTTP异常: {detail}",
            extra={
                "request_id": request_id,
                "status_code": status_code,
                "detail": detail,
                "path": request.url.path,
                "method": request.method,
            },
        )

        resp = ApiResponse[dict](
            code=error_code,
            message=str(detail),
            data={"request_id": request_id},
        )
        return JSONResponse(
            status_code=status_code,
            content=resp.model_dump(),
        )

    # 处理其他未知异常
    logger.error(
        f"未处理的异常: {type(exc).__name__}: {str(exc)}",
        exc_info=True,
        extra={
            "request_id": request_id,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "path": request.url.path,
            "method": request.method,
        },
    )

    resp = ApiResponse[dict](
        code=ErrorCode.UNKNOWN_ERROR.value,
        message="服务器内部错误",
        data={
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "request_id": request_id,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=resp.model_dump(),
    )

