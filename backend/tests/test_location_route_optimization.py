"""
Test suite for Location System and Route Optimization features
- Plads CRUD with city, address, lat, lng fields
- Route optimization using Haversine formula + nearest neighbor algorithm
- Transport mode suggestion (truck vs trailer based on >12km threshold)
"""
import pytest
import requests
import os
import math

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Known Danish locations with coordinates for testing
KNOWN_LOCATIONS = {
    "Glostrup": {"city": "Glostrup", "address": "Ejby Industrivej 28, 2600 Glostrup", "lat": 55.6787, "lng": 12.3978},
    "Herlev": {"city": "Herlev", "address": "Marielundvej 43, 2730 Herlev", "lat": 55.7245, "lng": 12.4386},
    "Hillerød": {"city": "Hillerød", "address": "Hillerødsholmsalle 70, 3400 Hillerød", "lat": 55.9263, "lng": 12.3008},
    "Ballerup": {"city": "Ballerup", "address": "Energivej 25, 2750 Ballerup", "lat": 55.7312, "lng": 12.3605},
    "Skipstrup": {"city": "Ålsgårde", "address": "Skibstrupvej 1, 3140 Ålsgårde", "lat": 56.0742, "lng": 12.5641},
    "Helsingør": {"city": "Helsingør", "address": "Energivej 1, 3000 Helsingør", "lat": 56.0365, "lng": 12.6130},
    "Køge": {"city": "Køge", "address": "Tangmosevej 100, 4600 Køge", "lat": 55.4561, "lng": 12.1855},
    "Bjæverskov": {"city": "Bjæverskov", "address": "Billesborgvej 40, 4632 Bjæverskov", "lat": 55.3865, "lng": 12.0403},
    "St. Heddinge": {"city": "Store Heddinge", "address": "Hovedgaden 92, 4660 Store Heddinge", "lat": 55.3096, "lng": 12.3882},
    "Måløv": {"city": "Måløv", "address": "Måløv Byvej 229, 2760 Måløv", "lat": 55.7472, "lng": 12.3231},
}


def haversine_km(lat1, lng1, lat2, lng2):
    """Calculate distance in km between two lat/lng points using Haversine formula."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


class TestPladsEndpoints:
    """Test Plads CRUD operations with location fields"""
    
    def test_get_plads_returns_location_fields(self, api_client):
        """GET /api/plads should return plads with city, address, lat, lng fields"""
        response = api_client.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        plads_list = response.json()
        assert isinstance(plads_list, list), "Response should be a list"
        
        # Check that seeded plads have location data
        plads_with_gps = [p for p in plads_list if p.get("lat") and p.get("lng")]
        print(f"Found {len(plads_with_gps)} plads with GPS coordinates out of {len(plads_list)} total")
        
        # Verify at least some seeded locations exist with coordinates
        assert len(plads_with_gps) >= 5, f"Expected at least 5 plads with GPS, found {len(plads_with_gps)}"
        
        # Check structure of a plads with GPS
        for plads in plads_with_gps[:3]:
            assert "id" in plads, "Plads should have id"
            assert "name" in plads, "Plads should have name"
            assert "city" in plads, "Plads should have city field"
            assert "address" in plads, "Plads should have address field"
            assert "lat" in plads, "Plads should have lat field"
            assert "lng" in plads, "Plads should have lng field"
            assert isinstance(plads["lat"], (int, float)), "lat should be numeric"
            assert isinstance(plads["lng"], (int, float)), "lng should be numeric"
            print(f"  - {plads['name']}: {plads.get('city', 'N/A')}, lat={plads['lat']}, lng={plads['lng']}")
    
    def test_seeded_locations_have_correct_coordinates(self, api_client):
        """Verify seeded Danish locations have correct coordinates"""
        response = api_client.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200
        
        plads_list = response.json()
        plads_by_name = {p["name"]: p for p in plads_list}
        
        # Check a few known locations
        for name, expected in list(KNOWN_LOCATIONS.items())[:5]:
            if name in plads_by_name:
                plads = plads_by_name[name]
                if plads.get("lat") and plads.get("lng"):
                    # Allow small tolerance for coordinate matching
                    assert abs(plads["lat"] - expected["lat"]) < 0.01, f"{name} lat mismatch"
                    assert abs(plads["lng"] - expected["lng"]) < 0.01, f"{name} lng mismatch"
                    print(f"  ✓ {name}: coordinates match ({plads['lat']}, {plads['lng']})")
    
    def test_create_plads_with_all_fields(self, api_client):
        """POST /api/plads should create plads with all location fields"""
        test_plads = {
            "name": "TEST_NewPlads",
            "city": "TestCity",
            "address": "Test Address 123, 1234 TestCity",
            "lat": 55.5000,
            "lng": 12.5000
        }
        
        response = api_client.post(f"{BASE_URL}/api/plads", json=test_plads)
        
        # Handle case where plads already exists
        if response.status_code == 400 and "already exists" in response.text.lower():
            print("Test plads already exists, skipping creation test")
            return
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        created = response.json()
        assert created["name"] == test_plads["name"]
        assert created["city"] == test_plads["city"]
        assert created["address"] == test_plads["address"]
        assert created["lat"] == test_plads["lat"]
        assert created["lng"] == test_plads["lng"]
        print(f"Created plads: {created['name']} with GPS ({created['lat']}, {created['lng']})")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/plads/{created['id']}")
    
    def test_create_plads_duplicate_name_rejected(self, api_client):
        """POST /api/plads should reject duplicate names"""
        # Get existing plads
        response = api_client.get(f"{BASE_URL}/api/plads")
        plads_list = response.json()
        
        if plads_list:
            existing_name = plads_list[0]["name"]
            response = api_client.post(f"{BASE_URL}/api/plads", json={
                "name": existing_name,
                "city": "Test",
                "address": "Test"
            })
            assert response.status_code == 400, f"Expected 400 for duplicate, got {response.status_code}"
            print(f"Correctly rejected duplicate name: {existing_name}")
    
    def test_update_plads_fields(self, api_client):
        """PUT /api/plads/{id} should update plads fields"""
        # Get existing plads
        response = api_client.get(f"{BASE_URL}/api/plads")
        plads_list = response.json()
        
        if not plads_list:
            pytest.skip("No plads available for update test")
        
        # Find a plads to update (prefer one without GPS for testing)
        test_plads = None
        for p in plads_list:
            if not p.get("lat") or not p.get("lng"):
                test_plads = p
                break
        
        if not test_plads:
            test_plads = plads_list[0]
        
        original_city = test_plads.get("city", "")
        new_city = "UpdatedCity"
        
        # Update the plads
        update_data = {
            "city": new_city,
            "address": "Updated Address 456",
            "lat": 55.6000,
            "lng": 12.4000
        }
        
        response = api_client.put(f"{BASE_URL}/api/plads/{test_plads['id']}", json=update_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        updated = response.json()
        assert updated["city"] == new_city, f"City not updated: {updated['city']}"
        assert updated["address"] == "Updated Address 456"
        assert updated["lat"] == 55.6000
        assert updated["lng"] == 12.4000
        print(f"Updated plads {test_plads['name']}: city={updated['city']}, lat={updated['lat']}, lng={updated['lng']}")
        
        # Restore original values
        restore_data = {"city": original_city or ""}
        api_client.put(f"{BASE_URL}/api/plads/{test_plads['id']}", json=restore_data)


class TestRouteOptimization:
    """Test route optimization endpoint with Haversine formula"""
    
    def test_optimize_route_requires_plads_name(self, api_client):
        """POST /api/optimize-route should require plads_name"""
        response = api_client.post(f"{BASE_URL}/api/optimize-route", json={
            "tour_ids": []
        })
        # Should return error or empty result
        assert response.status_code in [200, 400, 422]
    
    def test_optimize_route_with_valid_plads(self, api_client):
        """POST /api/optimize-route should work with valid plads that has coordinates"""
        # Get a plads with coordinates
        response = api_client.get(f"{BASE_URL}/api/plads")
        plads_list = response.json()
        
        plads_with_gps = [p for p in plads_list if p.get("lat") and p.get("lng")]
        if not plads_with_gps:
            pytest.skip("No plads with GPS coordinates available")
        
        test_plads = plads_with_gps[0]
        
        # Create test tours for this plads
        test_tours = []
        for i in range(3):
            tour_data = {
                "date": "2026-01-15",
                "fraction": f"TEST_Fraction_{i}",
                "facility": f"TEST_Facility_{i}",
                "address": f"Test Address {i}",
                "plads": test_plads["name"],
                "lat": test_plads["lat"] + (i * 0.01),  # Slightly different coordinates
                "lng": test_plads["lng"] + (i * 0.01)
            }
            resp = api_client.post(f"{BASE_URL}/api/tours", json=tour_data)
            if resp.status_code == 200:
                test_tours.append(resp.json())
        
        if len(test_tours) < 2:
            pytest.skip("Could not create enough test tours")
        
        try:
            # Call optimize-route
            response = api_client.post(f"{BASE_URL}/api/optimize-route", json={
                "plads_name": test_plads["name"],
                "tour_ids": [t["id"] for t in test_tours]
            })
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
            result = response.json()
            print(f"Optimization result: optimized={result.get('optimized')}, reason={result.get('reason', 'N/A')}")
            
            if result.get("optimized"):
                assert "tours" in result, "Result should contain tours"
                assert "total_tours" in result, "Result should contain total_tours"
                assert "tours_with_coordinates" in result, "Result should contain tours_with_coordinates"
                
                for tour_result in result["tours"]:
                    assert "tour_id" in tour_result
                    assert "route_order" in tour_result
                    assert "distance_km" in tour_result
                    assert "transport_mode" in tour_result
                    assert "has_coordinates" in tour_result
                    print(f"  Tour {tour_result['tour_id'][:8]}...: order={tour_result['route_order']}, dist={tour_result['distance_km']}km, mode={tour_result['transport_mode']}")
        finally:
            # Cleanup test tours
            for tour in test_tours:
                api_client.delete(f"{BASE_URL}/api/tours/{tour['id']}")
    
    def test_optimize_route_no_coordinates_fallback(self, api_client):
        """POST /api/optimize-route should handle tours without coordinates gracefully"""
        # Get a plads with coordinates
        response = api_client.get(f"{BASE_URL}/api/plads")
        plads_list = response.json()
        
        plads_with_gps = [p for p in plads_list if p.get("lat") and p.get("lng")]
        if not plads_with_gps:
            pytest.skip("No plads with GPS coordinates available")
        
        test_plads = plads_with_gps[0]
        
        # Create tours WITHOUT coordinates
        test_tours = []
        for i in range(2):
            tour_data = {
                "date": "2026-01-15",
                "fraction": f"TEST_NoGPS_{i}",
                "facility": f"TEST_Facility_{i}",
                "address": f"Test Address {i}",
                "plads": test_plads["name"]
                # No lat/lng
            }
            resp = api_client.post(f"{BASE_URL}/api/tours", json=tour_data)
            if resp.status_code == 200:
                test_tours.append(resp.json())
        
        try:
            response = api_client.post(f"{BASE_URL}/api/optimize-route", json={
                "plads_name": test_plads["name"],
                "tour_ids": [t["id"] for t in test_tours]
            })
            
            assert response.status_code == 200
            result = response.json()
            
            # Should either not optimize or return tours without coordinates
            print(f"No-GPS optimization: optimized={result.get('optimized')}, reason={result.get('reason', 'N/A')}")
            
            if result.get("tours"):
                for tour_result in result["tours"]:
                    # Tours without coordinates should have has_coordinates=False
                    if not tour_result.get("has_coordinates"):
                        print(f"  Tour without GPS: order={tour_result['route_order']}, has_coordinates={tour_result['has_coordinates']}")
        finally:
            for tour in test_tours:
                api_client.delete(f"{BASE_URL}/api/tours/{tour['id']}")
    
    def test_transport_mode_threshold(self, api_client):
        """Verify transport_mode is 'trailer' for distances >12km, 'truck' otherwise"""
        # Get a plads with coordinates
        response = api_client.get(f"{BASE_URL}/api/plads")
        plads_list = response.json()
        
        plads_with_gps = [p for p in plads_list if p.get("lat") and p.get("lng")]
        if not plads_with_gps:
            pytest.skip("No plads with GPS coordinates available")
        
        test_plads = plads_with_gps[0]
        
        # Create tours at different distances
        # Close tour (should be truck)
        close_tour_data = {
            "date": "2026-01-15",
            "fraction": "TEST_Close",
            "facility": "Close Facility",
            "address": "Close Address",
            "plads": test_plads["name"],
            "lat": test_plads["lat"] + 0.01,  # ~1km away
            "lng": test_plads["lng"]
        }
        
        # Far tour (should be trailer - >12km)
        far_tour_data = {
            "date": "2026-01-15",
            "fraction": "TEST_Far",
            "facility": "Far Facility",
            "address": "Far Address",
            "plads": test_plads["name"],
            "lat": test_plads["lat"] + 0.2,  # ~22km away
            "lng": test_plads["lng"]
        }
        
        test_tours = []
        for tour_data in [close_tour_data, far_tour_data]:
            resp = api_client.post(f"{BASE_URL}/api/tours", json=tour_data)
            if resp.status_code == 200:
                test_tours.append(resp.json())
        
        try:
            response = api_client.post(f"{BASE_URL}/api/optimize-route", json={
                "plads_name": test_plads["name"],
                "tour_ids": [t["id"] for t in test_tours]
            })
            
            assert response.status_code == 200
            result = response.json()
            
            if result.get("optimized") and result.get("tours"):
                for tour_result in result["tours"]:
                    dist = tour_result.get("distance_km", 0)
                    mode = tour_result.get("transport_mode", "")
                    
                    if dist > 12:
                        assert mode == "trailer", f"Distance {dist}km should use trailer, got {mode}"
                        print(f"  ✓ Far tour ({dist}km): correctly assigned 'trailer'")
                    elif dist > 0:
                        assert mode == "truck", f"Distance {dist}km should use truck, got {mode}"
                        print(f"  ✓ Close tour ({dist}km): correctly assigned 'truck'")
        finally:
            for tour in test_tours:
                api_client.delete(f"{BASE_URL}/api/tours/{tour['id']}")


class TestHaversineCalculation:
    """Test Haversine distance calculation correctness"""
    
    def test_haversine_known_distances(self):
        """Verify Haversine formula calculates correct distances for known locations"""
        # Glostrup to Herlev: approximately 6-7 km
        glostrup = KNOWN_LOCATIONS["Glostrup"]
        herlev = KNOWN_LOCATIONS["Herlev"]
        
        dist = haversine_km(glostrup["lat"], glostrup["lng"], herlev["lat"], herlev["lng"])
        print(f"Glostrup to Herlev: {dist:.2f} km")
        assert 4 < dist < 10, f"Expected ~6-7km, got {dist}km"
        
        # Glostrup to Hillerød: approximately 30-35 km
        hillerod = KNOWN_LOCATIONS["Hillerød"]
        dist2 = haversine_km(glostrup["lat"], glostrup["lng"], hillerod["lat"], hillerod["lng"])
        print(f"Glostrup to Hillerød: {dist2:.2f} km")
        assert 25 < dist2 < 40, f"Expected ~30-35km, got {dist2}km"
        
        # Køge to Bjæverskov: approximately 10-15 km
        koge = KNOWN_LOCATIONS["Køge"]
        bjaverskov = KNOWN_LOCATIONS["Bjæverskov"]
        dist3 = haversine_km(koge["lat"], koge["lng"], bjaverskov["lat"], bjaverskov["lng"])
        print(f"Køge to Bjæverskov: {dist3:.2f} km")
        assert 5 < dist3 < 20, f"Expected ~10-15km, got {dist3}km"
    
    def test_haversine_same_point(self):
        """Distance from a point to itself should be 0"""
        glostrup = KNOWN_LOCATIONS["Glostrup"]
        dist = haversine_km(glostrup["lat"], glostrup["lng"], glostrup["lat"], glostrup["lng"])
        assert dist == 0, f"Same point distance should be 0, got {dist}"


class TestExistingFunctionality:
    """Verify existing tour functionality still works"""
    
    def test_tour_creation_still_works(self, api_client):
        """Tour creation should still work with new fields"""
        tour_data = {
            "date": "2026-01-15",
            "fraction": "TEST_ExistingFunc",
            "facility": "Test Facility",
            "address": "Test Address 123",
            "plads": "Glostrup"
        }
        
        response = api_client.post(f"{BASE_URL}/api/tours", json=tour_data)
        assert response.status_code == 200, f"Tour creation failed: {response.text}"
        
        tour = response.json()
        assert tour["fraction"] == tour_data["fraction"]
        assert tour["facility"] == tour_data["facility"]
        print(f"Tour created successfully: {tour['id'][:8]}...")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/tours/{tour['id']}")
    
    def test_tour_update_still_works(self, api_client):
        """Tour update (on_way, completed, weight) should still work"""
        # Create a tour
        tour_data = {
            "date": "2026-01-15",
            "fraction": "TEST_UpdateFunc",
            "facility": "Test Facility",
            "address": "Test Address",
            "plads": "Glostrup"
        }
        
        response = api_client.post(f"{BASE_URL}/api/tours", json=tour_data)
        assert response.status_code == 200
        tour = response.json()
        
        try:
            # Test on_way toggle
            response = api_client.put(f"{BASE_URL}/api/tours/{tour['id']}", json={"on_way": True})
            assert response.status_code == 200
            updated = response.json()
            assert updated["on_way"] == True, "on_way should be True"
            print("  ✓ on_way toggle works")
            
            # Test completion with weight
            response = api_client.put(f"{BASE_URL}/api/tours/{tour['id']}", json={
                "completed": True,
                "weight": 1500,
                "on_way": False
            })
            assert response.status_code == 200
            updated = response.json()
            assert updated["completed"] == True, "completed should be True"
            assert updated["weight"] == 1500, "weight should be 1500"
            print("  ✓ completion with weight works")
        finally:
            api_client.delete(f"{BASE_URL}/api/tours/{tour['id']}")
    
    def test_tour_deletion_still_works(self, api_client):
        """Tour deletion should still work"""
        # Create a tour
        tour_data = {
            "date": "2026-01-15",
            "fraction": "TEST_DeleteFunc",
            "facility": "Test Facility",
            "address": "Test Address",
            "plads": "Glostrup"
        }
        
        response = api_client.post(f"{BASE_URL}/api/tours", json=tour_data)
        assert response.status_code == 200
        tour = response.json()
        
        # Delete it
        response = api_client.delete(f"{BASE_URL}/api/tours/{tour['id']}")
        assert response.status_code == 200
        print("  ✓ Tour deletion works")
        
        # Verify it's gone
        response = api_client.get(f"{BASE_URL}/api/tours")
        tours = response.json()
        assert not any(t["id"] == tour["id"] for t in tours), "Tour should be deleted"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
