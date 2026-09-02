from tortoise import fields
from tortoise.models import Model


class CategoryModel(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=50, unique=True)
    total_capacity = fields.IntField()
    walkin_capacity = fields.IntField()
    booking_capacity = fields.IntField()
    spot_taken_walkin = fields.IntField(default=0)
    spot_available_walkin = fields.IntField()
    spot_taken_booking = fields.IntField(default=0)
    spot_available_booking = fields.IntField()

    class Meta:
        table = "categories"


class TemporaryHoldModel(Model):
    id = fields.IntField(pk=True)
    category = fields.ForeignKeyField("models.CategoryModel", related_name="holds")
    commercial_type = fields.CharField(max_length=20)
    status = fields.CharField(max_length=20)
    created_at = fields.DatetimeField()
    end_at = fields.DatetimeField()

    class Meta:
        table = "temporary_holds"
