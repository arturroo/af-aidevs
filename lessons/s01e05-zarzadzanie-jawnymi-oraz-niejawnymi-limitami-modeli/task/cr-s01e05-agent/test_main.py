import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Import app to test
from main import app

class TestMainRouting(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        """Test that the /health endpoint is registered and returns OK."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_root_endpoint(self):
        """Test that the root / endpoint is registered and returns welcome message."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Welcome to S01E05 Agent Service", data["message"])
        self.assertIn("endpoints", data)

    @patch("main.run_langchain_agent", new_callable=AsyncMock)
    @patch("main.run_adk_agent", new_callable=AsyncMock)
    def test_run_endpoint_langchain(self, mock_run_adk, mock_run_langchain):
        """Test that POST /run with backend 'langchain' calls run_langchain_agent."""
        payload = {"backend": "langchain"}
        response = self.client.post("/run", json=payload)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success", "backend": "langchain"})
        
        mock_run_langchain.assert_called_once()
        mock_run_adk.assert_not_called()

    @patch("main.run_langchain_agent", new_callable=AsyncMock)
    @patch("main.run_adk_agent", new_callable=AsyncMock)
    def test_run_endpoint_adk(self, mock_run_adk, mock_run_langchain):
        """Test that POST /run with backend 'adk' calls run_adk_agent."""
        payload = {"backend": "adk"}
        response = self.client.post("/run", json=payload)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success", "backend": "adk"})
        
        mock_run_adk.assert_called_once()
        mock_run_langchain.assert_not_called()

    @patch("main.run_langchain_agent", new_callable=AsyncMock)
    @patch("main.run_adk_agent", new_callable=AsyncMock)
    def test_run_endpoint_default(self, mock_run_adk, mock_run_langchain):
        """Test that POST /run without payload defaults to langchain."""
        response = self.client.post("/run", json={})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success", "backend": "langchain"})
        
        mock_run_langchain.assert_called_once()
        mock_run_adk.assert_not_called()

    def test_404_routing_non_existent(self):
        """Test that non-existent paths correctly return 404."""
        response = self.client.get("/non-existent-path")
        self.assertEqual(response.status_code, 404)

if __name__ == "__main__":
    unittest.main()
