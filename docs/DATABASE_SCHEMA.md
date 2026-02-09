# 数据库表结构说明

## 核心业务表

### 1. sites - 站点信息
**用途**: 存储微电网站点的基本信息

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | TEXT | 站点名称 |
| timezone | TEXT | 时区（默认: Asia/Kuala_Lumpur） |
| lat, lon | DOUBLE PRECISION | 地理坐标 |
| capacity_kw | DOUBLE PRECISION | 装机容量 (kW) |
| tilt_deg, azimuth_deg | DOUBLE PRECISION | 光伏阵列倾角和方位角 |
| created_at | TIMESTAMPTZ | 创建时间 |

---

### 2. telemetry - 遥测数据 (Hypertable)
**用途**: 存储实时设备数据

| 字段 | 类型 | 说明 |
|------|------|------|
| ts | TIMESTAMPTZ | 时间戳（分区键） |
| site_id | UUID | 站点ID |
| asset_id | UUID | 资产ID（可选） |
| metric | TEXT | 指标名称（如 pv_power_kw） |
| value | DOUBLE PRECISION | 数值 |
| quality | SMALLINT | 数据质量标志 |

**索引**: `idx_telemetry_site_metric_ts` (site_id, metric, ts DESC)

---

## 预测与调度表

### 3. forecast_runs - 预测运行记录
**用途**: 记录每次预测任务的元信息

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键（run_id） |
| site_id | UUID | 站点ID |
| horizon | TEXT | 预测周期（如 day_ahead） |
| resolution_minutes | INT | 时间分辨率 |
| model_version | TEXT | 模型版本 |
| feature_version | TEXT | 特征版本 |
| data_version | TEXT | 数据版本 |
| created_at | TIMESTAMPTZ | 创建时间 |

---

### 4. forecasts - 光伏功率预测 (Hypertable)
**用途**: 存储光伏功率预测结果（分位数）

| 字段 | 类型 | 说明 |
|------|------|------|
| ts | TIMESTAMPTZ | 预测时刻（分区键） |
| site_id | UUID | 站点ID |
| run_id | UUID | 对应 forecast_runs.id |
| p10 | DOUBLE PRECISION | 10% 分位数 |
| p50 | DOUBLE PRECISION | 50% 分位数（中位数） |
| p90 | DOUBLE PRECISION | 90% 分位数 |
| unit | TEXT | 单位（默认: kW） |

**索引**: `idx_forecasts_site_ts` (site_id, ts DESC)

---

### 5. load_forecasts - 负荷预测 (Hypertable) 🆕
**用途**: 存储负荷预测结果

| 字段 | 类型 | 说明 |
|------|------|------|
| ts | TIMESTAMPTZ | 预测时刻（分区键） |
| site_id | UUID | 站点ID |
| run_id | UUID | 预测运行ID |
| p50 | DOUBLE PRECISION | 50% 分位数 (MVP) |
| unit | TEXT | 单位（默认: kW） |

**索引**: `idx_load_site_ts` (site_id, ts DESC)  
**扩展**: 后续可添加 p10, p90 字段

---

### 6. dispatch_runs - 调度运行记录
**用途**: 记录每次调度优化任务的元信息

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键（run_id） |
| site_id | UUID | 站点ID |
| status | TEXT | 状态 |
| solver | TEXT | 求解器名称 |
| objective_config | JSONB | 目标函数配置 |
| timeout_ms | INT | 超时时间（毫秒） |
| created_at | TIMESTAMPTZ | 创建时间 |

---

### 7. dispatch_schedule - 调度计划 (Hypertable)
**用途**: 存储能源管理调度计划

| 字段 | 类型 | 说明 |
|------|------|------|
| ts | TIMESTAMPTZ | 时刻（分区键） |
| site_id | UUID | 站点ID |
| run_id | UUID | 对应 dispatch_runs.id |
| pv_set_kw | DOUBLE PRECISION | 光伏设定功率 |
| batt_ch_kw | DOUBLE PRECISION | 电池充电功率 |
| batt_dis_kw | DOUBLE PRECISION | 电池放电功率 |
| grid_imp_kw | DOUBLE PRECISION | 电网进口功率 |
| grid_exp_kw | DOUBLE PRECISION | 电网出口功率 |
| curtail_kw | DOUBLE PRECISION | 削减功率 |
| soc | DOUBLE PRECISION | 电池荷电状态 |
| reason | TEXT | 决策原因（可解释性） |

**索引**: `idx_dispatch_site_ts` (site_id, ts DESC)

---

### 8. dispatch_kpis - 调度关键指标 🆕
**用途**: 存储每次调度优化的关键性能指标

| 字段 | 类型 | 说明 |
|------|------|------|
| run_id | UUID | 主键（对应 dispatch_runs.id） |
| site_id | UUID | 站点ID |
| total_cost | DOUBLE PRECISION | 总成本 |
| total_curtail_kwh | DOUBLE PRECISION | 总削减电量 |
| peak_grid_import_kw | DOUBLE PRECISION | 峰值电网进口功率 |
| avg_soc | DOUBLE PRECISION | 平均荷电状态 |
| created_at | TIMESTAMPTZ | 创建时间 |

**索引**: `idx_dispatch_kpi_site_time` (site_id, created_at DESC)

---

## 配置与参数表

### 9. tariff_profiles - 电价表 🆕
**用途**: 存储电价费率配置

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| site_id | UUID | 站点ID |
| name | TEXT | 费率名称 |
| currency | TEXT | 货币（默认: MYR） |
| resolution_minutes | INT | 时间分辨率（默认: 15） |
| buy | JSONB | 购电价格数组（长度=96） |
| sell | JSONB | 售电价格数组（长度=96） |
| valid_from | TIMESTAMPTZ | 生效时间 |

**索引**: `idx_tariff_site_time` (site_id, valid_from DESC)  
**数组格式**: 96个点 = 24小时 × 4个点/小时（15分钟分辨率）

---

### 10. bess_profiles - 电池储能配置 🆕
**用途**: 存储 BESS 参数配置

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| site_id | UUID | 站点ID |
| name | TEXT | 配置名称 |
| params | JSONB | 参数对象 |
| valid_from | TIMESTAMPTZ | 生效时间 |

**索引**: `idx_bess_site_time` (site_id, valid_from DESC)

**params 字段结构**:
```json
{
  "capacity_kwh": 100.0,
  "p_charge_max_kw": 50.0,
  "p_discharge_max_kw": 50.0,
  "soc0": 0.5,
  "soc_min": 0.2,
  "soc_max": 0.9,
  "eta_charge": 0.95,
  "eta_discharge": 0.95
}
```

---

## 模型验证与校准表

### 11. validation_runs - 模型验证记录
**用途**: 存储模型验证评估结果

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| site_id | UUID | 站点ID |
| horizon | TEXT | 预测周期 |
| start_ts, end_ts | TIMESTAMPTZ | 验证时间范围 |
| resolution_minutes | INT | 时间分辨率 |
| run_id_forecast | UUID | 对应的预测运行ID（可选） |
| metric | TEXT | 验证指标（默认: pv_power_kw） |
| mae | DOUBLE PRECISION | 平均绝对误差 |
| nrmse | DOUBLE PRECISION | 归一化均方根误差 |
| bias | DOUBLE PRECISION | 偏差 |
| created_at | TIMESTAMPTZ | 创建时间 |

**索引**: `idx_validation_site_time` (site_id, created_at DESC)

---

### 12. model_calibration - 模型校准参数
**用途**: 存储模型校准参数

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| site_id | UUID | 站点ID |
| model_type | TEXT | 模型类型（默认: forecast_baseline） |
| params | JSONB | 校准参数（如 PR, soiling） |
| valid_from | TIMESTAMPTZ | 生效时间 |

**索引**: `idx_calibration_site_time` (site_id, valid_from DESC)

**params 字段示例**:
```json
{
  "pr": 0.843,
  "soiling": 0.98
}
```

---

### 13. model_health - 模型健康监控 🆕
**用途**: 监控模型性能漂移和退化

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| site_id | UUID | 站点ID |
| model_type | TEXT | 模型类型 |
| window_start, window_end | TIMESTAMPTZ | 评估窗口时间范围 |
| mae | DOUBLE PRECISION | 平均绝对误差 |
| nrmse | DOUBLE PRECISION | 归一化均方根误差 |
| drift_score | DOUBLE PRECISION | 漂移评分 |
| status | TEXT | 状态（green/amber/red） |
| created_at | TIMESTAMPTZ | 创建时间 |

**索引**: `idx_health_site_time` (site_id, created_at DESC)

---

## 审计与告警表

### 14. audit_log - 审计日志
**用途**: 记录所有操作审计

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| actor | TEXT | 操作者 |
| action | TEXT | 操作类型（如 forecast_run） |
| payload | JSONB | 操作详情 |
| created_at | TIMESTAMPTZ | 创建时间 |

---

### 15. alerts - 告警表 🆕
**用途**: 存储系统告警信息（比赛展示加分项）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| site_id | UUID | 站点ID |
| severity | TEXT | 严重级别（info/warn/critical） |
| category | TEXT | 类别（data_quality/forecast/asset/dispatch） |
| title | TEXT | 标题 |
| detail | TEXT | 详情 |
| ts | TIMESTAMPTZ | 告警时间 |
| acknowledged | BOOLEAN | 是否已确认 |
| meta | JSONB | 元数据 |

**索引**:
- `idx_alert_site_ts` (site_id, ts DESC)
- `idx_alert_severity` (severity, acknowledged)

---

## 表结构总结

### 按功能分类

**核心业务** (2):
- sites, telemetry

**预测与调度** (6):
- forecast_runs, forecasts, load_forecasts
- dispatch_runs, dispatch_schedule, dispatch_kpis

**配置参数** (2):
- tariff_profiles, bess_profiles

**模型管理** (3):
- validation_runs, model_calibration, model_health

**审计与告警** (2):
- audit_log, alerts

### Hypertables (时序表)

使用 TimescaleDB 的 Hypertable 优化时序数据存储和查询：
- telemetry
- forecasts
- load_forecasts
- dispatch_schedule

### 索引策略

所有时序表都有 `(site_id, ts DESC)` 复合索引，优化按站点查询最新数据的场景。

---

## 后续扩展建议

1. **Alembic 迁移**: 使用 Alembic 管理数据库版本和迁移
2. **外键约束**: 在生产环境添加外键约束提高数据完整性
3. **分区策略**: 配置 TimescaleDB 数据保留策略和压缩策略
4. **视图**: 创建常用查询的物化视图提高性能
