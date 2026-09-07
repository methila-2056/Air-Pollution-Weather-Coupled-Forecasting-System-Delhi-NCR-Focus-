# data/ — Datasets & Sources

Raw CSVs, processed datasets, and split exports used by AeroCast-NCR.

## Layout

```
weather/    <station>_weather.csv        Open-Meteo per-station weather
pollution/  <station>_pollution.csv      CPCB per-station readings
fire/       firms_fires.csv              NASA FIRMS hotspots (North-west India)
processed/  featured_dataset.csv*        engineered feature matrix (124 cols)
            coupled_dataset.csv          coupling-feature variant
            quality_report.txt           dataset audit
```

## Sources

| Source | Content | Access |
|--------|---------|--------|
| CPCB / data.gov.in | PM2.5, PM10, O3, NO2, SO2, CO, AQI | API / CSV |
| Open-Meteo | Temperature, humidity, wind, pressure, PBL | Free API |
| NASA FIRMS | Fire hotspots, FRP, confidence | API (MAP_KEY) |

Downloaders: `scripts/download_{weather,pollution,fire,atmosphere}.py`.
Demo fire data (deterministic, no key required): `scripts/generate_fire_data.py`.

## The split export

`featured_dataset_part1.csv` + `featured_dataset_part2.csv` reproduce the
original 120 MB `featured_dataset.csv` byte-for-byte; see `SPLIT_NOTE.txt`.
Assemble with:

```bash
# unix
cat featured_dataset_part1.csv featured_dataset_part2.csv > featured_dataset.csv
# windows
copy /b featured_dataset_part1.csv + featured_dataset_part2.csv featured_dataset.csv
```

## Regeneration

```bash
python scripts/build_dataset.py
```