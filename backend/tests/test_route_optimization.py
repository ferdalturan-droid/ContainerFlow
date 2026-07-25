"""
Test Route Optimization API - SOLO/HÆNGER classification, distance calculation, and smart ordering
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestRouteOptimization:
    """Test /api/optimize-route endpoint with SOLO/HÆNGER detection"""
    
    def test_optimize_route_returns_optimized_true(self):
        """POST /api/optimize-route returns optimized:true with valid data"""
        # First get tours for Glostrup on 2026-03-31
        tours_res = requests.get(f"{BASE_URL}/api/tours?plads=Glostrup&date=2026-03-31")
        assert tours_res.status_code == 200
        tours = tours_res.json()
        assert len(tours) >= 5, f"Expected at least 5 tours, got {len(tours)}"
        
        tour_ids = [t['id'] for t in tours]
        
        # Call optimize-route
        res = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": "Glostrup",
            "tour_ids": tour_ids
        })
        assert res.status_code == 200
        data = res.json()
        
        # Verify optimized flag
        assert data.get("optimized") == True, f"Expected optimized=True, got {data.get('optimized')}"
        print(f"PASSED: optimize-route returns optimized=True")
    
    def test_optimize_route_groups_nearby_addresses_as_haenger(self):
        """POST /api/optimize-route groups nearby addresses (same postal code 2300) as HÆNGER"""
        tours_res = requests.get(f"{BASE_URL}/api/tours?plads=Glostrup&date=2026-03-31")
        tours = tours_res.json()
        tour_ids = [t['id'] for t in tours]
        
        res = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": "Glostrup",
            "tour_ids": tour_ids
        })
        data = res.json()
        
        # Check groups exist
        groups = data.get("groups", {})
        assert len(groups) >= 1, f"Expected at least 1 HÆNGER group, got {len(groups)}"
        
        # Check haenger_count
        haenger_count = data.get("haenger_count", 0)
        assert haenger_count >= 2, f"Expected haenger_count >= 2, got {haenger_count}"
        
        # Verify G1 group has 2 members (Beton and Gips both in 2300)
        g1_members = groups.get("G1", [])
        assert len(g1_members) == 2, f"Expected G1 group to have 2 members, got {len(g1_members)}"
        
        print(f"PASSED: Groups nearby addresses as HÆNGER - {haenger_count} HÆNGER tours in {len(groups)} groups")
    
    def test_optimize_route_sorts_by_nearest_distance(self):
        """POST /api/optimize-route sorts tours by nearest distance first"""
        tours_res = requests.get(f"{BASE_URL}/api/tours?plads=Glostrup&date=2026-03-31")
        tours = tours_res.json()
        tour_ids = [t['id'] for t in tours]
        
        res = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": "Glostrup",
            "tour_ids": tour_ids
        })
        data = res.json()
        
        result_tours = data.get("tours", [])
        assert len(result_tours) >= 5, f"Expected at least 5 tours in result"
        
        # First tour should have smallest distance (nearest neighbor)
        first_tour = result_tours[0]
        assert first_tour.get("route_order") == 1
        first_distance = first_tour.get("distance_km", 0)
        
        # Verify first tour is reasonably close (< 10km from Glostrup)
        assert first_distance < 10, f"First tour should be close to plads, got {first_distance}km"
        
        print(f"PASSED: First tour is {first_distance}km from plads (nearest first)")
    
    def test_optimize_route_returns_required_fields(self):
        """POST /api/optimize-route returns total_distance_km, total_estimated_minutes, solo_count, haenger_count, groups"""
        tours_res = requests.get(f"{BASE_URL}/api/tours?plads=Glostrup&date=2026-03-31")
        tours = tours_res.json()
        tour_ids = [t['id'] for t in tours]
        
        res = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": "Glostrup",
            "tour_ids": tour_ids
        })
        data = res.json()
        
        # Check all required fields exist
        required_fields = ["total_distance_km", "total_estimated_minutes", "solo_count", "haenger_count", "groups", "tours"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Verify values are reasonable
        assert data["total_distance_km"] > 0, "total_distance_km should be > 0"
        assert data["total_estimated_minutes"] > 0, "total_estimated_minutes should be > 0"
        assert data["solo_count"] >= 0, "solo_count should be >= 0"
        assert data["haenger_count"] >= 0, "haenger_count should be >= 0"
        assert isinstance(data["groups"], dict), "groups should be a dict"
        assert isinstance(data["tours"], list), "tours should be a list"
        
        print(f"PASSED: All required fields present - {data['total_distance_km']}km, ~{data['total_estimated_minutes']}min, {data['solo_count']} SOLO, {data['haenger_count']} HÆNGER")
    
    def test_optimize_route_uses_postal_code_geocoding(self):
        """POST /api/optimize-route uses postal code geocoding for tours without lat/lng"""
        tours_res = requests.get(f"{BASE_URL}/api/tours?plads=Glostrup&date=2026-03-31")
        tours = tours_res.json()
        
        # Verify tours don't have lat/lng in database
        tours_without_coords = [t for t in tours if not t.get('lat') or not t.get('lng')]
        assert len(tours_without_coords) >= 1, "Expected some tours without coordinates"
        
        tour_ids = [t['id'] for t in tours]
        
        res = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": "Glostrup",
            "tour_ids": tour_ids
        })
        data = res.json()
        
        # Check tours_with_coordinates matches total (geocoding worked)
        tours_with_coords = data.get("tours_with_coordinates", 0)
        total_tours = data.get("total_tours", 0)
        
        assert tours_with_coords == total_tours, f"Expected all {total_tours} tours to have coordinates via geocoding, got {tours_with_coords}"
        
        # Verify all result tours have has_coordinates=True
        for tour in data.get("tours", []):
            assert tour.get("has_coordinates") == True, f"Tour {tour.get('tour_id')} should have coordinates"
        
        print(f"PASSED: Postal code geocoding worked - {tours_with_coords}/{total_tours} tours have coordinates")
    
    def test_optimize_route_tour_fields(self):
        """Each tour in result has job_type, distance_km, estimated_minutes, route_order"""
        tours_res = requests.get(f"{BASE_URL}/api/tours?plads=Glostrup&date=2026-03-31")
        tours = tours_res.json()
        tour_ids = [t['id'] for t in tours]
        
        res = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": "Glostrup",
            "tour_ids": tour_ids
        })
        data = res.json()
        
        for tour in data.get("tours", []):
            assert "job_type" in tour, f"Tour missing job_type"
            assert tour["job_type"] in ["SOLO", "HAENGER"], f"Invalid job_type: {tour['job_type']}"
            assert "distance_km" in tour, f"Tour missing distance_km"
            assert "estimated_minutes" in tour, f"Tour missing estimated_minutes"
            assert "route_order" in tour, f"Tour missing route_order"
            assert "group_size" in tour, f"Tour missing group_size"
        
        print(f"PASSED: All tour fields present (job_type, distance_km, estimated_minutes, route_order)")
    
    def test_optimize_route_haenger_grouped_together(self):
        """HÆNGER tours are grouped together in route order"""
        tours_res = requests.get(f"{BASE_URL}/api/tours?plads=Glostrup&date=2026-03-31")
        tours = tours_res.json()
        tour_ids = [t['id'] for t in tours]
        
        res = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": "Glostrup",
            "tour_ids": tour_ids
        })
        data = res.json()
        
        result_tours = data.get("tours", [])
        
        # Find HÆNGER tours and verify they are consecutive
        haenger_tours = [t for t in result_tours if t.get("job_type") == "HAENGER"]
        if len(haenger_tours) >= 2:
            # Get route orders of HÆNGER tours
            haenger_orders = sorted([t["route_order"] for t in haenger_tours])
            # Check they are consecutive
            for i in range(1, len(haenger_orders)):
                assert haenger_orders[i] == haenger_orders[i-1] + 1, f"HÆNGER tours not consecutive: {haenger_orders}"
        
        print(f"PASSED: HÆNGER tours are grouped together in route order")
    
    def test_optimize_route_no_tours(self):
        """POST /api/optimize-route with empty tour_ids returns optimized=False"""
        res = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": "Glostrup",
            "tour_ids": []
        })
        assert res.status_code == 200
        data = res.json()
        assert data.get("optimized") == False
        assert "reason" in data
        print(f"PASSED: Empty tour_ids returns optimized=False with reason: {data.get('reason')}")
    
    def test_optimize_route_invalid_plads(self):
        """POST /api/optimize-route with invalid plads returns optimized=False"""
        res = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": "NonExistentPlads",
            "tour_ids": ["some-id"]
        })
        assert res.status_code == 200
        data = res.json()
        assert data.get("optimized") == False
        print(f"PASSED: Invalid plads returns optimized=False")


class TestDriverLogin:
    """Test driver login with name + code 3030"""
    
    def test_driver_login_success(self):
        """POST /api/driver/login with correct code (3030) returns success"""
        res = requests.post(f"{BASE_URL}/api/driver/login", json={
            "name": "Test Driver",
            "code": "3030"
        })
        assert res.status_code == 200
        data = res.json()
        assert data.get("success") == True
        assert data.get("driver_name") == "Test Driver"
        print(f"PASSED: Driver login with code 3030 succeeds")
    
    def test_driver_login_wrong_code(self):
        """POST /api/driver/login with wrong code returns 401"""
        res = requests.post(f"{BASE_URL}/api/driver/login", json={
            "name": "Test Driver",
            "code": "1234"
        })
        assert res.status_code == 401
        print(f"PASSED: Driver login with wrong code returns 401")


class TestAdminLogin:
    """Test admin login with code 3030"""
    
    def test_admin_login_success(self):
        """POST /api/admin/login with correct password (3030) returns success"""
        res = requests.post(f"{BASE_URL}/api/admin/login", json={
            "password": "3030"
        })
        assert res.status_code == 200
        data = res.json()
        assert data.get("success") == True
        print(f"PASSED: Admin login with password 3030 succeeds")
    
    def test_admin_login_wrong_password(self):
        """POST /api/admin/login with wrong password returns 401"""
        res = requests.post(f"{BASE_URL}/api/admin/login", json={
            "password": "wrong"
        })
        assert res.status_code == 401
        print(f"PASSED: Admin login with wrong password returns 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
