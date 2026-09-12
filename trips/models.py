from django.db import models


class FuelStation(models.Model):
    opis_id = models.IntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    rack_id = models.IntegerField(null=True, blank=True)

    effective_price = models.DecimalField(max_digits=10, decimal_places=4)
    price_min = models.DecimalField(max_digits=10, decimal_places=4)
    price_max = models.DecimalField(max_digits=10, decimal_places=4)
    price_observation_count = models.IntegerField()
    source_row_count = models.IntegerField()

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    geocode_source = models.CharField(max_length=50, default="unresolved")
    geocode_precision = models.CharField(max_length=50, default="unresolved")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["opis_id"]

    def __str__(self):
        return f"{self.opis_id} - {self.name} ({self.city}, {self.state})"
