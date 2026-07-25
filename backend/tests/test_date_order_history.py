"""
Test Date Selection and Order History Features
- GET /api/container-orders/by-location/{code}?date=YYYY-MM-DD returns orders for that date
- POST /api/customer-orders/submit with order_date creates order and tour with correct date
- Order history filtering by date
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDateOrderHistory:
    """Test date selection in orders and order history retrieval"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.location_code = "3030"
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        self.yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        yield
    
    def test_get_orders_by_location_no_date_filter(self):
        """GET /api/container-orders/by-location/{code} returns all orders for location"""
        response = requests.get(f"{BASE_URL}/api/container-orders/by-location/{self.location_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"PASSED: GET orders by location (no date filter) - {len(data)} orders returned")
    
    def test_get_orders_by_location_with_today_date(self):
        """GET /api/container-orders/by-location/{code}?date=today returns only today's orders"""
        response = requests.get(f"{BASE_URL}/api/container-orders/by-location/{self.location_code}?date={self.today}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        # Verify all returned orders have today's date
        for order in data:
            assert order.get("order_date") == self.today, f"Order date {order.get('order_date')} != {self.today}"
        print(f"PASSED: GET orders by location with today's date - {len(data)} orders for {self.today}")
    
    def test_get_orders_by_location_with_tomorrow_date(self):
        """GET /api/container-orders/by-location/{code}?date=tomorrow returns only tomorrow's orders"""
        response = requests.get(f"{BASE_URL}/api/container-orders/by-location/{self.location_code}?date={self.tomorrow}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        # Verify all returned orders have tomorrow's date
        for order in data:
            assert order.get("order_date") == self.tomorrow, f"Order date {order.get('order_date')} != {self.tomorrow}"
        print(f"PASSED: GET orders by location with tomorrow's date - {len(data)} orders for {self.tomorrow}")
    
    def test_get_orders_by_location_with_yesterday_date(self):
        """GET /api/container-orders/by-location/{code}?date=yesterday returns only yesterday's orders"""
        response = requests.get(f"{BASE_URL}/api/container-orders/by-location/{self.location_code}?date={self.yesterday}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        # Verify all returned orders have yesterday's date
        for order in data:
            assert order.get("order_date") == self.yesterday, f"Order date {order.get('order_date')} != {self.yesterday}"
        print(f"PASSED: GET orders by location with yesterday's date - {len(data)} orders for {self.yesterday}")


class TestOrderSubmitWithDate:
    """Test order submission with date selection"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.location_code = "3030"
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        self.custom_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        yield
    
    def test_submit_order_with_today_date(self):
        """POST /api/customer-orders/submit with today's date creates order and tour"""
        payload = {
            "location_code": self.location_code,
            "material": "TEST_DateOrder_Today",
            "container_number": "Container 1",
            "priority": "normal",
            "comment": "Test order for today",
            "custom_address": "",
            "custom_container_id": "",
            "order_date": self.today
        }
        response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response contains order_date
        assert "order_date" in data, "Response should contain order_date"
        assert data["order_date"] == self.today, f"Order date {data['order_date']} != {self.today}"
        assert "order_id" in data, "Response should contain order_id"
        assert "tour_id" in data, "Response should contain tour_id"
        
        print(f"PASSED: Submit order with today's date - order_id: {data['order_id']}, tour_id: {data['tour_id']}")
        
        # Verify order was created with correct date
        order_response = requests.get(f"{BASE_URL}/api/container-orders/by-location/{self.location_code}?date={self.today}")
        orders = order_response.json()
        matching_orders = [o for o in orders if o.get("material") == "TEST_DateOrder_Today"]
        assert len(matching_orders) > 0, "Order should be found in today's orders"
        print(f"PASSED: Order found in today's order history")
        
        # Verify tour was created with correct date
        tour_response = requests.get(f"{BASE_URL}/api/tours?date={self.today}")
        tours = tour_response.json()
        matching_tours = [t for t in tours if t.get("fraction") == "TEST_DateOrder_Today"]
        assert len(matching_tours) > 0, "Tour should be found in today's tours"
        assert matching_tours[0]["date"] == self.today, f"Tour date {matching_tours[0]['date']} != {self.today}"
        print(f"PASSED: Tour created with today's date")
    
    def test_submit_order_with_tomorrow_date(self):
        """POST /api/customer-orders/submit with tomorrow's date creates order and tour for tomorrow"""
        payload = {
            "location_code": self.location_code,
            "material": "TEST_DateOrder_Tomorrow",
            "container_number": "Container 2",
            "priority": "haster",
            "comment": "Test order for tomorrow",
            "custom_address": "Test Address 123",
            "custom_container_id": "CONT-123",
            "order_date": self.tomorrow
        }
        response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response contains correct order_date
        assert data["order_date"] == self.tomorrow, f"Order date {data['order_date']} != {self.tomorrow}"
        print(f"PASSED: Submit order with tomorrow's date - order_date: {data['order_date']}")
        
        # Verify order was created with tomorrow's date
        order_response = requests.get(f"{BASE_URL}/api/container-orders/by-location/{self.location_code}?date={self.tomorrow}")
        orders = order_response.json()
        matching_orders = [o for o in orders if o.get("material") == "TEST_DateOrder_Tomorrow"]
        assert len(matching_orders) > 0, "Order should be found in tomorrow's orders"
        assert matching_orders[0]["order_date"] == self.tomorrow
        print(f"PASSED: Order found in tomorrow's order history")
        
        # Verify tour was created with tomorrow's date
        tour_response = requests.get(f"{BASE_URL}/api/tours?date={self.tomorrow}")
        tours = tour_response.json()
        matching_tours = [t for t in tours if t.get("fraction") == "TEST_DateOrder_Tomorrow"]
        assert len(matching_tours) > 0, "Tour should be found in tomorrow's tours"
        assert matching_tours[0]["date"] == self.tomorrow, f"Tour date {matching_tours[0]['date']} != {self.tomorrow}"
        print(f"PASSED: Tour created with tomorrow's date")
    
    def test_submit_order_with_custom_date(self):
        """POST /api/customer-orders/submit with custom date creates order and tour for that date"""
        payload = {
            "location_code": self.location_code,
            "material": "TEST_DateOrder_Custom",
            "container_number": "Container 3",
            "priority": "senere",
            "comment": "Test order for custom date",
            "custom_address": "",
            "custom_container_id": "",
            "order_date": self.custom_date
        }
        response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response contains correct order_date
        assert data["order_date"] == self.custom_date, f"Order date {data['order_date']} != {self.custom_date}"
        print(f"PASSED: Submit order with custom date - order_date: {data['order_date']}")
        
        # Verify order was created with custom date
        order_response = requests.get(f"{BASE_URL}/api/container-orders/by-location/{self.location_code}?date={self.custom_date}")
        orders = order_response.json()
        matching_orders = [o for o in orders if o.get("material") == "TEST_DateOrder_Custom"]
        assert len(matching_orders) > 0, "Order should be found in custom date's orders"
        print(f"PASSED: Order found in custom date's order history")
        
        # Verify tour was created with custom date
        tour_response = requests.get(f"{BASE_URL}/api/tours?date={self.custom_date}")
        tours = tour_response.json()
        matching_tours = [t for t in tours if t.get("fraction") == "TEST_DateOrder_Custom"]
        assert len(matching_tours) > 0, "Tour should be found in custom date's tours"
        assert matching_tours[0]["date"] == self.custom_date, f"Tour date {matching_tours[0]['date']} != {self.custom_date}"
        print(f"PASSED: Tour created with custom date")
    
    def test_submit_order_with_empty_date_defaults_to_today(self):
        """POST /api/customer-orders/submit with empty order_date defaults to today"""
        payload = {
            "location_code": self.location_code,
            "material": "TEST_DateOrder_Empty",
            "container_number": "Container 4",
            "priority": "normal",
            "comment": "Test order with empty date",
            "custom_address": "",
            "custom_container_id": "",
            "order_date": ""  # Empty date should default to today
        }
        response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        today = datetime.now().strftime("%Y-%m-%d")
        assert data["order_date"] == today, f"Empty order_date should default to today: {data['order_date']} != {today}"
        print(f"PASSED: Empty order_date defaults to today: {data['order_date']}")


class TestOrderHistoryFields:
    """Test that order history returns all required fields"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.location_code = "3030"
        self.today = datetime.now().strftime("%Y-%m-%d")
        yield
    
    def test_order_history_contains_required_fields(self):
        """Order history should contain material, container, address, priority, status, created_at"""
        # First create an order to ensure we have data
        payload = {
            "location_code": self.location_code,
            "material": "TEST_HistoryFields",
            "container_number": "Container 1",
            "priority": "haster",
            "comment": "Test comment",
            "custom_address": "Test Address 456",
            "custom_container_id": "CONT-456",
            "order_date": self.today
        }
        create_response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json=payload)
        assert create_response.status_code == 200
        
        # Get order history
        response = requests.get(f"{BASE_URL}/api/container-orders/by-location/{self.location_code}?date={self.today}")
        assert response.status_code == 200
        orders = response.json()
        
        # Find our test order
        test_orders = [o for o in orders if o.get("material") == "TEST_HistoryFields"]
        assert len(test_orders) > 0, "Test order should be in history"
        
        order = test_orders[0]
        
        # Verify required fields
        required_fields = ["material", "container_number", "customer_address", "priority", "status", "created_at", "order_date"]
        for field in required_fields:
            assert field in order, f"Order should contain field: {field}"
            print(f"  - {field}: {order[field]}")
        
        # Verify field values
        assert order["material"] == "TEST_HistoryFields"
        assert order["container_number"] == "Container 1"
        assert order["customer_address"] == "Test Address 456"
        assert order["priority"] == "haster"
        assert order["status"] == "pending"
        assert order["order_date"] == self.today
        
        print(f"PASSED: Order history contains all required fields")


class TestMaterialCRUDStillWorks:
    """Verify material CRUD still works after date feature addition"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.location_code = "3030"
        yield
    
    def test_add_material(self):
        """POST /api/locations/{code}/materials adds material"""
        response = requests.post(
            f"{BASE_URL}/api/locations/{self.location_code}/materials",
            json={"material": "TEST_DateFeature_Material"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "TEST_DateFeature_Material" in data.get("materials", [])
        print(f"PASSED: Add material still works")
    
    def test_delete_material(self):
        """DELETE /api/locations/{code}/materials removes material"""
        response = requests.delete(
            f"{BASE_URL}/api/locations/{self.location_code}/materials?material=TEST_DateFeature_Material"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"PASSED: Delete material still works")


class TestContainerOverrideStillWorks:
    """Verify container override (address save) still works"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.location_code = "3030"
        self.today = datetime.now().strftime("%Y-%m-%d")
        yield
    
    def test_order_with_custom_address_saves_override(self):
        """Submitting order with custom_address saves it as override"""
        unique_address = f"TEST_Override_Address_{datetime.now().timestamp()}"
        payload = {
            "location_code": self.location_code,
            "material": "TEST_Override_Material",
            "container_number": "Container 1",
            "priority": "normal",
            "comment": "",
            "custom_address": unique_address,
            "custom_container_id": "OVERRIDE-123",
            "order_date": self.today
        }
        response = requests.post(f"{BASE_URL}/api/customer-orders/submit", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["address"] == unique_address, f"Address should be {unique_address}, got {data['address']}"
        print(f"PASSED: Container override (address save) still works")


# Cleanup test data
class TestCleanup:
    """Cleanup test data created during tests"""
    
    def test_cleanup_test_orders(self):
        """Remove test orders and tours"""
        location_code = "3030"
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        custom_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        
        # Get all orders for cleanup
        for date in [today, tomorrow, custom_date, ""]:
            url = f"{BASE_URL}/api/container-orders/by-location/{location_code}"
            if date:
                url += f"?date={date}"
            response = requests.get(url)
            if response.status_code == 200:
                orders = response.json()
                for order in orders:
                    if order.get("material", "").startswith("TEST_"):
                        # Delete order
                        del_response = requests.delete(f"{BASE_URL}/api/container-orders/{order['id']}")
                        if del_response.status_code == 200:
                            print(f"  Deleted test order: {order['id']}")
        
        # Cleanup test tours
        for date in [today, tomorrow, custom_date]:
            tour_response = requests.get(f"{BASE_URL}/api/tours?date={date}")
            if tour_response.status_code == 200:
                tours = tour_response.json()
                for tour in tours:
                    if tour.get("fraction", "").startswith("TEST_"):
                        del_response = requests.delete(f"{BASE_URL}/api/tours/{tour['id']}")
                        if del_response.status_code == 200:
                            print(f"  Deleted test tour: {tour['id']}")
        
        print("PASSED: Cleanup completed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
