from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler


class DomainException(Exception):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_code = "INTERNAL_ERROR"
    default_message = "An unexpected error occurred."

    def __init__(self, message: str = None, code: str = None):
        self.message = message or self.default_message
        self.code = code or self.default_code
        super().__init__(self.message)


class InvalidRequestError(DomainException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "INVALID_REQUEST"
    default_message = "Invalid request payload."


class LocationNotFoundError(DomainException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "LOCATION_NOT_FOUND"
    default_message = "Location could not be resolved."


class UnsupportedRegionError(DomainException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "UNSUPPORTED_REGION"
    default_message = "Location is outside the supported USA region."


class RouteNotFoundError(DomainException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "ROUTE_NOT_FOUND"
    default_message = "Provider cannot find a drivable route."


class InfeasibleRouteError(DomainException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "NO_FEASIBLE_FUEL_PLAN"
    default_message = "No feasible fuel plan could be found for this route."


class StationDataUnavailableError(DomainException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "STATION_DATA_UNAVAILABLE"
    default_message = "Fuel station database is empty. Please run station preprocessing/import first."


class RoutingProviderError(DomainException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_code = "ROUTING_PROVIDER_ERROR"
    default_message = "Provider returned an unexpected upstream error."


class RoutingProviderTimeoutError(DomainException):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    default_code = "ROUTING_PROVIDER_TIMEOUT"
    default_message = "Provider request timed out."


def custom_exception_handler(exc, context):
    if isinstance(exc, DomainException):
        return Response(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                }
            },
            status=exc.status_code,
        )

    response = exception_handler(exc, context)

    if response is not None:
        if isinstance(response.data, dict) and "error" in response.data:
            return response

        message = "Invalid request payload."
        if isinstance(response.data, dict):
            # Extract first error message if available
            messages = []
            for field, errors in response.data.items():
                if isinstance(errors, list) and errors:
                    messages.append(f"{field}: {errors[0]}")
                elif isinstance(errors, str):
                    messages.append(f"{field}: {errors}")
            if messages:
                message = "; ".join(messages)
        elif isinstance(response.data, list) and response.data:
            message = str(response.data[0])

        return Response(
            {
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": message,
                }
            },
            status=response.status_code,
        )

    return Response(
        {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal server error occurred.",
            }
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
