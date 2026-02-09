# Forecast Service 升级 - 快速开始

## 🚀 立即开始

### 1. 重建服务

```powershell
cd c:\Users\TIAN FENG\Desktop\SDEA\sedai-solar2grid\infra

# 停止旧服务
docker-compose down

# 重建 forecast service（安装新依赖）
docker-compose build forecast

# 启动所有服务
docker-compose up -d
```

### 2. 验证服务运行

```powershell
# 检查服务状态
docker-compose ps

# 查看 forecast service 日志
docker-compose logs -f forecast
```

预期输出应包含：
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8001
```

---

## 🧪 测试新功能

### 测试 1: 物理模型预测（无需训练）

```powershell
$body = @'
{
  "site_id": "11111111-1111-1111-1111-111111111111",
  "horizon": "day_ahead",
  "resolution_minutes": 60,
  "use_ml_model": false,
  "weather_source": "mock"
}
'@

$result = Invoke-RestMethod -Uri http://localhost:8001/forecast/run `
  -Method Post `
  -ContentType "application/json" `
  -Body $body

$result
```

**预期输出**:
```json
{
  "run_id": "uuid",
  "status": "ok",
  "model_version": "physical_baseline",
  "fallback_used": false,
  "points_generated": 24
}
```

### 测试 2: 查看预测结果

```powershell
$forecast = Invoke-RestMethod -Uri "http://localhost:8001/forecast/latest?site_id=11111111-1111-1111-1111-111111111111"

$forecast.points | Select-Object -First 5 | Format-Table
```

---

## 🎓 训练 ML 模型

### 前提条件

需要历史 telemetry 数据（至少 30 天）：
- `ghi` (W/m²)
- `temp_amb` (°C)
- `wind` (m/s)
- `pv_power_kw` (kW)

### 训练命令

```powershell
$body = @'
{
  "site_id": "11111111-1111-1111-1111-111111111111",
  "start": "2026-01-10T00:00:00Z",
  "end": "2026-02-09T00:00:00Z",
  "quantiles": [0.1, 0.5, 0.9],
  "test_size": 0.2
}
'@

$training_result = Invoke-RestMethod -Uri http://localhost:8001/train `
  -Method Post `
  -ContentType "application/json" `
  -Body $body

$training_result
```

**预期输出**:
```json
{
  "status": "ok",
  "version": "v20260209_001",
  "metrics": {
    "0.5": {
      "quantile_loss": 0.0189,
      "mae": 4.8,
      "test_samples": 576
    }
  },
  "training_samples": 2880
}
```

---

## 🔮 使用 ML 增强预测

训练完成后，再次运行预测（这次会自动使用 ML 模型）：

```powershell
$body = @'
{
  "site_id": "11111111-1111-1111-1111-111111111111",
  "horizon": "day_ahead",
  "resolution_minutes": 15,
  "use_ml_model": true,
  "weather_source": "mock"
}
'@

$result = Invoke-RestMethod -Uri http://localhost:8001/forecast/run `
  -Method Post `
  -ContentType "application/json" `
  -Body $body

$result
```

现在 `model_version` 应该是 `v20260209_001` 而不是 `physical_baseline`。

---

## 📊 查看模型信息

### 列出所有模型版本

```powershell
Invoke-RestMethod -Uri "http://localhost:8001/models/list?site_id=11111111-1111-1111-1111-111111111111"
```

### 查看模型详情

```powershell
Invoke-RestMethod -Uri "http://localhost:8001/models/info?site_id=11111111-1111-1111-1111-111111111111&version=v20260209_001"
```

---

## 🐛 故障排查

### 问题 1: 训练失败 - "No data available"

**原因**: 缺少历史 telemetry 数据

**解决**: 插入测试数据

```sql
-- 连接到数据库
docker exec -it infra-db-1 psql -U postgres -d sedai

-- 检查数据
SELECT metric, COUNT(*)
FROM telemetry
WHERE site_id = '11111111-1111-1111-1111-111111111111'
GROUP BY metric;

-- 如果没有数据，需要先运行 IoT ingestor 或手动插入测试数据
```

### 问题 2: 依赖安装失败

**症状**: Docker build 报错

**解决**:
```powershell
# 清理并重建
docker-compose down
docker-compose build --no-cache forecast
docker-compose up -d
```

### 问题 3: 模型加载失败

**症状**: `model_version: "physical_baseline"` 即使已训练

**原因**: 模型文件未持久化

**解决**: 检查 volume 挂载
```powershell
# 查看 volume
docker volume ls | Select-String forecast

# 检查容器内模型目录
docker exec infra-forecast-1 ls -la /app/model_store
```

---

## 📁 文件清单

新增/修改的文件：

```
services/forecast_service/
├── main.py                    ✅ 重构（新增 3 个端点）
├── requirements.txt           ✅ 更新（添加 ML 依赖）
├── pv_physics.py             ✨ 新增
├── data_repo.py              ✨ 新增
├── test_components.py        ✨ 新增（测试脚本）
└── models/
    ├── __init__.py           ✨ 新增
    ├── model_registry.py     ✨ 新增
    ├── trainer.py            ✨ 新增
    └── predictor.py          ✨ 新增

infra/
└── docker-compose.yml         ✅ 更新（添加 volume）

docs/
├── FORECAST_SERVICE_UPGRADE.md  ✨ 新增（完整文档）
└── QUICKSTART_FORECAST.md       ✨ 新增（本文件）
```

---

## 🎯 核心概念

### 预测架构

```
┌─────────────────┐
│  Mock Weather   │ (或 NWP 预报)
└────────┬────────┘
         ↓
┌─────────────────┐
│ Physical Model  │ → 基线预测（可解释）
└────────┬────────┘
         ↓
┌─────────────────┐
│  LightGBM Model │ → 残差修正（精度提升）
└────────┬────────┘
         ↓
┌─────────────────┐
│ Final Forecast  │ = 物理基线 + ML 残差
└─────────────────┘
```

### 分位数预测

- **p10**: 悲观预测（90% 概率实际值 > p10）
- **p50**: 中位数预测（最佳估计）
- **p90**: 乐观预测（10% 概率实际值 > p90）

用于不确定性量化和风险管理。

---

## 🔄 定期维护

建议每周运行重训练：

```powershell
# weekly_retrain.ps1
$end = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddT00:00:00Z")
$start = (Get-Date).AddDays(-30).ToUniversalTime().ToString("yyyy-MM-ddT00:00:00Z")

$body = @"
{
  "site_id": "11111111-1111-1111-1111-111111111111",
  "start": "$start",
  "end": "$end",
  "quantiles": [0.1, 0.5, 0.9]
}
"@

Invoke-RestMethod -Uri http://localhost:8001/train `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

---

## 📚 更多信息

详细文档: [FORECAST_SERVICE_UPGRADE.md](FORECAST_SERVICE_UPGRADE.md)

API 端点清单: [API_ENDPOINTS.md](API_ENDPOINTS.md)
