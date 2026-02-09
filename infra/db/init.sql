CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;

-- sites
CREATE TABLE IF NOT EXISTS sites (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  timezone TEXT NOT NULL DEFAULT 'Asia/Kuala_Lumpur',
  lat DOUBLE PRECISION,
  lon DOUBLE PRECISION,
  capacity_kw DOUBLE PRECISION,
  tilt_deg DOUBLE PRECISION,
  azimuth_deg DOUBLE PRECISION,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- telemetry (hypertable)
CREATE TABLE IF NOT EXISTS telemetry (
  ts TIMESTAMPTZ NOT NULL,
  site_id UUID NOT NULL,
  asset_id UUID,
  metric TEXT NOT NULL,
  value DOUBLE PRECISION NOT NULL,
  quality SMALLINT NOT NULL DEFAULT 0
);

SELECT create_hypertable('telemetry', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_telemetry_site_metric_ts ON telemetry(site_id, metric, ts DESC);

-- forecast runs + forecasts (hypertable)
CREATE TABLE IF NOT EXISTS forecast_runs (
  id UUID PRIMARY KEY,
  site_id UUID NOT NULL,
  horizon TEXT NOT NULL,
  resolution_minutes INT NOT NULL,
  model_version TEXT NOT NULL,
  feature_version TEXT NOT NULL,
  data_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS forecasts (
  ts TIMESTAMPTZ NOT NULL,
  site_id UUID NOT NULL,
  run_id UUID NOT NULL,
  p10 DOUBLE PRECISION NOT NULL,
  p50 DOUBLE PRECISION NOT NULL,
  p90 DOUBLE PRECISION NOT NULL,
  unit TEXT NOT NULL DEFAULT 'kW'
);

SELECT create_hypertable('forecasts', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_forecasts_site_ts ON forecasts(site_id, ts DESC);

-- dispatch runs + schedules (hypertable)
CREATE TABLE IF NOT EXISTS dispatch_runs (
  id UUID PRIMARY KEY,
  site_id UUID NOT NULL,
  status TEXT NOT NULL,
  solver TEXT NOT NULL,
  objective_config JSONB NOT NULL,
  timeout_ms INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dispatch_schedule (
  ts TIMESTAMPTZ NOT NULL,
  site_id UUID NOT NULL,
  run_id UUID NOT NULL,
  pv_set_kw DOUBLE PRECISION NOT NULL,
  batt_ch_kw DOUBLE PRECISION NOT NULL,
  batt_dis_kw DOUBLE PRECISION NOT NULL,
  grid_imp_kw DOUBLE PRECISION NOT NULL,
  grid_exp_kw DOUBLE PRECISION NOT NULL,
  curtail_kw DOUBLE PRECISION NOT NULL,
  soc DOUBLE PRECISION NOT NULL,
  reason TEXT
);

SELECT create_hypertable('dispatch_schedule', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_dispatch_site_ts ON dispatch_schedule(site_id, ts DESC);

-- audit log
CREATE TABLE IF NOT EXISTS audit_log (
  id UUID PRIMARY KEY,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- seed one site
INSERT INTO sites (id, name, lat, lon, capacity_kw, tilt_deg, azimuth_deg)
VALUES ('11111111-1111-1111-1111-111111111111', 'Demo Microgrid', 5.4164, 100.3327, 500, 10, 180)
ON CONFLICT (id) DO NOTHING;

-- validation runs (闭环校正 - 验证评估)
CREATE TABLE IF NOT EXISTS validation_runs (
  id UUID PRIMARY KEY,
  site_id UUID NOT NULL,
  horizon TEXT NOT NULL,
  start_ts TIMESTAMPTZ NOT NULL,
  end_ts TIMESTAMPTZ NOT NULL,
  resolution_minutes INT NOT NULL,
  run_id_forecast UUID,
  metric TEXT NOT NULL DEFAULT 'pv_power_kw',
  mae DOUBLE PRECISION NOT NULL,
  nrmse DOUBLE PRECISION NOT NULL,
  bias DOUBLE PRECISION NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- store calibration parameters used by forecast baseline (闭环校正 - 模型校准)
CREATE TABLE IF NOT EXISTS model_calibration (
  id UUID PRIMARY KEY,
  site_id UUID NOT NULL,
  model_type TEXT NOT NULL DEFAULT 'forecast_baseline',
  params JSONB NOT NULL,
  valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validation_site_time ON validation_runs(site_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_calibration_site_time ON model_calibration(site_id, valid_from DESC);

-- 2.1 负荷预测表 load_forecasts（必须）
-- MVP 只存 p50，进阶可存 p10/p90
CREATE TABLE IF NOT EXISTS load_forecasts (
  ts TIMESTAMPTZ NOT NULL,
  site_id UUID NOT NULL,
  run_id UUID NOT NULL,
  p50 DOUBLE PRECISION NOT NULL,
  unit TEXT NOT NULL DEFAULT 'kW'
);

SELECT create_hypertable('load_forecasts', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_load_site_ts ON load_forecasts(site_id, ts DESC);

-- 2.2 电价表 tariff_profiles（必须）
-- buy/sell 为 JSONB 数组，长度=96（24小时×15分钟分辨率）
CREATE TABLE IF NOT EXISTS tariff_profiles (
  id UUID PRIMARY KEY,
  site_id UUID NOT NULL,
  name TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'MYR',
  resolution_minutes INT NOT NULL DEFAULT 15,
  buy JSONB NOT NULL,   -- length=96
  sell JSONB NOT NULL,  -- length=96
  valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tariff_site_time ON tariff_profiles(site_id, valid_from DESC);

-- 2.3 BESS 配置表 bess_profiles（必须）
-- params: capacity_kwh, p_charge_max_kw, p_discharge_max_kw, soc_min, soc_max, eta_charge, eta_discharge
CREATE TABLE IF NOT EXISTS bess_profiles (
  id UUID PRIMARY KEY,
  site_id UUID NOT NULL,
  name TEXT NOT NULL,
  params JSONB NOT NULL,
  valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bess_site_time ON bess_profiles(site_id, valid_from DESC);

-- 2.4 调度 KPI 表 dispatch_kpis（强烈建议）
-- 用于存储每次调度优化的关键指标
CREATE TABLE IF NOT EXISTS dispatch_kpis (
  run_id UUID PRIMARY KEY,
  site_id UUID NOT NULL,
  total_cost DOUBLE PRECISION NOT NULL,
  total_curtail_kwh DOUBLE PRECISION NOT NULL,
  peak_grid_import_kw DOUBLE PRECISION NOT NULL,
  avg_soc DOUBLE PRECISION NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dispatch_kpi_site_time ON dispatch_kpis(site_id, created_at DESC);

-- 2.5 模型健康监控表 model_health（闭环必备）
-- 用于监控模型漂移和性能退化
CREATE TABLE IF NOT EXISTS model_health (
  id UUID PRIMARY KEY,
  site_id UUID NOT NULL,
  model_type TEXT NOT NULL,
  window_start TIMESTAMPTZ NOT NULL,
  window_end TIMESTAMPTZ NOT NULL,
  mae DOUBLE PRECISION NOT NULL,
  nrmse DOUBLE PRECISION NOT NULL,
  drift_score DOUBLE PRECISION NOT NULL,
  status TEXT NOT NULL, -- green/amber/red
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_health_site_time ON model_health(site_id, created_at DESC);

-- 2.6 告警表 alerts（比赛展示很加分）
-- severity: info/warn/critical
-- category: data_quality/forecast/asset/dispatch
CREATE TABLE IF NOT EXISTS alerts (
  id UUID PRIMARY KEY,
  site_id UUID NOT NULL,
  severity TEXT NOT NULL,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  detail TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_alert_site_ts ON alerts(site_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_alert_severity ON alerts(severity, acknowledged);
