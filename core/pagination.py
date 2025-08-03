from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

def paginated_results(queryset, serializer_class, request, extra_data: dict = None, page_size=10):
    """Returns paginated results using DRF's paginator"""
    paginator = PageNumberPagination()
    paginator.page_size = page_size
    result_page = paginator.paginate_queryset(queryset, request)
    serialized_data = serializer_class(result_page, many=True).data

    response_data = {
        "results": serialized_data,
    }


    return Response(response_data)
