import re
import secrets
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers
from django.utils import timezone

from .models import Invitations, SharePermissions, Project, CustomDomain
from Qr.access import project_role, qr_role, role_allows
from system.models import ConfigChoice

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
from accounts.models import User
from system.models import ConfigChoice


class StatusSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigChoice
        fields = ["id", "name","image"]


class ProjectSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CreateOnlyDefault(serializers.CurrentUserDefault()))
    qr_count = serializers.IntegerField(read_only=True)
    accepted_people_count = serializers.IntegerField(read_only=True)
    access_level = serializers.SerializerMethodField()
    # status = StatusSummarySerializer(read_only=True)

    class Meta:
        model = Project
        # fields = "__all__"
        exclude = ["is_deleted", "deleted_at"]

    def get_access_level(self, obj):
        request = self.context.get("request")
        if request is None or not getattr(request, "user", None) or not request.user.is_authenticated:
            return None
        role = project_role(request.user, obj)
        return "all" if role == "owner" else role

    # def create(self, validated_data):
    #     validated_data["status"] = True
    #     return super().create(validated_data)


class QRCodeSerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CreateOnlyDefault(serializers.CurrentUserDefault()))
    permission = serializers.SerializerMethodField()
    access_level = serializers.SerializerMethodField()
    domain_name = serializers.SerializerMethodField()

    class Meta:
        model = QRCode
        exclude = ["is_deleted", "deleted_at"]

    def validate_project(self, project):
        request = self.context.get("request")
        if project and (request is None or not role_allows(project_role(request.user, project), "edit")):
            raise serializers.ValidationError("You cannot modify QR codes in this project.")
        return project

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

    def get_domain_name(self, obj):
        return obj.domain_name

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["qr_type"] = StatusSummarySerializer(instance.qr_type).data
        design_data = QRDesign.objects.filter(qr_code=instance).first()
        representation['json_data'] = QRDesignSerializer(design_data).data
        template = TemplateDesign.objects.filter(qr_code=instance).first()
        representation["template_id"] = str(template.id) if template else None
        return representation

    def get_permission(self, obj):
        request = self.context.get("request")
        if request is None or not getattr(request, "user", None) or not request.user.is_authenticated:
            return None

        if obj.created_by_id == request.user.id:
            return "edit"

        access_level = self._get_effective_access_level(obj, request.user)
        if access_level is None:
            return None

        if access_level in {"all", "admin", "edit"}:
            return "edit"
        if access_level == "view":
            return "view"
        if access_level == "delete":
            return "edit"
        return access_level

    def get_access_level(self, obj):
        request = self.context.get("request")
        if request is None or not getattr(request, "user", None) or not request.user.is_authenticated:
            return None

        if obj.created_by_id == request.user.id:
            return "all"

        return self._get_effective_access_level(obj, request.user)

    def _get_effective_access_level(self, obj, user):
        role = qr_role(user, obj)
        return "all" if role == "owner" else role


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
    template_id = serializers.SerializerMethodField()

    class Meta:
        model = QRDesign
        exclude = ["is_deleted", "deleted_at"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # representation["eye_style"] = StatusSummarySerializer(instance.eye_style).data
        # representation["pattern_style"] = StatusSummarySerializer(instance.pattern_style).data
        # representation["frame"] = StatusSummarySerializer(instance.frame).data if instance.frame else None
        return representation

    def get_template_id(self, obj):
        return obj.template_id


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
        obj = TemplateDesign.objects.filter(qr_code=instance).first()
        representation["template_id"] = obj.id if obj else None
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
        # Pass the parent instance through so unchanged unique fields are allowed on update.
        self.fields["QRCode"].instance = self.instance
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
        request = self.context.get("request")
        qrcodes = QRCode.objects.filter(project=obj, is_deleted=False).order_by("name")

        if request is not None and getattr(request, "user", None) and request.user.is_authenticated:
            if obj.owner_id == request.user.id:
                return QRCodeSerializer(qrcodes, many=True, context=self.context).data

            project_content_type = ContentType.objects.get_for_model(Project)
            has_project_access = SharePermissions.objects.filter(
                user_id=request.user,
                content_type=project_content_type,
                resource_id=obj.id,
                is_deleted=False,
            ).exists()

            if has_project_access:
                return QRCodeSerializer(qrcodes, many=True, context=self.context).data

        return []


class ProjectQRActionSerializer(serializers.Serializer):
    qr_id = serializers.UUIDField(help_text="ID of the QR code to add to or remove from the project.")


class ProjectMemberRoleSerializer(serializers.Serializer):
    role = serializers.UUIDField()

    def validate_role(self, value):
        try:
            return ConfigChoice.objects.get(
                id=value,
                category__name__iexact="sharing_permission",
                name__in=("Admin", "Edit", "View"),
                status=True,
            )
        except ConfigChoice.DoesNotExist:
            raise serializers.ValidationError("Invalid project role.")



class TemplateDesignSerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CreateOnlyDefault(serializers.CurrentUserDefault()))
    # qr_code = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = TemplateDesign
        exclude = ["is_deleted", "deleted_at"]

    def validate_qr_code(self, qr_code):
        request = self.context.get("request")
        if qr_code and (request is None or not role_allows(qr_role(request.user, qr_code), "edit")):
            raise serializers.ValidationError("You cannot edit this QR code.")
        return qr_code

    def _resolve_qr_code(self, qr_code_id):
        if qr_code_id in (None, ""):
            return None
        if isinstance(qr_code_id, QRCode):
            return qr_code_id
        try:
            return QRCode.objects.get(id=qr_code_id)
        except QRCode.DoesNotExist:
            raise serializers.ValidationError({"qr_code": "QR code not found."})

    def create(self, validated_data):
        qr_code_id = validated_data.pop("qr_code", None)
        qr_code = self._resolve_qr_code(qr_code_id)
        validated_data["qr_code"] = qr_code
        print(qr_code)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "qr_code" in validated_data:
            qr_code_id = validated_data.pop("qr_code")
            instance.qr_code = self._resolve_qr_code(qr_code_id)
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["qr_code"] = (
            {"id":instance.qr_code_id, "name":instance.qr_code.name}
            if instance.qr_code_id
            else None
        )
        return representation




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





class ProjectInvitationSerializer(serializers.Serializer):
    emails = serializers.ListField(
        child=serializers.EmailField(),
        required=True,
        allow_empty=False,
    )
    role = serializers.UUIDField()
    project_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=True,
        allow_empty=False,
    )

    def validate_emails(self, value):
        normalized = []
        seen = set()
        for email in value:
            email = email.strip().lower()
            if email in seen:
                continue
            seen.add(email)
            normalized.append(email)
        return normalized

    def validate_role(self, value):
        try:
            role = ConfigChoice.objects.get(
                id=value,
                category__name__iexact="sharing_permission",
                name__in=("Admin", "Edit", "View"),
                status=True,
            )
        except ConfigChoice.DoesNotExist:
            raise serializers.ValidationError(
                "Invalid project role."
            )

        self._role = role
        return value

    def validate(self, attrs):
        emails = attrs["emails"]
        project_ids = attrs["project_ids"]

        projects = list(
            Project.objects.filter(
                id__in=project_ids,
                is_deleted=False,
            )
        )

        found_ids = {str(item.id) for item in projects}
        missing_ids = [str(project_id) for project_id in project_ids if str(project_id) not in found_ids]
        if missing_ids or any(
            not role_allows(project_role(self.context["request"].user, project), "admin")
            for project in projects
        ):
            raise serializers.ValidationError(
                {
                    "project_ids": "One or more projects were not found or you do not have access to them."
                }
            )

        # Keep a stable unique list while preserving order.
        seen_ids = set()
        unique_projects = []
        for item in projects:
            if item.id in seen_ids:
                continue
            seen_ids.add(item.id)
            unique_projects.append(item)

        self._projects = unique_projects

        content_type = ContentType.objects.get_for_model(Project)
        for email in emails:
            user = User.objects.filter(
                email__iexact=email,
                is_deleted=False,
            ).first()

            if user:
                already_member_project_ids = list(
                    SharePermissions.objects.filter(
                        user_id=user,
                        content_type=content_type,
                        resource_id__in=[item.id for item in unique_projects],
                        is_deleted=False,
                    ).values_list("resource_id", flat=True)
                )

                if already_member_project_ids:
                    raise serializers.ValidationError(
                        {
                            "emails": f"{email} is already a member of one or more selected projects."
                        }
                    )

            pending_invitation = Invitations.objects.filter(
                email__iexact=email,
                content_type=content_type,
                resource_id__in=[item.id for item in unique_projects],
                status__name__iexact="pending",
                is_deleted=False,
            ).exists()

            if pending_invitation:
                raise serializers.ValidationError(
                    {
                        "emails": f"An invitation is already pending for {email}."
                    }
                )

        return attrs

    def create(self, validated_data):
        projects = getattr(self, "_projects", None)
        if not projects:
            raise serializers.ValidationError({"project_ids": "At least one project is required."})
        role = getattr(self, "_role", None)

        if role is None:
            raise serializers.ValidationError({"role": "Invalid project role."})

        pending_status = ConfigChoice.objects.filter(name__iexact="pending").first()
        if pending_status is None:
            raise serializers.ValidationError(
                {"status": "Pending invitation status is not configured."}
            )

        invitations = []
        content_type = ContentType.objects.get_for_model(Project)

        for email in validated_data["emails"]:
            for project in projects:
                invitations.append(
                    Invitations.objects.create(
                        email=email,
                        content_type=content_type,
                        resource_id=project.id,
                        role=role,
                        token=uuid4().hex,
                        invited_by=self.context["request"].user,
                        status=pending_status,
                        expires_at=timezone.now() + timedelta(days=7),
                    )
                )

        return invitations[0] if len(invitations) == 1 else invitations


class ProjectInvitationDetailSerializer(serializers.ModelSerializer):
    token = serializers.CharField(read_only=True)
    project_id = serializers.UUIDField(source="resource_id", read_only=True)
    project_name = serializers.SerializerMethodField()
    invited_by_name = serializers.SerializerMethodField()
    invited_by_email = serializers.EmailField(source="invited_by.email", read_only=True)
    role_name = serializers.CharField(
        source="role.name",
        read_only=True,
    )
    status = serializers.CharField(source="status.name", read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Invitations
        fields = [
            "token",
            "project_id",
            "email",
            "project_name",
            "invited_by_name",
            "invited_by_email",
            "role_name",
            "status",
            "expires_at",
            "created_at",
        ]

    def get_project_name(self, obj):
        return obj.content_object.name

    def get_invited_by_name(self, obj):
        return (
            obj.invited_by.get_full_name()
            or obj.invited_by.email
        )


from rest_framework import serializers

from .models import Project, QRCode, QRImportJob
from system.models import ConfigChoice


class QRImportJobUploadSerializer(serializers.Serializer):
    qr_type_id = serializers.UUIDField()
    project_id = serializers.UUIDField(required=False, allow_null=True)
    design_data = serializers.JSONField(required=False, allow_null=True)
    file = serializers.FileField()

    def validate_file(self, file):
        filename = file.name.lower()

        if not filename.endswith((".xlsx", ".xls")):
            raise serializers.ValidationError(
                "Only Excel files (.xlsx or .xls) are allowed."
            )

        # Optional safety limit: 5 MB
        max_size = 5 * 1024 * 1024

        if file.size > max_size:
            raise serializers.ValidationError(
                "Excel file size cannot exceed 5 MB."
            )

        return file

    def validate(self, attrs):
        qr_type_id = attrs["qr_type_id"]

        try:
            qr_type = ConfigChoice.objects.get(
                id=qr_type_id,
            )
        except ConfigChoice.DoesNotExist:
            raise serializers.ValidationError({
                "qr_type_id": "Invalid QR type."
            })

        attrs["qr_type"] = qr_type

        project_id = attrs.get("project_id")
        if project_id is not None:
            try:
                attrs["project"] = Project.objects.get(id=project_id)
            except Project.DoesNotExist:
                raise serializers.ValidationError({
                    "project_id": "Invalid project."
                })
            request = self.context.get("request")
            if request is None or not role_allows(project_role(request.user, attrs["project"]), "edit"):
                raise serializers.ValidationError({
                    "project_id": "You cannot modify QR codes in this project."
                })
        else:
            attrs["project"] = None

        attrs["design_data"] = attrs.get("design_data")

        return attrs


class QRImportJobStatusSerializer(serializers.ModelSerializer):
    status = serializers.CharField(source="status.name", read_only=True)
    qr_type = serializers.CharField(source="qr_type.name", read_only=True)
    project = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = QRImportJob
        fields = [
            "id",
            "project",
            "qr_type",
            "status",
            "total_rows",
            "processed_rows",
            "successful_rows",
            "failed_rows",
            "progress",
            "error_details",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields


class CustomDomainSerializer(serializers.ModelSerializer):
    verification_instructions = serializers.SerializerMethodField()
    is_verified = serializers.BooleanField(read_only=True)
    verification_url = serializers.SerializerMethodField()

    class Meta:
        model = CustomDomain
        fields = [
            'id',
            'domain',
            'status',
            'is_default',
            'verification_token',
            'verified_at',
            'activated_at',
            'created_at',
            'updated_at',
            'is_verified',
            'verification_url',
            'verification_instructions',
            'verification_attempts',
        ]
        read_only_fields = [
            'id',
            'status',
            'verification_token',
            'verified_at',
            'activated_at',
            'created_at',
            'updated_at',
            'is_verified',
            'verification_url',
            'verification_instructions',
            'verification_attempts',
        ]

    def validate_domain(self, value):
        """Validate domain format"""
        # Remove protocol if present
        domain = re.sub(r'^https?://', '', value)
        domain = domain.split('/')[0]

        # Validate domain format
        domain_regex = r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
        if not re.match(domain_regex, domain):
            raise serializers.ValidationError("Invalid domain format")

        # Check if domain is already taken
        if CustomDomain.objects.filter(
                domain=domain,
                is_deleted=False
        ).exists():
            raise serializers.ValidationError("Domain is already registered")

        return domain

    def get_verification_url(self, obj):
        """Return the URL the user can use to verify the domain."""
        return obj.get_verification_url()

    def get_verification_instructions(self, obj):
        """Generate verification instructions for the user"""
        return {
            'type': 'DNS',
            'cname_record': {
                'type': 'CNAME',
                'host': obj.domain,
                'value': settings.CUSTOM_DOMAIN_CNAME_TARGET,
                'ttl': 3600,
                'purpose': 'Required - Points the domain to the frontend gateway'
            },
            'txt_record': {
                'type': 'TXT',
                'host': obj.domain,
                'value': f'domain-verify={obj.verification_token}',
                'ttl': 3600,
                'purpose': 'Optional - Used for verification'
            },

            'verification_url': obj.get_verification_url(),
            'dns_propagation_time': 'Up to 24 hours',
            'frontend_note': 'The custom domain serves the frontend application, not the API server.'
        }


class AdminCustomDomainSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    is_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = CustomDomain
        fields = (
            "id", "domain", "status", "is_default", "is_verified",
            "user", "verification_attempts", "verified_at",
            "activated_at", "ssl_verified", "ssl_verified_at", "ssl_expires_at",
            "nginx_enabled", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_user(self, obj):
        return {
            "id": str(obj.user_id),
            "name": obj.user.full_name,
            "email": obj.user.email,
        }

    def get_verification_url(self, obj):
        return obj.get_verification_url()

    def create(self, validated_data):
        """Create domain with verification token"""
        validated_data['verification_token'] = secrets.token_urlsafe(32)
        return super().create(validated_data)

    class DomainVerificationSerializer(serializers.Serializer):
        token = serializers.CharField(max_length=100)

    class DomainResponseSerializer(serializers.Serializer):
        success = serializers.BooleanField()
        message = serializers.CharField()
        domain = serializers.CharField(required=False)
        method = serializers.CharField(required=False)
        attempts = serializers.IntegerField(required=False)
        verification_results = serializers.DictField(required=False)
