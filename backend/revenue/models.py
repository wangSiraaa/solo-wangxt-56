from django.core.exceptions import ValidationError
from django.db import models


class Building(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Unit(models.Model):
    building = models.ForeignKey(Building, related_name="units", on_delete=models.CASCADE)
    code = models.CharField(max_length=20)
    area = models.DecimalField(max_digits=10, decimal_places=2)
    is_vacant = models.BooleanField(default=False, help_text="空置房,无依据不得从受益基数剔除")

    class Meta:
        unique_together = ("building", "code")
        ordering = ["building_id", "code"]

    def __str__(self):
        return f"{self.building.name}-{self.code}"


class OwnershipPeriod(models.Model):
    """权属期间:某套房屋在 [start_date, end_date] 内归属某业主;end_date 为空表示至今。"""

    unit = models.ForeignKey(Unit, related_name="ownership_periods", on_delete=models.CASCADE)
    owner_name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["start_date"]

    def clean(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("权属期间结束日期不能早于开始日期")
        qs = self.unit.ownership_periods.exclude(pk=self.pk)
        my_end = self.end_date or "9999-12-31"
        for other in qs:
            other_end = other.end_date or "9999-12-31"
            if self.start_date <= other_end and other.start_date <= my_end:
                raise ValidationError(f"权属期间与已有记录重叠:{other}")

    def __str__(self):
        return f"{self.unit} {self.owner_name} {self.start_date}~{self.end_date or '至今'}"


class RevenueContract(models.Model):
    """公共收益合同:收入归属期与收款日期分开记录。"""

    SOURCE_CHOICES = [("PARKING", "停车位"), ("AD", "广告位"), ("OTHER", "其他")]

    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    period_start = models.DateField(help_text="收入归属期起")
    period_end = models.DateField(help_text="收入归属期止")
    received_date = models.DateField(help_text="实际收款日期,与归属期无关")
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.period_end < self.period_start:
            raise ValidationError("归属期结束不能早于开始")

    def __str__(self):
        return f"{self.name} ¥{self.total_amount}"


class ContractAttachment(models.Model):
    """合同附件:缺少附件的收益不允许公示。"""

    contract = models.ForeignKey(RevenueContract, related_name="attachments", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    file = models.FileField(upload_to="contracts/")
    uploaded_at = models.DateTimeField(auto_now_add=True)


class AllocationRule(models.Model):
    """分摊规则(版本化):任何规则或受益基数变化都生成新版本作废旧版本。"""

    SCOPE_CHOICES = [("ALL", "全体业主"), ("BUILDINGS", "指定楼栋")]
    METHOD_CHOICES = [("BY_AREA", "按建筑面积"), ("FIXED_SHARE", "固定份额")]
    SHORTFALL_CHOICES = [("SCALE", "份额不足按比例放大"), ("RESERVE", "份额不足部分结余留存")]

    contract = models.ForeignKey(RevenueContract, related_name="rules", on_delete=models.CASCADE)
    version_no = models.PositiveIntegerField(default=1)
    supersedes = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="superseded_by"
    )
    is_active = models.BooleanField(default=True)
    scope_type = models.CharField(max_length=10, choices=SCOPE_CHOICES, default="ALL")
    buildings = models.ManyToManyField(Building, blank=True, help_text="受益范围限定的楼栋")
    method = models.CharField(max_length=12, choices=METHOD_CHOICES, default="BY_AREA")
    exclude_vacant = models.BooleanField(default=False)
    vacant_basis = models.FileField(
        upload_to="basis/", null=True, blank=True, help_text="剔除空置房的依据文件,必传"
    )
    shortfall_policy = models.CharField(max_length=10, choices=SHORTFALL_CHOICES, default="RESERVE")
    publication_days = models.PositiveIntegerField(default=7, help_text="公示天数,期内不可结转")
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.exclude_vacant and not self.vacant_basis:
            raise ValidationError("剔除空置房必须上传依据文件,不能无依据从基数剔除")

    def __str__(self):
        return f"规则v{self.version_no}@{self.contract.name}"


class RuleShare(models.Model):
    """固定份额模式下每个单元的份额(0~1)。合计不足 1 时按 shortfall_policy 处理。"""

    rule = models.ForeignKey(AllocationRule, related_name="shares", on_delete=models.CASCADE)
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE)
    share = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        unique_together = ("rule", "unit")


class AllocationVersion(models.Model):
    """公示版本:一次计算结果。规则变化须重新生成;公示期内不可结转。"""

    STATUS_CHOICES = [("DRAFT", "草稿"), ("PUBLISHED", "公示中"), ("CARRIED", "已结转")]

    rule = models.ForeignKey(AllocationRule, related_name="versions", on_delete=models.PROTECT)
    version_no = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="DRAFT")
    allocated_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    unallocated_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, help_text="份额不足等原因未分配的结余"
    )
    computed_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("rule", "version_no")
        ordering = ["-computed_at"]

    def __str__(self):
        return f"版本v{self.version_no}({self.get_status_display()}) {self.rule}"


class AllocationDetail(models.Model):
    """分摊明细:每一行可追溯到原收入合同与权属期间片段。"""

    version = models.ForeignKey(AllocationVersion, related_name="details", on_delete=models.CASCADE)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    owner_name = models.CharField(max_length=100)
    ownership_period = models.ForeignKey(
        OwnershipPeriod, null=True, on_delete=models.PROTECT, help_text="追溯到权属期间"
    )
    slice_start = models.DateField(help_text="该明细覆盖的归属期片段起")
    slice_end = models.DateField(help_text="该明细覆盖的归属期片段止")
    share = models.DecimalField(max_digits=14, decimal_places=8, help_text="占总收益的比例")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    remainder_applied = models.BooleanField(default=False, help_text="尾差调整标记(+0.01)")
    frozen_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, help_text="异议冻结金额"
    )

    class Meta:
        ordering = ["unit__building_id", "unit__code", "slice_start"]

    @property
    def payable(self):
        return self.amount - self.frozen_amount


class Dispute(models.Model):
    """异议:公示期内对某条明细提出,按约定范围冻结对应金额。"""

    STATUS_CHOICES = [("OPEN", "未处理"), ("RESOLVED", "已处理")]

    detail = models.ForeignKey(AllocationDetail, related_name="disputes", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="OPEN")
    resolution = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


class CarryForward(models.Model):
    """结转记录:结转后版本只读,仅允许追加调整。"""

    version = models.OneToOneField(AllocationVersion, related_name="carry_forward", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=14, decimal_places=2, help_text="实际结转金额(扣除冻结)")
    frozen_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    note = models.CharField(max_length=200, blank=True)
    carried_at = models.DateTimeField(auto_now_add=True)


class Adjustment(models.Model):
    """追加调整:仅允许挂在已结转记录上,只增不改不删。"""

    carry_forward = models.ForeignKey(CarryForward, related_name="adjustments", on_delete=models.PROTECT)
    detail = models.ForeignKey(AllocationDetail, related_name="adjustments", on_delete=models.PROTECT)
    delta = models.DecimalField(max_digits=14, decimal_places=2, help_text="正为补分,负为扣回")
    reason = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
