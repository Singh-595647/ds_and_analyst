#!/usr/bin/env python3
"""
Test script for the FastAPI application
"""

import requests
import json
import os

def test_api():
    """Test the API with example questions"""
    
    # Check if server is running
    try:
        response = requests.get("http://localhost:8000/")
        print(f"Server status: {response.json()}")
    except requests.exceptions.ConnectionError:
        print("Server not running. Start with: uvicorn main:app --reload")
        return
    
    # Test with example questions
    with open('example_questions.txt', 'r') as f:
        questions_content = f.read()
    
    files = {
        'questions.txt': ('questions.txt', questions_content, 'text/plain')
    }
    
    print("Sending test request...")
    response = requests.post("http://localhost:8000/api/", files=files)
    
    if response.status_code == 200:
        print("Success!")
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
    else:
        print(f"Error: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    test_api()
