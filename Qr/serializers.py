from django.db import transaction
from rest_framework import serializers

from Qr.models import Project, QRCode, QRCodeData, QRDesign, QRSchedule, QRScanSetting, TemplateDesign
from system.models import ConfigChoice


class StatusSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigChoice
        fields = ["id", "name","image"]


class ProjectSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    qr_count = serializers.IntegerField(read_only=True)
    # status = StatusSummarySerializer(read_only=True)

    class Meta:
        model = Project
        # fields = "__all__"
        exclude = ["is_deleted", "deleted_at"]

    # def create(self, validated_data):
    #     validated_data["status"] = True
    #     return super().create(validated_data)


class QRCodeSerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = QRCode
        exclude = ["is_deleted", "deleted_at"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["qr_type"] = StatusSummarySerializer(instance.qr_type).data
        design_data = QRDesign.objects.filter(qr_code=instance).first()
        representation['json_data'] = QRDesignSerializer(design_data).data
        return representation


class QRCodeDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = QRCodeData
        exclude = ["is_deleted", "deleted_at", "qr_code"]


class QRScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = QRSchedule
        exclude = ["is_deleted", "deleted_at", "qr_code"]


class QRScanSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = QRScanSetting
        exclude = ["is_deleted", "deleted_at", "qr_code"]


class QRDesignSerializer(serializers.ModelSerializer):
    class Meta:
        model = QRDesign
        exclude = ["is_deleted", "deleted_at"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # representation["eye_style"] = StatusSummarySerializer(instance.eye_style).data
        # representation["pattern_style"] = StatusSummarySerializer(instance.pattern_style).data
        # representation["frame"] = StatusSummarySerializer(instance.frame).data if instance.frame else None
        return representation


class QRCodeSummarySerializer(serializers.ModelSerializer):
    # type = serializers.CharField(read_only=True)
    domain_name = serializers.SerializerMethodField()
    design_data = serializers.SerializerMethodField()
    content_data = serializers.SerializerMethodField()
    # QRCodeData = QRCodeDataSerializer()

    class Meta:
        model = QRCode
        fields = ["id", "name", "qr_type", "project","created_at", "status", "domain_name","content_data", "design_data"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["qr_type"] = StatusSummarySerializer(instance.qr_type).data
        # design_data = QRDesign.objects.filter(qr_code=instance).first()
        # representation['json_data'] = QRDesignSerializer(design_data).data
        return representation


    def get_domain_name(self, obj):
        scan_setting = QRScanSetting.objects.filter(qr_code=obj).first()
        return scan_setting.domain if scan_setting else None

    def get_content_data(self, obj):
        content_data = QRCodeData.objects.filter(qr_code=obj).first()
        return  QRCodeDataSerializer(content_data).data

    def get_design_data(self, obj):
        design = QRDesign.objects.filter(qr_code=obj).first()
        design_ser = QRDesignSerializer(design).data if design else None
        if design_ser is not None:
            design_ser = design_ser["design_data"]
        return design_ser



class QRCodeBundleSerializer(serializers.Serializer):
    QRCode = QRCodeSerializer(required=True)
    QRCodeData = QRCodeDataSerializer(required=False)
    QRSchedule = QRScheduleSerializer(required=False)
    QRScanSetting = QRScanSettingSerializer(required=False)

    def to_internal_value(self, data):
        data = data.copy()
        aliases = {
            "qr_code": "QRCode",
            "qr_code_data": "QRCodeData",
            "qr_schedule": "QRSchedule",
            "qr_scan_setting": "QRScanSetting",
        }
        for alias, field in aliases.items():
            if alias in data and field not in data:
                data[field] = data[alias]
        return super().to_internal_value(data)

    @transaction.atomic
    def create(self, validated_data):
        qr_code_data = validated_data.pop("QRCodeData", None)
        qr_schedule_data = validated_data.pop("QRSchedule", None)
        qr_scan_setting_data = validated_data.pop("QRScanSetting", None)

        qr_code = QRCode.objects.create(**validated_data["QRCode"])
        if qr_code_data is not None:
            QRCodeData.objects.create(qr_code=qr_code, **qr_code_data)
        if qr_schedule_data is not None:
            QRSchedule.objects.create(qr_code=qr_code, **qr_schedule_data)
        if qr_scan_setting_data is not None:
            QRScanSetting.objects.create(qr_code=qr_code, **qr_scan_setting_data)
        return qr_code

    @transaction.atomic
    def update(self, instance, validated_data):
        qr_code_data = validated_data.pop("QRCodeData", None)
        qr_schedule_data = validated_data.pop("QRSchedule", None)
        qr_scan_setting_data = validated_data.pop("QRScanSetting", None)

        for attr, value in validated_data.get("QRCode", {}).items():
            setattr(instance, attr, value)
        instance.save()

        if qr_code_data is not None:
            self._update_or_create_related(QRCodeData, instance, qr_code_data)
        if qr_schedule_data is not None:
            self._update_or_create_related(QRSchedule, instance, qr_schedule_data)
        if qr_scan_setting_data is not None:
            self._update_or_create_related(QRScanSetting, instance, qr_scan_setting_data)
        return instance

    def _update_or_create_related(self, model, qr_code, data):
        related = model.objects.filter(qr_code=qr_code).first()
        if related is None:
            return model.objects.create(qr_code=qr_code, **data)

        for attr, value in data.items():
            setattr(related, attr, value)
        related.save()
        return related

    def to_representation(self, instance):
        data = {
            "QRCode": QRCodeSerializer(instance, context=self.context).data,
            "QRCodeData": None,
            "QRSchedule": None,
            "QRScanSetting": None,
        }

        qr_code_data = QRCodeData.objects.filter(qr_code=instance).first()
        qr_schedule = QRSchedule.objects.filter(qr_code=instance).first()
        qr_scan_setting = QRScanSetting.objects.filter(qr_code=instance).first()

        if qr_code_data:
            data["QRCodeData"] = QRCodeDataSerializer(qr_code_data).data
        if qr_schedule:
            data["QRSchedule"] = QRScheduleSerializer(qr_schedule).data
        if qr_scan_setting:
            data["QRScanSetting"] = QRScanSettingSerializer(qr_scan_setting).data
        return data


class ProjectDetailSerializer(ProjectSerializer):
    qrcodes = serializers.SerializerMethodField()

    class Meta(ProjectSerializer.Meta):
        pass

    def get_qrcodes(self, obj):
        qrcodes = QRCode.objects.filter(project=obj)
        return QRCodeSerializer(qrcodes, many=True).data


class ProjectQRActionSerializer(serializers.Serializer):
    qr_id = serializers.UUIDField(help_text="ID of the QR code to add to or remove from the project.")



class TemplateDesignSerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = TemplateDesign
        exclude = ["is_deleted", "deleted_at"]




class VideoUploadSerializer(serializers.Serializer):
    playlist_id = serializers.UUIDField(required=False)

    qr_code = serializers.UUIDField(required=False)

    playlist_title = serializers.CharField(required=False, allow_blank=True)
    video_description = serializers.CharField(required=False, allow_blank=True)

    video_title = serializers.CharField(required=False, allow_blank=True)

    video = serializers.FileField()
    thumbnail = serializers.ImageField(required=False)

    def validate(self, attrs):
        if attrs.get("playlist_id") is None and attrs.get("qr_code") is None:
            raise serializers.ValidationError(
                "qr_code is required when creating a new playlist."
            )
        return attrs


class VideoDeleteSerializer(serializers.Serializer):
    id = serializers.UUIDField(help_text="ID of the media item to delete.")
