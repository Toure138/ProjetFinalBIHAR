import openmeteo_requests

import pandas as pd
import requests_cache
from retry_requests import retry

# Setup the Open-Meteo API client with cache and retry on error
cache_session = requests_cache.CachedSession('.cache', expire_after = -1)
retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
openmeteo = openmeteo_requests.Client(session = retry_session)

# Make sure all required weather variables are listed here
# The order of variables in hourly or daily is important to assign them correctly below
url = "https://archive-api.open-meteo.com/v1/archive"
params = {
	"latitude": 6.816667,
	"longitude": -5.283333,
	"start_date": "2023-01-01",
	"end_date": "2025-01-31",
	"hourly": "temperature_2m",
	"timezone": "GMT",
}
responses = openmeteo.weather_api(url, params=params)

# Process first location. Add a for-loop for multiple locations or weather models
response = responses[0]
print(f"Coordinates: {response.Latitude()}°N {response.Longitude()}°E")
print(f"Elevation: {response.Elevation()} m asl")
print(f"Timezone: {response.Timezone()}{response.TimezoneAbbreviation()}")
print(f"Timezone difference to GMT+0: {response.UtcOffsetSeconds()}s")

# Process hourly data. The order of variables needs to be the same as requested.
hourly = response.Hourly()
hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()

hourly_data = {"date": pd.date_range(
	start = pd.to_datetime(hourly.Time(), unit = "s", utc = True),
	end =  pd.to_datetime(hourly.TimeEnd(), unit = "s", utc = True),
	freq = pd.Timedelta(seconds = hourly.Interval()),
	inclusive = "left"
)}

hourly_data["temperature_2m"] = hourly_temperature_2m

hourly_dataframe = pd.DataFrame(data = hourly_data)
print("\nHourly data\n", hourly_dataframe)

# Export data to CSV and JSON
import os
from datetime import datetime

# Create data directory if it doesn't exist
os.makedirs('data', exist_ok=True)

# Generate filename with timestamp
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
csv_filename = f"data/weather_data_{timestamp}.csv"
json_filename = f"data/weather_data_{timestamp}.json"

# Export to CSV
hourly_dataframe.to_csv(csv_filename, index=False)
print(f"\nData exported to CSV: {csv_filename}")

# Export to JSON
hourly_dataframe.to_json(json_filename, orient='records', date_format='iso')
print(f"Data exported to JSON: {json_filename}")

print(f"\nExport summary:")
print(f"- Total records: {len(hourly_dataframe)}")
print(f"- Date range: {hourly_dataframe['date'].min()} to {hourly_dataframe['date'].max()}")
print(f"- Temperature range: {hourly_dataframe['temperature_2m'].min():.1f}°C to {hourly_dataframe['temperature_2m'].max():.1f}°C")
