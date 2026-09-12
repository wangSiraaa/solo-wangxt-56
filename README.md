# 小区公共收益分摊公示系统

业委会公共收益(停车位、广告位等)的**来源登记 → 规则分摊 → 公示 → 异议冻结 → 结转 → 追加调整**全流程系统。每一笔分摊明细都可逐项追溯到原收入合同与权属期间片段。

- **前端** Angular 18(standalone components):收益来源、适用范围、分摊明细、追溯视图
- **后端** Django 5 + DRF:分摊计算与全部业务约束
- **数据库** PostgreSQL 16:合同附件、权属期间、公示版本
- **金额** 全程 `Decimal`,尾差用最大余数法确定性分配

## 快速开始(本地容器,docker compose 一条命令)

```bash
docker compose up --build
```

- 前端 http://localhost:4200 (nginx 反代 `/api`)
- 后端 http://localhost:8000/api/
- 首次启动自动建表并灌入三个演示样例(幂等,重复启动不重复灌)

无 Docker 的本地开发:

```bash
cd backend && pip install -r requirements.txt
DB_ENGINE=sqlite python manage.py migrate --run-syncdb
DB_ENGINE=sqlite python manage.py seed_demo
DB_ENGINE=sqlite python manage.py runserver
cd ../frontend && npm install && npm start   # 另开终端
```

运行测试:`DB_ENGINE=sqlite python manage.py test revenue`(13 个用例)

## 核心规则与实现位置

| 需求 | 实现 |
|---|---|
| 收入归属期与收款日期分开 | `RevenueContract.period_start/end` vs `received_date` |
| 缺少附件不能公示 | `services.publish()` 检查 `contract.attachments` |
| 空置房不能无依据剔除 | `AllocationRule.exclude_vacant` 必须配 `vacant_basis` 文件,否则校验拒绝 |
| 规则/受益基数变化须重新生成版本 | `revise_rule()` 作废旧规则生成 v+1;旧规则生成的版本不能公示 |
| 公示期内不可结转 | `carry_forward()` 检查 `published_at + publication_days` |
| 异议按约定范围冻结 | `Dispute` 冻结额 ≤ 明细未冻结额;结转金额 = 合计 − 冻结 |
| 已结转只读、仅追加调整 | `Adjustment` 只挂已结转版本,API 不提供改/删 |
| 逐笔追溯 | `GET /api/versions/{id}/trace/` 明细 → 合同 + 权属期间 |
| 尾差 | 最大余数法,命中行 `remainder_applied=True`,合计精确等于总额 |
| 权属期间未覆盖归属期 | 拒绝计算,提示补录权属数据 |

## 三个演示样例(`seed_demo`)

1. **跨两个产权期间**:电梯广告 ¥10,000,归属期 2026-01-01~06-30(收款日 07-05)。1-101 于 03-15 过户,¥2,500 按 74/107 天拆为 张三 ¥1,022.10(含尾差+0.01)/ 李四 ¥1,477.90。版本公示中,李四的明细有 ¥200 异议冻结。
2. **共有份额不足**:停车位 ¥3,000,固定份额 0.30+0.25+0.35=0.90 < 1,`RESERVE` 策略下分配 ¥2,700、结余 ¥300 明示未分配(不静默放大;`SCALE` 策略则按比例放大)。
3. **尾差分配**:快递柜场地费 ¥100 三套等面积房屋 → 33.34 / 33.33 / 33.33,尾差按确定顺序(楼栋、房号)补给 3-301。已结转,并演示两笔追加调整(+0.01 / −0.01)。

## API 一览

```
GET  /api/contracts/                 合同列表(来源/归属期/收款日期/附件)
POST /api/contracts/{id}/attachments/ 上传合同附件(公示前置条件)
GET  /api/rules/  POST /api/rules/{id}/revise/   规则与版本化变更
POST /api/rules/{id}/generate/       生成公示版本(草稿)
GET  /api/versions/  GET /api/versions/{id}/
POST /api/versions/{id}/publish/     公示(校验附件与规则有效性)
POST /api/versions/{id}/carry_forward/  公示期满后结转(扣除冻结)
GET  /api/versions/{id}/trace/       逐笔追溯到原收入与权属期间
POST /api/details/{id}/disputes/     公示期内提异议(冻结)
POST /api/versions/{id}/adjustments/ 已结转版本追加调整(只增不改)
```

## 目录结构

```
backend/
  config/            Django 设置(PostgreSQL 默认,DB_ENGINE=sqlite 可回退)
  revenue/
    models.py        楼栋/房屋/权属期间/合同/附件/规则/版本/明细/异议/结转/调整
    services.py      分摊引擎与工作流(全部业务约束)
    views.py         DRF API
    tests.py         13 个用例覆盖三个样例与全部约束
    management/commands/seed_demo.py
frontend/            Angular 18(合同、版本、明细追溯三个页面)
docker-compose.yml   db(PostgreSQL) + backend + frontend(nginx)
```
