"""
Test new features for iteration 6:
1. PUT /api/tours/{id} accepts receipt_image field
2. GET /api/driver-archive returns list of driver names
3. GET /api/driver-archive/{driver_name} returns days array with sessions, tours, receipts
4. GET /api/receipts/{id}/image returns receipt image data
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestTourReceiptImage:
    """Test that PUT /api/tours/{id} accepts receipt_image field"""
    
    def test_create_tour_and_update_with_receipt_image(self):
        """Create a tour and update it with receipt_image"""
        # First create a tour
        tour_data = {
            "date": "2026-03-20",
            "container": f"TEST-{uuid.uuid4().hex[:6]}",
            "fraction": "Test Fraction",
            "facility": "Test Facility",
            "address": "Test Address 123",
            "driver_name": "TestDriver",
            "plads": "Glostrup"
        }
        
        create_res = requests.post(f"{BASE_URL}/api/tours", json=tour_data)
        assert create_res.status_code == 200, f"Failed to create tour: {create_res.text}"
        
        tour = create_res.json()
        tour_id = tour["id"]
        
        # Update tour with receipt_image
        test_receipt_image = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAB//2Q=="
        
        update_res = requests.put(f"{BASE_URL}/api/tours/{tour_id}", json={
            "receipt_image": test_receipt_image,
            "weight": 1500,
            "completed": True
        })
        assert update_res.status_code == 200, f"Failed to update tour with receipt_image: {update_res.text}"
        
        updated_tour = update_res.json()
        assert updated_tour["receipt_image"] == test_receipt_image, "receipt_image not saved correctly"
        assert updated_tour["weight"] == 1500, "weight not saved correctly"
        assert updated_tour["completed"] == True, "completed not saved correctly"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
        print("PASSED: PUT /api/tours/{id} accepts receipt_image field")


class TestDriverArchive:
    """Test driver archive endpoints"""
    
    def test_get_driver_archive_list(self):
        """GET /api/driver-archive returns list of driver names"""
        res = requests.get(f"{BASE_URL}/api/driver-archive")
        assert res.status_code == 200, f"Failed to get driver archive: {res.text}"
        
        data = res.json()
        assert "drivers" in data, "Response should have 'drivers' key"
        assert isinstance(data["drivers"], list), "drivers should be a list"
        
        print(f"PASSED: GET /api/driver-archive returns {len(data['drivers'])} drivers: {data['drivers'][:5]}...")
    
    def test_get_driver_archive_detail(self):
        """GET /api/driver-archive/{driver_name} returns days array"""
        # First get list of drivers
        list_res = requests.get(f"{BASE_URL}/api/driver-archive")
        drivers = list_res.json().get("drivers", [])
        
        if not drivers:
            # Create test data if no drivers exist
            # Create a driver session
            session_data = {
                "driver_name": "TestArchiveDriver",
                "vehicle_reg": "TEST123",
                "current_plads": "Glostrup",
                "start_time": "08:00",
                "report_date": "2026-03-20"
            }
            requests.post(f"{BASE_URL}/api/driver-session", json=session_data)
            test_driver = "TestArchiveDriver"
        else:
            test_driver = drivers[0]
        
        # Get driver archive detail
        res = requests.get(f"{BASE_URL}/api/driver-archive/{test_driver}")
        assert res.status_code == 200, f"Failed to get driver archive detail: {res.text}"
        
        data = res.json()
        assert "driver_name" in data, "Response should have 'driver_name' key"
        assert "days" in data, "Response should have 'days' key"
        assert isinstance(data["days"], list), "days should be a list"
        
        # Check structure of days if any exist
        if data["days"]:
            day = data["days"][0]
            assert "date" in day, "Day should have 'date' key"
            assert "sessions" in day, "Day should have 'sessions' key"
            assert "tours" in day, "Day should have 'tours' key"
            assert "receipts" in day, "Day should have 'receipts' key"
            print(f"PASSED: GET /api/driver-archive/{test_driver} returns {len(data['days'])} days with proper structure")
        else:
            print(f"PASSED: GET /api/driver-archive/{test_driver} returns empty days array (no data for driver)")


class TestReceiptImage:
    """Test receipt image endpoint"""
    
    def test_get_receipt_image(self):
        """GET /api/receipts/{id}/image returns receipt image data"""
        # First create a receipt with image
        test_image = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAB//2Q=="
        
        receipt_data = {
            "driver_name": "TestReceiptDriver",
            "plads": "Glostrup",
            "amount": 100.0,
            "description": "Test Receipt",
            "image_data": test_image
        }
        
        create_res = requests.post(f"{BASE_URL}/api/receipts", json=receipt_data)
        assert create_res.status_code == 200, f"Failed to create receipt: {create_res.text}"
        
        receipt = create_res.json()
        receipt_id = receipt["id"]
        
        # Get receipt image
        image_res = requests.get(f"{BASE_URL}/api/receipts/{receipt_id}/image")
        assert image_res.status_code == 200, f"Failed to get receipt image: {image_res.text}"
        
        image_data = image_res.json()
        assert "image_data" in image_data, "Response should have 'image_data' key"
        assert image_data["image_data"] == test_image, "Image data should match"
        assert "description" in image_data, "Response should have 'description' key"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/receipts/{receipt_id}")
        print("PASSED: GET /api/receipts/{id}/image returns receipt image data")
    
    def test_get_receipt_image_not_found(self):
        """GET /api/receipts/{id}/image returns 404 for non-existent receipt"""
        res = requests.get(f"{BASE_URL}/api/receipts/nonexistent-id-12345/image")
        assert res.status_code == 404, f"Expected 404, got {res.status_code}"
        print("PASSED: GET /api/receipts/{id}/image returns 404 for non-existent receipt")


class TestExistingEndpoints:
    """Verify existing endpoints still work"""
    
    def test_api_root(self):
        """GET /api/ returns API info"""
        res = requests.get(f"{BASE_URL}/api/")
        assert res.status_code == 200
        print("PASSED: GET /api/ returns 200")
    
    def test_get_drivers(self):
        """GET /api/drivers returns list"""
        res = requests.get(f"{BASE_URL}/api/drivers")
        assert res.status_code == 200
        assert isinstance(res.json(), list)
        print(f"PASSED: GET /api/drivers returns {len(res.json())} drivers")
    
    def test_get_tours(self):
        """GET /api/tours returns list"""
        res = requests.get(f"{BASE_URL}/api/tours")
        assert res.status_code == 200
        assert isinstance(res.json(), list)
        print(f"PASSED: GET /api/tours returns {len(res.json())} tours")
    
    def test_admin_login(self):
        """POST /api/admin/login with correct password"""
        res = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": "admin",
            "password": "1234"
        })
        assert res.status_code == 200
        assert res.json().get("success") == True
        print("PASSED: POST /api/admin/login with password 1234 works")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
