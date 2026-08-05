from django.db import transaction
from rest_framework import serializers

from Qr.models import (
    Project,
    QRCode,
    QRCodeData,
    QRDesign,
    QRSchedule,
    QRScanSetting,
    TemplateDesign,
    QrMedia,
    MediaItem,
)
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

    def validate_link_name(self, value):
        if value in (None, ""):
            return value

        queryset = QRCode.objects.filter(link_name=value)
        instance = getattr(self, "instance", None)
        if instance is not None:
            queryset = queryset.exclude(pk=instance.pk)

        if queryset.exists():
            raise serializers.ValidationError("A QR code with this link name already exists.")

        return value

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


class MediaItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaItem
        exclude = ["is_deleted", "deleted_at", "qr_media"]


class QrMediaSerializer(serializers.ModelSerializer):
    videos = MediaItemSerializer(many=True, read_only=True)

    class Meta:
        model = QrMedia
        exclude = ["is_deleted", "deleted_at", "qrcode", "qr_code"]


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
        fields = [
            "id",
            "short_code",
            "link_name",
            "name",
            "qr_type",
            "project",
            "created_at",
            "status",
            "domain_name",
            "content_data",
            "design_data",
        ]

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
    QrMedia = QrMediaSerializer(required=False)

    def to_internal_value(self, data):
        data = data.copy()
        aliases = {
            "qr_code": "QRCode",
            "qr_code_data": "QRCodeData",
            "qr_schedule": "QRSchedule",
            "qr_scan_setting": "QRScanSetting",
            "qr_media": "QrMedia",
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
        qr_media_data = validated_data.pop("QrMedia", None)

        qr_code = QRCode.objects.create(**validated_data["QRCode"])
        if qr_code_data is not None:
            QRCodeData.objects.create(qr_code=qr_code, **qr_code_data)
        if qr_schedule_data is not None:
            QRSchedule.objects.create(qr_code=qr_code, **qr_schedule_data)
        if qr_scan_setting_data is not None:
            QRScanSetting.objects.create(qr_code=qr_code, **qr_scan_setting_data)
        if qr_media_data is not None:
            videos_data = qr_media_data.pop("videos", [])
            qr_media = QrMedia.objects.create(qrcode=qr_code, qr_code=qr_code, **qr_media_data)
            for video_data in videos_data:
                MediaItem.objects.create(qr_media=qr_media, **video_data)
        return qr_code

    @transaction.atomic
    def update(self, instance, validated_data):
        qr_code_data = validated_data.pop("QRCodeData", None)
        qr_schedule_data = validated_data.pop("QRSchedule", None)
        qr_scan_setting_data = validated_data.pop("QRScanSetting", None)
        qr_media_data = validated_data.pop("QrMedia", None)

        for attr, value in validated_data.get("QRCode", {}).items():
            setattr(instance, attr, value)
        instance.save()

        if qr_code_data is not None:
            self._update_or_create_related(QRCodeData, instance, qr_code_data)
        if qr_schedule_data is not None:
            self._update_or_create_related(QRSchedule, instance, qr_schedule_data)
        if qr_scan_setting_data is not None:
            self._update_or_create_related(QRScanSetting, instance, qr_scan_setting_data)
        if qr_media_data is not None:
            self._update_or_create_qr_media(instance, qr_media_data)
        return instance

    def _update_or_create_related(self, model, qr_code, data):
        related = model.objects.filter(qr_code=qr_code).first()
        if related is None:
            return model.objects.create(qr_code=qr_code, **data)

        for attr, value in data.items():
            setattr(related, attr, value)
        related.save()
        return related

    def _update_or_create_qr_media(self, qr_code, data):
        videos_data = data.pop("videos", None)
        related = QrMedia.objects.filter(qr_code=qr_code).first()
        if related is None:
            related = QrMedia.objects.create(qrcode=qr_code, qr_code=qr_code, **data)
        else:
            for attr, value in data.items():
                setattr(related, attr, value)
            related.save()

        if videos_data is not None:
            related.videos.all().delete()
            for index, video_data in enumerate(videos_data, start=1):
                MediaItem.objects.create(
                    qr_media=related,
                    sort_order=video_data.get("sort_order", index),
                    **{k: v for k, v in video_data.items() if k != "sort_order"},
                )
        return related

    def to_representation(self, instance):
        data = {
            "QRCode": QRCodeSerializer(instance, context=self.context).data,
            "QRCodeData": None,
            "QRSchedule": None,
            "QRScanSetting": None,
            "QrMedia": None,
        }

        qr_code_data = QRCodeData.objects.filter(qr_code=instance).first()
        qr_schedule = QRSchedule.objects.filter(qr_code=instance).first()
        qr_scan_setting = QRScanSetting.objects.filter(qr_code=instance).first()
        qr_media = QrMedia.objects.filter(qr_code=instance).first()

        if qr_code_data:
            data["QRCodeData"] = QRCodeDataSerializer(qr_code_data).data
        if qr_schedule:
            data["QRSchedule"] = QRScheduleSerializer(qr_schedule).data
        if qr_scan_setting:
            data["QRScanSetting"] = QRScanSettingSerializer(qr_scan_setting).data
        if qr_media:
            data["QrMedia"] = QrMediaSerializer(qr_media).data
        return data


class QRCodeDuplicateRequestSerializer(serializers.Serializer):
    pass

    def validate(self, attrs):
        request = self.context.get("request")
        source_qr = self.context.get("source_qr")

        if source_qr is None:
            raise serializers.ValidationError("source_qr is required.")

        if request is None or request.user is None:
            raise serializers.ValidationError("Authenticated request is required.")

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        source_qr = self.context["source_qr"]
        user = self.context["request"].user

        duplicate = QRCode.objects.create(
            project=source_qr.project,
            name=f"{source_qr.name}-copy" if source_qr.name else "copy",
            qr_type=source_qr.qr_type,
            status=source_qr.status,
            created_by=user,
        )

        self._duplicate_related(source_qr, duplicate)

        return duplicate

    def _duplicate_related(self, source_qr, duplicate_qr):
        source_qr_data = QRCodeData.objects.filter(qr_code=source_qr).first()
        if source_qr_data is not None:
            QRCodeData.objects.create(
                qr_code=duplicate_qr,
                content_json=source_qr_data.content_json,
            )

        source_schedule = QRSchedule.objects.filter(qr_code=source_qr).first()
        if source_schedule is not None:
            QRSchedule.objects.create(
                qr_code=duplicate_qr,
                name=source_schedule.name,
                start_date=source_schedule.start_date,
                end_date=source_schedule.end_date,
                is_scheduled=source_schedule.is_scheduled,
            )

        source_scan_setting = QRScanSetting.objects.filter(qr_code=source_qr).first()
        if source_scan_setting is not None:
            QRScanSetting.objects.create(
                qr_code=duplicate_qr,
                is_scan_limit=source_scan_setting.is_scan_limit,
                domain=source_scan_setting.domain,
                password_enabled=source_scan_setting.password_enabled,
                password=source_scan_setting.password,
                scan_limit=source_scan_setting.scan_limit,
                is_time_limit=source_scan_setting.is_time_limit,
                time_limit=source_scan_setting.time_limit,
            )

        source_design = QRDesign.objects.filter(qr_code=source_qr).first()
        if source_design is not None:
            QRDesign.objects.create(
                qr_code=duplicate_qr,
                design_data=source_design.design_data,
                template=source_design.template,
            )

        source_media = QrMedia.objects.filter(qr_code=source_qr).first()
        if source_media is not None:
            duplicate_media = QrMedia.objects.create(
                qrcode=duplicate_qr,
                qr_code=duplicate_qr,
                title=source_media.title,
                autoplay=source_media.autoplay,
                loop_playlist=source_media.loop_playlist,
                show_thumbnails=source_media.show_thumbnails,
            )

            for media_item in source_media.videos.all().order_by("sort_order"):
                MediaItem.objects.create(
                    qr_media=duplicate_media,
                    title=media_item.title,
                    description=media_item.description,
                    video=media_item.video,
                    thumbnail=media_item.thumbnail,
                    sort_order=media_item.sort_order,
                    is_active=media_item.is_active,
                )


class ProjectDetailSerializer(ProjectSerializer):
    qrcodes = serializers.SerializerMethodField()

    class Meta(ProjectSerializer.Meta):
        pass

    def get_qrcodes(self, obj):
        qrcodes = QRCode.objects.filter(project=obj, created_by=obj.owner)
        return QRCodeSerializer(qrcodes, many=True).data


class ProjectQRActionSerializer(serializers.Serializer):
    qr_id = serializers.UUIDField(help_text="ID of the QR code to add to or remove from the project.")



class TemplateDesignSerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = TemplateDesign
        exclude = ["is_deleted", "deleted_at"]




class VideoUploadSerializer(serializers.Serializer):
    # playlist_id = serializers.UUIDField(required=False)

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


class VideoUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    video = serializers.FileField(required=False)
    thumbnail = serializers.ImageField(required=False, allow_null=True)
    sort_order = serializers.IntegerField(required=False, min_value=1)
    is_active = serializers.BooleanField(required=False)


class VideoDeleteSerializer(serializers.Serializer):
    id = serializers.UUIDField(help_text="ID of the media item to delete.")
