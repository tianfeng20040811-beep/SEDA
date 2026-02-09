-- 插入示例 BESS 配置
INSERT INTO bess_profiles (id, site_id, name, params, valid_from)
VALUES (
  '33333333-3333-3333-3333-333333333333',
  '11111111-1111-1111-1111-111111111111',
  'Default BESS 100kWh',
  '{"capacity_kwh": 100.0, "p_charge_max_kw": 50.0, "p_discharge_max_kw": 50.0, "soc0": 0.5, "soc_min": 0.2, "soc_max": 0.9, "eta_charge": 0.95, "eta_discharge": 0.95}'::jsonb,
  NOW()
) ON CONFLICT (id) DO NOTHING;

-- 插入几个示例告警
INSERT INTO alerts (id, site_id, severity, category, title, detail, ts, acknowledged, meta)
VALUES 
  (
    '44444444-4444-4444-4444-444444444444',
    '11111111-1111-1111-1111-111111111111',
    'warn',
    'forecast',
    'Forecast Accuracy Degraded',
    'nRMSE increased from 18% to 23% over the past week',
    NOW() - INTERVAL '2 hours',
    false,
    '{"prev_nrmse": 0.18, "curr_nrmse": 0.23}'::jsonb
  ),
  (
    '55555555-5555-5555-5555-555555555555',
    '11111111-1111-1111-1111-111111111111',
    'info',
    'dispatch',
    'Calibration Applied',
    'Model calibration successfully reduced bias from 7.0 kW to -3.0 kW',
    NOW() - INTERVAL '1 hour',
    true,
    '{"old_bias": 7.0, "new_bias": -3.0, "pr_old": 0.85, "pr_new": 0.843}'::jsonb
  )
ON CONFLICT (id) DO NOTHING;
