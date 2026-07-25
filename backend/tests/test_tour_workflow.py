"""
Backend tests for KORKMAN2 logistics app - Tour workflow testing
Focus on: on_way state, weight-only update, completion, and partial updates
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
    assert response.status_code == 200, f"Failed to create report: {response.text}"
    return response.json()

@pytest.fixture(scope="module")
def test_tour(api_client, test_report):
    """Create a test tour"""
    response = api_client.post(f"{BASE_URL}/api/tours", json={
        "fraction": "TEST_FRACTION",
        "facility": "TEST_FACILITY",
        "address": "TEST_ADDRESS",
        "plads": "Glostrup",
        "report_id": test_report["id"],
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    assert response.status_code == 200, f"Failed to create tour: {response.text}"
    return response.json()


class TestAPIHealth:
    """Basic API health checks"""
    
    def test_api_root(self, api_client):
        """API root endpoint is accessible"""
        response = api_client.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"API Health: OK - {data['message']}")

    def test_plads_endpoint(self, api_client):
        """Get plads list"""
        response = api_client.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200
        plads = response.json()
        assert isinstance(plads, list)
        plads_names = [p["name"] for p in plads]
        assert "Glostrup" in plads_names, "Glostrup plads should exist"
        print(f"Plads endpoint: OK - Found {len(plads)} plads including Glostrup")

    def test_tours_endpoint(self, api_client):
        """Get tours list"""
        response = api_client.get(f"{BASE_URL}/api/tours")
        assert response.status_code == 200
        tours = response.json()
        assert isinstance(tours, list)
        print(f"Tours endpoint: OK - Found {len(tours)} tours")


class TestTourOnWayWorkflow:
    """Test tour on_way (På vej) workflow - Step 1 of driver workflow"""
    
    def test_set_tour_on_way(self, api_client, test_tour):
        """Click truck icon - sets on_way=True, should NOT set completed"""
        tour_id = test_tour["id"]
        
        # Set on_way to True (simulating truck icon click)
        response = api_client.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "on_way": True,
            "time": "09:30"
        })
        assert response.status_code == 200
        updated = response.json()
        
        # Verify on_way is set
        assert updated["on_way"] == True, "on_way should be True after truck icon click"
        # Verify completed is NOT set
        assert updated["completed"] == False, "completed should remain False when setting on_way"
        # Verify time is saved
        assert updated["time"] == "09:30"
        
        print(f"Tour on_way set: OK - on_way={updated['on_way']}, completed={updated['completed']}")
    
    def test_toggle_on_way_off(self, api_client, test_tour):
        """Toggle on_way back to False"""
        tour_id = test_tour["id"]
        
        response = api_client.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "on_way": False
        })
        assert response.status_code == 200
        updated = response.json()
        
        assert updated["on_way"] == False
        print(f"Tour on_way toggled off: OK")


class TestWeightOnlyUpdate:
    """Test weight entry - Step 2 of driver workflow - CRITICAL: Weight should NOT auto-complete"""
    
    def test_weight_only_update_does_not_complete(self, api_client, test_tour):
        """CRITICAL: Entering weight should ONLY save weight, NOT mark as completed"""
        tour_id = test_tour["id"]
        
        # First set on_way to True (normal workflow)
        api_client.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "on_way": True,
            "time": "09:30"
        })
        
        # Now update ONLY the weight (simulating Enter key in weight field)
        response = api_client.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "weight": 500
        })
        assert response.status_code == 200
        updated = response.json()
        
        # CRITICAL ASSERTIONS - Weight update should NOT change completed or on_way status
        assert updated["weight"] == 500, "Weight should be saved"
        assert updated["on_way"] == True, "on_way should remain True after weight entry"
        assert updated["completed"] == False, "completed should remain False after weight entry - CRITICAL BUG if True"
        
        print(f"Weight-only update: OK - weight={updated['weight']}, on_way={updated['on_way']}, completed={updated['completed']}")
    
    def test_weight_update_preserves_state(self, api_client, test_tour):
        """Verify weight update preserves all other tour state"""
        tour_id = test_tour["id"]
        
        # Get current state
        get_response = api_client.get(f"{BASE_URL}/api/tours?plads=Glostrup")
        assert get_response.status_code == 200
        
        # Find our test tour
        tours = get_response.json()
        tour = next((t for t in tours if t["id"] == tour_id), None)
        assert tour is not None, "Test tour should exist"
        
        # Verify state was preserved
        assert tour["weight"] == 500
        assert tour["on_way"] == True
        assert tour["completed"] == False
        
        print(f"State preserved after weight update: OK")


class TestTourCompleteWorkflow:
    """Test tour completion (OK button) - Step 3 of driver workflow"""
    
    def test_complete_tour(self, api_client, test_tour):
        """Click OK/checkmark button - sets completed=True, on_way=False"""
        tour_id = test_tour["id"]
        
        # Complete the tour (simulating OK button click)
        response = api_client.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "completed": True,
            "on_way": False,
            "time": "10:00"
        })
        assert response.status_code == 200
        updated = response.json()
        
        # Verify completed state
        assert updated["completed"] == True, "completed should be True after OK button"
        assert updated["on_way"] == False, "on_way should be False after completion"
        # Verify weight is still saved from earlier
        assert updated["weight"] == 500, "Weight should still be 500"
        
        print(f"Tour completed: OK - completed={updated['completed']}, on_way={updated['on_way']}, weight={updated['weight']}")
    
    def test_uncomplete_tour(self, api_client, test_tour):
        """Toggle completed back to False (reset button)"""
        tour_id = test_tour["id"]
        
        response = api_client.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "completed": False
        })
        assert response.status_code == 200
        updated = response.json()
        
        assert updated["completed"] == False
        print(f"Tour uncompleted: OK")


class TestTourUpdateModel:
    """Test TourUpdate model - All fields should be Optional"""
    
    def test_partial_update_weight_only(self, api_client, test_tour):
        """Partial update with only weight field"""
        tour_id = test_tour["id"]
        
        response = api_client.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "weight": 750
        })
        assert response.status_code == 200
        updated = response.json()
        assert updated["weight"] == 750
        print(f"Partial update (weight only): OK")
    
    def test_partial_update_time_only(self, api_client, test_tour):
        """Partial update with only time field"""
        tour_id = test_tour["id"]
        
        response = api_client.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "time": "11:30"
        })
        assert response.status_code == 200
        updated = response.json()
        assert updated["time"] == "11:30"
        print(f"Partial update (time only): OK")
    
    def test_partial_update_on_way_only(self, api_client, test_tour):
        """Partial update with only on_way field"""
        tour_id = test_tour["id"]
        
        response = api_client.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "on_way": True
        })
        assert response.status_code == 200
        updated = response.json()
        assert updated["on_way"] == True
        # Ensure weight wasn't reset
        assert updated["weight"] == 750
        print(f"Partial update (on_way only): OK - weight preserved")
    
    def test_partial_update_completed_only(self, api_client, test_tour):
        """Partial update with only completed field"""
        tour_id = test_tour["id"]
        
        response = api_client.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "completed": True
        })
        assert response.status_code == 200
        updated = response.json()
        assert updated["completed"] == True
        # Ensure other fields weren't reset
        assert updated["weight"] == 750
        assert updated["time"] == "11:30"
        print(f"Partial update (completed only): OK - other fields preserved")


class TestPladsToursVisibility:
    """Test that tours assigned to a plads are visible when filtering by that plads"""
    
    def test_get_tours_by_plads(self, api_client):
        """Admin adds tours to Glostrup → Driver selects Glostrup → Sees those tours"""
        # Get tours filtered by Glostrup plads
        response = api_client.get(f"{BASE_URL}/api/tours?plads=Glostrup")
        assert response.status_code == 200
        tours = response.json()
        
        # All returned tours should have plads=Glostrup
        for tour in tours:
            assert tour["plads"] == "Glostrup", f"Tour {tour['id']} has wrong plads: {tour['plads']}"
        
        print(f"Tours by plads (Glostrup): OK - Found {len(tours)} tours")
    
    def test_tours_endpoint_without_filter(self, api_client):
        """All tours returned without filter"""
        response = api_client.get(f"{BASE_URL}/api/tours")
        assert response.status_code == 200
        all_tours = response.json()
        
        # Should return all tours
        assert isinstance(all_tours, list)
        print(f"All tours: OK - Found {len(all_tours)} total tours")


class TestCleanup:
    """Clean up test data"""
    
    def test_delete_test_tour(self, api_client, test_tour):
        """Delete the test tour"""
        tour_id = test_tour["id"]
        response = api_client.delete(f"{BASE_URL}/api/tours/{tour_id}")
        assert response.status_code == 200
        print(f"Test tour deleted: OK")
    
    def test_delete_test_report(self, api_client, test_report):
        """Delete the test report"""
        report_id = test_report["id"]
        response = api_client.delete(f"{BASE_URL}/api/reports/{report_id}")
        assert response.status_code == 200
        print(f"Test report deleted: OK")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
