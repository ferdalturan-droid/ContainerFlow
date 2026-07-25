"""
Backend tests for KORKMAN2 - Weight Auto-Complete Feature
Tests the new behavior where entering weight also sets completed=true, on_way=false, time
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session

@pytest.fixture(scope="module")
def test_report(api_client):
    """Create a test report for tours"""
    today = datetime.now().strftime("%Y-%m-%d")
    response = api_client.post(f"{BASE_URL}/api/reports", json={
        "report_date": today,
        "start_time": "07:00"
    })
    assert response.status_code == 200
    return response.json()

@pytest.fixture(scope="module")
def test_tour(api_client, test_report):
    """Create a test tour"""
    response = api_client.post(f"{BASE_URL}/api/tours", json={
        "fraction": "TEST_WEIGHT_COMPLETE",
        "facility": "TEST_FACILITY",
        "address": "TEST_ADDRESS",
        "plads": "Glostrup",
        "report_id": test_report["id"],
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    assert response.status_code == 200
    return response.json()


class TestWeightAutoComplete:
    """Test weight entry with auto-complete behavior - Frontend sends weight+completed+on_way+time"""
    
    def test_weight_with_complete_fields(self, api_client, test_tour):
        """
        Frontend handleWeightSubmit now sends:
        { weight: val, completed: true, on_way: false, time: currentTime }
        """
        tour_id = test_tour["id"]
        current_time = datetime.now().strftime("%H:%M")
        
        # Simulate frontend weight submit which sends all fields together
        response = api_client.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "weight": 500,
            "completed": True,
            "on_way": False,
            "time": current_time
        })
        assert response.status_code == 200
        updated = response.json()
        
        # Verify all fields are set correctly
        assert updated["weight"] == 500, "Weight should be 500"
        assert updated["completed"] == True, "completed should be True"
        assert updated["on_way"] == False, "on_way should be False"
        assert updated["time"] == current_time, f"time should be {current_time}"
        
        print(f"Weight auto-complete: OK - weight={updated['weight']}, completed={updated['completed']}, on_way={updated['on_way']}, time={updated['time']}")
    
    def test_verify_persisted_state(self, api_client, test_tour):
        """GET the tour to verify data was persisted"""
        tour_id = test_tour["id"]
        
        response = api_client.get(f"{BASE_URL}/api/tours?plads=Glostrup")
        assert response.status_code == 200
        
        tours = response.json()
        tour = next((t for t in tours if t["id"] == tour_id), None)
        assert tour is not None, "Test tour should exist"
        
        assert tour["weight"] == 500, "Weight should be persisted"
        assert tour["completed"] == True, "completed should be persisted"
        assert tour["on_way"] == False, "on_way should be persisted"
        assert tour["time"] != "", "time should be set"
        
        print(f"Persistence verified: OK")


class TestCleanup:
    """Clean up test data"""
    
    def test_delete_test_tour(self, api_client, test_tour):
        """Delete the test tour"""
        tour_id = test_tour["id"]
        response = api_client.delete(f"{BASE_URL}/api/tours/{tour_id}")
        assert response.status_code == 200
        print("Test tour deleted: OK")
    
    def test_delete_test_report(self, api_client, test_report):
        """Delete the test report"""
        report_id = test_report["id"]
        response = api_client.delete(f"{BASE_URL}/api/reports/{report_id}")
        assert response.status_code == 200
        print("Test report deleted: OK")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
