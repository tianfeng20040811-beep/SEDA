# API 端点完整清单

## 系统状态

### GET /health
**描述**: 系统健康检查  
**参数**: 无  
**响应**:
```json
{"status": "ok"}
```

---

## 1. Sites & Config（站点和配置）

### GET /sites
**描述**: 获取所有站点列表  
**参数**: 无  
**响应**:
```json
{
  "sites": [
    {
      "id": "uuid",
      "name": "Demo Microgrid",
      "timezone": "Asia/Kuala_Lumpur",
      "lat": 5.4164,
      "lon": 100.3327,
      "capacity_kw": 500.0
    }
  ]
}
```

### GET /sites/{site_id}
**描述**: 获取单个站点详细信息  
**参数**:
- `site_id` (path): 站点UUID  

**响应**:
```json
{
  "id": "uuid",
  "name": "Demo Microgrid",
  "timezone": "Asia/Kuala_Lumpur",
  "lat": 5.4164,
  "lon": 100.3327,
  "capacity_kw": 500.0,
  "tilt_deg": 10.0,
  "azimuth_deg": 180.0,
  "created_at": "2026-02-09T12:55:35Z"
}
```

### GET /config/tariff/latest
**描述**: 获取站点最新电价配置  
**参数**:
- `site_id` (query): 站点UUID  

**响应**:
```json
{
  "id": "uuid",
  "site_id": "uuid",
  "name": "Malaysia Standard TOU",
  "currency": "MYR",
  "resolution_minutes": 15,
  "buy": [0.10, 0.12, ...],  // 96个点
  "sell": [0.05, 0.06, ...],  // 96个点
  "valid_from": "2026-02-09T00:00:00Z"
}
```

### POST /config/tariff/upsert
**描述**: 创建或更新电价配置  
**请求体**:
```json
{
  "site_id": "uuid",
  "name": "Custom TOU",
  "currency": "MYR",
  "resolution_minutes": 15,
  "buy": [0.10, ...],  // 96个点
  "sell": [0.05, ...]  // 96个点
}
```
**响应**:
```json
{
  "status": "ok",
  "tariff_id": "uuid"
}
```

### GET /config/bess/latest
**描述**: 获取站点最新BESS配置  
**参数**:
- `site_id` (query): 站点UUID  

**响应**:
```json
{
  "id": "uuid",
  "site_id": "uuid",
  "name": "Default BESS 100kWh",
  "params": {
    "capacity_kwh": 100.0,
    "p_charge_max_kw": 50.0,
    "p_discharge_max_kw": 50.0,
    "soc0": 0.5,
    "soc_min": 0.2,
    "soc_max": 0.9,
    "eta_charge": 0.95,
    "eta_discharge": 0.95
  },
  "valid_from": "2026-02-09T00:00:00Z"
}
```

### POST /config/bess/upsert
**描述**: 创建或更新BESS配置  
**请求体**:
```json
{
  "site_id": "uuid",
  "name": "Custom BESS",
  "params": {
    "capacity_kwh": 100.0,
    "p_charge_max_kw": 50.0,
    "p_discharge_max_kw": 50.0,
    "soc0": 0.5,
    "soc_min": 0.2,
    "soc_max": 0.9,
    "eta_charge": 0.95,
    "eta_discharge": 0.95
  }
}
```
**响应**:
```json
{
  "status": "ok",
  "bess_id": "uuid"
}
```

---

## 2. Telemetry（遥测）

### GET /telemetry/query
**描述**: 查询遥测数据  
**参数**:
- `site_id` (query): 站点UUID
- `metric` (query): 指标名称（如 pv_power_kw）
- `start` (query): 开始时间（ISO 8601）
- `end` (query): 结束时间（ISO 8601）
- `step_minutes` (query): 时间粒度（分钟，默认15）

**响应**:
```json
{
  "site_id": "uuid",
  "metric": "pv_power_kw",
  "unit": "kW",
  "series": [
    {"ts": "2026-02-09T00:00:00Z", "value": 200.0},
    {"ts": "2026-02-09T00:15:00Z", "value": 210.0}
  ]
}
```

---

## 3. Forecast（光伏预测）

### POST /forecast/run
**描述**: 触发光伏预测运行  
**请求体**:
```json
{
  "site_id": "uuid",
  "horizon": "day_ahead",
  "start": "2026-02-10T00:00:00Z",
  "end": "2026-02-11T00:00:00Z",
  "resolution_minutes": 15,
  "quantiles": [0.1, 0.5, 0.9],
  "weather_source": "telemetry_or_mock"
}
```
**响应**:
```json
{
  "run_id": "uuid",
  "status": "ok"
}
```

### GET /forecast/latest
**描述**: 获取最新光伏预测  
**参数**:
- `site_id` (query): 站点UUID
- `horizon` (query): 预测周期（默认 day_ahead）

**响应**:
```json
{
  "site_id": "uuid",
  "horizon": "day_ahead",
  "resolution_minutes": 15,
  "unit": "kW",
  "points": [
    {
      "ts": "2026-02-10T00:00:00Z",
      "p10": 6.61,
      "p50": 8.26,
      "p90": 9.91
    }
  ]
}
```

### GET /forecast/runs
**描述**: 获取预测运行历史  
**参数**:
- `site_id` (query): 站点UUID
- `limit` (query): 返回数量（默认10）

**响应**:
```json
{
  "runs": [
    {
      "id": "uuid",
      "site_id": "uuid",
      "horizon": "day_ahead",
      "resolution_minutes": 15,
      "model_version": "v1.0",
      "created_at": "2026-02-09T12:00:00Z"
    }
  ]
}
```

---

## 4. Load（负荷预测）

### POST /load/run
**描述**: 运行负荷预测（MVP: 生成典型负荷曲线）  
**请求体**:
```json
{
  "site_id": "uuid",
  "start": "2026-02-10T00:00:00Z",
  "end": "2026-02-10T23:59:59Z",
  "resolution_minutes": 15
}
```
**响应**:
```json
{
  "status": "ok",
  "run_id": "uuid",
  "points": 96
}
```

### GET /load/latest
**描述**: 获取最新负荷预测  
**参数**:
- `site_id` (query): 站点UUID

**响应**:
```json
{
  "site_id": "uuid",
  "resolution_minutes": 15,
  "unit": "kW",
  "points": [
    {"ts": "2026-02-10T00:00:00Z", "p50": 60.25},
    {"ts": "2026-02-10T00:15:00Z", "p50": 62.18}
  ]
}
```

---

## 5. Dispatch（能源调度）

### POST /dispatch/run
**描述**: 触发调度优化运行  
**请求体**:
```json
{
  "site_id": "uuid",
  "start": "2026-02-10T00:00:00Z",
  "end": "2026-02-11T00:00:00Z",
  "resolution_minutes": 15,
  "forecast_quantile": 0.5,
  "load_kw": [50, 50, ...],  // 96个点
  "tariff": {
    "buy": [0.10, 0.12, ...],
    "sell": [0.05, 0.06, ...]
  },
  "bess": {
    "capacity_kwh": 100.0,
    "p_charge_max_kw": 50.0,
    "p_discharge_max_kw": 50.0,
    "soc0": 0.5,
    "soc_min": 0.2,
    "soc_max": 0.9,
    "eta_charge": 0.95,
    "eta_discharge": 0.95
  },
  "limits": {
    "grid_import_max_kw": 200.0,
    "grid_export_max_kw": 200.0,
    "transformer_max_kw": 250.0
  },
  "weights": {
    "cost": 1.0,
    "curtail": 0.2,
    "carbon": 0.0,
    "violation": 1000.0
  }
}
```
**响应**:
```json
{
  "run_id": "uuid",
  "status": "ok",
  "fallback_used": false
}
```

### GET /dispatch/latest
**描述**: 获取最新调度计划  
**参数**:
- `site_id` (query): 站点UUID

**响应**:
```json
{
  "site_id": "uuid",
  "resolution_minutes": 15,
  "unit": "kW",
  "soc_unit": "fraction",
  "points": [
    {
      "ts": "2026-02-10T00:00:00Z",
      "pv_set_kw": 8.26,
      "batt_ch_kw": 0.0,
      "batt_dis_kw": 0.0,
      "grid_imp_kw": 51.74,
      "grid_exp_kw": 0.0,
      "curtail_kw": 0.0,
      "soc": 0.5,
      "reason": "Grid import to meet demand"
    }
  ]
}
```

### GET /dispatch/kpis
**描述**: 获取调度关键指标  
**参数**:
- `run_id` (query): 调度运行UUID

**响应**:
```json
{
  "run_id": "uuid",
  "site_id": "uuid",
  "total_cost": 125.50,
  "total_curtail_kwh": 5.25,
  "peak_grid_import_kw": 115.0,
  "avg_soc": 0.45,
  "created_at": "2026-02-09T12:00:00Z"
}
```

---

## 6. Validation & Calibration（验证与校准）

### POST /validate/run
**描述**: 运行模型验证（计算MAE/nRMSE/bias）  
**请求体**:
```json
{
  "site_id": "uuid",
  "horizon": "day_ahead",
  "metric": "pv_power_kw",
  "start": "2026-02-09T00:00:00Z",
  "end": "2026-02-09T23:59:59Z",
  "resolution_minutes": 15
}
```
**响应**:
```json
{
  "status": "ok",
  "validation_id": "uuid",
  "mae": 8.16,
  "nrmse": 0.227,
  "bias": -3.0,
  "points": 96
}
```

### GET /validate/latest
**描述**: 获取最新验证结果  
**参数**:
- `site_id` (query): 站点UUID
- `horizon` (query): 预测周期（默认 day_ahead）
- `metric` (query): 验证指标（默认 pv_power_kw）

**响应**:
```json
{
  "validation_id": "uuid",
  "site_id": "uuid",
  "horizon": "day_ahead",
  "metric": "pv_power_kw",
  "mae": 8.16,
  "nrmse": 0.227,
  "bias": -3.0,
  "start_ts": "2026-02-09T00:00:00Z",
  "end_ts": "2026-02-09T23:59:59Z",
  "created_at": "2026-02-09T12:00:00Z"
}
```

### POST /calibration/apply_latest
**描述**: 基于最新验证结果应用模型校准  
**请求体**:
```json
{
  "site_id": "uuid"
}
```
**响应**:
```json
{
  "status": "ok",
  "calibration_id": "uuid",
  "bias": -3.0,
  "pr_old": 0.85,
  "pr_new": 0.843,
  "soiling": 0.98
}
```

### GET /health/latest
**描述**: 获取模型健康状态（绿/黄/红灯）  
**参数**:
- `site_id` (query): 站点UUID
- `model_type` (query): 模型类型（默认 pv_forecast）

**响应**:
```json
{
  "id": "uuid",
  "site_id": "uuid",
  "model_type": "pv_forecast",
  "window_start": "2026-02-09T00:00:00Z",
  "window_end": "2026-02-09T23:59:59Z",
  "mae": 8.16,
  "nrmse": 0.227,
  "drift_score": 3.0,
  "status": "amber",
  "created_at": "2026-02-09T12:00:00Z"
}
```

**状态说明**:
- `green`: nRMSE < 15%（良好）
- `amber`: 15% ≤ nRMSE < 25%（警告）
- `red`: nRMSE ≥ 25%（需要关注）

---

## 7. Alerts & Audit & Reports（告警、审计、报告）

### GET /alerts
**描述**: 获取告警列表  
**参数**:
- `site_id` (query): 站点UUID
- `severity` (query, optional): 严重级别过滤（info/warn/critical）
- `limit` (query): 返回数量（默认50）

**响应**:
```json
{
  "alerts": [
    {
      "id": "uuid",
      "site_id": "uuid",
      "severity": "warn",
      "category": "forecast",
      "title": "Forecast Accuracy Degraded",
      "detail": "nRMSE increased from 18% to 23%",
      "ts": "2026-02-09T10:00:00Z",
      "acknowledged": false,
      "meta": {"prev_nrmse": 0.18, "curr_nrmse": 0.23}
    }
  ]
}
```

**告警类别**:
- `data_quality`: 数据质量问题
- `forecast`: 预测精度问题
- `asset`: 资产异常
- `dispatch`: 调度异常

### POST /alerts/{alert_id}/ack
**描述**: 确认告警  
**参数**:
- `alert_id` (path): 告警UUID

**响应**:
```json
{
  "status": "ok",
  "alert_id": "uuid"
}
```

### GET /audit
**描述**: 获取审计日志  
**参数**:
- `site_id` (query, optional): 站点UUID过滤
- `action` (query, optional): 操作类型过滤
- `limit` (query): 返回数量（默认100）

**响应**:
```json
{
  "entries": [
    {
      "id": "uuid",
      "actor": "system",
      "action": "forecast_run",
      "payload": {
        "site_id": "uuid",
        "horizon": "day_ahead",
        "result": {...}
      },
      "created_at": "2026-02-09T12:00:00Z"
    }
  ]
}
```

**常见操作类型**:
- `forecast_run`: 预测运行
- `dispatch_run`: 调度运行
- `calibration_applied`: 校准应用
- `config_updated`: 配置更新

### GET /reports/dispatch.csv
**描述**: 导出调度计划为CSV格式  
**参数**:
- `run_id` (query): 调度运行UUID

**响应**: CSV文件下载
```csv
timestamp,pv_set_kw,batt_ch_kw,batt_dis_kw,grid_imp_kw,grid_exp_kw,curtail_kw,soc,reason
2026-02-10T00:00:00Z,8.26,0.0,0.0,51.74,0.0,0.0,0.5,"Grid import to meet demand"
2026-02-10T08:00:00Z,60.0,20.0,0.0,0.0,0.0,0.0,0.55,"Charge using curtailed PV"
2026-02-10T18:00:00Z,5.0,0.0,50.0,65.0,0.0,0.0,0.575,"Discharge due to peak tariff hours"
```

---

## 端点总结

### 按功能分类

**站点配置** (6个):
- GET /sites
- GET /sites/{site_id}
- GET /config/tariff/latest
- POST /config/tariff/upsert
- GET /config/bess/latest
- POST /config/bess/upsert

**数据查询** (1个):
- GET /telemetry/query

**预测** (5个):
- POST /forecast/run
- GET /forecast/latest
- GET /forecast/runs
- POST /load/run
- GET /load/latest

**调度** (3个):
- POST /dispatch/run
- GET /dispatch/latest
- GET /dispatch/kpis

**验证与校准** (4个):
- POST /validate/run
- GET /validate/latest
- POST /calibration/apply_latest
- GET /health/latest

**告警与审计** (4个):
- GET /alerts
- POST /alerts/{alert_id}/ack
- GET /audit
- GET /reports/dispatch.csv

**总计**: 24个端点

---

## 接口契约规范

### 统一原则

1. **POST 端点**：全部使用 JSON body 传参
2. **GET 端点**：全部使用 query 参数传参
3. **时间格式**：ISO 8601 格式（YYYY-MM-DDTHH:MM:SSZ）
4. **UUID 格式**：标准36字符格式
5. **CORS**：允许跨域访问（生产环境应限制特定域名）

### 错误响应

所有端点遵循统一的错误响应格式：
```json
{
  "error": "Error message",
  "detail": "Detailed error information"
}
```

HTTP 状态码：
- `200 OK`: 成功
- `404 Not Found`: 资源不存在
- `500 Internal Server Error`: 服务器错误

---

## 测试示例

### PowerShell

```powershell
# 获取站点列表
Invoke-RestMethod -Uri "http://localhost:8000/sites" -Method Get

# 运行预测
$body = @'
{
  "site_id": "11111111-1111-1111-1111-111111111111",
  "horizon": "day_ahead",
  "start": "2026-02-10T00:00:00Z",
  "end": "2026-02-11T00:00:00Z",
  "resolution_minutes": 15,
  "quantiles": [0.1, 0.5, 0.9],
  "weather_source": "telemetry_or_mock"
}
'@
Invoke-RestMethod -Uri http://localhost:8000/forecast/run -Method Post -ContentType "application/json" -Body $body

# 获取告警
Invoke-RestMethod -Uri "http://localhost:8000/alerts?site_id=11111111-1111-1111-1111-111111111111&severity=warn" -Method Get
```

### cURL

```bash
# 获取站点详情
curl -X GET "http://localhost:8000/sites/11111111-1111-1111-1111-111111111111"

# 运行负荷预测
curl -X POST http://localhost:8000/load/run \
  -H "Content-Type: application/json" \
  -d '{"site_id":"11111111-1111-1111-1111-111111111111","start":"2026-02-10T00:00:00Z","end":"2026-02-10T23:59:59Z","resolution_minutes":15}'

# 下载CSV报告
curl -X GET "http://localhost:8000/reports/dispatch.csv?run_id=<run_id>" -o dispatch.csv
```

---

## 参考文档

- [接口契约示例](../docs/openapi/schema_examples.json)
- [数据库表结构](../docs/DATABASE_SCHEMA.md)
- [API迁移指南](../docs/API_MIGRATION_GUIDE.md)
