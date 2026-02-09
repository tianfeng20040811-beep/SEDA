# API 接口迁移指南

## 统一接口契约（v1.0）

### 核心原则

- **所有 POST 端点**：使用 JSON body 传参
- **所有 GET 端点**：使用 query 参数传参
- **时间格式**：ISO 8601 格式 (YYYY-MM-DDTHH:MM:SSZ)
- **UUID 格式**：标准 36 字符格式

## 接口变更详情

### 1. POST /forecast/run

**变更前**：简单参数
```json
{
  "site_id": "uuid",
  "horizon": "day_ahead",
  "resolution_minutes": 15
}
```

**变更后**：完整参数
```json
{
  "site_id": "11111111-1111-1111-1111-111111111111",
  "horizon": "day_ahead",
  "start": "2026-02-10T00:00:00Z",
  "end": "2026-02-11T00:00:00Z",
  "resolution_minutes": 15,
  "quantiles": [0.1, 0.5, 0.9],
  "weather_source": "telemetry_or_mock"
}
```

**响应格式**：
```json
{
  "run_id": "uuid",
  "status": "ok"
}
```

---

### 2. POST /dispatch/run

**变更前**：简单参数
```json
{
  "site_id": "uuid",
  "resolution_minutes": 15
}
```

**变更后**：完整参数（包含负载、电价、电池、限制、权重）
```json
{
  "site_id": "11111111-1111-1111-1111-111111111111",
  "start": "2026-02-10T00:00:00Z",
  "end": "2026-02-11T00:00:00Z",
  "resolution_minutes": 15,
  "forecast_quantile": 0.5,
  "load_kw": [50, 50, ...],  // 96个点
  "tariff": {
    "buy": [0.10, 0.12, ...],  // 96个点
    "sell": [0.05, 0.06, ...]  // 96个点
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

**响应格式**：
```json
{
  "run_id": "uuid",
  "status": "ok",
  "fallback_used": false
}
```

---

### 3. POST /calibration/apply_latest

**变更前**：Query 参数
```
POST /calibration/apply_latest?site_id=uuid
```

**变更后**：JSON body
```json
{
  "site_id": "11111111-1111-1111-1111-111111111111"
}
```

**响应格式**：
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

---

## 测试示例

### PowerShell

```powershell
# Forecast Run
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

# Calibration
$body = '{"site_id": "11111111-1111-1111-1111-111111111111"}'
Invoke-RestMethod -Uri http://localhost:8000/calibration/apply_latest -Method Post -ContentType "application/json" -Body $body
```

### cURL

```bash
# Forecast Run
curl -X POST http://localhost:8000/forecast/run \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "11111111-1111-1111-1111-111111111111",
    "horizon": "day_ahead",
    "start": "2026-02-10T00:00:00Z",
    "end": "2026-02-11T00:00:00Z",
    "resolution_minutes": 15,
    "quantiles": [0.1, 0.5, 0.9],
    "weather_source": "telemetry_or_mock"
  }'

# Calibration
curl -X POST http://localhost:8000/calibration/apply_latest \
  -H "Content-Type: application/json" \
  -d '{"site_id": "11111111-1111-1111-1111-111111111111"}'
```

---

## 实现说明

### 当前阶段（最小可行版）

目前 API Gateway 接受完整的 JSON body，但**下游服务调用仍使用简化参数**。

例如，`/forecast/run` 接收完整参数但目前只传递给下游：
- site_id
- horizon
- resolution_minutes

**完整参数的使用将在后续迭代中实现**：
- `start`, `end` → 时间范围控制
- `quantiles` → 多分位数预测
- `weather_source` → 天气数据源选择
- `load_kw`, `tariff` → 从前端传入或从 DB 查询

### 审计日志

所有请求的**完整参数**都会记录在 `audit_log` 表中，即使当前未被下游使用。这确保了：
1. 接口契约的完整性
2. 后续功能扩展的向后兼容
3. 完整的操作可追溯性

---

## 前端适配

Flutter 客户端需要更新：

### forecast/run 调用示例

```dart
final response = await apiClient.post('/forecast/run', data: {
  'site_id': siteId,
  'horizon': 'day_ahead',
  'start': '2026-02-10T00:00:00Z',
  'end': '2026-02-11T00:00:00Z',
  'resolution_minutes': 15,
  'quantiles': [0.1, 0.5, 0.9],
  'weather_source': 'telemetry_or_mock',
});
```

### dispatch/run 调用示例

需要构造完整的 load_kw、tariff 数组（96个点对应24小时 × 15分钟分辨率）。

---

## 参考文档

完整的接口契约和示例数据：
- [schema_examples.json](../docs/openapi/schema_examples.json)

所有字段定义、数据类型、约束条件均在此文件中维护。
