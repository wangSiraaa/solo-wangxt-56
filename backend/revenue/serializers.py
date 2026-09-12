from rest_framework import serializers

from .models import (
    Adjustment,
    AllocationDetail,
    AllocationRule,
    AllocationVersion,
    Building,
    CarryForward,
    ContractAttachment,
    Dispute,
    OwnershipPeriod,
    RevenueContract,
    RuleShare,
    Unit,
)


class BuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Building
        fields = ["id", "name"]


class UnitSerializer(serializers.ModelSerializer):
    building_name = serializers.CharField(source="building.name", read_only=True)

    class Meta:
        model = Unit
        fields = ["id", "building", "building_name", "code", "area", "is_vacant"]


class OwnershipPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = OwnershipPeriod
        fields = ["id", "unit", "owner_name", "start_date", "end_date"]


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractAttachment
        fields = ["id", "name", "file", "uploaded_at"]


class ContractSerializer(serializers.ModelSerializer):
    attachments = AttachmentSerializer(many=True, read_only=True)
    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)

    class Meta:
        model = RevenueContract
        fields = [
            "id", "name", "source_type", "source_type_display", "total_amount",
            "period_start", "period_end", "received_date", "attachments", "created_at",
        ]


class RuleShareSerializer(serializers.ModelSerializer):
    unit_code = serializers.CharField(source="unit.code", read_only=True)

    class Meta:
        model = RuleShare
        fields = ["id", "unit", "unit_code", "share"]


class RuleSerializer(serializers.ModelSerializer):
    shares = RuleShareSerializer(many=True, read_only=True)
    buildings = serializers.PrimaryKeyRelatedField(many=True, queryset=Building.objects.all())
    building_names = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="name", source="buildings"
    )
    scope_display = serializers.CharField(source="get_scope_type_display", read_only=True)
    method_display = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = AllocationRule
        fields = [
            "id", "contract", "version_no", "supersedes", "is_active",
            "scope_type", "scope_display", "buildings", "building_names",
            "method", "method_display", "exclude_vacant", "vacant_basis",
            "shortfall_policy", "publication_days", "shares", "created_at",
        ]


class DisputeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dispute
        fields = ["id", "detail", "amount", "reason", "status", "resolution", "created_at"]
        read_only_fields = ["status", "resolution"]


class AdjustmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Adjustment
        fields = ["id", "carry_forward", "detail", "delta", "reason", "created_at"]
        read_only_fields = ["carry_forward"]


class DetailSerializer(serializers.ModelSerializer):
    unit_code = serializers.CharField(source="unit.code", read_only=True)
    building_name = serializers.CharField(source="unit.building.name", read_only=True)
    disputes = DisputeSerializer(many=True, read_only=True)
    adjustments = AdjustmentSerializer(many=True, read_only=True)
    payable = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    contract_id = serializers.IntegerField(source="version.rule.contract_id", read_only=True)

    class Meta:
        model = AllocationDetail
        fields = [
            "id", "version", "contract_id", "unit", "unit_code", "building_name",
            "owner_name", "ownership_period", "slice_start", "slice_end",
            "share", "amount", "remainder_applied", "frozen_amount", "payable",
            "disputes", "adjustments",
        ]


class CarryForwardSerializer(serializers.ModelSerializer):
    adjustments = AdjustmentSerializer(many=True, read_only=True)

    class Meta:
        model = CarryForward
        fields = ["id", "version", "amount", "frozen_total", "note", "carried_at", "adjustments"]


class VersionSerializer(serializers.ModelSerializer):
    details = DetailSerializer(many=True, read_only=True)
    carry_forward = CarryForwardSerializer(read_only=True)
    contract_name = serializers.CharField(source="rule.contract.name", read_only=True)
    contract_id = serializers.IntegerField(source="rule.contract_id", read_only=True)
    rule_version_no = serializers.IntegerField(source="rule.version_no", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    scope_display = serializers.CharField(source="rule.get_scope_type_display", read_only=True)
    method_display = serializers.CharField(source="rule.get_method_display", read_only=True)
    building_names = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="name", source="rule.buildings"
    )

    class Meta:
        model = AllocationVersion
        fields = [
            "id", "rule", "contract_id", "contract_name", "rule_version_no",
            "version_no", "status", "status_display", "allocated_total",
            "unallocated_amount", "computed_at", "published_at",
            "scope_display", "method_display", "building_names",
            "details", "carry_forward",
        ]


class VersionListSerializer(serializers.ModelSerializer):
    contract_id = serializers.IntegerField(source="rule.contract_id", read_only=True)
    contract_name = serializers.CharField(source="rule.contract.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    scope_display = serializers.CharField(source="rule.get_scope_type_display", read_only=True)
    building_names = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="name", source="rule.buildings"
    )

    class Meta:
        model = AllocationVersion
        fields = [
            "id", "rule", "contract_id", "contract_name", "version_no",
            "status", "status_display", "allocated_total", "unallocated_amount",
            "computed_at", "published_at", "scope_display", "building_names",
        ]
