# Dispatch Service Quick Start

快速启动和测试 Dispatch Service 的 MILP 优化功能。

## 1. 启动服务 (Start Services)

```bash
# 进入项目根目录
cd sedai-solar2grid

# 启动数据库和 Dispatch Service
docker-compose up -d db
docker-compose up dispatch_service
```

服务将在 `http://localhost:8002` 启动。

## 2. 最小测试 (Minimal Test)

最简单的请求只需要 3 个参数：

```bash
curl -X POST http://localhost:8002/dispatch/run \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "TEST001",
    "resolution_minutes": 15,
    "load_kw": [80, 85, 90, 95, 100, 105, 110, 115, 120, 125, 130, 135, 140, 135, 130, 125, 120, 115, 110, 105, 100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115, 120, 125, 130, 135, 140, 135, 130, 125, 120, 115, 110, 105, 100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115],
    "tariff": {
      "buy": [0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.70, 0.70, 0.70, 0.65, 0.60, 0.55, 0.80, 0.80, 0.80, 0.80, 0.65, 0.55, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.70, 0.70, 0.70, 0.65, 0.60, 0.55, 0.80, 0.80, 0.80, 0.80, 0.65, 0.55, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.70, 0.70, 0.70, 0.65, 0.60, 0.55, 0.80, 0.80, 0.80, 0.80, 0.65, 0.55, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.70, 0.70, 0.70, 0.65, 0.60, 0.55, 0.80, 0.80, 0.80, 0.80, 0.65, 0.55],
      "sell": [0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.22, 0.25, 0.28, 0.30, 0.32, 0.35, 0.35, 0.35, 0.35, 0.32, 0.30, 0.28, 0.40, 0.40, 0.40, 0.40, 0.32, 0.28, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.22, 0.25, 0.28, 0.30, 0.32, 0.35, 0.35, 0.35, 0.35, 0.32, 0.30, 0.28, 0.40, 0.40, 0.40, 0.40, 0.32, 0.28, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.22, 0.25, 0.28, 0.30, 0.32, 0.35, 0.35, 0.35, 0.35, 0.32, 0.30, 0.28, 0.40, 0.40, 0.40, 0.40, 0.32, 0.28, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.22, 0.25, 0.28, 0.30, 0.32, 0.35, 0.35, 0.35, 0.35, 0.32, 0.30, 0.28, 0.40, 0.40, 0.40, 0.40, 0.32, 0.28]
    }
  }'
```

**默认参数** (不需要指定):
- BESS: 100kWh, 50kW 充放电功率, SOC 20%-90%
- 电网限制: 200kW 进口/出口, 250kW 变压器
- 优化权重: 成本=1.0, 削减=0.2, 违规=1000.0

## 3. 完整测试 (Full Test)

包含所有可选参数的完整请求：

```bash
curl -X POST http://localhost:8002/dispatch/run \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "ADVANCED",
    "start": "2024-03-15T00:00:00Z",
    "end": "2024-03-16T00:00:00Z",
    "resolution_minutes": 15,
    "forecast_quantile": 0.5,
    "load_kw": [60,65,70,75,80,85,90,95,100,105,110,115,120,125,130,125,120,115,110,105,100,95,90,85,80,75,70,65,60,55,50,45,40,35,30,35,40,45,50,55,60,65,70,75,80,85,90,95,100,105,110,115,120,125,130,125,120,115,110,105,100,95,90,85,80,75,70,65,60,55,50,45,40,35,30,35,40,45,50,55,60,65,70,75,80,85,90,95,100,105,110,115,120,125,130,125],
    "tariff": {
      "buy": [0.35,0.35,0.35,0.35,0.35,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.65,0.65,0.65,0.60,0.55,0.50,0.75,0.75,0.75,0.75,0.60,0.50,0.35,0.35,0.35,0.35,0.35,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.65,0.65,0.65,0.60,0.55,0.50,0.75,0.75,0.75,0.75,0.60,0.50,0.35,0.35,0.35,0.35,0.35,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.65,0.65,0.65,0.60,0.55,0.50,0.75,0.75,0.75,0.75,0.60,0.50,0.35,0.35,0.35,0.35,0.35,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.65,0.65,0.65,0.60,0.55,0.50,0.75,0.75,0.75,0.75,0.60,0.50],
      "sell": [0.15,0.15,0.15,0.15,0.15,0.15,0.18,0.20,0.22,0.25,0.28,0.30,0.30,0.30,0.30,0.28,0.25,0.22,0.35,0.35,0.35,0.35,0.28,0.22,0.15,0.15,0.15,0.15,0.15,0.15,0.18,0.20,0.22,0.25,0.28,0.30,0.30,0.30,0.30,0.28,0.25,0.22,0.35,0.35,0.35,0.35,0.28,0.22,0.15,0.15,0.15,0.15,0.15,0.15,0.18,0.20,0.22,0.25,0.28,0.30,0.30,0.30,0.30,0.28,0.25,0.22,0.35,0.35,0.35,0.35,0.28,0.22,0.15,0.15,0.15,0.15,0.15,0.15,0.18,0.20,0.22,0.25,0.28,0.30,0.30,0.30,0.30,0.28,0.25,0.22,0.35,0.35,0.35,0.35,0.28,0.22]
    },
    "bess": {
      "capacity_kwh": 150.0,
      "p_charge_max_kw": 75.0,
      "p_discharge_max_kw": 75.0,
      "soc0": 0.6,
      "soc_min": 0.15,
      "soc_max": 0.95,
      "eta_charge": 0.96,
      "eta_discharge": 0.96
    },
    "limits": {
      "grid_import_max_kw": 250.0,
      "grid_export_max_kw": 150.0,
      "transformer_max_kw": 300.0
    },
    "weights": {
      "cost": 1.0,
      "curtail": 0.3,
      "violation": 2000.0
    },
    "use_milp": true
  }'
```

## 4. 查看结果 (View Results)

### 获取最新调度计划

```bash
curl http://localhost:8002/dispatch/latest?site_id=TEST001 | jq
```

### 解析关键字段

```bash
# 提取 KPIs
curl http://localhost:8002/dispatch/latest?site_id=TEST001 | jq '.points | length'  # 应该是 96

# 查看前 5 个时间点
curl http://localhost:8002/dispatch/latest?site_id=TEST001 | jq '.points[0:5]'

# 提取所有 SOC 值
curl http://localhost:8002/dispatch/latest?site_id=TEST001 | jq '.points[].soc'

# 查看所有原因
curl http://localhost:8002/dispatch/latest?site_id=TEST001 | jq '.points[].reason'
```

## 5. 数据库查询 (Database Queries)

```bash
# 连接到数据库
docker exec -it db psql -U postgres -d sedai_db
```

### 查看最近的运行记录

```sql
SELECT id, site_id, status, solver, created_at 
FROM dispatch_runs 
ORDER BY created_at DESC 
LIMIT 5;
```

### 查看 KPIs

```sql
SELECT r.site_id, r.solver, k.total_cost, k.total_curtail_kwh, 
       k.peak_grid_import_kw, k.avg_soc
FROM dispatch_kpis k
JOIN dispatch_runs r ON r.id = k.run_id
ORDER BY k.created_at DESC
LIMIT 5;
```

### 查看某次运行的详细调度

```sql
-- 替换 <run_id> 为实际的 run_id
SELECT ts, pv_set_kw, batt_ch_kw, batt_dis_kw, soc, reason
FROM dispatch_schedule
WHERE run_id = '<run_id>'
ORDER BY ts ASC
LIMIT 10;
```

### 验证功率平衡

```sql
-- 检查前 10 个时间点的功率平衡
-- pv_set + batt_dis + grid_imp ≈ load + batt_ch + grid_exp
SELECT ts, 
       pv_set_kw, batt_dis_kw, grid_imp_kw,  -- 输入
       batt_ch_kw, grid_exp_kw,               -- 输出
       (pv_set_kw + batt_dis_kw + grid_imp_kw - batt_ch_kw - grid_exp_kw) AS balance_error
FROM dispatch_schedule
WHERE run_id = '<run_id>'
ORDER BY ts ASC
LIMIT 10;
```

## 6. 测试 Fallback 模式 (Test Fallback)

强制使用 fallback 规则（不使用 MILP）：

```bash
curl -X POST http://localhost:8002/dispatch/run \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "FALLBACK_TEST",
    "resolution_minutes": 15,
    "load_kw": [80, 85, 90, 95, 100, 105, 110, 115, 120, 125, 130, 135, 140, 135, 130, 125, 120, 115, 110, 105, 100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115, 120, 125, 130, 135, 140, 135, 130, 125, 120, 115, 110, 105, 100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115],
    "tariff": {
      "buy": [0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.70, 0.70, 0.70, 0.65, 0.60, 0.55, 0.80, 0.80, 0.80, 0.80, 0.65, 0.55, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.70, 0.70, 0.70, 0.65, 0.60, 0.55, 0.80, 0.80, 0.80, 0.80, 0.65, 0.55, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.70, 0.70, 0.70, 0.65, 0.60, 0.55, 0.80, 0.80, 0.80, 0.80, 0.65, 0.55, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.70, 0.70, 0.70, 0.65, 0.60, 0.55, 0.80, 0.80, 0.80, 0.80, 0.65, 0.55],
      "sell": [0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.22, 0.25, 0.28, 0.30, 0.32, 0.35, 0.35, 0.35, 0.35, 0.32, 0.30, 0.28, 0.40, 0.40, 0.40, 0.40, 0.32, 0.28, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.22, 0.25, 0.28, 0.30, 0.32, 0.35, 0.35, 0.35, 0.35, 0.32, 0.30, 0.28, 0.40, 0.40, 0.40, 0.40, 0.32, 0.28, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.22, 0.25, 0.28, 0.30, 0.32, 0.35, 0.35, 0.35, 0.35, 0.32, 0.30, 0.28, 0.40, 0.40, 0.40, 0.40, 0.32, 0.28, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.22, 0.25, 0.28, 0.30, 0.32, 0.35, 0.35, 0.35, 0.35, 0.32, 0.30, 0.28, 0.40, 0.40, 0.40, 0.40, 0.32, 0.28]
    },
    "use_milp": false
  }'
```

检查响应中的 `"solver": "rule_based"` 和 `"fallback_used": true`。

## 7. API 文档 (API Docs)

访问自动生成的 API 文档：

```
http://localhost:8002/docs
```

可以直接在浏览器中测试 API。

## 8. 验证清单 (Verification Checklist)

运行优化后，验证以下内容：

- [ ] 响应中 `status` 为 `"ok"` 或 `"fallback"`
- [ ] `run_id` 是有效的 UUID
- [ ] `objective_value` > 0 (总成本)
- [ ] `kpis.avg_soc` 在 0-1 之间
- [ ] `kpis.peak_grid_import_kw` < `limits.grid_import_max_kw`
- [ ] `/dispatch/latest` 返回 96 个时间点
- [ ] 所有 `soc` 值在 `soc_min` 和 `soc_max` 之间
- [ ] 每个时间点都有 `reason` 字段
- [ ] 数据库中有对应的 `dispatch_runs`, `dispatch_schedule`, `dispatch_kpis` 记录

## 9. 常见问题 (Troubleshooting)

### 问题: 服务启动失败

```bash
# 检查 CBC 求解器是否安装
docker exec -it dispatch_service cbc --version

# 重新构建镜像
docker-compose build dispatch_service
docker-compose up dispatch_service
```

### 问题: 总是使用 fallback

检查日志中是否有 MILP 失败的错误信息：

```bash
docker-compose logs dispatch_service | grep -i "milp\|fallback"
```

可能原因：
- 求解器未安装
- 约束过于严格（不可行）
- 超时（3 秒）

### 问题: KPI 值异常

验证输入数据：
- `load_kw` 数组长度 = 96 (对于 15 分钟分辨率, 24 小时)
- `tariff.buy` 和 `tariff.sell` 数组长度 = 96
- 所有数值 > 0

### 问题: 功率不平衡

运行数据库查询验证：

```sql
SELECT ts, 
       (pv_set_kw + batt_dis_kw + grid_imp_kw) AS supply,
       (batt_ch_kw + grid_exp_kw) AS consumption,
       ABS(pv_set_kw + batt_dis_kw + grid_imp_kw - batt_ch_kw - grid_exp_kw) AS error
FROM dispatch_schedule
WHERE run_id = '<run_id>'
  AND ABS(pv_set_kw + batt_dis_kw + grid_imp_kw - batt_ch_kw - grid_exp_kw) > 0.1
ORDER BY error DESC;
```

误差应 < 0.1 kW (数值精度)。

## 10. 下一步 (Next Steps)

- 阅读完整文档: [DISPATCH_SERVICE_UPGRADE.md](DISPATCH_SERVICE_UPGRADE.md)
- 测试组件: 运行 `optimizer/` 文件夹中的测试代码
- 集成真实数据: 从 PV forecast service 获取预测数据
- 调整参数: 尝试不同的 BESS 配置和优化权重
- 分析结果: 比较 MILP 和 fallback 的性能差异

---

**快速参考**:
- API 地址: http://localhost:8002
- API 文档: http://localhost:8002/docs
- 数据库: `docker exec -it db psql -U postgres -d sedai_db`
- 日志: `docker-compose logs dispatch_service`
