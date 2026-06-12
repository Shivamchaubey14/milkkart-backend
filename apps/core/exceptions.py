from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        data = {"status_code": response.status_code}

        if isinstance(response.data, dict):
            data["errors"] = response.data
        elif isinstance(response.data, list):
            data["errors"] = {"detail": response.data}
        else:
            data["errors"] = {"detail": str(response.data)}

        response.data = data

    return response
