from rest_framework import serializers

from system.models import ConfigCategory, ConfigChoice


class ConfigCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigCategory
        fields = ["id", "name"]


class ConfigChoiceSerializer(serializers.ModelSerializer):
    # category_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ConfigChoice
        fields = ["id", "name", "image", "description"]


class ConfigCategoryListResponseSerializer(serializers.Serializer):
    data = ConfigCategorySerializer(many=True)
    msg = serializers.CharField()


class ConfigChoiceListResponseSerializer(serializers.Serializer):
    data = ConfigChoiceSerializer(many=True)
    msg = serializers.CharField()


class PaginatedListResponseSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    data = serializers.JSONField()
    msg = serializers.CharField(required=False)


class ConfigCategoryPaginatedResponseSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    data = ConfigCategorySerializer(many=True)
    msg = serializers.CharField()


class ConfigChoicePaginatedResponseSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    data = ConfigChoiceSerializer(many=True)
    msg = serializers.CharField()
