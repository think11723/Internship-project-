"""Test company details endpoint"""
import requests

# Test with a known company from seed data
company_name = "Anthropic"
url = f"http://localhost:8000/api/companies/{company_name}"

try:
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
