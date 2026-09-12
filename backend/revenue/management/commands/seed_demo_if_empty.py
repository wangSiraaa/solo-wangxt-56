"""容器启动用:数据库为空时才灌入演示数据,保证重复启动幂等。"""
from django.core.management import call_command
from django.core.management.base import BaseCommand

from revenue.models import RevenueContract


class Command(BaseCommand):
    help = "数据库为空时执行 seed_demo,否则跳过"

    def handle(self, *args, **options):
        if RevenueContract.objects.exists():
            self.stdout.write("已有数据,跳过种子")
            return
        call_command("seed_demo")
