"""演示数据:三个样例
1. 电梯广告收益 ¥10,000 跨两个产权期间(1-101 中途过户),按面积分摊,含尾差;
2. 地面停车位收益 ¥3,000 固定份额合计仅 90%,份额不足部分按约定结余留存;
3. 快递柜场地费 ¥100.00 三套等面积房屋,演示尾差 0.01 的确定性分配。
"""
from datetime import date
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from revenue import services
from revenue.models import (
    AllocationRule,
    Building,
    ContractAttachment,
    OwnershipPeriod,
    RevenueContract,
    RuleShare,
    Unit,
)


class Command(BaseCommand):
    help = "生成演示数据(三个样例场景)"

    def handle(self, *args, **options):
        b1 = Building.objects.create(name="1号楼")
        b2 = Building.objects.create(name="2号楼")
        b3 = Building.objects.create(name="3号楼")

        u101 = Unit.objects.create(building=b1, code="1-101", area=Decimal("100.00"))
        u102 = Unit.objects.create(building=b1, code="1-102", area=Decimal("80.00"))
        u201 = Unit.objects.create(building=b2, code="2-201", area=Decimal("120.00"), is_vacant=True)
        u202 = Unit.objects.create(building=b2, code="2-202", area=Decimal("100.00"))
        u301 = Unit.objects.create(building=b3, code="3-301", area=Decimal("60.00"))
        u302 = Unit.objects.create(building=b3, code="3-302", area=Decimal("60.00"))
        u303 = Unit.objects.create(building=b3, code="3-303", area=Decimal("60.00"))

        # 权属期间:1-101 在归属期中途过户(张三 -> 李四),其余业主稳定持有
        OwnershipPeriod.objects.create(unit=u101, owner_name="张三", start_date=date(2025, 1, 1), end_date=date(2026, 3, 15))
        OwnershipPeriod.objects.create(unit=u101, owner_name="李四", start_date=date(2026, 3, 16), end_date=None)
        for u, name in [(u102, "王五"), (u201, "赵六"), (u202, "孙七"), (u301, "周八"), (u302, "吴九"), (u303, "郑十")]:
            OwnershipPeriod.objects.create(unit=u, owner_name=name, start_date=date(2025, 1, 1), end_date=None)

        dummy_file = lambda n: ContentFile(b"demo contract scan", name=n)

        # ---- 样例 1:广告收益跨两个产权期间 + 按面积 + 尾差 ----
        c1 = RevenueContract.objects.create(
            name="电梯广告位收益(2026上半年)", source_type="AD",
            total_amount=Decimal("10000.00"),
            period_start=date(2026, 1, 1), period_end=date(2026, 6, 30),
            received_date=date(2026, 7, 5),  # 收款日期与归属期分开
        )
        ContractAttachment.objects.create(contract=c1, name="广告合同扫描件.pdf", file=dummy_file("ad.pdf"))
        r1 = AllocationRule.objects.create(
            contract=c1, scope_type="BUILDINGS", method="BY_AREA", publication_days=7,
        )
        r1.buildings.set([b1, b2])  # 广告只涉及 1、2 号楼,受益范围限定
        v1 = services.generate_allocation(r1)
        services.publish(v1)
        # 公示期内对李四的明细提异议(冻结部分金额)
        detail_li = v1.details.get(owner_name="李四")
        services.add_dispute(detail_li, Decimal("200.00"), "对过户后分摊天数有异议")

        # ---- 样例 2:停车位收益,固定份额合计 90%,不足部分结余留存 ----
        c2 = RevenueContract.objects.create(
            name="地面停车位收益(2026上半年)", source_type="PARKING",
            total_amount=Decimal("3000.00"),
            period_start=date(2026, 1, 1), period_end=date(2026, 6, 30),
            received_date=date(2026, 6, 28),
        )
        ContractAttachment.objects.create(contract=c2, name="停车管理协议.pdf", file=dummy_file("parking.pdf"))
        r2 = AllocationRule.objects.create(
            contract=c2, scope_type="BUILDINGS", method="FIXED_SHARE",
            shortfall_policy="RESERVE", publication_days=7,
        )
        r2.buildings.set([b1, b2])
        for u, s in [(u101, "0.30"), (u102, "0.25"), (u201, "0.35")]:  # 合计 0.90 < 1
            RuleShare.objects.create(rule=r2, unit=u, share=Decimal(s))
        v2 = services.generate_allocation(r2)  # 草稿:结余 300.00 未分配

        # ---- 样例 3:¥100 三套等面积,尾差 0.01;公示期 0 天以便演示结转与追加调整 ----
        c3 = RevenueContract.objects.create(
            name="快递柜场地费(2026年3月)", source_type="OTHER",
            total_amount=Decimal("100.00"),
            period_start=date(2026, 3, 1), period_end=date(2026, 3, 31),
            received_date=date(2026, 4, 2),
        )
        ContractAttachment.objects.create(contract=c3, name="场地租赁协议.pdf", file=dummy_file("locker.pdf"))
        r3 = AllocationRule.objects.create(
            contract=c3, scope_type="BUILDINGS", method="BY_AREA", publication_days=0,
        )
        r3.buildings.set([b3])
        v3 = services.generate_allocation(r3)
        services.publish(v3)
        services.carry_forward(v3, note="公示期满,全体结转")
        d301 = v3.details.get(unit=u301)
        services.add_adjustment(v3, d301, Decimal("0.01"), "银行回单尾差补分给 3-301")

        self.stdout.write(self.style.SUCCESS(
            f"演示数据已生成:\n"
            f"  样例1 版本 v{v1.version_no} 公示中(含 200.00 异议冻结)\n"
            f"  样例2 版本 v{v2.version_no} 草稿(份额不足,结余 {v2.unallocated_amount})\n"
            f"  样例3 版本 v{v3.version_no} 已结转并追加 1 笔调整"
        ))
