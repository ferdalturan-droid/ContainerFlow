"""
Test Push Notification and Receipt APIs for KORKMAN2 app
Tests the new features: Push notifications (VAPID, subscribe, unsubscribe, send) and Receipt CRUD
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://role-analysis-flow.preview.emergentagent.com').rstrip('/')

class TestPushNotificationAPIs:
    """Push notification endpoint tests"""
    
    def test_vapid_public_key_endpoint(self):
        """GET /api/push/vapid-public-key returns a valid VAPID public key"""
        response = requests.get(f"{BASE_URL}/api/push/vapid-public-key")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "public_key" in data, "Response should contain 'public_key'"
        assert isinstance(data["public_key"], str), "public_key should be a string"
        assert len(data["public_key"]) > 0, "public_key should not be empty"
        print(f"VAPID public key retrieved: {data['public_key'][:30]}...")
    
    def test_push_subscribe_endpoint(self):
        """POST /api/push/subscribe accepts driver_name and subscription object"""
        test_driver = f"TEST_Driver_{uuid.uuid4().hex[:8]}"
        subscription_data = {
            "driver_name": test_driver,
            "subscription": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-123",
                "keys": {
                    "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
                    "auth": "tBHItJI5svbpez7KI4CCXg"
                }
            }
        }
        
        response = requests.post(f"{BASE_URL}/api/push/subscribe", json=subscription_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "subscribed" in data or "message" in data, "Response should contain 'subscribed' or 'message'"
        if "subscribed" in data:
            assert data["subscribed"] == True, "subscribed should be True"
        print(f"Push subscription created for driver: {test_driver}")
        
        # Cleanup - unsubscribe
        requests.delete(f"{BASE_URL}/api/push/unsubscribe?driver_name={test_driver}")
    
    def test_push_unsubscribe_endpoint(self):
        """DELETE /api/push/unsubscribe?driver_name=TestDriver works"""
        test_driver = f"TEST_Unsub_{uuid.uuid4().hex[:8]}"
        
        # First subscribe
        subscription_data = {
            "driver_name": test_driver,
            "subscription": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-456",
                "keys": {
                    "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
                    "auth": "tBHItJI5svbpez7KI4CCXg"
                }
            }
        }
        requests.post(f"{BASE_URL}/api/push/subscribe", json=subscription_data)
        
        # Now unsubscribe
        response = requests.delete(f"{BASE_URL}/api/push/unsubscribe?driver_name={test_driver}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "unsubscribed" in data or "message" in data, "Response should contain 'unsubscribed' or 'message'"
        if "unsubscribed" in data:
            assert data["unsubscribed"] == True, "unsubscribed should be True"
        print(f"Push unsubscribe successful for driver: {test_driver}")
    
    def test_push_send_endpoint(self):
        """POST /api/push/send accepts title, body, driver_names and returns sent/failed counts"""
        send_data = {
            "title": "Test Notification",
            "body": "This is a test push notification",
            "driver_names": ["NonExistentDriver"],  # No actual subscriptions
            "url": "/"
        }
        
        response = requests.post(f"{BASE_URL}/api/push/send", json=send_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "sent" in data, "Response should contain 'sent' count"
        assert "failed" in data, "Response should contain 'failed' count"
        assert isinstance(data["sent"], int), "'sent' should be an integer"
        assert isinstance(data["failed"], int), "'failed' should be an integer"
        print(f"Push send result: sent={data['sent']}, failed={data['failed']}")
    
    def test_push_send_to_all_drivers(self):
        """POST /api/push/send with empty driver_names sends to all"""
        send_data = {
            "title": "Broadcast Test",
            "body": "This is a broadcast test",
            "driver_names": [],  # Empty = all drivers
            "url": "/"
        }
        
        response = requests.post(f"{BASE_URL}/api/push/send", json=send_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "sent" in data and "failed" in data
        print(f"Broadcast push result: sent={data['sent']}, failed={data['failed']}")


class TestReceiptCRUD:
    """Receipt CRUD endpoint tests"""
    
    @pytest.fixture
    def test_receipt_data(self):
        """Generate test receipt data"""
        return {
            "driver_name": f"TEST_ReceiptDriver_{uuid.uuid4().hex[:8]}",
            "plads": "Glostrup",
            "tour_id": "",
            "amount": 125.50,
            "description": "Test receipt for fuel",
            "image_data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        }
    
    def test_create_receipt(self, test_receipt_data):
        """POST /api/receipts creates a new receipt"""
        response = requests.post(f"{BASE_URL}/api/receipts", json=test_receipt_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "id" in data, "Response should contain 'id'"
        assert data["driver_name"] == test_receipt_data["driver_name"]
        assert data["amount"] == test_receipt_data["amount"]
        assert data["description"] == test_receipt_data["description"]
        assert "created_at" in data
        print(f"Receipt created with ID: {data['id']}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/receipts/{data['id']}")
        return data["id"]
    
    def test_get_receipts(self, test_receipt_data):
        """GET /api/receipts returns list of receipts"""
        # Create a receipt first
        create_res = requests.post(f"{BASE_URL}/api/receipts", json=test_receipt_data)
        created_id = create_res.json()["id"]
        
        # Get all receipts
        response = requests.get(f"{BASE_URL}/api/receipts")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Retrieved {len(data)} receipts")
        
        # Verify our created receipt is in the list
        receipt_ids = [r["id"] for r in data]
        assert created_id in receipt_ids, "Created receipt should be in the list"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/receipts/{created_id}")
    
    def test_get_receipts_by_driver(self, test_receipt_data):
        """GET /api/receipts?driver_name=X filters by driver"""
        # Create a receipt
        create_res = requests.post(f"{BASE_URL}/api/receipts", json=test_receipt_data)
        created_id = create_res.json()["id"]
        
        # Get receipts filtered by driver
        response = requests.get(f"{BASE_URL}/api/receipts?driver_name={test_receipt_data['driver_name']}")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1, "Should have at least one receipt for this driver"
        assert all(r["driver_name"] == test_receipt_data["driver_name"] for r in data)
        print(f"Retrieved {len(data)} receipts for driver {test_receipt_data['driver_name']}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/receipts/{created_id}")
    
    def test_delete_receipt(self, test_receipt_data):
        """DELETE /api/receipts/{id} removes a receipt"""
        # Create a receipt
        create_res = requests.post(f"{BASE_URL}/api/receipts", json=test_receipt_data)
        created_id = create_res.json()["id"]
        
        # Delete it
        response = requests.delete(f"{BASE_URL}/api/receipts/{created_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "deleted" in data or "message" in data, "Response should contain 'deleted' or 'message'"
        if "deleted" in data:
            assert data["deleted"] == True, "deleted should be True"
        print(f"Receipt {created_id} deleted successfully")
        
        # Verify it's gone
        get_res = requests.get(f"{BASE_URL}/api/receipts/{created_id}")
        assert get_res.status_code == 404, "Deleted receipt should return 404"
    
    def test_delete_nonexistent_receipt(self):
        """DELETE /api/receipts/{id} returns 404 for non-existent receipt"""
        fake_id = f"nonexistent-{uuid.uuid4().hex}"
        response = requests.delete(f"{BASE_URL}/api/receipts/{fake_id}")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestAdminLogin:
    """Admin login endpoint tests"""
    
    def test_admin_login_success(self):
        """POST /api/admin/login with correct credentials (admin/1234)"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": "admin",
            "password": "1234"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True, "Login should be successful"
        print("Admin login successful with password 1234")
    
    def test_admin_login_wrong_password(self):
        """POST /api/admin/login with wrong password returns 401"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "username": "admin",
            "password": "wrongpassword"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Admin login correctly rejected wrong password")


class TestExistingEndpoints:
    """Verify existing endpoints still work"""
    
    def test_api_root(self):
        """GET /api/ returns API info"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"API root: {data['message']}")
    
    def test_drivers_endpoint(self):
        """GET /api/drivers returns list of drivers"""
        response = requests.get(f"{BASE_URL}/api/drivers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} drivers")
    
    def test_plads_endpoint(self):
        """GET /api/plads returns list of plads"""
        response = requests.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} plads")
    
    def test_tours_endpoint(self):
        """GET /api/tours returns list of tours"""
        response = requests.get(f"{BASE_URL}/api/tours")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} tours")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
