"""
Test Pro Scanner Feature - Backend API Tests
Tests for the ContainerFlow Pro Scanner receipt camera feature
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8080')

class TestProScannerFeature:
    """Tests for Pro Scanner related functionality"""
    
    def test_health_check(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("Health check passed")
    
    def test_get_tours_for_today(self):
        """Test getting tours for today"""
        response = requests.get(f"{BASE_URL}/api/tours?date=2026-04-05")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} tours for today")
        
        # Verify tour structure has receipt_image field
        if len(data) > 0:
            tour = data[0]
            assert "receipt_image" in tour, "Tour should have receipt_image field"
            print("Tour has receipt_image field")
    
    def test_update_tour_with_receipt_image(self):
        """Test updating a tour with receipt image"""
        # First get a tour
        response = requests.get(f"{BASE_URL}/api/tours?date=2026-04-05")
        assert response.status_code == 200
        tours = response.json()
        
        if len(tours) == 0:
            pytest.skip("No tours available for testing")
        
        tour_id = tours[0]["id"]
        
        # Update tour with a mock receipt image (base64 data URL)
        mock_receipt_image = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBEQCEAwEPwAB//9k="
        
        update_data = {
            "receipt_image": mock_receipt_image
        }
        
        update_response = requests.put(f"{BASE_URL}/api/tours/{tour_id}", json=update_data)
        assert update_response.status_code == 200
        print(f"Successfully updated tour {tour_id} with receipt image")
        
        # Verify the update
        verify_response = requests.get(f"{BASE_URL}/api/tours?date=2026-04-05")
        assert verify_response.status_code == 200
        updated_tours = verify_response.json()
        
        updated_tour = next((t for t in updated_tours if t["id"] == tour_id), None)
        assert updated_tour is not None
        assert updated_tour.get("receipt_image") == mock_receipt_image
        print("Receipt image verified in tour data")
        
        # Clean up - remove receipt image
        cleanup_response = requests.put(f"{BASE_URL}/api/tours/{tour_id}", json={"receipt_image": ""})
        assert cleanup_response.status_code == 200
        print("Cleaned up test data")
    
    def test_complete_tour_with_weight_and_receipt(self):
        """Test completing a tour with weight and receipt image"""
        # Get a tour
        response = requests.get(f"{BASE_URL}/api/tours?date=2026-04-05")
        assert response.status_code == 200
        tours = response.json()
        
        if len(tours) == 0:
            pytest.skip("No tours available for testing")
        
        # Find a non-completed tour
        non_completed_tour = next((t for t in tours if not t.get("completed")), None)
        if non_completed_tour is None:
            pytest.skip("No non-completed tours available")
        
        tour_id = non_completed_tour["id"]
        
        # Complete the tour with weight and receipt
        complete_data = {
            "weight": 500,
            "completed": True,
            "on_way": False,
            "time": "14:30",
            "claimed_by": "TestDriver",
            "receipt_image": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBEQCEAwEPwAB//9k="
        }
        
        update_response = requests.put(f"{BASE_URL}/api/tours/{tour_id}", json=complete_data)
        assert update_response.status_code == 200
        print(f"Successfully completed tour {tour_id} with weight and receipt")
        
        # Verify completion
        verify_response = requests.get(f"{BASE_URL}/api/tours?date=2026-04-05")
        completed_tour = next((t for t in verify_response.json() if t["id"] == tour_id), None)
        
        assert completed_tour is not None
        assert completed_tour.get("completed") == True
        assert completed_tour.get("weight") == 500
        assert completed_tour.get("claimed_by") == "TestDriver"
        print("Tour completion verified")
        
        # Reset tour for other tests
        reset_data = {
            "weight": None,
            "completed": False,
            "on_way": False,
            "time": "",
            "claimed_by": "",
            "receipt_image": ""
        }
        requests.put(f"{BASE_URL}/api/tours/{tour_id}", json=reset_data)
        print("Reset tour for other tests")
    
    def test_get_plads(self):
        """Test getting plads list"""
        response = requests.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        print(f"Found {len(data)} plads")
    
    def test_get_drivers(self):
        """Test getting drivers list"""
        response = requests.get(f"{BASE_URL}/api/drivers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} drivers")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
