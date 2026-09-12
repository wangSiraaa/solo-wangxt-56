"""分摊计算引擎与公示/结转工作流。所有金额用 Decimal,尾差用最大余数法确定性地分配。"""
from datetime import timedelta
from decimal import ROUND_FLOOR, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    Adjustment,
    AllocationDetail,
    AllocationRule,
    AllocationVersion,
    CarryForward,
    Dispute,
    RuleShare,
    Unit,
)

CENT = Decimal("0.01")
ZERO = Decimal("0")


def _scope_units(rule: AllocationRule):
    qs = Unit.objects.select_related("building")
    if rule.scope_type == "BUILDINGS":
        qs = qs.filter(building__in=rule.buildings.all())
    if rule.exclude_vacant:
        if not rule.vacant_basis:
            raise ValidationError("剔除空置房必须上传依据文件,不能无依据从基数剔除")
        qs = qs.filter(is_vacant=False)
    return list(qs.order_by("building_id", "code"))


def _ownership_slices(unit, start, end):
    """返回该单元在归属期内的权属片段 [(period, s, e, days)],要求完整覆盖归属期。"""
    slices = []
    for p in unit.ownership_periods.all():
        s = max(p.start_date, start)
        e = min(p.end_date or end, end)
        if s <= e:
            slices.append((p, s, e, (e - s).days + 1))
    total_days = (end - start).days + 1
    covered = sum(d for *_, d in slices)
    if covered != total_days:
        raise ValidationError(
            f"{unit} 的权属期间未完整覆盖收益归属期(覆盖 {covered}/{total_days} 天),请先补录权属数据"
        )
    return slices


def _split_into_slices(lines, unit, exact_amount, share, contract):
    """把某单元的应分金额按权属期间天数拆成可追溯的明细行。"""
    slices = _ownership_slices(unit, contract.period_start, contract.period_end)
    covered = sum(d for *_, d in slices)
    for period, s, e, days in slices:
        lines.append(
            {
                "unit": unit,
                "owner_name": period.owner_name,
                "ownership_period": period,
                "slice_start": s,
                "slice_end": e,
                "share": share,
                "exact": exact_amount * days / covered,
            }
        )


def _apply_rounding(lines, target_total):
    """最大余数法:先向下取整到分,剩余分额按小数部分从大到小补 0.01,保证合计精确等于目标。"""
    for ln in lines:
        ln["amount"] = ln["exact"].quantize(CENT, rounding=ROUND_FLOOR)
        ln["frac"] = ln["exact"] - ln["amount"]
        ln["remainder"] = False
    diff_cents = int(((target_total - sum(l["amount"] for l in lines)) / CENT).to_integral_value())
    order = sorted(
        range(len(lines)),
        key=lambda i: (
            -lines[i]["frac"],
            lines[i]["unit"].building_id,
            lines[i]["unit"].code,
            lines[i]["slice_start"],
        ),
    )
    if diff_cents > 0:
        for i in order[:diff_cents]:
            lines[i]["amount"] += CENT
            lines[i]["remainder"] = True
    elif diff_cents < 0:  # 理论上不会发生,防御性处理
        for i in reversed(order[: -diff_cents]):
            lines[i]["amount"] -= CENT
            lines[i]["remainder"] = True


@transaction.atomic
def generate_allocation(rule: AllocationRule) -> AllocationVersion:
    """按规则生成一个新的公示版本(草稿)。规则或受益基数变化后必须重新生成。"""
    if not rule.is_active:
        raise ValidationError("该规则已被新版本取代,不能用于生成公示版本")
    contract = rule.contract
    total = contract.total_amount
    lines = []
    unallocated = ZERO

    if rule.method == "BY_AREA":
        units = _scope_units(rule)
        if not units:
            raise ValidationError("受益范围为空")
        total_area = sum(u.area for u in units)
        if total_area <= 0:
            raise ValidationError("受益基数(总面积)为 0")
        for u in units:
            share = u.area / total_area
            _split_into_slices(lines, u, total * share, share, contract)
    else:  # FIXED_SHARE
        shares = list(rule.shares.select_related("unit", "unit__building").order_by(
            "unit__building_id", "unit__code"
        ))
        if not shares:
            raise ValidationError("固定份额模式但未配置任何份额")
        share_sum = sum((s.share for s in shares), ZERO)
        if share_sum > 1:
            raise ValidationError(f"固定份额合计 {share_sum} 超过 100%")
        if share_sum < 1 and rule.shortfall_policy == "RESERVE":
            unallocated = (total * (1 - share_sum)).quantize(CENT)
        factor = (1 / share_sum) if rule.shortfall_policy == "SCALE" else Decimal(1)
        for s in shares:
            eff_share = s.share * factor
            _split_into_slices(lines, s.unit, total * eff_share, eff_share, contract)

    target = total - unallocated
    _apply_rounding(lines, target)

    version = AllocationVersion.objects.create(
        rule=rule,
        version_no=rule.versions.count() + 1,
        allocated_total=target,
        unallocated_amount=unallocated,
    )
    AllocationDetail.objects.bulk_create(
        [
            AllocationDetail(
                version=version,
                unit=ln["unit"],
                owner_name=ln["owner_name"],
                ownership_period=ln["ownership_period"],
                slice_start=ln["slice_start"],
                slice_end=ln["slice_end"],
                share=ln["share"],
                amount=ln["amount"],
                remainder_applied=ln["remainder"],
            )
            for ln in lines
        ]
    )
    return version


@transaction.atomic
def revise_rule(rule: AllocationRule, shares=None, **changes) -> AllocationRule:
    """规则变更:作废旧版本、生成新版本规则。shares 为 [{unit, share}]。"""
    new_rule = AllocationRule(
        contract=rule.contract,
        version_no=rule.version_no + 1,
        supersedes=rule,
        is_active=True,
        scope_type=changes.get("scope_type", rule.scope_type),
        method=changes.get("method", rule.method),
        exclude_vacant=changes.get("exclude_vacant", rule.exclude_vacant),
        vacant_basis=changes.get("vacant_basis", rule.vacant_basis),
        shortfall_policy=changes.get("shortfall_policy", rule.shortfall_policy),
        publication_days=changes.get("publication_days", rule.publication_days),
    )
    new_rule.full_clean()
    new_rule.save()
    new_rule.buildings.set(changes.get("buildings", rule.buildings.all()))
    src_shares = shares if shares is not None else [
        {"unit": s.unit, "share": s.share} for s in rule.shares.all()
    ]
    for s in src_shares:
        RuleShare.objects.create(rule=new_rule, unit=s["unit"], share=s["share"])
    rule.is_active = False
    rule.save(update_fields=["is_active"])
    return new_rule


@transaction.atomic
def publish(version: AllocationVersion) -> AllocationVersion:
    """公示:必须有合同附件;规则必须仍是当前有效版本。"""
    if version.status != "DRAFT":
        raise ValidationError("只有草稿版本可以公示")
    if not version.rule.is_active:
        raise ValidationError("规则已变更,请基于新规则重新生成版本后再公示")
    if not version.rule.contract.attachments.exists():
        raise ValidationError("缺少合同附件,不能公示")
    version.status = "PUBLISHED"
    version.published_at = timezone.now()
    version.save(update_fields=["status", "published_at"])
    return version


@transaction.atomic
def carry_forward(version: AllocationVersion, note="") -> CarryForward:
    """结转:公示期满才允许;异议部分按冻结金额扣除。"""
    if version.status != "PUBLISHED":
        raise ValidationError("只有公示中的版本可以结转")
    deadline = version.published_at + timedelta(days=version.rule.publication_days)
    if timezone.now() < deadline:
        raise ValidationError(f"公示期内不可结转,公示至 {deadline:%Y-%m-%d %H:%M}")
    frozen_total = ZERO
    for detail in version.details.all():
        frozen = sum(
            (d.amount for d in detail.disputes.filter(status="OPEN")), ZERO
        )
        frozen = min(frozen, detail.amount)
        if frozen != detail.frozen_amount:
            detail.frozen_amount = frozen
            detail.save(update_fields=["frozen_amount"])
        frozen_total += frozen
    cf = CarryForward.objects.create(
        version=version,
        amount=version.allocated_total - frozen_total,
        frozen_total=frozen_total,
        note=note,
    )
    version.status = "CARRIED"
    version.save(update_fields=["status"])
    return cf


@transaction.atomic
def add_dispute(detail: AllocationDetail, amount: Decimal, reason: str) -> Dispute:
    """异议:仅公示期内可提出,冻结范围不超过该明细未冻结金额。"""
    if detail.version.status != "PUBLISHED":
        raise ValidationError("仅公示期内可提出异议;已结转记录请使用追加调整")
    amount = Decimal(amount)
    if amount <= 0:
        raise ValidationError("异议金额必须为正")
    open_frozen = sum(
        (d.amount for d in detail.disputes.filter(status="OPEN")), ZERO
    )
    if open_frozen + amount > detail.amount:
        raise ValidationError("异议冻结合计不能超过该明细金额")
    return Dispute.objects.create(detail=detail, amount=amount, reason=reason)


@transaction.atomic
def add_adjustment(version: AllocationVersion, detail: AllocationDetail, delta, reason: str) -> Adjustment:
    """追加调整:只允许挂在已结转记录上,只增不改。"""
    if version.status != "CARRIED" or not hasattr(version, "carry_forward"):
        raise ValidationError("只有已结转的版本才能追加调整")
    if detail.version_id != version.id:
        raise ValidationError("调整必须针对本版本的明细")
    delta = Decimal(delta)
    if delta == 0:
        raise ValidationError("调整金额不能为 0")
    if detail.payable + sum(
        (a.delta for a in detail.adjustments.all()), ZERO
    ) + delta < 0:
        raise ValidationError("调整后该明细不能为负")
    return Adjustment.objects.create(
        carry_forward=version.carry_forward, detail=detail, delta=delta, reason=reason
    )
