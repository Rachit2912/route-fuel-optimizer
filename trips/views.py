from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from trips.serializers import TripOptimizeRequestSerializer
from trips.services.trip_optimization import TripOptimizationService


class TripOptimizeView(APIView):
    def __init__(self, trip_service: TripOptimizationService = None, **kwargs):
        super().__init__(**kwargs)
        self.trip_service = trip_service or TripOptimizationService()

    def post(self, request, *args, **kwargs):
        serializer = TripOptimizeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        result = self.trip_service.optimize_trip(
            start_input=validated_data["start"],
            finish_input=validated_data["finish"],
        )

        return Response(result, status=status.HTTP_200_OK)
