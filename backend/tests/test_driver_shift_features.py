"""
Test suite for Driver Login, End-of-Shift, and PDF Archive features.
Tests:
- Driver login with name + code (3030) validation
- Admin login with new code (3030)
- End-of-shift API saves shift report
- PDF archive list and download endpoints
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDriverLogin:
    """Test driver login with name + code validation"""
    
    def test_driver_login_success_with_correct_code(self):
        """Driver login with correct code 3030 should succeed"""
        response = requests.post(f"{BASE_URL}/api/driver/login", json={
            "name": "TEST_Driver_Login",
            "code": "3030"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert data.get("driver_name") == "TEST_Driver_Login"
        print("PASSED: Driver login with correct code 3030 succeeds")
    
    def test_driver_login_fails_with_wrong_code(self):
        """Driver login with wrong code should fail with 401"""
        response = requests.post(f"{BASE_URL}/api/driver/login", json={
            "name": "TEST_Driver_Wrong",
            "code": "1234"  # Old code, should fail
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASSED: Driver login with wrong code 1234 fails with 401")
    
    def test_driver_login_fails_with_empty_code(self):
        """Driver login with empty code should fail"""
        response = requests.post(f"{BASE_URL}/api/driver/login", json={
            "name": "TEST_Driver_Empty",
            "code": ""
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASSED: Driver login with empty code fails")
    
    def test_driver_login_fails_without_name(self):
        """Driver login without name should fail with 400"""
        response = requests.post(f"{BASE_URL}/api/driver/login", json={
            "name": "",
            "code": "3030"
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASSED: Driver login without name fails with 400")


class TestAdminLogin:
    """Test admin login with new code 3030"""
    
    def test_admin_login_success_with_new_code(self):
        """Admin login with new code 3030 should succeed"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "password": "3030"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success") == True
        print("PASSED: Admin login with new code 3030 succeeds")
    
    def test_admin_login_fails_with_old_code(self):
        """Admin login with old code 1234 should fail"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "password": "1234"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASSED: Admin login with old code 1234 fails with 401")
    
    def test_admin_login_fails_with_wrong_password(self):
        """Admin login with wrong password should fail"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={
            "password": "wrong"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASSED: Admin login with wrong password fails")


class TestEndOfShift:
    """Test end-of-shift API that saves shift report"""
    
    def test_end_shift_saves_report(self):
        """POST /api/driver/end-shift should save shift report"""
        today = datetime.now().strftime("%Y-%m-%d")
        response = requests.post(f"{BASE_URL}/api/driver/end-shift", json={
            "driver_name": "TEST_EndShift_Driver",
            "vehicle_reg": "AB12345",
            "plads": "Test Plads",
            "report_date": today,
            "file_name": f"dagrapport_{today}_TEST_EndShift_Driver.pdf",
            "file_data": "dGVzdCBwZGYgZGF0YQ==",  # base64 "test pdf data"
            "total_tours": 5,
            "completed_tours": 4,
            "total_weight": 1500.5,
            "start_time": "07:00",
            "end_time": "15:30"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data, "Response should contain archive id"
        assert data.get("message") == "Dagrapport gemt"
        print(f"PASSED: End-of-shift saves report with id: {data.get('id')}")
        return data.get("id")
    
    def test_end_shift_requires_driver_name(self):
        """POST /api/driver/end-shift without driver_name should fail"""
        response = requests.post(f"{BASE_URL}/api/driver/end-shift", json={
            "vehicle_reg": "AB12345",
            "report_date": "2026-01-15"
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASSED: End-of-shift requires driver_name")


class TestPDFArchive:
    """Test PDF archive list and download endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup_test_archive(self):
        """Create a test archive for testing"""
        today = datetime.now().strftime("%Y-%m-%d")
        response = requests.post(f"{BASE_URL}/api/driver/end-shift", json={
            "driver_name": "TEST_PDFArchive_Driver",
            "vehicle_reg": "CD67890",
            "plads": "Archive Test Plads",
            "report_date": today,
            "file_name": f"dagrapport_{today}_TEST_PDFArchive_Driver.pdf",
            "file_data": "dGVzdCBwZGYgY29udGVudA==",  # base64 "test pdf content"
            "total_tours": 3,
            "completed_tours": 3,
            "total_weight": 800.0,
            "start_time": "08:00",
            "end_time": "16:00"
        })
        if response.status_code == 200:
            self.archive_id = response.json().get("id")
        else:
            self.archive_id = None
        yield
        # Cleanup
        if self.archive_id:
            requests.delete(f"{BASE_URL}/api/pdf-archive/{self.archive_id}")
    
    def test_get_pdf_archive_list(self):
        """GET /api/pdf-archive should return list of archives"""
        response = requests.get(f"{BASE_URL}/api/pdf-archive", params={"days": 30})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"PASSED: GET /api/pdf-archive returns list with {len(data)} archives")
    
    def test_pdf_archive_list_excludes_file_data(self):
        """GET /api/pdf-archive should not include file_data for efficiency"""
        response = requests.get(f"{BASE_URL}/api/pdf-archive", params={"days": 30})
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            # file_data should not be in the list response
            assert "file_data" not in data[0], "file_data should not be in list response"
            print("PASSED: PDF archive list excludes file_data")
        else:
            print("SKIPPED: No archives to check file_data exclusion")
    
    def test_pdf_archive_contains_required_fields(self):
        """PDF archive entries should contain required fields"""
        response = requests.get(f"{BASE_URL}/api/pdf-archive", params={"days": 30})
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            archive = data[0]
            required_fields = ["id", "driver_name", "report_date", "total_tours", "completed_tours", "total_weight"]
            for field in required_fields:
                assert field in archive, f"Missing field: {field}"
            print("PASSED: PDF archive contains required fields")
        else:
            print("SKIPPED: No archives to check fields")
    
    def test_download_pdf_archive(self):
        """GET /api/pdf-archive/{id} should return PDF file"""
        if not self.archive_id:
            pytest.skip("No archive created for download test")
        
        response = requests.get(f"{BASE_URL}/api/pdf-archive/{self.archive_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        # Check content type is PDF
        content_type = response.headers.get("content-type", "")
        assert "application/pdf" in content_type, f"Expected PDF content type, got: {content_type}"
        # Check content-disposition header
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp, f"Expected attachment disposition, got: {content_disp}"
        print(f"PASSED: Download PDF archive {self.archive_id} returns PDF file")
    
    def test_download_nonexistent_archive_returns_404(self):
        """GET /api/pdf-archive/{invalid_id} should return 404"""
        response = requests.get(f"{BASE_URL}/api/pdf-archive/nonexistent-id-12345")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("PASSED: Download nonexistent archive returns 404")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_archives(self):
        """Clean up TEST_ prefixed archives"""
        response = requests.get(f"{BASE_URL}/api/pdf-archive", params={"days": 30})
        if response.status_code == 200:
            archives = response.json()
            deleted = 0
            for archive in archives:
                if archive.get("driver_name", "").startswith("TEST_"):
                    del_resp = requests.delete(f"{BASE_URL}/api/pdf-archive/{archive['id']}")
                    if del_resp.status_code == 200:
                        deleted += 1
            print(f"PASSED: Cleaned up {deleted} test archives")
        else:
            print("SKIPPED: Could not fetch archives for cleanup")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
