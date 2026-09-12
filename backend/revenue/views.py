from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import exception_handler

from . import services
from .models import (
    Adjustment,
    AllocationDetail,
    AllocationRule,
    AllocationVersion,
    Building,
    ContractAttachment,
    RevenueContract,
    Unit,
)
from .serializers import (
    AdjustmentSerializer,
    BuildingSerializer,
    ContractSerializer,
    DetailSerializer,
    DisputeSerializer,
    RuleSerializer,
    UnitSerializer,
    VersionListSerializer,
    VersionSerializer,
)


def drf_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
    return exception_handler(exc, context)


class BuildingViewSet(viewsets.ModelViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer


class UnitViewSet(viewsets.ModelViewSet):
    queryset = Unit.objects.select_related("building").all()
    serializer_class = UnitSerializer


class ContractViewSet(viewsets.ModelViewSet):
    queryset = RevenueContract.objects.prefetch_related("attachments").all()
    serializer_class = ContractSerializer

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def attachments(self, request, pk=None):
        """上传合同附件(公示前置条件)。"""
        contract = self.get_object()
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "缺少文件"}, status=400)
        att = ContractAttachment.objects.create(
            contract=contract, name=request.data.get("name") or f.name, file=f
        )
        return Response({"id": att.id, "name": att.name}, status=201)


class RuleViewSet(viewsets.ModelViewSet):
    queryset = AllocationRule.objects.prefetch_related("shares", "buildings").all()
    serializer_class = RuleSerializer

    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        """规则变更:作废旧规则,生成 version_no+1 的新规则。"""
        rule = self.get_object()
        data = request.data
        changes = {
            k: data[k]
            for k in ["scope_type", "method", "exclude_vacant", "shortfall_policy", "publication_days"]
            if k in data
        }
        if "buildings" in data:
            changes["buildings"] = Building.objects.filter(id__in=data["buildings"])
        shares = None
        if "shares" in data:
            shares = [
                {"unit": Unit.objects.get(id=s["unit"]), "share": s["share"]}
                for s in data["shares"]
            ]
        new_rule = services.revise_rule(rule, shares=shares, **changes)
        return Response(RuleSerializer(new_rule).data, status=201)

    @action(detail=True, methods=["post"])
    def generate(self, request, pk=None):
        """基于当前规则生成新的公示版本(草稿)。"""
        version = services.generate_allocation(self.get_object())
        return Response(VersionSerializer(version).data, status=201)


class VersionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AllocationVersion.objects.select_related("rule__contract").all()

    def get_serializer_class(self):
        return VersionListSerializer if self.action == "list" else VersionSerializer

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        return Response(VersionSerializer(services.publish(self.get_object())).data)

    @action(detail=True, methods=["post"])
    def carry_forward(self, request, pk=None):
        cf = services.carry_forward(self.get_object(), note=request.data.get("note", ""))
        return Response({"id": cf.id, "amount": str(cf.amount), "frozen_total": str(cf.frozen_total)})

    @action(detail=True, methods=["get"])
    def trace(self, request, pk=None):
        """逐笔追溯:每条分摊明细 -> 原收入合同与权属期间片段。"""
        version = self.get_object()
        c = version.rule.contract
        return Response(
            {
                "contract": {
                    "id": c.id,
                    "name": c.name,
                    "total_amount": str(c.total_amount),
                    "period_start": c.period_start,
                    "period_end": c.period_end,
                    "received_date": c.received_date,
                },
                "rule_version": version.rule.version_no,
                "details": DetailSerializer(version.details.all(), many=True).data,
            }
        )

    @action(detail=True, methods=["post"])
    def adjustments(self, request, pk=None):
        """已结转版本追加调整(只允许新增,不允许修改/删除历史)。"""
        version = self.get_object()
        detail = AllocationDetail.objects.get(id=request.data.get("detail"))
        adj = services.add_adjustment(
            version, detail, request.data.get("delta"), request.data.get("reason", "")
        )
        return Response(AdjustmentSerializer(adj).data, status=201)


class DetailViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AllocationDetail.objects.select_related("unit__building").all()
    serializer_class = DetailSerializer

    @action(detail=True, methods=["post"])
    def disputes(self, request, pk=None):
        dispute = services.add_dispute(
            self.get_object(), request.data.get("amount"), request.data.get("reason", "")
        )
        return Response(DisputeSerializer(dispute).data, status=201)


class AdjustmentViewSet(viewsets.ReadOnlyModelViewSet):
    """调整记录只读列表:追加通过 versions/{id}/adjustments/ 完成,不提供修改/删除。"""

    queryset = Adjustment.objects.all()
    serializer_class = AdjustmentSerializer
