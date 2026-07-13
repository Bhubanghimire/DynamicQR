from rest_framework.schemas.openapi import AutoSchema


class PaginatedAutoSchema(AutoSchema):
    def get_pagination_parameters(self, path, method):
        if method.upper() != "GET":
            return []

        return [
            {
                "name": "page",
                "required": False,
                "in": "query",
                "description": "Page number for paginated list responses.",
                "schema": {"type": "integer"},
            },
            {
                "name": "page_size",
                "required": False,
                "in": "query",
                "description": "Number of items per page.",
                "schema": {"type": "integer"},
            },
        ]
