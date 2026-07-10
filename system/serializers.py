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
        fields = ["id", "name", "image"]


class ConfigCategoryListResponseSerializer(serializers.Serializer):
    data = ConfigCategorySerializer(many=True)
    msg = serializers.CharField()


class ConfigChoiceListResponseSerializer(serializers.Serializer):
    data = ConfigChoiceSerializer(many=True)
    msg = serializers.CharField()
