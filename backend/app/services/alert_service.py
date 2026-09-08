ALERT_LEVEL_RANK = {"WATCH": 1, "ADVISORY": 2, "WARNING": 3, "SEVERE": 4}

def generate_alerts(forecast_data: dict, weather_data: dict, fire_data: dict) -> list[dict]:
    alerts = []
    forecast_data = forecast_data or {}
    weather_data = weather_data or {}
    fire_data = fire_data or {}

    aqi = forecast_data.get("aqi_pred", 0) or 0
    dominant = forecast_data.get("dominant_pollutant", "")
    trend = forecast_data.get("trend", "stable")

    if aqi >= 401:
        alerts.append({
            "alert_level": "SEVERE",
            "title": "Severe Pollution Alert",
            "description": f"Severe AQI conditions expected. Forecast AQI: {aqi}.",
            "factors": f"Severe concentrations; dominant pollutant: {dominant or 'n/a'}",
            "recommendation": "Avoid outdoor activities. Sensitive groups should remain indoors with air purifiers.",
            "forecast_horizon_hours": forecast_data.get("horizon_hours"),
        })
    elif aqi >= 301:
        alerts.append({
            "alert_level": "WARNING",
            "title": "Very Poor AQI Warning",
            "description": f"Very Poor AQI conditions expected. Forecast AQI: {aqi}.",
            "factors": f"Elevated pollution levels; dominant pollutant: {dominant or 'n/a'}",
            "recommendation": "Limit prolonged outdoor exertion. Use N95 masks outdoors.",
            "forecast_horizon_hours": forecast_data.get("horizon_hours"),
        })
    elif aqi >= 201:
        alerts.append({
            "alert_level": "ADVISORY",
            "title": "Poor AQI Advisory",
            "description": f"Poor AQI conditions expected. Forecast AQI: {aqi}.",
            "factors": f"Elevated pollution driven by {dominant or 'multiple pollutants'}",
            "recommendation": "Consider reducing strenuous outdoor activity.",
            "forecast_horizon_hours": forecast_data.get("horizon_hours"),
        })

    if trend == "rising":
        alerts.append({
            "alert_level": "WATCH",
            "title": "Rising Pollution Trend",
            "description": "Pollution levels are forecast to increase across the forecast window.",
            "factors": "Concentrations trending upward hour over hour",
            "recommendation": "Monitor future forecasts; pollution controls may be needed if the trend persists.",
        })
    elif trend == "falling":
        alerts.append({
            "alert_level": "WATCH",
            "title": "Improving Air Quality",
            "description": "Pollution levels are forecast to decline over the coming hours.",
            "factors": "Concentrations trending downward",
            "recommendation": "Conditions are expected to improve; verify before resuming outdoor activity.",
        })

    if dominant == "pm25" and aqi >= 201:
        alerts.append({
            "alert_level": "WATCH",
            "title": "PM2.5 Dominated Pollution",
            "description": "PM2.5 is the dominant pollutant and is in the Poor-to-Severe range.",
            "factors": "Fine particulate matter primary driver",
            "recommendation": "Avoid intense physical activity; fine particles penetrate indoors.",
            "forecast_horizon_hours": forecast_data.get("horizon_hours"),
        })

    wind = weather_data.get("wind_speed")
    if wind is not None and wind < 2:
        alerts.append({
            "alert_level": "WATCH",
            "title": "Low Wind Speed Watch",
            "description": f"Wind speed is {wind:.1f} m/s, limiting pollutant dispersion.",
            "factors": "Low wind speed",
            "recommendation": "Pollution may accumulate due to poor ventilation.",
            "forecast_horizon_hours": forecast_data.get("horizon_hours"),
        })
    if wind is not None and wind > 15:
        alerts.append({
            "alert_level": "WATCH",
            "title": "High Wind / Dust Watch",
            "description": f"Wind speed of {wind:.1f} m/s may resuspend dust and aggravate PM10.",
            "factors": "Strong winds",
            "recommendation": "Expect elevated PM10; cover windows near construction sites.",
        })

    pbl = weather_data.get("pbl_height")
    if pbl is not None and pbl < 150:
        alerts.append({
            "alert_level": "WARNING",
            "title": "Strong Inversion Trapping",
            "description": f"A strong inversion with PBL at {pbl:.0f}m is trapping pollutants.",
            "factors": "Strong inversion layer",
            "recommendation": "Expect rapid AQI deterioration overnight into morning.",
            "forecast_horizon_hours": forecast_data.get("horizon_hours"),
        })
    elif pbl is not None and pbl < 300:
        alerts.append({
            "alert_level": "WATCH",
            "title": "Weak Inversion / Low PBL",
            "description": f"Planetary boundary layer at {pbl:.0f}m limits vertical mixing.",
            "factors": "Compressed boundary layer",
            "recommendation": "Pollution trapping likely near the surface.",
            "forecast_horizon_hours": forecast_data.get("horizon_hours"),
        })

    humidity = weather_data.get("humidity")
    if humidity is not None and humidity > 80:
        alerts.append({
            "alert_level": "ADVISORY",
            "title": "High Humidity / Secondary Aerosol",
            "description": f"Relative humidity of {humidity:.0f}% promotes secondary aerosol formation.",
            "factors": "High relative humidity",
            "recommendation": "Secondary particles may push AQI higher than direct-emission forecasts.",
        })

    precipitation = weather_data.get("precipitation")
    if precipitation is not None and precipitation <= 0.5 and aqi >= 201:
        alerts.append({
            "alert_level": "WATCH",
            "title": "No Rain Scavenging",
            "description": "Absence of precipitation means no washout of accumulated pollutants.",
            "factors": "Dry conditions",
            "recommendation": "Pollution is unlikely to be flushed out; expect persistence.",
        })

    fire_count = fire_data.get("fire_count", 0) or 0
    nearest = fire_data.get("distance_nearest_fire")
    if fire_count > 50 and nearest is not None and nearest < 300:
        alerts.append({
            "alert_level": "WARNING",
            "title": "Approaching Smoke Plume",
            "description": f"{fire_count} regional fire hotspots with nearest fire {nearest:.0f}km from Delhi NCR.",
            "factors": "Stubble burning plume advection",
            "recommendation": "Fire smoke may compound local pollution; prepare for elevated AQI.",
            "forecast_horizon_hours": forecast_data.get("horizon_hours"),
        })
    elif fire_count > 20:
        alerts.append({
            "alert_level": "WATCH",
            "title": "Elevated Regional Burning",
            "description": f"{fire_count} fire hotspots detected across the northern plains.",
            "factors": "Regional agricultural burning",
            "recommendation": "Monitor winds; smoke may drift into the NCR.",
        })

    alerts.sort(key=lambda a: ALERT_LEVEL_RANK.get(a["alert_level"], 0), reverse=True)
    return alerts
