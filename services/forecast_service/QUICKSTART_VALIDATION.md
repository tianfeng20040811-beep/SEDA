# Forecast Validation & Calibration Quick Start

快速测试预测验证、漂移检测和自动校准功能。

## 1. 启动服务

```bash
cd sedai-solar2grid
docker-compose up -d db
docker-compose up forecast_service
```

服务将在 `http://localhost:8001` 启动。

## 2. 验证工作流 (Validation → Drift → Calibration)

### Step 1: 运行预测验证

验证预测准确性，计算 MAE、NRMSE、Bias等KPI。

```bash
curl -X POST http://localhost:8001/validate/run \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "11111111-1111-1111-1111-111111111111",
    "start": "2024-03-01T00:00:00Z",
    "end": "2024-03-02T00:00:00Z",
    "resolution_minutes": 15,
    "metric": "pv_power_kw"
  }'
```

**响应示例**:
```json
{
  "validation_id": "uuid",
  "status": "ok",
  "metrics": {
    "mae": 12.5,
    "rmse": 18.3,
    "nrmse": 0.152,
    "bias": -5.2,
    "r2": 0.92
  },
  "points": {
    "n_points": 96,
    "mean_actual": 120.5,
    "mean_forecast": 115.3
  }
}
```

**KPI 解释**:
- `mae`: 平均绝对误差 (kW) - 越小越好
- `nrmse`: 归一化均方根误差 (0-1) - < 0.15 为优秀
- `bias`: 偏差 (kW) - 负值表示预测偏低，正值表示预测偏高
- `r2`: 决定系数 - 越接近1越好

### Step 2: 查看最新验证结果

```bash
curl http://localhost:8001/validate/latest?site_id=11111111-1111-1111-1111-111111111111
```

### Step 3: 检测模型漂移

检测模型性能是否退化（最近7天 vs 过去30天）。

```bash
curl -X POST http://localhost:8001/drift/check?site_id=11111111-1111-1111-1111-111111111111
```

**响应示例**:
```json
{
  "health_id": "uuid",
  "status": "green",
  "drift_score": 0.08,
  "baseline_nrmse": 0.15,
  "recent_nrmse": 0.162,
  "message": "Model healthy (drift 8.0%)"
}
```

**Status 含义**:
- 🟢 **green**: drift < 15% - 模型健康
- 🟡 **amber**: 15% ≤ drift < 30% - 模型退化，建议重新校准
- 🔴 **red**: drift ≥ 30% - 模型漂移严重，需立即校准

### Step 4: 查看模型健康状态

```bash
curl http://localhost:8001/health/latest?site_id=11111111-1111-1111-1111-111111111111
```

### Step 5: 自动校准模型参数

根据最新的bias自动调整PR或soiling参数。

```bash
curl -X POST "http://localhost:8001/calibrate/run?site_id=11111111-1111-1111-1111-111111111111&capacity_kw=500"
```

**响应示例**:
```json
{
  "calibration_id": "uuid",
  "status": "ok",
  "bias": -5.2,
  "parameter": "pr",
  "old_params": {
    "pr": 0.85,
    "soiling": 0.98
  },
  "new_params": {
    "pr": 0.8552,
    "soiling": 0.98,
    "bias": -5.2,
    "calibrated_at": "2024-03-15T10:30:00Z"
  },
  "delta": {
    "pr": 0.0052,
    "soiling": 0.0
  }
}
```

**校准逻辑**:
- **Bias < 0** (预测偏低): 增加 PR → 提高预测值
- **Bias > 0** (预测偏高): 减少 PR → 降低预测值
- PR 调整范围: [0.70, 0.95]
- Soiling 调整范围: [0.90, 1.00]

### Step 6: 查看最新校准参数

```bash
curl http://localhost:8001/calibrate/latest?site_id=11111111-1111-1111-1111-111111111111
```

### Step 7: 验证校准效果

重新运行预测（会自动使用最新校准参数），然后再次验证：

```bash
# 1. 运行新的预测
curl -X POST http://localhost:8001/forecast/run \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "11111111-1111-1111-1111-111111111111",
    "horizon": "day_ahead",
    "resolution_minutes": 15,
    "use_ml_model": true
  }'

# 2. 再次验证
curl -X POST http://localhost:8001/validate/run \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "11111111-1111-1111-1111-111111111111",
    "start": "2024-03-02T00:00:00Z",
    "end": "2024-03-03T00:00:00Z",
    "resolution_minutes": 15,
    "metric": "pv_power_kw"
  }'
```

期望结果: **Bias 接近 0**，NRMSE 降低。

## 3. 完整工作流示例

### 自动化脚本

```bash
#!/bin/bash
SITE_ID="11111111-1111-1111-1111-111111111111"
BASE_URL="http://localhost:8001"

echo "=== Step 1: Validate Forecast ==="
curl -X POST $BASE_URL/validate/run \
  -H "Content-Type: application/json" \
  -d "{
    \"site_id\": \"$SITE_ID\",
    \"start\": \"2024-03-01T00:00:00Z\",
    \"end\": \"2024-03-02T00:00:00Z\",
    \"resolution_minutes\": 15,
    \"metric\": \"pv_power_kw\"
  }" | jq

echo -e "\n=== Step 2: Check Drift ==="
curl -X POST "$BASE_URL/drift/check?site_id=$SITE_ID" | jq

echo -e "\n=== Step 3: Calibrate ==="
curl -X POST "$BASE_URL/calibrate/run?site_id=$SITE_ID&capacity_kw=500" | jq

echo -e "\n=== Step 4: View Latest Calibration ==="
curl "$BASE_URL/calibrate/latest?site_id=$SITE_ID" | jq
```

保存为 `test_validation.sh`，运行：

```bash
chmod +x test_validation.sh
./test_validation.sh
```

## 4. 数据库查询

### 查看验证历史

```sql
SELECT id, mae, nrmse, bias, created_at
FROM validation_runs
WHERE site_id = '11111111-1111-1111-1111-111111111111'
ORDER BY created_at DESC
LIMIT 10;
```

### 查看模型健康历史

```sql
SELECT id, drift_score, status, nrmse, created_at
FROM model_health
WHERE site_id = '11111111-1111-1111-1111-111111111111'
ORDER BY created_at DESC
LIMIT 10;
```

### 查看校准历史

```sql
SELECT id, params, valid_from
FROM model_calibration
WHERE site_id = '11111111-1111-1111-1111-111111111111'
ORDER BY valid_from DESC
LIMIT 10;
```

### 可视化PR调整趋势

```sql
SELECT 
  valid_from,
  (params->>'pr')::float AS pr,
  (params->>'soiling')::float AS soiling,
  (params->>'bias')::float AS bias
FROM model_calibration
WHERE site_id = '11111111-1111-1111-1111-111111111111'
ORDER BY valid_from ASC;
```

## 5. 测试组件

每个验证模块都有独立的测试代码：

```bash
cd services/forecast_service

# 测试验证器
python validation/validator.py

# 测试漂移检测器
python validation/drift_detector.py

# 测试校准器
python validation/calibrator.py
```

## 6. API 文档

访问自动生成的API文档：

```
http://localhost:8001/docs
```

### 新增端点列表

| 端点 | 方法 | 功能 |
|------|------|------|
| `/validate/run` | POST | 运行预测验证 |
| `/validate/latest` | GET | 获取最新验证结果 |
| `/drift/check` | POST | 检测模型漂移 |
| `/health/latest` | GET | 获取最新健康状态 |
| `/calibrate/run` | POST | 自动校准参数 |
| `/calibrate/latest` | GET | 获取最新校准参数 |

## 7. 验证清单

运行完整工作流后，检查：

- [ ] `validation_runs` 表有新记录
- [ ] `model_health` 表有新记录
- [ ] `model_calibration` 表有新记录
- [ ] NRMSE < 0.20 (20%)
- [ ] |Bias| < 10 kW
- [ ] Drift status 为 green 或 amber
- [ ] 校准后的 PR 在 [0.70, 0.95] 范围内
- [ ] 新预测自动使用最新的校准参数

## 8. 常见问题

### 问题: "No validation found"

原因: 需要先运行验证才能进行漂移检测和校准。

解决: 
```bash
# 先运行验证
curl -X POST http://localhost:8001/validate/run -d '{...}'
```

### 问题: "No actual telemetry found"

原因: 数据库中没有对应时间段的实际测量数据。

解决: 
1. 检查 `telemetry` 表是否有数据
2. 使用正确的时间范围（过去的时间，不是未来的）
3. 确保 `metric` 参数正确（默认 "pv_power_kw"）

### 问题: Drift status 总是 "green"

原因: 验证数据不足（少于7天）。

解决: 
- 等待积累更多验证数据（至少7天）
- 或者调整 DriftDetector 的 `recent_days` 参数

### 问题: 校准后 Bias 仍然很大

原因: 单次校准可能不够，需要迭代调整。

解决: 
1. 运行新的预测（使用校准后的参数）
2. 再次验证
3. 如果 Bias 仍大，再次校准
4. 重复直到 Bias 接近 0

## 9. 性能基准

| 操作 | 响应时间 | 备注 |
|------|---------|------|
| 验证（96点） | < 0.5s | 包括数据库查询和KPI计算 |
| 漂移检测 | < 0.2s | 查询历史NRMSE并计算 |
| 校准 | < 0.1s | 简单的线性调整 |

## 10. 下一步

- 阅读完整文档: [FORECAST_SERVICE_UPGRADE.md](FORECAST_SERVICE_UPGRADE.md)
- 集成到Flutter App: 显示模型健康灯（green/amber/red）
- 设置定时任务: 每天自动运行验证和漂移检测
- 告警集成: 当 drift status = "red" 时发送告警
- 高级校准: 尝试调整 soiling 参数或其他物理模型参数

---

**快速参考**:
- API 地址: http://localhost:8001
- API 文档: http://localhost:8001/docs
- 数据库: `docker exec -it db psql -U postgres -d sedai_db`
- 日志: `docker-compose logs forecast_service`
