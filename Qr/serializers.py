from rest_framework import serializers

from Qr.models import Project, QRCode
from system.models import ConfigChoice


class StatusSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigChoice
        fields = ["id", "name"]


class ProjectSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    status = StatusSummarySerializer(read_only=True)

    class Meta:
        model = Project
        # fields = "__all__"
        exclude = ["is_deleted", "deleted_at"]

    def create(self, validated_data):
        validated_data["status_id"] = 1
        return super().create(validated_data)


class QRCodeSerializer(serializers.ModelSerializer):
    status = StatusSummarySerializer(read_only=True)
    qr_type = StatusSummarySerializer(read_only=True)

    class Meta:
        model = QRCode
        exclude = ["is_deleted", "deleted_at"]


class ProjectDetailSerializer(ProjectSerializer):
    qrcodes = serializers.SerializerMethodField()

    class Meta(ProjectSerializer.Meta):
        pass

    def get_qrcodes(self, obj):
        qrcodes = QRCode.objects.filter(project=obj)
        return QRCodeSerializer(qrcodes, many=True).data


class ProjectQRActionSerializer(serializers.Serializer):
    qr_id = serializers.IntegerField(help_text="ID of the QR code to add to or remove from the project.")
