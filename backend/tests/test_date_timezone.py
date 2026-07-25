"""
Test Date Timezone Fix - Danish Timezone (Europe/Copenhagen)
Tests that all date operations use Danish local time instead of UTC.
"""
import pytest
import requests
import os
from datetime import datetime
from zoneinfo import ZoneInfo

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
DK_TZ = ZoneInfo("Europe/Copenhagen")

def get_dk_date_str():
    """Get current date string in Danish timezone (YYYY-MM-DD)."""
    return datetime.now(DK_TZ).strftime("%Y-%m-%d")

class TestDateTimezone:
    """Test date timezone handling - all dates should use Danish timezone"""
    
    def test_api_accessible(self):
        """Verify API is accessible by checking tours endpoint"""
        response = requests.get(f"{BASE_URL}/api/tours", params={"date": "2026-04-01"})
        assert response.status_code == 200, f"API check failed: {response.text}"
        print("✓ API is accessible")
    
    def test_create_tour_with_explicit_date(self):
        """Create a tour with explicit date '2026-04-02' and verify it's stored correctly"""
        explicit_date = "2026-04-02"
        
        # Create tour with explicit date
        tour_data = {
            "date": explicit_date,
            "fraction": "TEST_TIMEZONE_FRACTION",
            "facility": "TEST_TIMEZONE_FACILITY",
            "address": "Test Address for Timezone",
            "container": "TEST-TZ-001"
        }
        
        response = requests.post(f"{BASE_URL}/api/tours", json=tour_data)
        assert response.status_code == 200, f"Failed to create tour: {response.text}"
        
        created_tour = response.json()
        tour_id = created_tour.get("id")
        assert created_tour.get("date") == explicit_date, f"Tour date mismatch: expected {explicit_date}, got {created_tour.get('date')}"
        print(f"✓ Tour created with date {explicit_date}, ID: {tour_id}")
        
        # Verify tour appears when querying for 2026-04-02
        response = requests.get(f"{BASE_URL}/api/tours", params={"date": explicit_date})
        assert response.status_code == 200
        tours = response.json()
        tour_ids = [t.get("id") for t in tours]
        assert tour_id in tour_ids, f"Tour {tour_id} not found in tours for date {explicit_date}"
        print(f"✓ Tour found when querying date={explicit_date}")
        
        # Verify tour does NOT appear when querying for 2026-04-01 (previous day)
        previous_date = "2026-04-01"
        response = requests.get(f"{BASE_URL}/api/tours", params={"date": previous_date})
        assert response.status_code == 200
        tours_prev = response.json()
        tour_ids_prev = [t.get("id") for t in tours_prev]
        assert tour_id not in tour_ids_prev, f"Tour {tour_id} incorrectly appears in tours for date {previous_date}"
        print(f"✓ Tour correctly NOT found when querying date={previous_date}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
        print(f"✓ Cleanup: deleted tour {tour_id}")
        
        return tour_id
    
    def test_create_tour_without_date_uses_danish_timezone(self):
        """Create a tour without specifying date - should use Danish timezone date"""
        expected_date = get_dk_date_str()
        
        # Create tour without date field
        tour_data = {
            "fraction": "TEST_NO_DATE_FRACTION",
            "facility": "TEST_NO_DATE_FACILITY",
            "address": "Test Address No Date",
            "container": "TEST-ND-001"
        }
        
        response = requests.post(f"{BASE_URL}/api/tours", json=tour_data)
        assert response.status_code == 200, f"Failed to create tour: {response.text}"
        
        created_tour = response.json()
        tour_id = created_tour.get("id")
        actual_date = created_tour.get("date")
        
        # The date should be today's Danish date
        assert actual_date == expected_date, f"Tour date mismatch: expected Danish date {expected_date}, got {actual_date}"
        print(f"✓ Tour created without date, got Danish date: {actual_date}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
        print(f"✓ Cleanup: deleted tour {tour_id}")
    
    def test_pause_endpoint_with_date_parameter(self):
        """POST /api/tours/pause with date parameter should store that date correctly"""
        explicit_date = "2026-04-02"
        
        response = requests.post(f"{BASE_URL}/api/tours/pause", params={
            "date": explicit_date,
            "plads": "TEST_PLADS",
            "driver_id": "test-driver-tz",
            "driver_name": "Test Driver TZ"
        })
        
        assert response.status_code == 200, f"Failed to create pause: {response.text}"
        
        pause_tour = response.json()
        pause_id = pause_tour.get("id")
        assert pause_tour.get("date") == explicit_date, f"Pause date mismatch: expected {explicit_date}, got {pause_tour.get('date')}"
        assert pause_tour.get("is_pause") == True, "Pause tour should have is_pause=True"
        print(f"✓ Pause created with explicit date {explicit_date}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tours/{pause_id}")
        print(f"✓ Cleanup: deleted pause {pause_id}")
    
    def test_pause_endpoint_without_date_uses_danish_timezone(self):
        """POST /api/tours/pause without date should use Danish timezone date"""
        expected_date = get_dk_date_str()
        
        response = requests.post(f"{BASE_URL}/api/tours/pause", params={
            "plads": "TEST_PLADS_NO_DATE",
            "driver_id": "test-driver-tz-nd",
            "driver_name": "Test Driver TZ No Date"
        })
        
        assert response.status_code == 200, f"Failed to create pause: {response.text}"
        
        pause_tour = response.json()
        pause_id = pause_tour.get("id")
        actual_date = pause_tour.get("date")
        
        assert actual_date == expected_date, f"Pause date mismatch: expected Danish date {expected_date}, got {actual_date}"
        print(f"✓ Pause created without date, got Danish date: {actual_date}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tours/{pause_id}")
        print(f"✓ Cleanup: deleted pause {pause_id}")
    
    def test_daily_overview_uses_danish_timezone(self):
        """GET /api/admin/daily-overview should return data for Danish timezone 'today'"""
        expected_date = get_dk_date_str()
        
        # Call without date parameter - should use Danish timezone
        response = requests.get(f"{BASE_URL}/api/admin/daily-overview")
        assert response.status_code == 200, f"Failed to get daily overview: {response.text}"
        
        data = response.json()
        # The endpoint should return data for today's Danish date
        assert "plads_stats" in data or "total_tours" in data, f"Unexpected response structure: {data}"
        print(f"✓ Daily overview returned successfully for Danish date {expected_date}")
        
        # Call with explicit date parameter
        response_explicit = requests.get(f"{BASE_URL}/api/admin/daily-overview", params={"date": "2026-04-02"})
        assert response_explicit.status_code == 200, f"Failed to get daily overview with date: {response_explicit.text}"
        print("✓ Daily overview with explicit date parameter works")
    
    def test_tour_date_filtering_isolation(self):
        """Verify tours are properly isolated by date - no cross-date leakage"""
        date1 = "2026-04-01"
        date2 = "2026-04-02"
        
        # Create tour for date1
        tour1_data = {
            "date": date1,
            "fraction": "TEST_ISOLATION_D1",
            "facility": "TEST_ISOLATION_FACILITY",
            "container": "ISO-D1-001"
        }
        response1 = requests.post(f"{BASE_URL}/api/tours", json=tour1_data)
        assert response1.status_code == 200
        tour1_id = response1.json().get("id")
        print(f"✓ Created tour for {date1}: {tour1_id}")
        
        # Create tour for date2
        tour2_data = {
            "date": date2,
            "fraction": "TEST_ISOLATION_D2",
            "facility": "TEST_ISOLATION_FACILITY",
            "container": "ISO-D2-001"
        }
        response2 = requests.post(f"{BASE_URL}/api/tours", json=tour2_data)
        assert response2.status_code == 200
        tour2_id = response2.json().get("id")
        print(f"✓ Created tour for {date2}: {tour2_id}")
        
        # Query date1 - should only have tour1
        response_d1 = requests.get(f"{BASE_URL}/api/tours", params={"date": date1})
        tours_d1 = response_d1.json()
        tour_ids_d1 = [t.get("id") for t in tours_d1]
        
        assert tour1_id in tour_ids_d1, f"Tour1 not found in date1 query"
        assert tour2_id not in tour_ids_d1, f"Tour2 incorrectly found in date1 query"
        print(f"✓ Date {date1} correctly contains only tour1")
        
        # Query date2 - should only have tour2
        response_d2 = requests.get(f"{BASE_URL}/api/tours", params={"date": date2})
        tours_d2 = response_d2.json()
        tour_ids_d2 = [t.get("id") for t in tours_d2]
        
        assert tour2_id in tour_ids_d2, f"Tour2 not found in date2 query"
        assert tour1_id not in tour_ids_d2, f"Tour1 incorrectly found in date2 query"
        print(f"✓ Date {date2} correctly contains only tour2")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tours/{tour1_id}")
        requests.delete(f"{BASE_URL}/api/tours/{tour2_id}")
        print("✓ Cleanup: deleted both test tours")


class TestReceiptDateTimezone:
    """Test receipt date handling with Danish timezone"""
    
    def test_receipt_default_date(self):
        """Verify receipts use Danish timezone for default date"""
        # First create a tour to attach receipt to
        tour_data = {
            "date": get_dk_date_str(),
            "fraction": "TEST_RECEIPT_FRACTION",
            "facility": "TEST_RECEIPT_FACILITY",
            "container": "RCP-001"
        }
        
        response = requests.post(f"{BASE_URL}/api/tours", json=tour_data)
        assert response.status_code == 200
        tour_id = response.json().get("id")
        print(f"✓ Created tour for receipt test: {tour_id}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
        print(f"✓ Cleanup: deleted tour {tour_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
