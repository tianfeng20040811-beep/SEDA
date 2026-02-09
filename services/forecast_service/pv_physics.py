"""
PV Physics Model - Baseline physical model for solar power prediction
Based on simplified PVWatts approach with temperature correction
"""
import math
from typing import Dict, List, Optional


def compute_p_physical(
    ghi: float,
    t_amb: float,
    wind: float,
    capacity_kw: float,
    params: Optional[Dict] = None
) -> float:
    """
    Compute physical PV power output based on irradiance and weather conditions
    
    Args:
        ghi: Global Horizontal Irradiance (W/m²)
        t_amb: Ambient temperature (°C)
        wind: Wind speed (m/s)
        capacity_kw: Rated PV capacity (kW)
        params: Calibration parameters dict with keys:
            - pr: Performance ratio (default 0.85)
            - soiling: Soiling loss factor (default 0.98)
            - NOCT: Nominal Operating Cell Temperature (°C, default 45)
            - gamma: Temperature coefficient (%/°C, default -0.004)
            - tilt_deg: Panel tilt angle (degrees, default 10)
            - azimuth_deg: Panel azimuth (degrees, 180=south, default 180)
    
    Returns:
        Predicted power output (kW)
    """
    if params is None:
        params = {}
    
    # Default calibration parameters
    pr = params.get("pr", 0.85)
    soiling = params.get("soiling", 0.98)
    NOCT = params.get("NOCT", 45.0)
    gamma = params.get("gamma", -0.004)  # %/°C
    
    # Standard Test Conditions
    STC_irradiance = 1000.0  # W/m²
    STC_temperature = 25.0   # °C
    
    # Cell temperature estimation (simplified Ross model)
    # T_cell = T_amb + (NOCT - 20) * (GHI / 800) * (1 - 0.0256 * wind)
    k_wind = max(0, 1 - 0.0256 * wind)  # Wind cooling factor
    t_cell = t_amb + (NOCT - 20) * (ghi / 800.0) * k_wind
    
    # Temperature loss factor
    delta_t = t_cell - STC_temperature
    f_temp = 1.0 + gamma * delta_t
    
    # Irradiance factor (linear relationship at first approximation)
    f_irr = ghi / STC_irradiance
    
    # Power output calculation
    p_dc = capacity_kw * f_irr * f_temp * pr * soiling
    
    # Ensure non-negative output
    p_dc = max(0.0, p_dc)
    
    # Inverter efficiency (simplified: 96% for power > 10% rated, else proportional)
    inverter_threshold = 0.1 * capacity_kw
    if p_dc < inverter_threshold:
        eta_inv = 0.92 * (p_dc / inverter_threshold)
    else:
        eta_inv = 0.96
    
    p_ac = p_dc * eta_inv
    
    return p_ac


def compute_poa_from_ghi(
    ghi: float,
    tilt_deg: float,
    azimuth_deg: float,
    lat: float,
    lon: float,
    timestamp: float
) -> float:
    """
    Convert GHI to Plane-of-Array (POA) irradiance
    Simplified transposition model (Perez would be better for production)
    
    Args:
        ghi: Global Horizontal Irradiance (W/m²)
        tilt_deg: Panel tilt angle (degrees)
        azimuth_deg: Panel azimuth (degrees, 180=south)
        lat: Latitude (degrees)
        lon: Longitude (degrees)
        timestamp: Unix timestamp (seconds)
    
    Returns:
        POA irradiance (W/m²)
    """
    # For MVP: use simplified cosine projection
    # In production, use pvlib for accurate sun position and transposition
    
    # Simple approximation: POA ≈ GHI * cos(tilt) for low tilt angles
    # This is a placeholder - real implementation would calculate sun position
    tilt_rad = math.radians(tilt_deg)
    
    # First-order correction: lower tilt = closer to GHI
    f_tilt = math.cos(tilt_rad) + 0.1 * math.sin(tilt_rad)
    
    poa = ghi * f_tilt
    return max(0.0, poa)


def batch_compute_physical(
    features: List[Dict],
    capacity_kw: float,
    params: Optional[Dict] = None
) -> List[float]:
    """
    Batch compute physical predictions for multiple timesteps
    
    Args:
        features: List of dicts with keys: ghi, t_amb, wind, timestamp
        capacity_kw: Rated PV capacity (kW)
        params: Calibration parameters
    
    Returns:
        List of predicted power values (kW)
    """
    predictions = []
    for f in features:
        p = compute_p_physical(
            ghi=f.get("ghi", 0.0),
            t_amb=f.get("t_amb", 25.0),
            wind=f.get("wind", 0.0),
            capacity_kw=capacity_kw,
            params=params
        )
        predictions.append(p)
    
    return predictions


# Mock weather generator for testing when telemetry unavailable
def generate_mock_weather(
    start_ts: float,
    end_ts: float,
    resolution_minutes: int = 15,
    lat: float = 5.4164
) -> List[Dict]:
    """
    Generate mock weather data for testing
    Sinusoidal GHI profile with daily pattern
    
    Args:
        start_ts: Start timestamp (Unix seconds)
        end_ts: End timestamp (Unix seconds)
        resolution_minutes: Time resolution (minutes)
        lat: Latitude for sunrise/sunset estimation
    
    Returns:
        List of dicts with: timestamp, ghi, t_amb, wind
    """
    import datetime
    
    data = []
    current = start_ts
    step = resolution_minutes * 60
    
    while current < end_ts:
        dt = datetime.datetime.fromtimestamp(current, tz=datetime.timezone.utc)
        hour = dt.hour + dt.minute / 60.0
        
        # Daylight hours: 6:00 - 19:00 (tropical location)
        if 6 <= hour <= 19:
            # Sinusoidal GHI profile peaking at noon
            hour_angle = (hour - 12.5) / 6.5  # Normalize to [-1, 1]
            ghi = 800 * math.cos(hour_angle * math.pi / 2) ** 2
        else:
            ghi = 0.0
        
        # Temperature: 25°C base + 5°C swing (peak at 14:00)
        t_amb = 25.0 + 5.0 * math.sin((hour - 6) / 12.0 * math.pi)
        
        # Wind: 1-3 m/s with some variation
        wind = 2.0 + 1.0 * math.sin(hour / 24.0 * 2 * math.pi)
        
        data.append({
            "timestamp": current,
            "ghi": ghi,
            "t_amb": t_amb,
            "wind": wind
        })
        
        current += step
    
    return data


if __name__ == "__main__":
    # Test the physical model
    test_cases = [
        {"ghi": 1000, "t_amb": 25, "wind": 2, "desc": "STC conditions"},
        {"ghi": 800, "t_amb": 35, "wind": 1, "desc": "High temp, light wind"},
        {"ghi": 500, "t_amb": 20, "wind": 5, "desc": "Partial cloud, windy"},
        {"ghi": 0, "t_amb": 15, "wind": 0, "desc": "Night time"},
    ]
    
    capacity = 500.0  # kW
    params = {"pr": 0.85, "soiling": 0.98}
    
    print("PV Physics Model Test")
    print("=" * 60)
    for tc in test_cases:
        p = compute_p_physical(tc["ghi"], tc["t_amb"], tc["wind"], capacity, params)
        print(f"{tc['desc']:30s} -> {p:6.2f} kW")
    
    # Test mock weather generation
    import time
    now = time.time()
    start = now - now % 86400  # Start of today
    end = start + 86400
    weather = generate_mock_weather(start, end, resolution_minutes=60)
    
    print("\nMock Weather (24h, hourly):")
    print("=" * 60)
    for w in weather[::4]:  # Show every 4 hours
        import datetime
        dt = datetime.datetime.fromtimestamp(w["timestamp"], tz=datetime.timezone.utc)
        print(f"{dt.strftime('%H:%M')} | GHI: {w['ghi']:6.1f} W/m² | T: {w['t_amb']:5.1f}°C | Wind: {w['wind']:.1f} m/s")
