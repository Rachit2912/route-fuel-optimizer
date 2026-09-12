from rest_framework import serializers


class TripOptimizeRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        max_length=255,
        error_messages={
            "required": "Start location is required.",
            "blank": "Start location cannot be blank.",
            "invalid": "Start location must be a valid string.",
            "max_length": "Start location exceeds maximum length of 255 characters.",
        },
    )
    finish = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        max_length=255,
        error_messages={
            "required": "Finish location is required.",
            "blank": "Finish location cannot be blank.",
            "invalid": "Finish location must be a valid string.",
            "max_length": "Finish location exceeds maximum length of 255 characters.",
        },
    )
