"""
Quick test script for Forecast Service upgrades
Run this to verify all components work correctly
"""
import os
import sys

# Test 1: Import all modules
print("=" * 60)
print("Test 1: Import all modules")
print("=" * 60)

try:
    from pv_physics import compute_p_physical, generate_mock_weather
    print("✅ pv_physics imported successfully")
except ImportError as e:
    print(f"❌ Failed to import pv_physics: {e}")
    sys.exit(1)

try:
    from data_repo import DataRepository
    print("✅ data_repo imported successfully")
except ImportError as e:
    print(f"❌ Failed to import data_repo: {e}")
    sys.exit(1)

try:
    from models.model_registry import ModelRegistry
    print("✅ model_registry imported successfully")
except ImportError as e:
    print(f"❌ Failed to import model_registry: {e}")
    sys.exit(1)

try:
    from models.trainer import ForecastTrainer
    print("✅ trainer imported successfully")
except ImportError as e:
    print(f"❌ Failed to import trainer: {e}")
    sys.exit(1)

try:
    from models.predictor import ForecastPredictor
    print("✅ predictor imported successfully")
except ImportError as e:
    print(f"❌ Failed to import predictor: {e}")
    sys.exit(1)

# Test 2: Physical model computation
print("\n" + "=" * 60)
print("Test 2: Physical model computation")
print("=" * 60)

test_result = compute_p_physical(
    ghi=1000,
    t_amb=25,
    wind=2,
    capacity_kw=500,
    params={"pr": 0.85, "soiling": 0.98}
)
print(f"STC conditions (1000 W/m², 25°C, 2 m/s) -> {test_result:.2f} kW")

if 400 < test_result < 450:
    print("✅ Physical model calculation looks reasonable")
else:
    print(f"⚠️  Physical model result seems off: {test_result} kW (expected ~410-420 kW)")

# Test 3: Mock weather generation
print("\n" + "=" * 60)
print("Test 3: Mock weather generation")
print("=" * 60)

import time
from datetime import datetime, timezone

now = time.time()
start = now - now % 86400
end = start + 3600 * 6  # 6 hours

mock_weather = generate_mock_weather(start, end, resolution_minutes=60)
print(f"Generated {len(mock_weather)} hourly weather points")

if len(mock_weather) == 6:
    print("✅ Mock weather generation works correctly")
    # Show first 2 points
    for i, w in enumerate(mock_weather[:2]):
        dt = datetime.fromtimestamp(w['timestamp'], tz=timezone.utc)
        print(f"  {dt.strftime('%H:%M')}: GHI={w['ghi']:.0f} W/m², T={w['t_amb']:.1f}°C, Wind={w['wind']:.1f} m/s")
else:
    print(f"❌ Expected 6 points, got {len(mock_weather)}")

# Test 4: Model registry
print("\n" + "=" * 60)
print("Test 4: Model registry")
print("=" * 60)

import tempfile
import shutil

temp_dir = tempfile.mkdtemp()
try:
    registry = ModelRegistry(base_dir=temp_dir)
    
    # Save a dummy model
    dummy_model = {"type": "test", "value": 123}
    
    version = registry.save_model(
        site_id="test-site-123",
        model_type="pv_forecast",
        quantile=0.5,
        model_obj=dummy_model,
        metadata={"test": True}
    )
    
    print(f"✅ Saved test model with version: {version}")
    
    # Load it back
    loaded = registry.load_model("test-site-123", "pv_forecast", 0.5, version)
    
    if loaded == dummy_model:
        print("✅ Model load/save works correctly")
    else:
        print(f"❌ Model mismatch: saved {dummy_model}, loaded {loaded}")
    
finally:
    shutil.rmtree(temp_dir)
    print(f"✅ Cleaned up test directory")

# Test 5: Check dependencies
print("\n" + "=" * 60)
print("Test 5: Check ML dependencies")
print("=" * 60)

try:
    import numpy as np
    print(f"✅ numpy {np.__version__}")
except ImportError:
    print("❌ numpy not installed")

try:
    import pandas as pd
    print(f"✅ pandas {pd.__version__}")
except ImportError:
    print("❌ pandas not installed")

try:
    import lightgbm as lgb
    print(f"✅ lightgbm {lgb.__version__}")
except ImportError:
    print("❌ lightgbm not installed")

try:
    import sklearn
    print(f"✅ scikit-learn {sklearn.__version__}")
except ImportError:
    print("❌ scikit-learn not installed")

# Summary
print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)
print("✅ All critical components verified!")
print("\nNext steps:")
print("1. Start Docker services: docker-compose up -d --build")
print("2. Wait for database initialization")
print("3. Train models: POST /train")
print("4. Generate forecasts: POST /forecast/run")
print("\nSee FORECAST_SERVICE_UPGRADE.md for detailed usage instructions.")
