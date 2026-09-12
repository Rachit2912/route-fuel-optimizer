import pytest
from trips.serializers import TripOptimizeRequestSerializer


def test_serializer_valid_data():
    data = {"start": "  Chicago, IL  ", "finish": "  Miami, FL  "}
    serializer = TripOptimizeRequestSerializer(data=data)
    assert serializer.is_valid()
    assert serializer.validated_data["start"] == "Chicago, IL"
    assert serializer.validated_data["finish"] == "Miami, FL"


def test_serializer_missing_start():
    data = {"finish": "Miami, FL"}
    serializer = TripOptimizeRequestSerializer(data=data)
    assert not serializer.is_valid()
    assert "start" in serializer.errors


def test_serializer_missing_finish():
    data = {"start": "Chicago, IL"}
    serializer = TripOptimizeRequestSerializer(data=data)
    assert not serializer.is_valid()
    assert "finish" in serializer.errors


def test_serializer_blank_start():
    data = {"start": "   ", "finish": "Miami, FL"}
    serializer = TripOptimizeRequestSerializer(data=data)
    assert not serializer.is_valid()
    assert "start" in serializer.errors


def test_serializer_blank_finish():
    data = {"start": "Chicago, IL", "finish": "   "}
    serializer = TripOptimizeRequestSerializer(data=data)
    assert not serializer.is_valid()
    assert "finish" in serializer.errors


def test_serializer_max_length_exceeded():
    data = {"start": "A" * 256, "finish": "Miami, FL"}
    serializer = TripOptimizeRequestSerializer(data=data)
    assert not serializer.is_valid()
    assert "start" in serializer.errors
