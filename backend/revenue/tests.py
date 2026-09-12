from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone

from . import services
from .models import (
    Adjustment,
    AllocationRule,
    Building,
    ContractAttachment,
    OwnershipPeriod,
    RevenueContract,
    RuleShare,
    Unit,
)


class BaseData(TestCase):
    def setUp(self):
        self.b1 = Building.objects.create(name="1号楼")
        self.b2 = Building.objects.create(name="2号楼")
        self.u101 = Unit.objects.create(building=self.b1, code="1-101", area=Decimal("100"))
        self.u102 = Unit.objects.create(building=self.b1, code="1-102", area=Decimal("80"))
        self.u201 = Unit.objects.create(building=self.b2, code="2-201", area=Decimal("120"), is_vacant=True)
        self.u202 = Unit.objects.create(building=self.b2, code="2-202", area=Decimal("100"))
        # 1-101 归属期内过户:张三 -> 李四
        OwnershipPeriod.objects.create(unit=self.u101, owner_name="张三",
                                       start_date=date(2025, 1, 1), end_date=date(2026, 3, 15))
        OwnershipPeriod.objects.create(unit=self.u101, owner_name="李四",
                                       start_date=date(2026, 3, 16), end_date=None)
        for u, n in [(self.u102, "王五"), (self.u201, "赵六"), (self.u202, "孙七")]:
            OwnershipPeriod.objects.create(unit=u, owner_name=n,
                                           start_date=date(2025, 1, 1), end_date=None)
        self.contract = RevenueContract.objects.create(
            name="广告收益", source_type="AD", total_amount=Decimal("10000.00"),
            period_start=date(2026, 1, 1), period_end=date(2026, 6, 30),
            received_date=date(2026, 7, 5),
        )

    def make_rule(self, **kw):
        defaults = dict(contract=self.contract, scope_type="ALL", method="BY_AREA")
        defaults.update(kw)
        return AllocationRule.objects.create(**defaults)

    def attach(self, contract=None):
        return ContractAttachment.objects.create(
            contract=contract or self.contract, name="合同.pdf",
            file=ContentFile(b"scan", name="c.pdf"),
        )


class CrossPeriodTest(BaseData):
    """样例一:一笔收益跨两个产权期间,按天拆分给前后业主。"""

    def test_split_across_ownership_periods(self):
        v = services.generate_allocation(self.make_rule())
        zhang = v.details.get(owner_name="张三")
        li = v.details.get(owner_name="李四")
        # 1-101 占总面积 400 的 1/4 => 2500;按 74/107 天拆分
        self.assertEqual(zhang.slice_start, date(2026, 1, 1))
        self.assertEqual(zhang.slice_end, date(2026, 3, 15))
        self.assertEqual(li.slice_start, date(2026, 3, 16))
        self.assertEqual(li.slice_end, date(2026, 6, 30))
        self.assertEqual(zhang.amount + li.amount, Decimal("2500.00"))
        self.assertEqual(zhang.amount, Decimal("1022.10"))  # 2500*74/181=1022.0994.. 尾差补给张三
        self.assertEqual(li.amount, Decimal("1477.90"))
        self.assertTrue(zhang.remainder_applied or li.remainder_applied)
        # 每行都能追溯到权属期间与原合同
        self.assertIsNotNone(zhang.ownership_period)
        self.assertEqual(v.rule.contract_id, self.contract.id)
        total = sum(d.amount for d in v.details.all())
        self.assertEqual(total, Decimal("10000.00"))

    def test_ownership_gap_rejected(self):
        OwnershipPeriod.objects.filter(unit=self.u102).update(end_date=date(2026, 3, 31))
        with self.assertRaisesMessage(ValidationError, "权属期间未完整覆盖"):
            services.generate_allocation(self.make_rule())


class RemainderTest(TestCase):
    """样例三:100 元三等分,尾差 0.01 确定性分配且合计精确。"""

    def test_remainder_allocation(self):
        b = Building.objects.create(name="3号楼")
        units = [Unit.objects.create(building=b, code=f"3-30{i}", area=Decimal("60")) for i in (1, 2, 3)]
        for i, u in enumerate(units):
            OwnershipPeriod.objects.create(unit=u, owner_name=f"业主{i}",
                                           start_date=date(2025, 1, 1), end_date=None)
        c = RevenueContract.objects.create(
            name="场地费", source_type="OTHER", total_amount=Decimal("100.00"),
            period_start=date(2026, 3, 1), period_end=date(2026, 3, 31),
            received_date=date(2026, 4, 2),
        )
        rule = AllocationRule.objects.create(contract=c, method="BY_AREA")
        v = services.generate_allocation(rule)
        amounts = sorted(d.amount for d in v.details.all())
        self.assertEqual(amounts, [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")])
        self.assertEqual(sum(amounts), Decimal("100.00"))
        flagged = [d for d in v.details.all() if d.remainder_applied]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0].amount, Decimal("33.34"))
        # 确定性:重算结果一致(按楼栋/房号排序打破平局)
        self.assertEqual(flagged[0].unit.code, "3-301")


class ShortfallTest(BaseData):
    """样例二:固定份额合计 90%,不足部分结余留存,不得静默放大。"""

    def make_share_rule(self, policy="RESERVE"):
        rule = self.make_rule(method="FIXED_SHARE", shortfall_policy=policy)
        for u, s in [(self.u101, "0.30"), (self.u102, "0.25"), (self.u201, "0.35")]:
            RuleShare.objects.create(rule=rule, unit=u, share=Decimal(s))
        return rule

    def test_reserve_policy(self):
        v = services.generate_allocation(self.make_share_rule("RESERVE"))
        self.assertEqual(v.allocated_total, Decimal("9000.00"))
        self.assertEqual(v.unallocated_amount, Decimal("1000.00"))
        total = sum(d.amount for d in v.details.all())
        self.assertEqual(total, Decimal("9000.00"))
        self.assertEqual(total + v.unallocated_amount, self.contract.total_amount)

    def test_scale_policy(self):
        v = services.generate_allocation(self.make_share_rule("SCALE"))
        self.assertEqual(v.unallocated_amount, Decimal("0.00"))
        self.assertEqual(sum(d.amount for d in v.details.all()), Decimal("10000.00"))

    def test_share_over_100_rejected(self):
        rule = self.make_rule(method="FIXED_SHARE")
        RuleShare.objects.create(rule=rule, unit=self.u101, share=Decimal("0.7"))
        RuleShare.objects.create(rule=rule, unit=self.u102, share=Decimal("0.5"))
        with self.assertRaisesMessage(ValidationError, "超过 100%"):
            services.generate_allocation(rule)


class VacantTest(BaseData):
    def test_vacant_exclusion_requires_basis(self):
        rule = self.make_rule(exclude_vacant=True)
        with self.assertRaisesMessage(ValidationError, "依据"):
            services.generate_allocation(rule)

    def test_vacant_included_by_default(self):
        v = services.generate_allocation(self.make_rule())
        self.assertTrue(v.details.filter(unit=self.u201).exists())


class WorkflowTest(BaseData):
    def test_publish_requires_attachment(self):
        v = services.generate_allocation(self.make_rule())
        with self.assertRaisesMessage(ValidationError, "缺少合同附件"):
            services.publish(v)
        self.attach()
        services.publish(v)
        self.assertEqual(v.status, "PUBLISHED")

    def test_no_carry_forward_during_publication(self):
        self.attach()
        v = services.generate_allocation(self.make_rule(publication_days=7))
        services.publish(v)
        with self.assertRaisesMessage(ValidationError, "公示期内不可结转"):
            services.carry_forward(v)
        # 公示期满后可结转
        v.published_at = timezone.now() - timedelta(days=8)
        v.save(update_fields=["published_at"])
        cf = services.carry_forward(v)
        self.assertEqual(cf.amount, Decimal("10000.00"))
        self.assertEqual(v.status, "CARRIED")

    def test_dispute_freezes_portion(self):
        self.attach()
        v = services.generate_allocation(self.make_rule(publication_days=0))
        services.publish(v)
        detail = v.details.get(owner_name="李四")
        services.add_dispute(detail, Decimal("200"), "天数异议")
        # 异议提出后冻结额立即反映到明细(无需等结转)
        detail.refresh_from_db()
        self.assertEqual(detail.frozen_amount, Decimal("200.00"))
        self.assertEqual(detail.payable, Decimal("1277.90"))
        with self.assertRaisesMessage(ValidationError, "不能超过"):
            services.add_dispute(detail, detail.amount, "超额冻结")
        cf = services.carry_forward(v)
        detail.refresh_from_db()
        self.assertEqual(detail.frozen_amount, Decimal("200.00"))
        self.assertEqual(cf.frozen_total, Decimal("200.00"))
        self.assertEqual(cf.amount, Decimal("9800.00"))

    def test_carried_version_append_only(self):
        self.attach()
        v = services.generate_allocation(self.make_rule(publication_days=0))
        services.publish(v)
        services.carry_forward(v)
        detail = v.details.get(owner_name="王五")
        adj = services.add_adjustment(v, detail, Decimal("-50.00"), "复核扣回")
        self.assertIsInstance(adj, Adjustment)
        # 未结转版本不允许调整
        v2 = services.generate_allocation(self.make_rule())
        with self.assertRaisesMessage(ValidationError, "已结转"):
            services.add_adjustment(v2, v2.details.first(), Decimal("1"), "x")
        # 已结转后不能再提异议
        with self.assertRaisesMessage(ValidationError, "追加调整"):
            services.add_dispute(detail, Decimal("1"), "太晚了")

    def test_rule_revision_regenerates(self):
        self.attach()
        rule = self.make_rule()
        v1 = services.generate_allocation(rule)
        new_rule = services.revise_rule(rule, method="FIXED_SHARE",
                                        shares=[{"unit": self.u101, "share": Decimal("1")}])
        rule.refresh_from_db()
        self.assertFalse(rule.is_active)
        self.assertEqual(new_rule.version_no, rule.version_no + 1)
        self.assertEqual(new_rule.supersedes, rule)
        # 旧规则不能再生成/公示
        with self.assertRaisesMessage(ValidationError, "取代"):
            services.generate_allocation(rule)
        with self.assertRaisesMessage(ValidationError, "重新生成"):
            services.publish(v1)
        v2 = services.generate_allocation(new_rule)
        self.assertTrue(v2.details.exists())
        self.assertEqual({d.unit for d in v2.details.all()}, {self.u101})


class ApiTest(BaseData):
    """版本列表/规则接口必须输出 contract_id 与实际受益楼栋,供前端过滤与展示。"""

    def test_version_list_contains_contract_id_and_buildings(self):
        rule = self.make_rule(scope_type="BUILDINGS")
        rule.buildings.set([self.b1, self.b2])
        services.generate_allocation(rule)
        data = self.client.get("/api/versions/").json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["contract_id"], self.contract.id)
        self.assertEqual(data[0]["building_names"], ["1号楼", "2号楼"])
        self.assertEqual(data[0]["scope_display"], "指定楼栋")

    def test_rule_detail_contains_building_names(self):
        rule = self.make_rule(scope_type="BUILDINGS")
        rule.buildings.set([self.b1])
        data = self.client.get(f"/api/rules/{rule.id}/").json()
        self.assertEqual(data["building_names"], ["1号楼"])

    def test_dispute_visible_on_published_detail(self):
        self.attach()
        v = services.generate_allocation(self.make_rule(publication_days=7))
        services.publish(v)
        detail = v.details.get(owner_name="李四")
        self.client.post(f"/api/details/{detail.id}/disputes/",
                         {"amount": "200.00", "reason": "天数异议"},
                         content_type="application/json")
        data = self.client.get(f"/api/versions/{v.id}/").json()
        row = next(d for d in data["details"] if d["owner_name"] == "李四")
        self.assertEqual(row["frozen_amount"], "200.00")
        self.assertEqual(row["payable"], "1277.90")
        # 公示期内结转仍被拒绝
        resp = self.client.post(f"/api/versions/{v.id}/carry_forward/", {})
        self.assertEqual(resp.status_code, 400)
