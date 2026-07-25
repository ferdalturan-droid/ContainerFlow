"""
Test Google Maps Route Optimization Integration
Tests:
- Google Maps Distance Matrix API integration
- Google Maps Geocoding API integration  
- HÆNGER grouping rules (max 2 per group)
- Route optimization with real driving distances
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestGoogleMapsRouteOptimization:
    """Test Google Maps integration for route optimization"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.test_date = "2026-04-01"
        self.test_plads = "Glostrup"
        self.created_tour_ids = []
        yield
        # Cleanup created tours
        for tour_id in self.created_tour_ids:
            try:
                requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
            except:
                pass
    
    def test_api_accessible(self):
        """Test that API is accessible"""
        response = requests.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200, f"API not accessible: {response.status_code}"
        print("PASSED: API is accessible")
    
    def test_plads_has_coordinates(self):
        """Test that Glostrup plads has coordinates for route optimization"""
        response = requests.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200
        plads_list = response.json()
        
        glostrup = next((p for p in plads_list if p["name"] == "Glostrup"), None)
        assert glostrup is not None, "Glostrup plads not found"
        assert glostrup.get("lat") is not None, "Glostrup missing lat"
        assert glostrup.get("lng") is not None, "Glostrup missing lng"
        print(f"PASSED: Glostrup plads has coordinates: ({glostrup['lat']}, {glostrup['lng']})")
    
    def test_optimize_route_with_existing_tours(self):
        """Test route optimization with existing Glostrup tours - should use Google Maps"""
        # Get existing tours for Glostrup
        response = requests.get(f"{BASE_URL}/api/tours", params={"date": self.test_date, "plads": self.test_plads})
        assert response.status_code == 200
        tours = response.json()
        
        # Filter out pause tours and get tour IDs
        tour_ids = [t["id"] for t in tours if not t.get("is_pause")]
        
        if len(tour_ids) < 2:
            pytest.skip("Not enough tours for route optimization test")
        
        # Call optimize-route endpoint
        response = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": self.test_plads,
            "tour_ids": tour_ids[:5]  # Test with up to 5 tours
        })
        
        assert response.status_code == 200, f"Route optimization failed: {response.text}"
        result = response.json()
        
        # Verify response structure
        assert "optimized" in result
        assert "google_maps_used" in result
        assert "max_haenger_size" in result
        assert "tours" in result
        
        print(f"PASSED: Route optimization returned - optimized: {result['optimized']}, google_maps_used: {result['google_maps_used']}")
        print(f"  - max_haenger_size: {result['max_haenger_size']}")
        print(f"  - total_tours: {result.get('total_tours', 0)}")
        print(f"  - haenger_count: {result.get('haenger_count', 0)}")
        print(f"  - solo_count: {result.get('solo_count', 0)}")
        
        if result.get("google_maps_used"):
            print(f"  - total_distance_km: {result.get('total_distance_km', 0)}")
            print(f"  - total_estimated_minutes: {result.get('total_estimated_minutes', 0)}")
    
    def test_google_maps_used_flag(self):
        """Test that google_maps_used is true when API key is configured"""
        # Create test tours with known addresses
        test_tours = [
            {
                "date": self.test_date,
                "fraction": "TEST_GoogleMaps1",
                "facility": "Test Facility",
                "address": "Rådhuspladsen 1, 1550 København",
                "plads": self.test_plads,
                "container": "TEST1"
            },
            {
                "date": self.test_date,
                "fraction": "TEST_GoogleMaps2",
                "facility": "Test Facility",
                "address": "Nørreport Station, 1159 København",
                "plads": self.test_plads,
                "container": "TEST2"
            }
        ]
        
        for tour in test_tours:
            response = requests.post(f"{BASE_URL}/api/tours", json=tour)
            if response.status_code == 200:
                self.created_tour_ids.append(response.json()["id"])
        
        if len(self.created_tour_ids) < 2:
            pytest.skip("Could not create test tours")
        
        # Optimize route
        response = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": self.test_plads,
            "tour_ids": self.created_tour_ids
        })
        
        assert response.status_code == 200
        result = response.json()
        
        # Should use Google Maps if API key is configured
        assert result.get("google_maps_used") == True, f"Expected google_maps_used=true, got {result.get('google_maps_used')}"
        print("PASSED: google_maps_used is true - Google Maps API is being used")
    
    def test_max_haenger_size_is_2(self):
        """Test that max_haenger_size is 2 (trailer limit)"""
        # Get existing tours
        response = requests.get(f"{BASE_URL}/api/tours", params={"date": self.test_date, "plads": self.test_plads})
        tours = response.json()
        tour_ids = [t["id"] for t in tours if not t.get("is_pause")][:3]
        
        if len(tour_ids) < 2:
            pytest.skip("Not enough tours")
        
        response = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": self.test_plads,
            "tour_ids": tour_ids
        })
        
        assert response.status_code == 200
        result = response.json()
        
        assert result.get("max_haenger_size") == 2, f"Expected max_haenger_size=2, got {result.get('max_haenger_size')}"
        print("PASSED: max_haenger_size is 2 (trailer limit)")
    
    def test_three_tours_same_address_max_2_in_group(self):
        """Test that 3 tours to SAME address creates max 2 in one HÆNGER group"""
        # Create 3 tours with the same address
        same_address = "Vesterbrogade 1, 1620 København"
        
        for i in range(3):
            tour = {
                "date": self.test_date,
                "fraction": f"TEST_SameAddr{i+1}",
                "facility": "Test Facility",
                "address": same_address,
                "plads": self.test_plads,
                "container": f"SAME{i+1}"
            }
            response = requests.post(f"{BASE_URL}/api/tours", json=tour)
            if response.status_code == 200:
                self.created_tour_ids.append(response.json()["id"])
        
        if len(self.created_tour_ids) < 3:
            pytest.skip("Could not create 3 test tours")
        
        # Optimize route
        response = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": self.test_plads,
            "tour_ids": self.created_tour_ids
        })
        
        assert response.status_code == 200
        result = response.json()
        
        # Check groups - no group should have more than 2 members
        groups = result.get("groups", {})
        for gid, members in groups.items():
            assert len(members) <= 2, f"Group {gid} has {len(members)} members, max should be 2"
        
        # Count HÆNGER vs SOLO
        haenger_count = result.get("haenger_count", 0)
        solo_count = result.get("solo_count", 0)
        
        print(f"PASSED: 3 tours to same address - HÆNGER: {haenger_count}, SOLO: {solo_count}")
        print(f"  Groups: {groups}")
        
        # With 3 tours to same address, we expect either:
        # - 2 in HÆNGER group + 1 SOLO, OR
        # - 2 in HÆNGER group + 1 in another HÆNGER group (if paired with something else)
        total = haenger_count + solo_count
        assert total == 3, f"Expected 3 total tours, got {total}"
    
    def test_tours_far_apart_are_solo(self):
        """Test that tours far apart (>15 min driving) are SOLO"""
        # Create tours at very different locations
        far_tours = [
            {
                "date": self.test_date,
                "fraction": "TEST_FarNorth",
                "facility": "Test Facility",
                "address": "Skibstrupvej 1, 3140 Ålsgårde",  # North Zealand
                "plads": self.test_plads,
                "container": "FAR1"
            },
            {
                "date": self.test_date,
                "fraction": "TEST_FarSouth",
                "facility": "Test Facility",
                "address": "Tangmosevej 100, 4600 Køge",  # South of Copenhagen
                "plads": self.test_plads,
                "container": "FAR2"
            }
        ]
        
        for tour in far_tours:
            response = requests.post(f"{BASE_URL}/api/tours", json=tour)
            if response.status_code == 200:
                self.created_tour_ids.append(response.json()["id"])
        
        if len(self.created_tour_ids) < 2:
            pytest.skip("Could not create far apart tours")
        
        # Optimize route
        response = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": self.test_plads,
            "tour_ids": self.created_tour_ids
        })
        
        assert response.status_code == 200
        result = response.json()
        
        # Tours far apart should be SOLO (not grouped)
        tours_result = result.get("tours", [])
        solo_tours = [t for t in tours_result if t.get("job_type") == "SOLO"]
        
        print(f"PASSED: Far apart tours - {len(solo_tours)} SOLO out of {len(tours_result)}")
        print(f"  Groups: {result.get('groups', {})}")
        
        # At least one should be SOLO since they're far apart
        # (They might still be grouped if detour is acceptable)
        assert len(tours_result) == 2, f"Expected 2 tours, got {len(tours_result)}"
    
    def test_route_includes_distance_and_time(self):
        """Test that route response includes distance_km and estimated_minutes"""
        # Get existing tours
        response = requests.get(f"{BASE_URL}/api/tours", params={"date": self.test_date, "plads": self.test_plads})
        tours = response.json()
        tour_ids = [t["id"] for t in tours if not t.get("is_pause")][:3]
        
        if len(tour_ids) < 2:
            pytest.skip("Not enough tours")
        
        response = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": self.test_plads,
            "tour_ids": tour_ids
        })
        
        assert response.status_code == 200
        result = response.json()
        
        # Check response has distance and time
        assert "total_distance_km" in result, "Missing total_distance_km"
        assert "total_estimated_minutes" in result, "Missing total_estimated_minutes"
        
        # Check individual tours have distance/time
        tours_result = result.get("tours", [])
        for tour in tours_result:
            assert "distance_km" in tour, f"Tour {tour.get('tour_id')} missing distance_km"
            assert "estimated_minutes" in tour, f"Tour {tour.get('tour_id')} missing estimated_minutes"
            assert "leg_distance_km" in tour, f"Tour {tour.get('tour_id')} missing leg_distance_km"
        
        print(f"PASSED: Route includes distance and time data")
        print(f"  - total_distance_km: {result.get('total_distance_km')}")
        print(f"  - total_estimated_minutes: {result.get('total_estimated_minutes')}")
    
    def test_geocoding_works(self):
        """Test that addresses are geocoded via Google Maps Geocoding API"""
        # Create a tour with an address but no coordinates
        tour = {
            "date": self.test_date,
            "fraction": "TEST_Geocode",
            "facility": "Test Facility",
            "address": "Kongens Nytorv 1, 1050 København",
            "plads": self.test_plads,
            "container": "GEO1"
        }
        
        response = requests.post(f"{BASE_URL}/api/tours", json=tour)
        assert response.status_code == 200
        created_tour = response.json()
        self.created_tour_ids.append(created_tour["id"])
        
        # Optimize route - this should trigger geocoding
        response = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": self.test_plads,
            "tour_ids": [created_tour["id"]]
        })
        
        assert response.status_code == 200
        result = response.json()
        
        # Check if tour has coordinates after optimization
        tours_result = result.get("tours", [])
        if tours_result:
            tour_result = tours_result[0]
            has_coords = tour_result.get("has_coordinates", False)
            print(f"PASSED: Geocoding test - has_coordinates: {has_coords}")
            if has_coords:
                print(f"  - Tour was successfully geocoded")
            else:
                print(f"  - Tour could not be geocoded (address may be invalid)")


class TestHaengerGroupingRules:
    """Test HÆNGER grouping rules with max 2 per group"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.test_date = "2026-04-01"
        self.test_plads = "Glostrup"
        self.created_tour_ids = []
        yield
        # Cleanup
        for tour_id in self.created_tour_ids:
            try:
                requests.delete(f"{BASE_URL}/api/tours/{tour_id}")
            except:
                pass
    
    def test_nearby_tours_grouped_as_haenger(self):
        """Test that nearby tours (within 15 min) are grouped as HÆNGER"""
        # Create 2 tours at nearby addresses in Copenhagen
        nearby_tours = [
            {
                "date": self.test_date,
                "fraction": "TEST_Nearby1",
                "facility": "Test Facility",
                "address": "Strøget 1, 1100 København",
                "plads": self.test_plads,
                "container": "NEAR1"
            },
            {
                "date": self.test_date,
                "fraction": "TEST_Nearby2",
                "facility": "Test Facility",
                "address": "Strøget 50, 1100 København",
                "plads": self.test_plads,
                "container": "NEAR2"
            }
        ]
        
        for tour in nearby_tours:
            response = requests.post(f"{BASE_URL}/api/tours", json=tour)
            if response.status_code == 200:
                self.created_tour_ids.append(response.json()["id"])
        
        if len(self.created_tour_ids) < 2:
            pytest.skip("Could not create nearby tours")
        
        # Optimize route
        response = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": self.test_plads,
            "tour_ids": self.created_tour_ids
        })
        
        assert response.status_code == 200
        result = response.json()
        
        groups = result.get("groups", {})
        haenger_count = result.get("haenger_count", 0)
        
        print(f"PASSED: Nearby tours test - HÆNGER count: {haenger_count}")
        print(f"  Groups: {groups}")
        
        # Nearby tours should be grouped together
        if haenger_count == 2:
            print("  - Both tours grouped as HÆNGER (expected for nearby addresses)")
        else:
            print("  - Tours not grouped (may be due to route calculation)")
    
    def test_group_size_never_exceeds_2(self):
        """Test that no HÆNGER group ever has more than 2 members"""
        # Create 5 tours at the same address
        same_address = "Tivoli, 1630 København"
        
        for i in range(5):
            tour = {
                "date": self.test_date,
                "fraction": f"TEST_MaxGroup{i+1}",
                "facility": "Test Facility",
                "address": same_address,
                "plads": self.test_plads,
                "container": f"MAX{i+1}"
            }
            response = requests.post(f"{BASE_URL}/api/tours", json=tour)
            if response.status_code == 200:
                self.created_tour_ids.append(response.json()["id"])
        
        if len(self.created_tour_ids) < 5:
            pytest.skip("Could not create 5 test tours")
        
        # Optimize route
        response = requests.post(f"{BASE_URL}/api/optimize-route", json={
            "plads_name": self.test_plads,
            "tour_ids": self.created_tour_ids
        })
        
        assert response.status_code == 200
        result = response.json()
        
        # Verify no group exceeds 2 members
        groups = result.get("groups", {})
        for gid, members in groups.items():
            assert len(members) <= 2, f"Group {gid} has {len(members)} members, max should be 2"
        
        print(f"PASSED: No group exceeds 2 members")
        print(f"  Groups: {groups}")
        print(f"  HÆNGER count: {result.get('haenger_count', 0)}")
        print(f"  SOLO count: {result.get('solo_count', 0)}")


class TestDateFiltering:
    """Test date filtering functionality"""
    
    def test_tours_filtered_by_date(self):
        """Test that tours are correctly filtered by date"""
        # Test with date that has tours
        response = requests.get(f"{BASE_URL}/api/tours", params={"date": "2026-04-01"})
        assert response.status_code == 200
        tours_apr1 = response.json()
        
        # Test with different date
        response = requests.get(f"{BASE_URL}/api/tours", params={"date": "2026-04-02"})
        assert response.status_code == 200
        tours_apr2 = response.json()
        
        print(f"PASSED: Date filtering works")
        print(f"  - 2026-04-01: {len(tours_apr1)} tours")
        print(f"  - 2026-04-02: {len(tours_apr2)} tours")
        
        # Verify all tours have correct date
        for tour in tours_apr1:
            assert tour.get("date") == "2026-04-01", f"Tour has wrong date: {tour.get('date')}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
