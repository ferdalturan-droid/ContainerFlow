"""
PWA Upgrade Tests for KORKMAN2
Tests PWA files accessibility, manifest content, service worker, and existing features
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPWAFilesAccessibility:
    """Test that all PWA files are accessible via HTTP"""
    
    def test_manifest_json_accessible(self):
        """manifest.json should be accessible at /manifest.json"""
        response = requests.get(f"{BASE_URL}/manifest.json")
        assert response.status_code == 200, f"manifest.json not accessible: {response.status_code}"
        assert response.headers.get('content-type', '').startswith('application/json'), "manifest.json should be JSON"
        print("✓ manifest.json is accessible")
    
    def test_manifest_json_content(self):
        """manifest.json should have correct PWA properties"""
        response = requests.get(f"{BASE_URL}/manifest.json")
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert data.get('name') == 'ILK Company ApS', f"name mismatch: {data.get('name')}"
        assert data.get('short_name') == 'ILK', f"short_name mismatch: {data.get('short_name')}"
        assert data.get('display') == 'standalone', f"display mismatch: {data.get('display')}"
        assert data.get('theme_color') == '#dc2626', f"theme_color mismatch: {data.get('theme_color')}"
        
        # Check icons
        icons = data.get('icons', [])
        assert len(icons) >= 2, f"Expected at least 2 icons, got {len(icons)}"
        
        icon_sizes = [icon.get('sizes') for icon in icons]
        assert '192x192' in icon_sizes, "Missing 192x192 icon"
        assert '512x512' in icon_sizes, "Missing 512x512 icon"
        
        print("✓ manifest.json has correct content")
    
    def test_service_worker_accessible(self):
        """service-worker.js should be accessible at /service-worker.js"""
        response = requests.get(f"{BASE_URL}/service-worker.js")
        assert response.status_code == 200, f"service-worker.js not accessible: {response.status_code}"
        assert 'javascript' in response.headers.get('content-type', '').lower(), "service-worker.js should be JavaScript"
        print("✓ service-worker.js is accessible")
    
    def test_service_worker_content(self):
        """service-worker.js should have correct cache names and strategies"""
        response = requests.get(f"{BASE_URL}/service-worker.js")
        assert response.status_code == 200
        content = response.text
        
        # Check cache names
        assert "ilk-static-v1" in content, "Missing STATIC_CACHE name"
        assert "ilk-data-v1" in content, "Missing DATA_CACHE name"
        assert "ilk-pwa-v1" in content, "Missing CACHE_NAME"
        
        # Check event listeners
        assert "self.addEventListener('install'" in content, "Missing install event listener"
        assert "self.addEventListener('activate'" in content, "Missing activate event listener"
        assert "self.addEventListener('fetch'" in content, "Missing fetch event listener"
        assert "self.addEventListener('push'" in content, "Missing push event listener"
        assert "self.addEventListener('sync'" in content, "Missing sync event listener"
        
        print("✓ service-worker.js has correct content")
    
    def test_icon_192_accessible(self):
        """icon-192.png should be accessible"""
        response = requests.get(f"{BASE_URL}/icon-192.png")
        assert response.status_code == 200, f"icon-192.png not accessible: {response.status_code}"
        assert 'image' in response.headers.get('content-type', '').lower(), "icon-192.png should be an image"
        print("✓ icon-192.png is accessible")
    
    def test_icon_512_accessible(self):
        """icon-512.png should be accessible"""
        response = requests.get(f"{BASE_URL}/icon-512.png")
        assert response.status_code == 200, f"icon-512.png not accessible: {response.status_code}"
        assert 'image' in response.headers.get('content-type', '').lower(), "icon-512.png should be an image"
        print("✓ icon-512.png is accessible")
    
    def test_apple_touch_icon_accessible(self):
        """apple-touch-icon.png should be accessible"""
        response = requests.get(f"{BASE_URL}/apple-touch-icon.png")
        assert response.status_code == 200, f"apple-touch-icon.png not accessible: {response.status_code}"
        assert 'image' in response.headers.get('content-type', '').lower(), "apple-touch-icon.png should be an image"
        print("✓ apple-touch-icon.png is accessible")


class TestIndexHTMLMetaTags:
    """Test that index.html has correct PWA meta tags"""
    
    def test_index_html_has_manifest_link(self):
        """index.html should have manifest link"""
        response = requests.get(f"{BASE_URL}/")
        assert response.status_code == 200
        content = response.text
        
        assert 'rel="manifest"' in content, "Missing manifest link"
        assert 'manifest.json' in content, "Manifest link should point to manifest.json"
        print("✓ index.html has manifest link")
    
    def test_index_html_has_theme_color(self):
        """index.html should have theme-color meta tag"""
        response = requests.get(f"{BASE_URL}/")
        assert response.status_code == 200
        content = response.text
        
        assert 'name="theme-color"' in content, "Missing theme-color meta tag"
        assert '#dc2626' in content, "theme-color should be #dc2626"
        print("✓ index.html has theme-color meta tag")
    
    def test_index_html_has_apple_meta_tags(self):
        """index.html should have Apple PWA meta tags"""
        response = requests.get(f"{BASE_URL}/")
        assert response.status_code == 200
        content = response.text
        
        assert 'apple-mobile-web-app-capable' in content, "Missing apple-mobile-web-app-capable"
        assert 'apple-mobile-web-app-status-bar-style' in content, "Missing apple-mobile-web-app-status-bar-style"
        assert 'apple-mobile-web-app-title' in content, "Missing apple-mobile-web-app-title"
        assert 'apple-touch-icon' in content, "Missing apple-touch-icon link"
        print("✓ index.html has Apple PWA meta tags")


class TestExistingFeaturesNotBroken:
    """Test that existing features still work after PWA upgrade"""
    
    def test_api_root_accessible(self):
        """API root should be accessible"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200, f"API root not accessible: {response.status_code}"
        print("✓ API root is accessible")
    
    def test_drivers_endpoint(self):
        """Drivers endpoint should work"""
        response = requests.get(f"{BASE_URL}/api/drivers")
        assert response.status_code == 200, f"Drivers endpoint failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Drivers should return a list"
        print(f"✓ Drivers endpoint works ({len(data)} drivers)")
    
    def test_plads_endpoint(self):
        """Plads endpoint should work"""
        response = requests.get(f"{BASE_URL}/api/plads")
        assert response.status_code == 200, f"Plads endpoint failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Plads should return a list"
        print(f"✓ Plads endpoint works ({len(data)} plads)")
    
    def test_admin_login_correct_credentials(self):
        """Admin login should work with correct credentials (admin/1234)"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={"username": "admin", "password": "1234"})
        assert response.status_code == 200, f"Admin login failed: {response.status_code}"
        data = response.json()
        assert data.get('success') == True, "Admin login should return success=True"
        print("✓ Admin login works with admin/1234")
    
    def test_admin_login_wrong_credentials(self):
        """Admin login should reject wrong credentials"""
        response = requests.post(f"{BASE_URL}/api/admin/login", json={"username": "admin", "password": "wrong"})
        assert response.status_code == 401, f"Expected 401 for wrong password, got {response.status_code}"
        print("✓ Admin login rejects wrong password")
    
    def test_tours_endpoint(self):
        """Tours endpoint should work"""
        response = requests.get(f"{BASE_URL}/api/tours")
        assert response.status_code == 200, f"Tours endpoint failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Tours should return a list"
        print(f"✓ Tours endpoint works ({len(data)} tours)")
    
    def test_reports_endpoint(self):
        """Reports endpoint should work"""
        response = requests.get(f"{BASE_URL}/api/reports")
        assert response.status_code == 200, f"Reports endpoint failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Reports should return a list"
        print(f"✓ Reports endpoint works ({len(data)} reports)")
    
    def test_admin_stats_endpoint(self):
        """Admin stats endpoint should work"""
        response = requests.get(f"{BASE_URL}/api/admin/stats")
        assert response.status_code == 200, f"Admin stats endpoint failed: {response.status_code}"
        print("✓ Admin stats endpoint works")


class TestBackgroundSyncOfflineQueue:
    """Test offline queue functionality in localStorage (via code inspection)"""
    
    def test_service_worker_has_offline_queue_handling(self):
        """Service worker should handle offline queue"""
        response = requests.get(f"{BASE_URL}/service-worker.js")
        assert response.status_code == 200
        content = response.text
        
        assert "OFFLINE_QUEUE_ADD" in content, "Missing OFFLINE_QUEUE_ADD message type"
        assert "SYNC_OFFLINE_QUEUE" in content, "Missing SYNC_OFFLINE_QUEUE message type"
        assert "ilk-offline-queue" in content, "Missing offline queue key"
        print("✓ Service worker has offline queue handling")
    
    def test_service_worker_has_background_sync(self):
        """Service worker should have background sync"""
        response = requests.get(f"{BASE_URL}/service-worker.js")
        assert response.status_code == 200
        content = response.text
        
        assert "sync-offline-queue" in content, "Missing sync tag"
        assert "syncOfflineQueue" in content, "Missing syncOfflineQueue function"
        print("✓ Service worker has background sync")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
